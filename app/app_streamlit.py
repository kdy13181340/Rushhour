"""서울 가로수길 — Streamlit UI (팀원 C 담당).

Figma Make 시안(shelf-cake-53560367.figma.site)을 그대로 옮긴 화면.
상단 다크 헤더 + 좌측 테마 목록(260px) + 지도 + 우측 챗봇 패널(420px)의 3분할 구조.

시안에서 뽑은 값(브라우저 computed style 실측):
    헤더 #1A2E22 · 배경 #F5F3EF · 패널 #FFFFFF · 경계 #DBD8D2 · 본문 #1A1A18
    포인트 #52B788(통계·로고) · 딥그린 #2D6A4F(칩 글자)
    계절색 봄 #E91E8C · 여름 #2D6A4F · 가을 #E76900 · 사계절 #546E7A (배지는 9.4% 틴트)
    테마명 13/500 · 자치구 10/400 #9A9690 · 섹션 라벨 11/600 #7A7770 ls .08em
    헤더 pill r20 pad 4/14 · 배지 r10 pad 1/6 · 칩 r20 pad 5/12 · 행 r10

시안과 다르게 한 두 가지:
    - 지도: 시안의 Leaflet+CARTO는 API 키가 없어 'API KEY REQUIRED'만 뜬다.
      키 없이 도는 pydeck+CARTO로 바꾸고, 마커는 수종 그림(assets.py)을 쓴다.
    - 헤더 숫자: 시안의 219,447은 원자료에서 나오지 않는 값이라 실제 집계로 바꿨다.

실행:
    bash /workspace/course/week5/start_agent_server.sh        # 채팅(LLM)용 8080
    cd /workspace/course && bash final_prj/start_app.sh --port 9000
"""

import datetime as dt
import math

import pydeck as pdk
import streamlit as st

from assets import THEME_COLOR, pydeck_atlas, sprite_uri
from map_api import street_points
from themes import BUCKETS, THEMES
from tools import _load, available_districts, find_theme_streets

# ── 디자인 토큰 ───────────────────────────────────────────────────────────────
INK, MUTED, FAINT = "#1A1A18", "#7A7770", "#9A9690"
BG, PANEL, LINE = "#F5F3EF", "#FFFFFF", "#DBD8D2"
HEADER, GREEN, DEEP = "#1A2E22", "#52B788", "#2D6A4F"
BUCKET_COLOR = {"봄": "#E91E8C", "여름": "#2D6A4F", "가을": "#E76900", "사계절": "#546E7A"}

SLUG = {"벚꽃": "cherry", "그늘": "shade", "이팝": "fringe", "은행회피": "avoid",
        "은행단풍": "ginkgo", "메타세쿼이아": "meta", "단풍": "maple", "상록": "pine"}
SEASON_PICK = {3: "벚꽃", 4: "벚꽃", 5: "이팝", 6: "그늘", 7: "그늘", 8: "그늘",
               9: "은행회피", 10: "은행회피", 11: "은행단풍", 12: "상록", 1: "상록", 2: "상록"}
SEOUL_CENTER = [37.5665, 126.9780]
MAP_W, MAP_H = 760, 720
# 스트림릿의 pydeck 컴포넌트는 initialViewState보다 정확히 1단계 더 확대해 그린다(실측).
RENDER_ZOOM_OFFSET = 1.0

ICON_ATLAS, ICON_MAPPING = pydeck_atlas()

st.set_page_config(page_title="서울 가로수길", page_icon="🌿", layout="wide")


# ── 데이터 ────────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner="가로수 데이터를 읽는 중…")
def overview() -> tuple[int, int]:
    df = _load()
    return len(df), len([g for g in df["구"].unique() if g.endswith("구")])


@st.cache_data(show_spinner=False)
def lookup(theme: str, district: str = "") -> dict:
    return find_theme_streets.invoke({"theme": theme, "district": district})


@st.cache_data(show_spinner=False)
def theme_districts(theme: str) -> list[str]:
    """그 테마의 상위 노선이 속한 자치구 두 곳 — 시안의 '금천구·관악구' 자리."""
    out: list[str] = []
    for s in lookup(theme).get("streets", []):
        if s["구"].endswith("구") and s["구"] not in out:
            out.append(s["구"])
        if len(out) == 2:
            break
    return out


@st.cache_data(show_spinner=False)
def cached_points(gu: str, line: str, theme: str) -> list[list[float]]:
    return street_points(gu, line, theme, limit=4000)


def _init():
    ss = st.session_state
    ss.setdefault("theme", SEASON_PICK.get(dt.date.today().month, "벚꽃"))
    ss.setdefault("focus", None)
    ss.setdefault("messages", [{"role": "assistant", "content":
        "안녕하세요! 🌿 **서울 가로수 산책길 안내 시스템**입니다.\n\n"
        "계절이나 원하는 분위기를 입력하시면 지도에 경로를 표시해드립니다.\n\n"
        "- 봄 벚꽃길 추천해줘\n- 여름에 그늘 많고 시원한 길\n"
        "- 가을 은행나무 단풍길\n- 메타세쿼이아 이국적인 터널길"}])


_init()


@st.cache_resource
def get_app():
    from graph import build_graph
    return build_graph()


# ── 스타일 ────────────────────────────────────────────────────────────────────
def css() -> str:
    rows = []
    for key, v in THEMES.items():
        sl, col = SLUG[key], BUCKET_COLOR[v["bucket"]]
        tint = f"{col}1A"                      # 약 10% 틴트 (시안 9.4%)
        rows.append(f"""
.st-key-row_{sl} .stButton button::before {{
    background:{tint} url('{sprite_uri(key, 40)}') center/19px no-repeat; }}
.st-key-row_{sl} .stButton button p:nth-of-type(2) {{ color:{col}; background:{tint}; }}
.st-key-row_{sl}.picked .stButton button {{ box-shadow:inset 3px 0 0 {col}; background:{BG}; }}
.st-key-chip_{sl} .stButton button::before {{ background-image:url('{sprite_uri(key, 32)}'); }}""")
    return f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap');

html, body, [class*="st-"] {{ font-family:'Noto Sans KR','Apple SD Gothic Neo',sans-serif; }}
.stApp {{ background:{BG}; }}
[data-testid="stSidebar"], [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display:none; }}
header[data-testid="stHeader"] {{ display:none; }}
.stMainBlockContainer, .block-container {{
    padding:0 !important; max-width:100% !important; }}
[data-testid="stHorizontalBlock"] {{ gap:0 !important; }}
[data-testid="stVerticalBlock"] {{ gap:0 !important; }}

/* ── 상단 다크 헤더 ─────────────────────────────────────────── */
.st-key-topbar {{
    background:{HEADER}; padding:0 28px; min-height:56px;
    border-bottom:1px solid rgba(255,255,255,.08); }}
.st-key-topbar [data-testid="stVerticalBlock"] {{ gap:0 !important; }}
.brand {{ display:flex; align-items:center; gap:10px; white-space:nowrap; }}
.brand .mark {{ width:26px; height:26px; border-radius:8px; background:{GREEN}22;
    display:grid; place-items:center; font-size:15px; }}
.brand b {{ font-size:15px; font-weight:600; color:#fff; letter-spacing:-.01em; }}
.brand span {{ font-size:12px; color:{GREEN}; letter-spacing:.04em; }}
.stats {{ display:flex; gap:26px; justify-content:flex-end; white-space:nowrap; }}
.stats div {{ text-align:center; }}
.stats b {{ display:block; font-size:14px; font-weight:700; color:{GREEN};
    font-variant-numeric:tabular-nums; line-height:1.3; }}
.stats span {{ font-size:11px; color:rgba(255,255,255,.4); }}

/* 계절 pill — 시안: 비활성 rgba(255,255,255,.08)/흐린 흰색, 활성 계절색/흰색 */
.st-key-seasonpick [data-baseweb="button-group"] {{ gap:6px; background:transparent; }}
.st-key-seasonpick button {{
    background:rgba(255,255,255,.08) !important; border:none !important; border-radius:20px !important;
    padding:4px 14px !important; min-height:0 !important; }}
.st-key-seasonpick button p {{
    font-size:12px !important; font-weight:400 !important; color:rgba(255,255,255,.5) !important; }}
.st-key-seasonpick button[aria-checked="true"] p {{ color:#fff !important; font-weight:600 !important; }}

/* ── 좌측 테마 목록 ─────────────────────────────────────────── */
/* 3분할 본문 — 좌·우 패널을 화면 아래까지 흰색으로 채운다.
   선택자를 stHorizontalBlock으로 넓게 잡으면 상단 헤더(가로 컨테이너)까지 100vh가 된다. */
.st-key-mainrow [data-testid="stColumn"] {{ min-height:calc(100vh - 57px); }}
.st-key-mainrow [data-testid="stColumn"]:first-child {{
    background:{PANEL}; border-right:1px solid {LINE}; }}
.st-key-mainrow [data-testid="stColumn"]:last-child {{
    background:{PANEL}; border-left:1px solid {LINE}; }}
.st-key-sidepanel {{ padding-bottom:14px; }}
.sec-label {{ font-size:11px; font-weight:600; color:{MUTED}; letter-spacing:.08em;
    padding:16px 16px 10px; margin:0; }}
.st-key-themelist {{ padding:0 8px; }}
.st-key-themelist .stButton button {{
    width:100%; display:flex; align-items:center; gap:10px; text-align:left;
    background:transparent; border:none; border-radius:10px; padding:9px 10px;
    min-height:0; transition:background .15s; }}
.st-key-themelist .stButton button:hover {{ background:{BG}; }}
.st-key-themelist .stButton button:focus:not(:active) {{ color:{INK}; }}
.st-key-themelist .stButton button::before {{
    content:""; width:30px; height:30px; border-radius:50%; flex:none; }}
.st-key-themelist [data-testid="stMarkdownContainer"] {{
    display:flex; flex-wrap:wrap; align-items:center; gap:5px; flex:1; }}
.st-key-themelist [data-testid="stMarkdownContainer"] p {{ margin:0 !important; }}
.st-key-themelist p:nth-of-type(1) {{
    width:100%; font-size:13px !important; font-weight:500 !important; color:{INK} !important;
    line-height:1.35 !important; }}
.st-key-themelist p:nth-of-type(2) {{
    font-size:10px !important; font-weight:500 !important; border-radius:10px; padding:1px 6px; }}
.st-key-themelist p:nth-of-type(3) {{ font-size:10px !important; color:{FAINT} !important; }}
.side-foot {{ font-size:10.5px; color:{FAINT}; line-height:1.6; padding:14px 16px 0;
    margin:8px 0 0; border-top:1px solid {LINE}; }}
{''.join(rows)}

/* ── 가운데 지도 ───────────────────────────────────────────── */
.st-key-mappanel {{ padding:0; }}
.maphead {{ display:flex; align-items:center; gap:10px; padding:11px 18px;
    background:{PANEL}; border-bottom:1px solid {LINE}; flex-wrap:wrap; }}
.maphead img {{ width:26px; height:26px; }}
.maphead b {{ font-size:14px; font-weight:600; color:{INK}; }}
.maphead .tag {{ font-size:10px; font-weight:500; border-radius:10px; padding:1px 7px; }}
.maphead .n {{ margin-left:auto; font-size:11.5px; color:{MUTED};
    font-variant-numeric:tabular-nums; }}
.maplegend {{ display:flex; gap:16px; align-items:center; flex-wrap:wrap;
    padding:9px 18px; font-size:11px; color:{MUTED};
    background:{PANEL}; border-top:1px solid {LINE}; }}
.maplegend img {{ width:17px; height:17px; vertical-align:middle; margin-right:5px; }}
.maplegend i {{ display:inline-block; width:8px; height:8px; border-radius:50%;
    opacity:.45; margin-right:5px; }}

/* ── 우측 챗봇 패널 ─────────────────────────────────────────── */
.st-key-chatpanel {{ padding:0 16px 12px; }}
.ph {{ padding:15px 2px 4px; }}
.ph b {{ font-size:14px; font-weight:600; color:{INK}; }}
.ph span {{ display:block; font-size:11.5px; color:{MUTED}; margin-top:3px; }}
.st-key-chips {{ padding:10px 0 6px; }}
.st-key-chips .stButton button {{
    background:rgba(255,255,255,.8); border:1px solid rgba(0,0,0,.1); border-radius:20px;
    padding:5px 12px; min-height:0; }}
.st-key-chips .stButton button p {{
    font-size:12px !important; font-weight:500 !important; color:{DEEP} !important; margin:0 !important; }}
.st-key-chips .stButton button:hover {{ border-color:{GREEN}; background:#fff; }}
.st-key-chips .stButton button::before {{
    content:""; width:16px; height:16px; margin-right:6px; flex:none;
    background-size:16px; background-repeat:no-repeat; background-position:center; }}

/* 노선 선택 — 지도 아래 가로 스크롤 없는 칩 줄 */
.st-key-routes {{ padding:10px 18px 14px; background:{PANEL}; border-top:1px solid {LINE}; }}
.st-key-routes .stButton button {{
    background:{BG}; border:1px solid {LINE}; border-radius:20px; padding:5px 13px;
    min-height:0; }}
.st-key-routes .stButton button p {{
    font-size:12px !important; font-weight:500 !important; color:{INK} !important;
    margin:0 !important; white-space:nowrap; }}
.st-key-routes .stButton button:hover {{ border-color:{DEEP}; background:#fff; }}
.st-key-chatscroll {{ border:none; }}
[data-testid="stChatMessage"] {{ background:transparent; padding:6px 0; }}
[data-testid="stChatMessageContent"] p {{ font-size:13px; line-height:1.65; }}
div[data-testid="stChatInput"] {{ border-radius:12px; border:1px solid {LINE}; }}
div[data-testid="stChatInput"] textarea {{ font-size:13px; }}
</style>"""


st.markdown(css(), unsafe_allow_html=True)


# ── 지도 ──────────────────────────────────────────────────────────────────────
def thin(points, cell: float):
    """같은 격자 칸에 하나만 남겨 아이콘이 뭉치지 않게 한다."""
    seen, out = set(), []
    for la, lo in points:
        k = (round(la / cell), round(lo / cell))
        if k not in seen:
            seen.add(k)
            out.append((la, lo))
    return out


def fit_zoom(lat_span: float, lon_span: float, pad: float = 0.6, lat: float = 37.55) -> float:
    """가로·세로 둘 다 담기는 줌. 세로를 빼먹으면 남북으로 긴 결과가 잘린다."""
    z_lon = math.log2(360 * MAP_W / (256 * max(lon_span, 1e-3)))
    z_lat = math.log2(360 * MAP_H * math.cos(math.radians(lat)) / (256 * max(lat_span, 1e-3)))
    return max(8.0, min(16.5, min(z_lon, z_lat) - pad - RENDER_ZOOM_OFFSET))


def cell_for(zoom: float, gap_px: float, lat: float = 37.55) -> float:
    return gap_px * (156543.03 * math.cos(math.radians(lat)) / 2 ** zoom) / 111320


def gather(hits: dict, focus):
    """축척에 따라 표현을 바꾼다 — 전체는 도로당 대표 마커, 확대하면 나무를 줄지어 찍는다."""
    theme = hits["theme"]
    streets = hits["streets"]
    if focus:
        streets = [s for s in streets if (s["구"], s["노선"]) == tuple(focus)] or streets
    per = [(s, cached_points(s["구"], s["노선"], theme)) for s in streets]
    haze = [{"lat": la, "lon": lo} for _, pts in per for la, lo in pts]

    if focus and any(p for _, p in per):
        lats = [p[0] for _, pts in per for p in pts]
        lons = [p[1] for _, pts in per for p in pts]
        zoom = fit_zoom(max(lats) - min(lats), max(lons) - min(lons), pad=0.55)
        cell = cell_for(zoom + RENDER_ZOOM_OFFSET, 30)
        icons = [{"lat": la, "lon": lo, "icon": theme, "rank": "",
                  "노선": f"{s['구']} {s['노선']}", "그루수": s["그루수"]}
                 for s, pts in per for la, lo in thin(pts, cell)]
        return icons, haze, pdk.ViewState(latitude=sum(lats) / len(lats),
                                          longitude=sum(lons) / len(lons), zoom=zoom), 26

    icons = [{"lat": s["center"][0], "lon": s["center"][1], "icon": theme, "rank": str(i),
              "노선": f"{s['구']} {s['노선']}", "그루수": s["그루수"]}
             for i, (s, pts) in enumerate(per, 1) if pts]
    if icons:
        lats = [r["lat"] for r in icons]
        lons = [r["lon"] for r in icons]
        return icons, haze, pdk.ViewState(
            latitude=(max(lats) + min(lats)) / 2, longitude=(max(lons) + min(lons)) / 2,
            zoom=fit_zoom(max(lats) - min(lats), max(lons) - min(lons), pad=0.45)), 40
    return [], haze, pdk.ViewState(latitude=SEOUL_CENTER[0], longitude=SEOUL_CENTER[1],
                                   zoom=10.2), 40


def render_map(hits, focus, accent):
    layers = []
    if hits and hits.get("ok"):
        icons, haze, view, isize = gather(hits, focus)
        rgb = [int(accent.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
        if haze:
            layers.append(pdk.Layer("ScatterplotLayer", data=haze, get_position="[lon, lat]",
                                    get_fill_color=rgb + [70], get_radius=30,
                                    radius_min_pixels=1.6, radius_max_pixels=7))
        if icons:
            layers.append(pdk.Layer("IconLayer", data=icons, get_position="[lon, lat]",
                                    get_icon="icon", get_size=isize, billboard=False,
                                    icon_atlas=ICON_ATLAS, icon_mapping=ICON_MAPPING,
                                    pickable=True))
            if any(r["rank"] for r in icons):
                layers.append(pdk.Layer(
                    "TextLayer", data=icons, get_position="[lon, lat]", get_text="rank",
                    get_size=14, get_color=[26, 26, 24], get_pixel_offset=[0, -26],
                    get_text_anchor="'middle'", get_alignment_baseline="'center'",
                    font_weight=700, background=True,
                    get_background_color=[255, 255, 255, 230], background_padding=[5, 2, 5, 2]))
    else:
        view = pdk.ViewState(latitude=SEOUL_CENTER[0], longitude=SEOUL_CENTER[1], zoom=10.2)
    st.pydeck_chart(
        pdk.Deck(layers=layers, initial_view_state=view, map_provider="carto", map_style="light",
                 tooltip={"html": "<b>{노선}</b><br/>{그루수}그루",
                          "style": {"backgroundColor": HEADER, "color": "#F2F5F0",
                                    "fontSize": "12px", "borderRadius": "8px",
                                    "padding": "7px 10px"}}),
        height=MAP_H, width="stretch")


# ── 상단 헤더 ─────────────────────────────────────────────────────────────────
total_trees, total_gu = overview()
with st.container(key="topbar", horizontal=True, vertical_alignment="center"):
    st.markdown(
        '<div class="brand"><span class="mark">🌿</span>'
        '<b>서울 가로수길</b><span>WALK SEOUL</span></div>', unsafe_allow_html=True)
    with st.container(key="seasonpick"):
        picked = st.pills("계절", BUCKETS, default="사계절", label_visibility="collapsed",
                          key="bucket")
    st.markdown(
        f'<div class="stats">'
        f'<div><b>{len(THEMES)}</b><span>테마 경로</span></div>'
        f'<div><b>{total_trees:,}</b><span>가로수 총계</span></div>'
        f'<div><b>{total_gu}</b><span>커버 구</span></div></div>', unsafe_allow_html=True)

visible = [k for k, v in THEMES.items()
           if picked in (None, "사계절") or v["bucket"] in (picked, "사계절")]

with st.container(key="mainrow"):
    left, mid, right = st.columns([260, 760, 420], gap="small")

# ── 좌측: 테마 경로 목록 ──────────────────────────────────────────────────────
with left:
    with st.container(key="sidepanel"):
        st.markdown('<p class="sec-label">테마 경로 목록</p>', unsafe_allow_html=True)
        with st.container(key="themelist"):
            for key in visible:
                v = THEMES[key]
                gus = theme_districts(key)
                picked_now = st.session_state.theme == key
                with st.container(key=f"row_{SLUG[key]}"):
                    if st.button(f"{v['label']}\n\n{v['bucket']}\n\n{'·'.join(gus) or '전역'}",
                                 key=f"btn_{SLUG[key]}"):
                        st.session_state.theme = key
                        st.session_state.focus = None
                        st.rerun()
                if picked_now:
                    st.markdown(
                        f"<style>.st-key-row_{SLUG[key]} .stButton button{{"
                        f"box-shadow:inset 3px 0 0 {BUCKET_COLOR[v['bucket']]};"
                        f"background:{BG};}}</style>", unsafe_allow_html=True)
        st.markdown(
            f'<p class="side-foot">서울시 가로수 위치정보 {total_trees:,}그루 · '
            f'{total_gu}개 자치구(+서울시설공단·중부공원여가센터 관리 구간).<br>'
            f'테마는 수종으로 정의되며, 실제 개화·단풍 시기는 자료에 없어 평년 기준 추정입니다.</p>',
            unsafe_allow_html=True)

theme = st.session_state.theme
spec = THEMES[theme]
accent = THEME_COLOR[theme]
bcol = BUCKET_COLOR[spec["bucket"]]
hits = lookup(theme)

# ── 가운데: 지도 ──────────────────────────────────────────────────────────────
with mid:
    with st.container(key="mappanel"):
        focus = st.session_state.focus
        where = f"{focus[0]} {focus[1]}" if focus else hits.get("district", "서울 전체")
        st.markdown(
            f'<div class="maphead"><img src="{sprite_uri(theme, 40)}"/>'
            f'<b>{spec["label"]}</b>'
            f'<span class="tag" style="color:{bcol};background:{bcol}1A">{spec["bucket"]}</span>'
            f'<span class="tag" style="color:{MUTED};background:{BG}">{where}</span>'
            f'<span class="n">{hits.get("total_trees", 0):,}그루 · '
            f'{len(hits.get("streets", []))}개 노선</span></div>', unsafe_allow_html=True)
        render_map(hits, focus, accent)
        avoid = spec["mode"] == "avoid"
        st.markdown(
            f'<div class="maplegend"><span><img src="{sprite_uri(theme, 34)}"/>'
            f'{"피할 노선" if avoid else "추천 노선"} 위치</span>'
            f'<span><i style="background:{accent}"></i>가로수 분포(밀도)</span>'
            f'<span>마커에 커서를 올리면 노선 이름이 나옵니다</span></div>', unsafe_allow_html=True)

        if hits.get("ok"):
            with st.container(key="routes", horizontal=True, wrap=True):
                for i, s in enumerate(hits["streets"], 1):
                    sel = focus == (s["구"], s["노선"])
                    if st.button(f"{'✓ ' if sel else ''}{i}. {s['노선']} {s['그루수']:,}",
                                 key=f"rt{i}"):
                        st.session_state.focus = None if sel else (s["구"], s["노선"])
                        st.rerun()

# ── 우측: 경로 추천 챗봇 ──────────────────────────────────────────────────────
CHIPS = [("벚꽃", "벚꽃 봄산책"), ("그늘", "여름 그늘길"), ("은행단풍", "가을 은행 단풍"),
         ("이팝", "이팝 흰꽃길"), ("메타세쿼이아", "메타세쿼이아"), ("단풍", "단풍 명소"),
         ("상록", "상록 소나무"), ("은행회피", "은행 냄새 회피")]

with right:
    with st.container(key="chatpanel"):
        st.markdown('<div class="ph"><b>🗺 경로 추천 챗봇</b>'
                    '<span>계절·수종·분위기를 자유롭게 입력하세요</span></div>',
                    unsafe_allow_html=True)
        with st.container(key="chips", horizontal=True, wrap=True):
            for key, label in CHIPS:
                with st.container(key=f"chip_{SLUG[key]}"):
                    clicked = st.button(label, key=f"chipbtn_{SLUG[key]}")
                if clicked:
                    st.session_state.theme = key
                    st.session_state.focus = None
                    h = lookup(key)
                    tops = "、".join(f"{s['노선']}({s['그루수']:,})" for s in h["streets"][:3])
                    verb = "피하는 게 좋은 노선" if THEMES[key]["mode"] == "avoid" else "추천 노선"
                    st.session_state.messages.append({"role": "assistant", "content":
                        f"**{THEMES[key]['label']}** · {h['district']}\n\n"
                        f"{verb}: {tops}\n\n{h['note']}"})
                    st.rerun()

        box = st.container(height=430, key="chatscroll", autoscroll=False)
        for m in st.session_state.messages:
            box.chat_message(m["role"], avatar="🌿" if m["role"] == "assistant" else None
                             ).write(m["content"])

        if q := st.chat_input("예: 가을에 은행나무 단풍길 추천해줘"):
            st.session_state.messages.append({"role": "user", "content": q})
            try:
                out = get_app().invoke({"question": q})
                ans = out.get("final_answer", "(답변 없음)")
                if out.get("hits", {}).get("ok"):
                    st.session_state.theme = out["hits"]["theme"]
                    st.session_state.focus = None
            except Exception as exc:      # 보통 8080 미기동 / API 키 미설정
                ans = (f"에이전트 호출 실패: {type(exc).__name__}. 로컬 서버(8080)를 켜거나 "
                       "위의 빠른 칩을 눌러보세요.")
            st.session_state.messages.append({"role": "assistant", "content": ans})
            st.rerun()
