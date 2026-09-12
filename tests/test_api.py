"""FastAPI 층 — SSE·도구 엔드포인트. LLM 없이."""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory, rag_index):
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
    assert set(client.get("/themes").json()) == {"은행회피", "벚꽃", "그늘", "이팝", "은행단풍", "메타세쿼이아", "크리스마스", "상록"}
    assert client.get("/districts").json()["count"] == 25


def test_leaflet_ui_shell_and_dtos(client):
    """develop2에서 이식한 Leaflet 화면은 정본 도구 결과를 UI DTO로만 소비한다."""
    shell = client.get("/")
    assert shell.status_code == 200 and "WALK SEOUL" in shell.text
    overview = client.get("/ui/overview").json()
    assert overview["totals"]["districts"] == 25 and len(overview["themes"]) == 8
    assert all(t["paths"] and not t["points"] for t in overview["themes"])
    detail = client.get(f"/ui/theme/{overview['themes'][0]['id']}").json()
    assert detail["points"] and detail["streets"]


def test_tool_endpoint_no_llm(client):
    r = client.post("/tools/find_theme_streets", json={"theme": "벚꽃", "district": "강동구"}).json()
    assert r["ok"] and r["streets"][0]["노선"] == "아리수로"
    pts = client.get("/map/street_points", params={"gu": "강동구", "line": "아리수로", "theme": "벚꽃"}).json()
    assert 0 < len(pts["points"]) <= 1000


def test_search_places_endpoint_and_health_rag(client):
    """벡터DB 검색을 API로 — LLM·임베딩 모델 없이(해시 채널 인덱스)."""
    h = client.get("/health").json()
    assert h["rag"]["ready"] and h["rag"]["docs"] > 1500 and h["rag"]["channel"] == "hash"
    assert h["embed"]["channel"] == "hash" and h["embed"]["reachable"] is True
    r = client.post("/tools/search_places", json={"query": "석촌호수 벚꽃", "k": 3}).json()
    assert r["ok"] and (r["results"][0]["구"], r["results"][0]["노선"]) == ("송파구", "석촌호수로")
    assert r["results"][0]["center"][0] > 37 and "score" in r["results"][0]
    r2 = client.post("/tools/search_places", json={"query": "벚꽃", "district": "강동구", "min_trees": 0}).json()
    assert r2["ok"] and {x["구"] for x in r2["results"]} == {"강동구"}
    assert client.post("/tools/search_places", json={"query": ""}).status_code == 422


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
    assert final["ui_routes"] and final["ui_routes"][0]["points"]
    # 체크포인트로 스레드 복구
    t = client.get("/threads/t-1").json()
    assert t["state"]["theme"] == "벚꽃" and t["next"] == []
    assert client.get("/threads/없음").status_code == 404


def test_chat_same_thread_next_turn_starts_fresh(client):
    """UI는 세션당 thread_id 하나를 재사용한다 — 두 번째 질문이 이전 답을 되돌려주면 안 된다(DP13)."""
    turns = [("강남구에서 봄에 벚꽃 예쁜 길", "벚꽃", "강남구", "match"),
             ("서초구 여름 그늘길", "그늘", "서초구", "match"),
             ("오늘 날씨 어때?", "unknown", "", "unknown_intent")]
    for q, theme, gu, verdict in turns:
        evs = _events(client.post("/chat", json={"message": q, "thread_id": "t-multi"}).text)
        nodes = [d["name"] for e, d in evs if e == "node"]
        assert nodes[:4] == ["supervisor", "season", "supervisor", "intake"], nodes
        final = evs[-1][1]
        assert (final["theme"], final["district"], final["verdict"]) == (theme, gu, verdict)
        assert final["visited"].count("supervisor") <= 4     # hops가 턴마다 누적되지 않음
    t = client.get("/threads/t-multi").json()                # 스레드 상태 = 마지막 턴
    assert t["state"]["verdict"] == "unknown_intent" and t["state"]["hits"] is None
