"""지도 렌더링용 좌표 헬퍼 — UI(C)가 직접 부른다. **LLM 도구 아님**.

무거운 좌표 배열은 에이전트 컨텍스트에 넣지 않는다. 에이전트는 (구, 노선)만 정하고,
UI가 이 헬퍼로 해당 도로의 나무 좌표를 가져와 지도에 마커/히트맵으로 찍는다.

사용 예 (Streamlit):
    from graph import build_graph, run_one
    from map_api import street_points
    out = run_one(app, "강남구 봄 벚꽃길")
    m.set_view(out["hits"]["focus"]["center"])           # 지도 이동
    for s in out["hits"]["streets"]:
        for lat, lon in street_points(s["구"], s["노선"], out["hits"]["theme"]):
            m.add_marker(lat, lon)                        # 나무 표시
"""

from themes import THEMES
from tools import _load


def street_points(gu: str, line: str, theme: str, limit: int = 1000) -> list[list[float]]:
    """특정 도로에서 그 테마 수종 나무의 [위도, 경도] 목록."""
    if theme not in THEMES:
        return []
    df = _load()
    seg = df[(df["구"] == gu) & (df["노선"] == line)
             & (df["수종"].isin(THEMES[theme]["species"]))]
    if len(seg) > limit:
        seg = seg.sample(limit, random_state=7)
    return [[round(float(la), 6), round(float(lo), 6)]
            for la, lo in zip(seg["위도"], seg["경도"])]


def theme_points(theme: str, district: str = "", limit: int = 3000) -> list[list[float]]:
    """테마 전체(또는 한 자치구)의 표본 좌표 — 지도 배경 히트맵용."""
    if theme not in THEMES:
        return []
    df = _load()
    sub = df[df["수종"].isin(THEMES[theme]["species"])]
    if district:
        sub = sub[sub["구"] == district]
    if len(sub) > limit:
        sub = sub.sample(limit, random_state=7)
    return [[round(float(la), 6), round(float(lo), 6)]
            for la, lo in zip(sub["위도"], sub["경도"])]


if __name__ == "__main__":
    pts = street_points("강동구", "아리수로", "벚꽃")
    print("강동구 아리수로 벚꽃 점 수:", len(pts), "예시:", pts[:2])
