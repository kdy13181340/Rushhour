"""서울 가로수 테마길 — Streamlit UI (팀원 C 담당).  [BE_DESIGN C4: API 클라이언트]

지도(pydeck) + 채팅. UI는 그래프를 직접 import하지 않고 FastAPI(backend/main.py)만 부른다.
  - 채팅       → POST /chat (SSE) : 노드 이벤트를 상태줄에 흘리고 final로 지도 갱신
  - 빠른 추천  → POST /tools/find_theme_streets : LLM 없이 도구만
  - 마커 좌표  → GET  /map/street_points
  - 첫 화면    → GET  /health : 모델 서버가 없으면 '규칙 모드' 배지

실행:
    # 1) 백엔드
    AGENT_CHANNEL=none uvicorn backend.main:app --port 8000        # 서버 없이 (규칙 모드)
    AGENT_CHANNEL=local uvicorn backend.main:app --port 8000       # 8080 모델 서버 있을 때
    # 2) UI
    RUSHHOUR_API=http://localhost:8000 python -m streamlit run app/app_streamlit.py --server.port 9000

── C가 손볼 곳(TODO) ────────────────────────────────────────────────
  TODO-UI1  지도 스타일·마커 크기·범례 디자인 다듬기
  TODO-UI2  추천 도로를 클릭하면 그 도로만 확대(현재는 focus 전체 뷰)
  TODO-UI3  겨울 조명 스팟(final.light_spots) 마커 레이어 (C7 find_light_spots 이후)
"""

import json
import uuid

import httpx
import pydeck as pdk
import streamlit as st

from config import get_settings

API = get_settings().rushhour_api.rstrip("/")

# 테마 → 지도 마커 색 (RGB). themes.py의 순서와 맞춤.
THEME_RGB = {
    "은행회피": [227, 73, 72], "벚꽃": [232, 123, 164], "그늘": [27, 175, 122],
    "이팝": [235, 104, 52], "은행단풍": [201, 133, 0], "메타세쿼이아": [42, 120, 214],
}
SEOUL_CENTER = [37.5665, 126.9780]

st.set_page_config(page_title="서울 가로수 테마길", page_icon="🌳", layout="wide")


# ── API 클라이언트 ────────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def api_health() -> dict | None:
    try:
        return httpx.get(f"{API}/health", timeout=3).json()
    except Exception:  # noqa: BLE001
        return None


@st.cache_data(ttl=600)
def api_meta() -> tuple[dict, list[str]]:
    themes = httpx.get(f"{API}/themes", timeout=10).json()
    dists = httpx.get(f"{API}/districts", timeout=10).json()["districts"]
    return themes, dists


@st.cache_data(ttl=600)
def api_points(gu: str, line: str, theme: str) -> list[list[float]]:
    r = httpx.get(f"{API}/map/street_points", params={"gu": gu, "line": line, "theme": theme}, timeout=30)
    return r.json()["points"]


def api_quick(theme: str, district: str) -> dict:
    return httpx.post(f"{API}/tools/find_theme_streets",
                      json={"theme": theme, "district": district}, timeout=60).json()


def api_chat(message: str, thread_id: str, on_node=None) -> dict:
    """SSE를 읽어 final 이벤트를 돌려준다. 노드 이벤트마다 on_node(name)."""
    final = None
    with httpx.stream("POST", f"{API}/chat", json={"message": message, "thread_id": thread_id},
                      timeout=httpx.Timeout(120, connect=5)) as r:
        r.raise_for_status()
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
                if event == "node" and on_node:
                    on_node(data["name"])
                elif event == "final":
                    final = data
                elif event == "error":
                    raise RuntimeError(f"{data['type']}: {data['message']}")
    if final is None:
        raise RuntimeError("final 이벤트 없음")
    return final


# ── 지도 ─────────────────────────────────────────────────────────────────────
def _zoom_for(bbox) -> float:
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
    if not hits or not hits.get("ok"):
        return
    theme = hits["theme"]
    rgb = THEME_RGB.get(theme, [120, 120, 120])
    pts = []
    for s in hits["streets"]:
        for lat, lon in api_points(s["구"], s["노선"], theme):
            pts.append({"lat": lat, "lon": lon})
    focus = hits.get("focus", {})
    center = focus.get("center", SEOUL_CENTER)
    zoom = _zoom_for(focus["bbox"]) if focus.get("bbox") else 11.0
    # 경로(route) 결과면 출발→도착 선(corridor.line)도 그린다
    line = hits.get("corridor", {}).get("line")
    st.session_state.map = {"points": pts, "rgb": rgb, "center": center,
                            "zoom": zoom, "line": line}


def render_map():
    m = st.session_state.get("map")
    center = m["center"] if m else SEOUL_CENTER
    zoom = m["zoom"] if m else 10.5
    layers = []
    if m and m.get("line"):
        # corridor.line = [[lat,lon],[lat,lon]] → PathLayer는 [lon,lat] 순서
        path = [[p[1], p[0]] for p in m["line"]]
        layers.append(pdk.Layer(
            "PathLayer", data=[{"path": path}], get_path="path",
            get_color=[90, 90, 90], get_width=5, width_min_pixels=3,
        ))
        # 출발(초록)·도착(빨강) 지점 마커
        ends = [{"lon": path[0][0], "lat": path[0][1], "c": [46, 139, 87]},
                {"lon": path[1][0], "lat": path[1][1], "c": [214, 69, 65]}]
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=ends, get_position="[lon, lat]",
            get_fill_color="c", get_radius=80, radius_min_pixels=6, radius_max_pixels=11,
            stroked=True, get_line_color=[255, 255, 255], line_width_min_pixels=2,
        ))
    if m and m["points"]:
        layers.append(pdk.Layer(
            "ScatterplotLayer", data=m["points"],
            get_position="[lon, lat]", get_fill_color=m["rgb"] + [170],
            get_radius=22, radius_min_pixels=2, radius_max_pixels=6, pickable=False,
        ))
    view = pdk.ViewState(latitude=center[0], longitude=center[1], zoom=zoom)
    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view,
                             map_provider="carto", map_style="light"),
                    use_container_width=True)


# ── 레이아웃 ──────────────────────────────────────────────────────────────
health = api_health()
if health is None:
    st.error(f"백엔드({API})에 연결할 수 없어요. `uvicorn backend.main:app --port 8000` 을 먼저 실행하세요.")
    st.stop()
themes, districts = api_meta()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant",
        "content": "안녕하세요! 예: “강남구에서 봄에 벚꽃 예쁜 길”, “가을에 냄새 안 나게 강동구 산책”"}]

# 채팅 전용 레이아웃 — 사이드바 없음. 모드 배지는 상단에.
st.title("서울 가로수 테마길")
mode = health["chat_mode"]
if mode == "llm":
    st.success(f"채팅: LLM 모드 ({health['llm'].get('model') or health['llm']['channel']}) · "
               f"서울 {len(districts)}개 자치구")
else:
    st.warning(f"채팅: 규칙 모드 (모델 서버 없음 — 키워드로 테마를 잡고 템플릿으로 답해요) · "
               f"서울 {len(districts)}개 자치구")
st.caption("계절·취향을 말하면 가로수 산책길을 추천하고 지도를 그 위치로 옮겨드려요. "
           "예) “강남구에서 송파구 가는 길 벚꽃길”, “서울에서 가장 큰 벚꽃길”")

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
        status = box.status("에이전트 실행 중…", expanded=False)
        try:
            final = api_chat(q, st.session_state.thread_id,
                             on_node=lambda n: status.write(f"→ {n}"))
            status.update(label=f"완료 · {final.get('elapsed_sec')}s · "
                                f"intake={final.get('intake_mode')} resolver={final.get('resolver_mode')}",
                          state="complete")
            ans = final.get("final_answer") or "(답변 없음 — 울타리 종료)"
            if final.get("hits"):
                set_map_from_hits(final["hits"])
        except Exception as exc:  # noqa: BLE001
            status.update(label="실패", state="error")
            ans = f"에이전트 호출 실패: {exc}. 잠시 후 다시 시도해 주세요."
        st.session_state.messages.append({"role": "assistant", "content": ans})
        box.chat_message("assistant").write(ans)
        st.rerun()
