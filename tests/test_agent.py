"""에이전트 경로(LLM tool-calling) — 실제 서버 없이 mock LLM으로 검증.

conftest는 AGENT_CHANNEL=none(규칙 경로)로 고정한다. 이 파일은 테스트별로 AGENT_CHANNEL=local을
setenv 하고 graph.get_agent_model/get_chat_model 을 스텁으로 갈아끼워 에이전트 경로만 격리 검증한다.
"""
import graph
from langchain_core.messages import AIMessage


class FakeAgentModel:
    """scripted 메시지를 호출 순서대로 돌려주는 스텁(라운드 간 상태 유지). tools/인자는 무시."""

    def __init__(self, scripted):
        self.scripted = scripted
        self.i = 0

    def invoke(self, messages):
        msg = self.scripted[min(self.i, len(self.scripted) - 1)]
        self.i += 1
        return msg


class FakeChatModel:
    """resolver용 — 도구결과 기반 답변 대신 고정 문장(그라운딩 자체는 test_tools/prompt가 다룸)."""

    def __init__(self, text="[테스트] 도구결과 기반 답변입니다."):
        self.text = text

    def invoke(self, prompt):
        return AIMessage(content=self.text)


def _tool_call(name, args, cid="c1"):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": cid}])


def _agent_mode(monkeypatch, agent_model):
    """AGENT_CHANNEL=local + get_agent_model/get_chat_model 스텁 설치."""
    monkeypatch.setenv("AGENT_CHANNEL", "local")
    monkeypatch.setattr(graph, "get_agent_model", lambda *a, **k: agent_model)
    monkeypatch.setattr(graph, "get_chat_model", lambda *a, **k: FakeChatModel())


def _run(q):
    return graph.build_graph().invoke({"question": q, "visited": []})


def test_agent_calls_tool_then_grounds(monkeypatch):
    """에이전트가 find_theme_streets 호출 → hits 확보 → resolver 답변. 좌표는 state에만."""
    agent = FakeAgentModel([
        _tool_call("find_theme_streets", {"theme": "벚꽃", "district": "강동구"}),
        AIMessage(content="충분합니다."),          # 도구 없이 종료 → resolver
    ])
    _agent_mode(monkeypatch, agent)
    out = _run("강동구 벚꽃 길")

    assert out["verdict"] == "match" and out["hits"]["ok"]
    assert "agent" in out["visited"] and "tools" in out["visited"]
    assert out["final_answer"]
    # 좌표 계약: hits(full)에는 center가 있어야 UI 지도가 나온다
    assert out["hits"]["streets"][0]["center"]
    # 슬림 계약: LLM에 간 ToolMessage에는 좌표가 없어야 한다
    from langchain_core.messages import ToolMessage
    tool_msgs = [m for m in out["messages"] if isinstance(m, ToolMessage)]
    assert tool_msgs and all("center" not in m.content for m in tool_msgs)


def test_agent_landmark_route(monkeypatch):
    """랜드마크 경로 — rule_intake가 못 잡던 origin/dest를 에이전트가 route_theme_streets로."""
    agent = FakeAgentModel([
        _tool_call("route_theme_streets",
                   {"origin": "올림픽공원", "dest": "롯데타워", "theme": "벚꽃"}),
        AIMessage(content="done"),
    ])
    _agent_mode(monkeypatch, agent)
    out = _run("올림픽공원에서 롯데타워 가는 길 벚꽃")
    assert "tools" in out["visited"]
    # ok면 경로 hits, 아니면 supervisor 폴백 — 둘 다 최종 답변은 나와야 한다
    assert out["final_answer"]


def test_safety_gate_refuses_without_agent(monkeypatch):
    """서울 밖 질의는 gate가 결정적으로 거절 — 에이전트/도구를 거치지 않는다."""
    agent = FakeAgentModel([AIMessage(content="이럴 리 없음")])  # 호출되면 안 됨
    _agent_mode(monkeypatch, agent)
    out = _run("부산 해운대 벚꽃길 추천해줘")
    assert out["resolver_mode"] == "refuse"
    assert "agent" not in out["visited"] and "tools" not in out["visited"]
    assert "prescan" in out["visited"] and "gate" in out["visited"]


def test_agent_llm_failure_falls_back_to_rules(monkeypatch):
    """에이전트 LLM 예외 → supervisor 규칙 경로 재진입으로 답이 반드시 나온다."""
    class Boom:
        def invoke(self, messages):
            raise RuntimeError("server down")

    _agent_mode(monkeypatch, Boom())
    out = _run("강동구 벚꽃 길")
    assert "agent" in out["visited"] and "supervisor" in out["visited"]
    assert out["final_answer"]                 # 규칙 폴백이 답 보장


def test_agent_loop_is_fenced(monkeypatch):
    """에이전트가 매 라운드 같은 도구를 반복해도 AGENT_MAX_ROUNDS에서 종료(무한루프 없음)."""
    agent = FakeAgentModel([
        _tool_call("find_theme_streets", {"theme": "벚꽃", "district": "강동구"}),
    ])  # 항상 같은 tool_call(끝나지 않음)
    _agent_mode(monkeypatch, agent)
    out = _run("강동구 벚꽃 길")
    assert out["agent_rounds"] <= graph.AGENT_MAX_ROUNDS
    assert out["final_answer"]                 # 울타리에서 resolver로 마무리
