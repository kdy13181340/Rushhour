"""서울 가로수 테마길 — Streamlit UI 골격 (팀원 C 담당).

지도(pydeck) + 채팅. 채팅으로 지역·계절·취향을 말하면 에이전트가 테마길을 추천하고,
지도가 추천 위치로 이동하며 해당 가로수를 점으로 표시한다.

실행:
    bash /workspace/course/week5/start_agent_server.sh          # 채팅(LLM)용 8080
    cd /workspace/Rushhour/app
    AGENT_CHANNEL=local /workspace/course/.venv/bin/python -m streamlit run app_streamlit.py

메모: 사이드바의 '빠른 추천'은 LLM 없이 도구만 호출하므로 8080이 없어도 지도 데모가 된다.
      채팅창은 에이전트(intake→researcher→resolver) 전체를 태우므로 8080/API가 필요하다.

── C가 손볼 곳(TODO) ────────────────────────────────────────────────
  TODO-UI1  지도 스타일·마커 크기·범례 디자인 다듬기
  TODO-UI2  추천 도로를 클릭하면 그 도로만 확대(현재는 focus 전체 뷰)
  TODO-UI3  langfuse 트레이스 연결(week8 ext01) — 대화별 추적
"""

import streamlit as st
import pydeck as pdk

from themes import THEMES
from tools import find_theme_streets, available_districts
from map_api import street_points

# 테마 → 지도 마커 색 (RGB). themes.py의 순서와 맞춤.
THEME_RGB = {
    "은행회피": [227, 73, 72], "벚꽃": [232, 123, 164], "그늘": [27, 175, 122],
    "이팝": [235, 104, 52], "은행단풍": [201, 133, 0], "메타세쿼이아": [42, 120, 214],
}
SEOUL_CENTER = [37.5665, 126.9780]

st.set_page_config(page_title="서울 가로수 테마길", page_icon="🌳", layout="wide")


@st.cache_resource
def get_app():
    """에이전트 그래프를 한 번만 컴파일해 캐시."""
    from graph import build_graph
    return build_graph()


def _zoom_for(bbox) -> float:
    """bbox 크기로 대략적 줌 레벨 산정."""
    span = max(bbox[1][0] - bbox[0][0], bbox[1][1] - bbox[0][1])
    if span > 0.15:
        return 11.0
    if span > 0.06:
        return 12.5
    if span > 0.02:
        return 13.5
    return 14.5


def set_map_from_hits(hits: dict):
    """도구 결과(hits)로 지도 상태(중심·줌·마커)를 갱신."""
    if not hits.get("ok"):
        return
    theme = hits["theme"]
    rgb = THEME_RGB.get(theme, [120, 120, 120])
    pts = []
    for s in hits["streets"]:
        for lat, lon in street_points(s["구"], s["노선"], theme):
            pts.append({"lat": lat, "lon": lon})
    focus = hits.get("focus", {})
    center = focus.get("center", SEOUL_CENTER)
    zoom = _zoom_for(focus["bbox"]) if focus.get("bbox") else 11.0
    st.session_state.map = {"points": pts, "rgb": rgb, "center": center, "zoom": zoom}


def render_map():
    m = st.session_state.get("map")
    center = m["center"] if m else SEOUL_CENTER
    zoom = m["zoom"] if m else 10.5
    layers = []
    if m and m["points"]:
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=m["points"],
            get_position="[lon, lat]", get_fill_color=m["rgb"] + [170],
            get_radius=22, radius_min_pixels=2, radius_max_pixels=6, pickable=False,
        ))
    view = pdk.ViewState(latitude=center[0], longitude=center[1], zoom=zoom)
    # map_provider carto → Mapbox 토큰 없이 기본 지도. (토큰 문제 시 map_style=None 로 폴백)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view,
                             map_provider="carto", map_style="light"),
                    use_container_width=True)


# ── 레이아웃 ──────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🌳 테마길")
    st.caption("채팅으로 물어보거나, 아래에서 바로 골라보세요.")
    st.subheader("빠른 추천 (LLM 불필요)")
    tkey = st.selectbox("테마", list(THEMES.keys()),
                        format_func=lambda k: f"{k} · {THEMES[k]['label']}")
    gu = st.selectbox("자치구", ["(서울 전체)"] + list(available_districts()))
    if st.button("이 조건으로 추천", use_container_width=True):
        district = "" if gu == "(서울 전체)" else gu
        hits = find_theme_streets.invoke({"theme": tkey, "district": district})
        set_map_from_hits(hits)
        if hits.get("ok"):
            top = "、".join(f"{s['노선']}({s['그루수']})" for s in hits["streets"][:3])
            ans = f"**{THEMES[tkey]['label']}** ({hits['district']}) — 추천 도로: {top}. {hits['note']}"
        else:
            ans = f"데이터를 찾지 못했어요: {hits.get('reason','')}"
        st.session_state.messages.append({"role": "assistant", "content": ans})
    st.divider()
    st.caption(f"커버리지: {len(available_districts())}개 자치구 · "
               "은행 열매 회피는 암나무 일부 라벨 기반 근사")

st.title("서울 가로수 테마길")
st.caption("계절·취향을 말하면 가로수 산책길을 추천하고 지도를 그 위치로 옮겨드려요.")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant",
        "content": "안녕하세요! 예: “강남구에서 봄에 벚꽃 예쁜 길”, “가을에 냄새 안 나게 강동구 산책”"}]

col_map, col_chat = st.columns([3, 2], gap="medium")

with col_map:
    render_map()

with col_chat:
    box = st.container(height=460)
    for msg in st.session_state.messages:
        box.chat_message(msg["role"]).write(msg["content"])
    if q := st.chat_input("어떤 산책길을 원하세요?"):
        st.session_state.messages.append({"role": "user", "content": q})
        box.chat_message("user").write(q)
        try:
            out = get_app().invoke({"question": q})
            ans = out.get("final_answer", "(답변 없음)")
            if out.get("hits"):
                set_map_from_hits(out["hits"])
        except Exception as exc:  # 보통 8080 미기동 / API 키 미설정
            ans = (f"에이전트 호출 실패: {type(exc).__name__}. "
                   "로컬 서버(8080)를 켜거나 사이드바 ‘빠른 추천’을 써보세요.")
        st.session_state.messages.append({"role": "assistant", "content": ans})
        box.chat_message("assistant").write(ans)
        st.rerun()
