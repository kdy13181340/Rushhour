"""가로수 데이터 접근 도구 (@tool).

에이전트(graph.py)가 호출하는 도구들. week5 도구 설계 원칙에 따라 이름·설명·인자를
명확히 둔다(ex02). 지금은 '노선(도로) 단위 집계'로 동작하는 MVP 구현이며,
실제 좌표 기반 경로탐색은 팀원 A/확장 단계에서 osmnx로 교체한다.

데이터: <repo>/data/seoul_tree_data.csv (cp949) — 환경변수 TREE_CSV로 덮어쓸 수 있음
컬럼: 자치구 · 노선 · 수종 · 도로명 주소 · 지번 주소 · 좌표(경도) · 좌표(위도)
"""

import functools
import os
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from themes import THEMES

# 레포를 어디에 두든 동작하도록 파일 위치 기준으로 잡음. TREE_CSV로 덮어쓸 수 있음.
_REPO_CSV = Path(__file__).resolve().parent.parent / "data" / "seoul_tree_data.csv"
DATA_PATH = os.environ.get("TREE_CSV", str(_REPO_CSV))


@functools.lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    """CSV를 한 번만 읽어 캐시. 컬럼명을 짧게 표준화하고 좌표를 숫자화."""
    df = pd.read_csv(DATA_PATH, encoding="cp949")
    df = df.rename(
        columns={
            "자치구": "구",
            "노선": "노선",
            "수종": "수종",
            "도로명 주소": "도로명",
            "좌표(경도)": "경도",
            "좌표(위도)": "위도",
        }
    )
    for c in ("구", "노선", "수종"):
        df[c] = df[c].astype(str).str.strip()
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    return df.dropna(subset=["경도", "위도"])


@functools.lru_cache(maxsize=1)
def available_districts() -> tuple[str, ...]:
    """데이터에 존재하는 자치구 목록(커버리지). '모르면 모른다'의 근거."""
    return tuple(sorted(_load()["구"].unique()))


@tool
def find_theme_streets(theme: str, district: str = "") -> dict:
    """특정 테마에 맞는(또는 회피할) 가로수가 밀집한 도로를 찾는다.

    Args:
        theme: 테마 키. 다음 중 하나 —
            은행회피 · 벚꽃 · 그늘 · 이팝 · 은행단풍 · 메타세쿼이아
        district: 자치구 이름(예: '강남구'). 비우면 서울 전체에서 찾는다.

    Returns:
        {ok, theme, mode, season, district, streets:[{구,노선,그루수}], note}
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

    top = (
        hit.groupby(["구", "노선"]).size()
        .sort_values(ascending=False).head(6).reset_index(name="그루수")
    )
    streets = []
    for _, r in top.iterrows():
        seg = hit[(hit["구"] == r["구"]) & (hit["노선"] == r["노선"])]
        streets.append({
            "구": r["구"], "노선": r["노선"], "그루수": int(r["그루수"]),
            # 지도 이동용 중심좌표(가벼움). 마커 점 배열은 map_api.street_points()로 UI가 따로 가져감.
            "center": [round(float(seg["위도"].mean()), 6), round(float(seg["경도"].mean()), 6)],
        })
    # 상위 3개 도로를 한눈에 담는 지도 뷰(pan/zoom 대상)
    focus_seg = hit.merge(top.head(3)[["구", "노선"]], on=["구", "노선"])
    focus = {
        "center": [round(float(focus_seg["위도"].mean()), 6),
                   round(float(focus_seg["경도"].mean()), 6)],
        "bbox": [[round(float(focus_seg["위도"].min()), 6), round(float(focus_seg["경도"].min()), 6)],
                 [round(float(focus_seg["위도"].max()), 6), round(float(focus_seg["경도"].max()), 6)]],
    }
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
    print("커버리지:", check_coverage.invoke({})["count"], "개 자치구")
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "강동구"}))
    print(find_theme_streets.invoke({"theme": "은행회피", "district": "강동구"}))
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "없는구"}))
