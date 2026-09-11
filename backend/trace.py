"""궤적 기록 — Langfuse 콜백 또는 JSONL(week6 TraceWriter 이식).  [BE_DESIGN C4]

TRACE_BACKEND=jsonl (기본)  → results/rushhour_trace.jsonl 에 이벤트 한 줄 = JSON 한 줄
TRACE_BACKEND=langfuse       → langfuse.langchain.CallbackHandler (LANGFUSE_* env 필요)
TRACE_BACKEND=none           → 기록 안 함

남기지 않은 것은 나중에 물어볼 수 없다. Langfuse 서버가 없어도 JSONL은 항상 남는다.
"""

import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE_PATH = Path(os.environ.get("TRACE_PATH", ROOT / "results" / "rushhour_trace.jsonl"))


class JsonlTracer:
    """이벤트를 JSONL 한 줄로 남김. 프로세스 시작 시각 기준 상대 시간(t)을 붙인다."""

    def __init__(self, path: Path = TRACE_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._t0 = time.time()

    def event(self, kind: str, payload: dict) -> None:
        record = {"t": round(time.time() - self._t0, 3), "ts": time.time(), "kind": kind, **payload}
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def callbacks(self) -> list:
        return []


class NullTracer:
    def event(self, kind: str, payload: dict) -> None:
        pass

    def callbacks(self) -> list:
        return []


class LangfuseTracer(JsonlTracer):
    """Langfuse 콜백 + JSONL 동시 기록. langfuse 미설치·서버 없음이면 JSONL만 남긴다."""

    def __init__(self, path: Path = TRACE_PATH):
        super().__init__(path)
        self._handler = None
        try:
            from langfuse.langchain import CallbackHandler
            self._handler = CallbackHandler()
        except Exception as exc:  # noqa: BLE001
            self.event("trace_warning", {"msg": f"langfuse 비활성: {type(exc).__name__}: {exc}"})

    def callbacks(self) -> list:
        return [self._handler] if self._handler else []


def make_tracer():
    backend = os.environ.get("TRACE_BACKEND", "jsonl").strip().lower()
    if backend == "none":
        return NullTracer()
    if backend == "langfuse":
        return LangfuseTracer()
    return JsonlTracer()
