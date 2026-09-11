"""FastAPI 층 — SSE·도구 엔드포인트. LLM 없이."""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    import os
    os.environ["CHECKPOINT_DB"] = str(tmp_path_factory.mktemp("ckpt") / "c.sqlite")
    from backend.main import app
    with TestClient(app) as c:
        yield c


def _events(text: str) -> list[tuple[str, dict]]:
    out = []
    for block in text.strip().split("\n\n"):
        ev = data = None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        out.append((ev, data))
    return out


def test_health(client):
    h = client.get("/health").json()
    assert h["ok"] and h["graph"] and h["data"]["districts"] == 25
    assert h["chat_mode"] == "rule"          # AGENT_CHANNEL=none


def test_meta(client):
    assert set(client.get("/themes").json()) == {"은행회피", "벚꽃", "그늘", "이팝", "은행단풍", "메타세쿼이아"}
    assert client.get("/districts").json()["count"] == 25


def test_tool_endpoint_no_llm(client):
    r = client.post("/tools/find_theme_streets", json={"theme": "벚꽃", "district": "강동구"}).json()
    assert r["ok"] and r["streets"][0]["노선"] == "아리수로"
    pts = client.get("/map/street_points", params={"gu": "강동구", "line": "아리수로", "theme": "벚꽃"}).json()
    assert 0 < len(pts["points"]) <= 1000


def test_chat_sse_stream_and_thread(client):
    r = client.post("/chat", json={"message": "강남구에서 봄에 벚꽃 예쁜 길", "thread_id": "t-1"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = _events(r.text)
    kinds = [e for e, _ in evs]
    assert kinds[0] == "start" and kinds[-1] == "final"
    nodes = [d["name"] for e, d in evs if e == "node"]
    assert nodes == ["supervisor", "season", "supervisor", "intake", "supervisor",
                     "researcher", "supervisor", "resolver"]
    final = evs[-1][1]
    assert final["verdict"] == "match" and final["hits"]["ok"]
    # 체크포인트로 스레드 복구
    t = client.get("/threads/t-1").json()
    assert t["state"]["theme"] == "벚꽃" and t["next"] == []
    assert client.get("/threads/없음").status_code == 404
