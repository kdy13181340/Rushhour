"""supervisor 라우터·그래프 배선 — LLM 없이(AGENT_CHANNEL=none)."""
import pytest

import graph as G
from graph import MAX_HOPS, build_graph, route_from_supervisor, rule_intake, run_one


# ── 라우터는 순수 함수 ────────────────────────────────────────────────────────
def test_router_fills_blanks_in_order():
    s = {"visited": []}
    assert route_from_supervisor(s) == "season"
    s["season"] = "autumn";                     assert route_from_supervisor(s) == "intake"
    s["theme"] = "은행단풍";                    assert route_from_supervisor(s) == "researcher"
    s["hits"] = {"ok": True};                   assert route_from_supervisor(s) == "resolver"
    s["final_answer"] = "…";                    assert route_from_supervisor(s) == "FINISH"


def test_router_refuses_before_tools():
    assert route_from_supervisor({"season": "autumn", "theme": "unknown"}) == "resolver"
    assert route_from_supervisor({"season": "autumn", "theme": "벚꽃", "district": "부산",
                                  "verdict": "out_of_coverage"}) == "resolver"


def test_router_winter_visits_light_once():
    s = {"season": "winter", "theme": "메타세쿼이아", "hits": {"ok": True}}
    assert route_from_supervisor(s) == "light"
    s["light_spots"] = []
    assert route_from_supervisor(s) == "resolver"


def test_router_fence_first():
    s = {"visited": ["supervisor"] * MAX_HOPS}       # 아무것도 안 채워졌어도
    assert route_from_supervisor(s) == "FINISH"


def test_router_return_values_match_graph_mapping():
    """ref07의 결함(반환 'finish' vs 매핑 'FINISH')이 여기서 걸린다."""
    import typing
    allowed = set(typing.get_args(G.Next))
    for s in ({}, {"season": "x"}, {"season": "x", "theme": "unknown"},
              {"season": "x", "theme": "벚꽃"}, {"season": "winter", "theme": "벚꽃", "hits": {}},
              {"season": "x", "theme": "벚꽃", "hits": {}, "final_answer": "a"}):
        assert route_from_supervisor(s) in allowed


# ── 규칙 intake ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("q,theme,gu,season", [
    ("강남구에서 봄에 벚꽃 예쁜 길", "벚꽃", "강남구", "spring"),
    ("가을에 냄새 안 나게 강동구 산책", "은행회피", "강동구", "autumn"),
    ("여름에 더운데 그늘진 길 서초구", "그늘", "서초구", "summer"),
    ("종로구 지금 볼만한 길", "은행단풍", "종로구", ""),     # 단서 없음 → 계절 prefer 테마
    ("오늘 날씨 어때?", "unknown", "", ""),
])
def test_rule_intake(q, theme, gu, season):
    r = rule_intake(q, "autumn")
    assert (r["theme"], r["district"], r["season"]) == (theme, gu, season)


def test_rule_intake_outside_seoul_and_superlative():
    r = rule_intake("부산 해운대 벚꽃길 추천해줘", "autumn")
    assert r["outside_seoul"] is True and r["theme"] == "벚꽃" and r["district"] == ""
    r = rule_intake("서울에서 가장 큰 벚꽃길", "autumn")
    assert r["superlative"] is True and r["outside_seoul"] is False
    # 자치구가 명시되면 서울 밖으로 보지 않음 (예: '광주'가 도로명 일부여도)
    assert rule_intake("강남구 벚꽃길 최고 어디", "autumn")["outside_seoul"] is False


# ── 그래프 종단 (규칙 경로) ──────────────────────────────────────────────────
@pytest.fixture(scope="module")
def app():
    return build_graph()


def test_e2e_match(app):
    out = run_one(app, "강남구에서 봄에 벚꽃 예쁜 길 알려줘")
    assert out["verdict"] == "match" and out["hits"]["ok"]
    assert out["season"] == "spring"                       # 사용자 명시가 날짜(autumn)를 덮음
    assert out["intake_mode"] == "rule" and out["resolver_mode"] == "template"
    assert out["visited"] == ["supervisor", "season", "supervisor", "intake",
                              "supervisor", "researcher", "supervisor", "resolver"]
    assert "자곡로" in out["final_answer"]                 # 도구가 준 도로만


def test_e2e_outside_seoul_suggests_alternative(app):
    out = run_one(app, "부산 해운대 벚꽃길 추천해줘")
    assert out["verdict"] == "outside_seoul" and "hits" not in out
    assert "서울에서" in out["final_answer"] and "봄 벚꽃길" in out["final_answer"]


def test_e2e_superlative_uses_top_only(app):
    out = run_one(app, "서울에서 가장 큰 벚꽃길")
    assert out["superlative"] is True and len(out["hits"]["streets"]) == 1
    assert out["hits"]["focus"]["primary"]["노선"] == out["hits"]["streets"][0]["노선"]


def test_e2e_unknown_intent_skips_tools(app):
    out = run_one(app, "오늘 날씨 어때?")
    assert out["verdict"] == "unknown_intent" and "hits" not in out
    assert out["resolver_mode"] == "refuse" and "researcher" not in out["visited"]


def test_e2e_no_data(app, monkeypatch):
    # 도구가 빈 결과를 주는 상황을 강제 — 라우터가 no_data를 resolver로 넘기는지
    import types
    monkeypatch.setattr(G, "find_theme_streets", types.SimpleNamespace(
        invoke=lambda args: {"ok": False, "reason": "테스트: 데이터 없음"}))
    out = run_one(app, "강남구 벚꽃길")
    assert out["verdict"] == "no_data" and "데이터 없음" in out["final_answer"]


def test_e2e_fence_terminates(monkeypatch):
    """resolver가 final_answer를 못 채우는 결함이 있어도 울타리로 끝난다."""
    monkeypatch.setattr(G, "resolver_node", lambda s: {"visited": ["resolver"]})
    monkeypatch.setattr(G, "route_from_supervisor",
                        lambda s: "FINISH" if s.get("visited", []).count("supervisor") >= MAX_HOPS
                        else "researcher")
    app = build_graph()
    out = app.invoke({"question": "x", "season": "autumn", "theme": "벚꽃", "visited": []})
    assert out["visited"].count("supervisor") == MAX_HOPS and "final_answer" not in out
