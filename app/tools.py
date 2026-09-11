"""가로수 데이터 접근 도구 (@tool).

에이전트(graph.py)가 호출하는 도구들. week5 도구 설계 원칙에 따라 이름·설명·인자를
명확히 둔다(ex02). 지금은 '노선(도로) 단위 집계'로 동작하는 MVP 구현이며,
실제 좌표 기반 경로탐색은 팀원 A/확장 단계에서 osmnx로 교체한다.

데이터 로드 순서 [BE_DESIGN C2·C5·C6]:
  1) TREE_PARQUET env  2) data/processed/seoul_trees.parquet (scripts/01 산출물)
  3) TREE_CSV env      4) data/seoul_tree_data.csv (cp949) — 같은 정제(clean)를 즉석 적용
경로는 저장소 루트 기준 상대경로라 clone 위치가 달라도 동작한다.
컬럼(정제 후): 구 · 노선 · 수종 · 도로명 · 지번 · 경도 · 위도 · 관리기관
"""

import functools
import os
import sys
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from themes import THEMES

ROOT = Path(__file__).resolve().parents[1]
PARQUET_PATH = Path(os.environ.get("TREE_PARQUET", ROOT / "data" / "processed" / "seoul_trees.parquet"))
CSV_PATH = Path(os.environ.get("TREE_CSV", ROOT / "data" / "seoul_tree_data.csv"))


@functools.lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    """데이터를 한 번만 읽어 캐시. Parquet 우선, 없으면 CSV를 읽어 같은 정제를 적용."""
    if PARQUET_PATH.exists():
        return pd.read_parquet(PARQUET_PATH)
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"가로수 데이터 없음: {PARQUET_PATH} / {CSV_PATH}. "
            "python scripts/01_csv_to_parquet.py 를 먼저 실행할 것.")
    sys.path.insert(0, str(ROOT / "scripts"))
    from importlib import import_module
    clean = import_module("01_csv_to_parquet").clean
    return clean(pd.read_csv(CSV_PATH, encoding="cp949"))


def data_source() -> str:
    """헬스체크용 — 지금 어떤 파일을 쓰는지."""
    return str(PARQUET_PATH if PARQUET_PATH.exists() else CSV_PATH)


@functools.lru_cache(maxsize=1)
def available_districts() -> tuple[str, ...]:
    """데이터에 존재하는 자치구 목록(커버리지). '모르면 모른다'의 근거. 정제 후 25개."""
    return tuple(sorted(_load()["구"].dropna().unique()))


def match_district(text: str) -> str:
    """자유 텍스트에서 자치구 이름을 찾는다(규칙 intake·폴백용). 없으면 ''."""
    for gu in available_districts():
        if gu in text or gu[:-1] in text:      # '강남구' 또는 '강남'
            return gu
    return ""


def _hotspot_focus(seg, cell: float = 0.004) -> dict:
    """도로 나무 좌표에서 가장 밀집한 ~1km 격자를 찾아 지도 focus(center·bbox) 반환.

    긴 대로도 걷기 좋은 밀집 구간으로 좁힌다. cell≈0.004°≈400~450m, 창은 ±1칸.
    """
    gy = (seg["위도"] / cell).round()
    gx = (seg["경도"] / cell).round()
    (by, bx) = gy.astype(str).str.cat(gx.astype(str), sep=",").mode().iloc[0].split(",")
    by, bx = float(by), float(bx)
    win = seg[(gy >= by - 1) & (gy <= by + 1) & (gx >= bx - 1) & (gx <= bx + 1)]
    return {
        "center": [round(float(win["위도"].mean()), 6), round(float(win["경도"].mean()), 6)],
        "bbox": [[round(float(win["위도"].min()), 6), round(float(win["경도"].min()), 6)],
                 [round(float(win["위도"].max()), 6), round(float(win["경도"].max()), 6)]],
    }


@tool
def find_theme_streets(theme: str, district: str = "", top_only: bool = False) -> dict:
    """특정 테마에 맞는(또는 회피할) 가로수가 밀집한 도로를 찾는다.

    Args:
        theme: 테마 키. 다음 중 하나 —
            은행회피 · 벚꽃 · 그늘 · 이팝 · 은행단풍 · 메타세쿼이아
        district: 자치구 이름(예: '강남구'). 비우면 서울 전체에서 찾는다.
        top_only: '가장 큰/제일 좋은 길 하나'처럼 단일 도로를 원할 때 True.
            True면 1등 도로만 반환하고 지도 focus도 그 도로로 좁힌다.

    Returns:
        {ok, theme, mode, season, district, streets:[{구,노선,그루수,center}], focus, note}
        - mode가 'prefer'면 streets는 '걷기 좋은 추천 길',
          'avoid'면 '피하는 게 좋은 길'이다.
        - 데이터에 없는 테마/자치구면 ok=False 와 사유·후보를 돌려준다.
    """
    if theme not in THEMES:
        return {"ok": False, "reason": f"모르는 테마: {theme}",
                "valid_themes": list(THEMES.keys())}
    df = _load()
    if district:
        if district not in available_districts():
            return {"ok": False, "reason": f"데이터에 없는 자치구: {district}",
                    "valid_districts_sample": list(available_districts())[:8],
                    "coverage": f"총 {len(available_districts())}개 자치구"}
        df = df[df["구"] == district]

    spec = THEMES[theme]
    hit = df[df["수종"].isin(spec["species"])]
    if hit.empty:
        return {"ok": False, "reason": "해당 지역에 이 테마의 가로수 데이터가 없음",
                "theme": theme, "district": district or "서울 전체"}

    # 노선 결측 행은 groupby에서 자동 제외됨(좌표 기반 경로로 가면 다시 살아남)
    ranked = (
        hit.groupby(["구", "노선"]).size()
        .sort_values(ascending=False).reset_index(name="그루수")
    )
    top = ranked.head(1 if top_only else 6)
    streets = []
    for _, r in top.iterrows():
        seg = hit[(hit["구"] == r["구"]) & (hit["노선"] == r["노선"])]
        streets.append({
            "구": str(r["구"]), "노선": str(r["노선"]), "그루수": int(r["그루수"]),
            # 지도 이동용 중심좌표(가벼움). 마커 점 배열은 map_api.street_points()로 UI가 따로 가져감.
            "center": [round(float(seg["위도"].mean()), 6), round(float(seg["경도"].mean()), 6)],
        })
    # 지도 뷰(pan/zoom 대상) = 1등 도로에서 나무가 가장 몰린 ~1km 핫스팟.
    # 도로 전체 bbox를 쓰면 올림픽대로처럼 도시를 가로지르는 대로에서 지도가 서울 전체로
    # 확대돼 버린다. 걷기 좋은 밀집 구간으로 좁힌다.
    r0 = top.iloc[0]
    primary_seg = hit[(hit["구"] == r0["구"]) & (hit["노선"] == r0["노선"])]
    focus = _hotspot_focus(primary_seg)
    focus["primary"] = {"구": str(r0["구"]), "노선": str(r0["노선"])}
    return {
        "ok": True, "theme": theme, "mode": spec["mode"], "season": spec["season"],
        "district": district or "서울 전체", "total_trees": int(len(hit)),
        "streets": streets, "focus": focus, "note": spec["note"],
    }


@tool
def check_coverage(district: str = "") -> dict:
    """가로수 데이터가 어떤 자치구를 포함하는지 확인한다.

    Args:
        district: 확인할 자치구. 비우면 전체 목록을 돌려준다.
    Returns:
        {covered: bool, districts: [...]} — 답할 수 있는 범위를 정직하게 알려준다.
    """
    dists = list(available_districts())
    if district:
        return {"covered": district in dists, "district": district, "districts": dists}
    return {"covered": None, "count": len(dists), "districts": dists}


# 에이전트에 넘길 도구 묶음
TOOLS = [find_theme_streets, check_coverage]


if __name__ == "__main__":
    # 도구 단독 점검
    print("데이터:", data_source())
    print("커버리지:", check_coverage.invoke({})["count"], "개 자치구")
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "강동구"}))
    print(find_theme_streets.invoke({"theme": "은행단풍", "district": "종로구"})["streets"][:2])
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "없는구"}))
