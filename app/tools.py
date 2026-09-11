"""가로수 데이터 접근 도구 (@tool).

에이전트(graph.py)가 호출하는 도구들. week5 도구 설계 원칙에 따라 이름·설명·인자를
명확히 둔다(ex02). 지금은 '노선(도로) 단위 집계'로 동작하는 MVP 구현이며,
실제 좌표 기반 경로탐색은 팀원 A/확장 단계에서 osmnx로 교체한다.

데이터: /workspace/Rushhour/data/seoul_tree_data.csv (cp949)
컬럼: 자치구 · 노선 · 수종 · 도로명 주소 · 지번 주소 · 좌표(경도) · 좌표(위도)
"""

import functools
import os

import pandas as pd
from langchain_core.tools import tool

from themes import THEMES

DATA_PATH = os.environ.get(
    "TREE_CSV", "/workspace/Rushhour/data/seoul_tree_data.csv"
)


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
        - focus.center/bbox는 지도 이동·줌 대상. 자치구 미지정이거나 top_only면
          1등 도로로 좁혀 서울 전체가 잡히지 않게 한다.
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

    ranked = (
        hit.groupby(["구", "노선"]).size()
        .sort_values(ascending=False).reset_index(name="그루수")
    )
    top = ranked.head(1 if top_only else 6)
    streets = []
    for _, r in top.iterrows():
        seg = hit[(hit["구"] == r["구"]) & (hit["노선"] == r["노선"])]
        streets.append({
            "구": r["구"], "노선": r["노선"], "그루수": int(r["그루수"]),
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
    print("커버리지:", check_coverage.invoke({})["count"], "개 자치구")
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "강동구"}))
    print(find_theme_streets.invoke({"theme": "은행회피", "district": "강동구"}))
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "없는구"}))
