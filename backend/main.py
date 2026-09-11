"""Rushhour FastAPI — 에이전트 그래프를 SSE로 노출.  [BE_DESIGN C4]

Streamlit(UI)은 이 API만 부른다. 그래프·툴은 app/ 의 것을 그대로 쓴다.

실행:  AGENT_CHANNEL=none uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
       (8080 모델 서버가 있으면 AGENT_CHANNEL=local)

엔드포인트:
  GET  /health                     모델 서버·데이터·그래프 상태 (UI가 첫 화면에서 배지 표시)
  POST /chat                       {thread_id, message} → SSE (node / final / error 이벤트)
  GET  /threads/{thread_id}        체크포인트 상태 조회 (UI 새로고침 복구)
  POST /tools/find_theme_streets   LLM 없이 도구만 호출 (사이드바 '빠른 추천')
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
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))          # app/ 모듈은 평면 import(dev1 구조 유지)

from graph import build_graph, MAX_HOPS               # noqa: E402
from llm import AGENT_BASE_URL                         # noqa: E402
from map_api import street_points                      # noqa: E402
from themes import THEMES, SEASON_LABEL                # noqa: E402
from tools import available_districts, data_source, find_theme_streets   # noqa: E402
from backend.trace import make_tracer                  # noqa: E402

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


@app.get("/map/street_points")
def map_street_points(gu: str, line: str, theme: str, limit: int = 1000):
    return {"points": street_points(gu, line, theme, limit=limit)}


# ── 채팅 (SSE) ──────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    thread_id: str | None = None


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


FINAL_KEYS = ("season", "theme", "district", "verdict", "intake_mode", "resolver_mode",
              "final_answer", "hits", "light_spots", "visited")


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
            # stream_mode="updates": 노드가 끝날 때마다 {노드명: 부분상태} 한 덩이
            for update in graph.stream(
                {"question": body.message, "visited": []}, config=config, stream_mode="updates"
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
            final["elapsed_sec"] = round(time.time() - t0, 2)
            tracer.event("result", {"thread_id": thread_id, "verdict": final["verdict"],
                                    "theme": final["theme"], "intake_mode": final["intake_mode"],
                                    "resolver_mode": final["resolver_mode"],
                                    "hops": (final["visited"] or []).count("supervisor"),
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

