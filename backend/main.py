"""Rushhour FastAPI — 에이전트 그래프를 SSE로 노출.  [BE_DESIGN C4]

Streamlit(UI)은 이 API만 부른다. 그래프·툴은 app/ 의 것을 그대로 쓴다.

실행:  AGENT_CHANNEL=none uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
       (8080 모델 서버가 있으면 AGENT_CHANNEL=local)

엔드포인트:
  GET  /health                     모델 서버·데이터·그래프 상태 (UI가 첫 화면에서 배지 표시)
  POST /chat                       {thread_id, message} → SSE (node / final / error 이벤트)
                                   같은 thread_id로 다음 질문을 보내면 이전 턴 상태를 비우고 처음부터 돈다(DP13)
  GET  /threads/{thread_id}        체크포인트 상태 조회 (UI 새로고침 복구)
  POST /tools/find_theme_streets   LLM 없이 도구만 호출 (사이드바 '빠른 추천')
  POST /tools/search_places        벡터DB 의미검색 (동네·지명·구어체 → (구, 노선) 후보)  [RAG]
  POST /tools/plan_route           출발→도착 경로 3가지 (최단·테마 경유·회피)  [DP17]
  GET  /spots                      테마길 목록(공원·하천·전국) — 공공자료 합본  [DP24]
  GET  /spots/points               좌표 있는 노선을 전부 — 지도에 나무로 뿌리는 용도
  GET  /map/theme_points           그 테마 가로수 좌표 **전부**(서울) — 상위 6개 도로만이 아니라
  GET  /themes  · GET /districts   UI 셀렉트박스용 메타
  GET  /map/street_points          지도 마커 좌표 (map_api.street_points)
"""

import json
import os
import sqlite3
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))          # app/ 모듈은 평면 import(dev1 구조 유지)

from graph import build_graph, MAX_HOPS, new_turn_input   # noqa: E402
from llm import AGENT_BASE_URL                         # noqa: E402
from map_api import street_points, theme_points        # noqa: E402
from rag import rag_status, search_places              # noqa: E402
from routing import osm_status, plan_route             # noqa: E402
from spots import all_points, find_spots, spots_status  # noqa: E402
from embeddings import EMBED_BASE_URL, channel as embed_channel, configured_model   # noqa: E402
from themes import THEMES, SEASON_LABEL                # noqa: E402
from tools import available_districts, data_source, find_theme_streets   # noqa: E402
from backend.trace import make_tracer                  # noqa: E402
from backend.web_ui import BY_ID, overview_payload, result_routes, theme_payload_cached  # noqa: E402

CHECKPOINT_PATH = Path(os.environ.get("CHECKPOINT_DB", ROOT / "data" / "checkpoints.sqlite"))
STATE = {}


def _make_checkpointer():
    from langgraph.checkpoint.sqlite import SqliteSaver
    CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CHECKPOINT_PATH, check_same_thread=False)
    return SqliteSaver(conn)


def _llm_reachable() -> dict:
    """8080(또는 AGENT_BASE_URL) 모델 서버가 살아 있는지 1초 안에 확인."""
    channel = os.environ.get("AGENT_CHANNEL", "local").lower()
    if channel == "none":
        return {"channel": "none", "reachable": False, "model": None}
    if channel in ("gemini", "openai"):
        return {"channel": channel, "reachable": True, "model": "(remote)"}
    try:
        import httpx
        r = httpx.get(f"{AGENT_BASE_URL}/models", timeout=1.0)
        model = r.json()["data"][0]["id"] if r.status_code == 200 else None
        return {"channel": "local", "reachable": r.status_code == 200, "model": model}
    except Exception:  # noqa: BLE001
        return {"channel": "local", "reachable": False, "model": None}


def _embed_reachable() -> dict:
    """임베딩 채널 상태. local이면 EMBED_BASE_URL/models 를 2초 안에 확인(프록시 뒤 서버 고려)."""
    ch = embed_channel()
    info = {"channel": ch, "model": configured_model(ch) or "(auto)", "base_url": EMBED_BASE_URL if ch == "local" else None}
    if ch in ("hash", "st"):
        return {**info, "reachable": True}                  # 로컬 계산 — 네트워크 없음
    if ch in ("openai", "gemini"):
        return {**info, "reachable": True}
    try:
        import httpx
        r = httpx.get(f"{EMBED_BASE_URL}/models", timeout=2.0)
        ids = [m.get("id") for m in r.json().get("data", [])] if r.status_code == 200 else []
        return {**info, "reachable": r.status_code == 200, "served": ids[:3]}
    except Exception:  # noqa: BLE001
        return {**info, "reachable": False}


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    STATE["tracer"] = make_tracer()
    STATE["graph"] = build_graph(checkpointer=_make_checkpointer())
    STATE["districts"] = available_districts()          # 데이터 로드(캐시 워밍)
    STATE["started"] = time.time()
    STATE["tracer"].event("startup", {"data": data_source(), "load_sec": round(time.time() - t0, 2)})
    yield


app = FastAPI(title="Rushhour BE", version="0.1", lifespan=lifespan)


# ── 메타 ─────────────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    llm = _llm_reachable()
    return {
        "ok": True, "graph": STATE.get("graph") is not None, "max_hops": MAX_HOPS,
        "data": {"source": data_source(), "districts": len(STATE.get("districts", ()))},
        "llm": llm,
        "rag": rag_status(),        # 벡터DB 인덱스 유무·임베딩 채널 일치 여부 (모델은 로드 안 함)
        "osm": osm_status(),        # 경로 탐색용 보행 도로망 산출물(scripts/04·05) 유무
        "spots": spots_status(),    # 테마길 합본(scripts/07) — 공원·하천·전국 목록
        "embed": _embed_reachable(),  # 임베딩 서버(local=llama-server 등) 도달 여부 — 검색 불가 배지용
        # LLM이 없어도 지도는 나온다 — UI는 이 값으로 '채팅은 규칙 모드' 배지를 띄운다
        "chat_mode": "llm" if llm["reachable"] else "rule",
        "uptime_sec": round(time.time() - STATE.get("started", time.time()), 1),
    }


@app.get("/themes")
def themes():
    return {k: {"label": v["label"], "mode": v["mode"], "season": v["season"],
                "seasons": v["seasons"]} for k, v in THEMES.items()}


@app.get("/districts")
def districts():
    return {"count": len(STATE["districts"]), "districts": list(STATE["districts"])}


# ── 도구 직접 호출 (LLM 불필요) ──────────────────────────────────────────────
class ThemeQuery(BaseModel):
    theme: str
    district: str = ""


@app.post("/tools/find_theme_streets")
def tool_find_theme_streets(q: ThemeQuery):
    res = find_theme_streets.invoke({"theme": q.theme, "district": q.district})
    STATE["tracer"].event("tool_call", {"tool": "find_theme_streets", "args": q.model_dump(),
                                        "ok": res.get("ok")})
    return res


class PlaceQuery(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    k: int = Field(default=5, ge=1, le=20)
    district: str = ""
    min_trees: int = Field(default=20, ge=0)               # 골목 제외 하한(0=없음)
    size_weight: float = Field(default=0.02, ge=0.0, le=1.0)  # 큰 길 우선 재정렬(0=유사도만). rag.DEFAULT_SIZE_WEIGHT


@app.post("/tools/search_places")
def tool_search_places(q: PlaceQuery):
    res = search_places.invoke(q.model_dump())
    STATE["tracer"].event("tool_call", {"tool": "search_places", "args": q.model_dump(),
                                        "ok": res.get("ok"), "embed": res.get("embed"),
                                        "top": [f"{x['구']} {x['노선']}" for x in res.get("results", [])[:3]]})
    return res


class RouteQuery(BaseModel):
    origin: str = Field(min_length=1, max_length=100)
    dest: str = Field(min_length=1, max_length=100)
    season: str = ""
    theme: str = ""


@app.post("/tools/plan_route")
def tool_plan_route(q: RouteQuery):
    res = plan_route.invoke(q.model_dump())
    STATE["tracer"].event("tool_call", {"tool": "plan_route", "args": q.model_dump(),
                                        "ok": res.get("ok"),
                                        "kinds": [r["kind"] for r in res.get("routes", [])]})
    return res


@app.get("/spots/points")
def spot_points(theme: str = ""):
    """좌표가 있는 노선을 전부 — 지도에 점(나무)으로 뿌린다. 필드를 줄여 한 번에 보낸다."""
    return all_points(theme=theme)


@app.get("/spots")
def spots(theme: str = "", sido: str = "", sigungu: str = "", kind: str = "",
          k: int = 30, seoul_only: bool = False):
    """테마길 명소 목록. 좌표는 노선당 한 점이라 화면에는 점으로 찍는다(도로 형상 아님)."""
    return find_spots(theme=theme, sido=sido, sigungu=sigungu, kind=kind,
                      k=k, seoul_only=seoul_only)


@app.get("/map/theme_points")
def map_theme_points(theme: str, district: str = "", limit: int = 60000):
    """그 테마 가로수의 좌표를 전부(서울). 상위 6개 도로만 주면 석촌호수처럼 순위 밖의 길이
    지도에서 사라진다 — 나무는 거기 있는데 안 보이는 셈이라 전부 준다."""
    pts = theme_points(theme, district=district, limit=limit)
    return {"theme": theme, "count": len(pts), "points": pts}


@app.get("/map/street_points")
def map_street_points(gu: str, line: str, theme: str, limit: int = 1000):
    return {"points": street_points(gu, line, theme, limit=limit)}


# ── Leaflet UI 읽기 모델 ─────────────────────────────────────────────────────
@app.get("/ui/overview")
def ui_overview():
    return overview_payload()


@app.get("/ui/theme/{theme_id}")
def ui_theme(theme_id: str, district: str = ""):
    theme = BY_ID.get(theme_id)
    if theme is None:
        raise HTTPException(404, "모르는 UI 테마")
    payload = theme_payload_cached(theme, district, True)
    if payload is None:
        raise HTTPException(404, "해당 조건의 가로수 데이터 없음")
    return payload


# ── 채팅 (SSE) ──────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    thread_id: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


FINAL_KEYS = ("season", "theme", "district", "place", "place_hits", "verdict",
              "intake_mode", "resolver_mode", "final_answer", "hits", "light_spots", "visited")


@app.post("/chat")
def chat(body: ChatIn):
    graph = STATE["graph"]
    tracer = STATE["tracer"]
    thread_id = body.thread_id or str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}, "callbacks": tracer.callbacks()}

    def gen():
        # 동기 제너레이터 — StreamingResponse가 스레드풀에서 돌린다.
        # (SqliteSaver는 async 미지원, 노드도 전부 동기 함수라 sync stream이 맞음)
        t0 = time.time()
        tracer.event("inquiry", {"thread_id": thread_id, "text": body.message[:120]})
        yield _sse("start", {"thread_id": thread_id})
        try:
            # stream_mode="updates": 노드가 끝날 때마다 {노드명: 부분상태} 한 덩이.
            # new_turn_input: 체크포인트에 남은 이전 턴(theme·hits·final_answer·visited)을 비운다 —
            # question만 바꾸면 라우터가 supervisor에서 바로 FINISH해 이전 답을 다시 보낸다(DP13).
            for update in graph.stream(
                new_turn_input(body.message), config=config, stream_mode="updates"
            ):
                for node, patch in update.items():
                    patch = patch or {}
                    tracer.event("node", {"thread_id": thread_id, "name": node,
                                          "keys": sorted(k for k in patch if k != "visited")})
                    # 좌표 무거운 hits는 노드 이벤트에선 요약만, final에서 전체
                    slim = {k: v for k, v in patch.items() if k not in ("visited", "hits")}
                    if "hits" in patch:
                        slim["hits_ok"] = bool((patch["hits"] or {}).get("ok"))
                    yield _sse("node", {"name": node, "patch": slim})
            snap = graph.get_state(config)
            final = {k: snap.values.get(k) for k in FINAL_KEYS}
            # Leaflet UI는 기존 hits 원본을 직접 해석하지 않는다. UI DTO만 추가한다.
            final["ui_routes"] = result_routes(final)
            final["elapsed_sec"] = round(time.time() - t0, 2)
            tracer.event("result", {"thread_id": thread_id, "verdict": final["verdict"],
                                    "theme": final["theme"], "intake_mode": final["intake_mode"],
                                    "resolver_mode": final["resolver_mode"],
                                    "hops": (final["visited"] or []).count("supervisor"),
                                    "place": final["place"] or None,      # 장소 해소 발동 여부(DP15)
                                    "place_gu": (final["place_hits"] or [{}])[0].get("구"),
                                    "tool_error": (final["hits"] or {}).get("tool_error"),
                                    "elapsed_sec": final["elapsed_sec"]})
            yield _sse("final", final)
        except Exception as exc:  # noqa: BLE001
            tracer.event("error", {"thread_id": thread_id, "type": type(exc).__name__, "msg": str(exc)[:300]})
            yield _sse("error", {"type": type(exc).__name__, "message": str(exc)[:300]})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/threads/{thread_id}")
def get_thread(thread_id: str):
    snap = STATE["graph"].get_state({"configurable": {"thread_id": thread_id}})
    if not snap.values:
        raise HTTPException(404, "thread 없음")
    return {"thread_id": thread_id, "next": list(snap.next),
            "state": {k: snap.values.get(k) for k in FINAL_KEYS}}


# API 라우트를 모두 등록한 뒤 정적 화면을 마지막에 붙인다.
WEB_DIR = ROOT / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
