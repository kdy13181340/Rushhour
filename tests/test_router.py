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


def test_rule_intake_route_extracts_origin_dest():
    r = rule_intake("강남구에서 송파구 가는 길 벚꽃", "spring")
    assert (r["origin"], r["dest"], r["theme"]) == ("강남구", "송파구", "벚꽃")
    # 경로 단서 없이 자치구 하나면 origin/dest 비움
    assert rule_intake("강남구 벚꽃길", "spring")["origin"] == ""


def test_e2e_route_visits_route_node(app):
    out = run_one(app, "강남구에서 송파구 가는 길 벚꽃길")
    assert "route" in out["visited"] and out["hits"]["kind"] == "route"
    assert out["origin"] == "강남구" and out["dest"] == "송파구"
    assert "강남구" in out["final_answer"] and "송파구" in out["final_answer"]


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


def test_e2e_tool_exception_falls_back_to_no_data(app, monkeypatch):
    """도구가 예외를 던져도 그래프는 죽지 않고 no_data로 안내한다(BE_DESIGN §3 폴백 ③)."""
    import types

    def boom(args):
        raise RuntimeError("테스트: 데이터 파일 손상")
    monkeypatch.setattr(G, "find_theme_streets", types.SimpleNamespace(invoke=boom))
    out = run_one(app, "강남구 벚꽃길")
    assert out["verdict"] == "no_data" and out["hits"]["tool_error"] == "RuntimeError"
    assert out["resolver_mode"] == "refuse" and "RuntimeError" in out["final_answer"]


# ── 멀티턴: 체크포인터가 있을 때 같은 thread의 다음 질문 (DP13) ─────────────
def test_visited_reducer_accumulates_and_resets():
    assert G._add_or_reset(["a"], ["b"]) == ["a", "b"]
    assert G._add_or_reset(["a", "b"], None) == []
    assert G._add_or_reset(None, ["a"]) == ["a"]


def test_new_turn_input_covers_all_state_keys():
    """RouteState에 턴 단위 필드를 추가하면 new_turn_input에도 넣어야 한다."""
    keys = set(G.RouteState.__annotations__) - {"question"}
    assert keys <= set(G.new_turn_input("q")), keys - set(G.new_turn_input("q"))


def test_new_turn_input_resets_thread_state():
    """체크포인터가 있을 때 같은 thread의 두 번째 질문이 season부터 다시 돈다."""
    from langgraph.checkpoint.memory import InMemorySaver
    app = build_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}
    a = app.invoke(G.new_turn_input("강남구에서 봄에 벚꽃 예쁜 길"), config=cfg)
    b = app.invoke(G.new_turn_input("서초구 여름 그늘길"), config=cfg)
    assert (a["theme"], a["district"], a["season"]) == ("벚꽃", "강남구", "spring")
    assert (b["theme"], b["district"], b["season"]) == ("그늘", "서초구", "summer")
    assert b["visited"].count("supervisor") == 4          # 턴마다 hops가 쌓이지 않음
    # 리셋 없이 question만 바꾸면 이전 턴이 그대로 남아 supervisor에서 바로 끝난다 —
    # 이 결함 때문에 new_turn_input이 있다.
    c = app.invoke({"question": "종로구 은행단풍", "visited": []}, config=cfg)
    assert c["theme"] == "그늘" and c["final_answer"] == b["final_answer"]
    assert c["visited"].count("supervisor") == 5


def test_new_turn_input_clears_route_fields():
    """경로 질문 다음의 일반 질문 — 이전 턴의 origin/dest가 남아 route로 가면 안 된다(DP13 × route 분기)."""
    from langgraph.checkpoint.memory import InMemorySaver
    app = build_graph(checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t-route"}}
    a = app.invoke(G.new_turn_input("강남구에서 송파구 가는 길 벚꽃길"), config=cfg)
    assert "route" in a["visited"] and (a["origin"], a["dest"]) == ("강남구", "송파구")
    b = app.invoke(G.new_turn_input("서초구 여름 그늘길"), config=cfg)
    assert "route" not in b["visited"] and b["origin"] == "" and b["hits"]["district"] == "서초구"


def test_e2e_route_tool_exception_falls_back_to_no_data(app, monkeypatch):
    import types

    def boom(args):
        raise RuntimeError("테스트: 경로 도구 실패")
    monkeypatch.setattr(G, "route_theme_streets", types.SimpleNamespace(invoke=boom))
    out = run_one(app, "강남구에서 송파구 가는 길 벚꽃길")
    assert out["verdict"] == "no_data" and out["hits"]["tool_error"] == "RuntimeError"


# ── places: 장소 표현 → 자치구 해소 (벡터DB, DP15) ─────────────────────────
def test_rule_intake_extracts_place_only_when_district_missing():
    assert rule_intake("양재천 근처 벚꽃길", "spring")["place"] == "양재천"
    assert rule_intake("대치동 산책길", "spring")["place"] == "대치동"
    # 자치구가 잡히면 장소는 비운다 — 해소할 게 없다
    assert rule_intake("강남구 벚꽃길", "spring")["place"] == ""
    # 서울 밖·경로 질문도 비운다(각자 다른 분기가 처리)
    assert rule_intake("부산 해운대 벚꽃길", "spring")["place"] == ""
    assert rule_intake("강남구에서 송파구 가는 길 벚꽃", "spring")["place"] == ""
    # 장소가 아닌 평범한 질문에 오탐이 없어야 한다
    for q in ("서울에서 가장 큰 벚꽃길", "오늘 날씨 어때?", "더운데 그늘진 길 없나", "지금 볼만한 길 있어?"):
        assert rule_intake(q, "spring")["place"] == "", q


def test_router_resolves_place_before_refusing():
    """테마를 못 잡아도 장소가 있으면 거절 전에 places를 거친다 — places가 살려낼 수 있다."""
    base = {"season": "spring", "theme": "unknown", "place": "대치동"}
    assert route_from_supervisor(base) == "places"
    # places가 한 번 다녀오면(place_hits 채워짐) 다시 가지 않는다
    assert route_from_supervisor({**base, "place_hits": []}) == "resolver"
    assert route_from_supervisor({**base, "place_hits": [{}], "theme": "벚꽃"}) == "researcher"
    # 자치구를 이미 알면 해소할 게 없다
    assert route_from_supervisor({**base, "theme": "벚꽃", "district": "강남구"}) == "researcher"
    # 서울 밖·커버리지 밖은 검색하지 않고 바로 안내
    assert route_from_supervisor({**base, "verdict": "outside_seoul"}) == "resolver"
    # 경로 질문은 route 분기가 가져간다
    assert route_from_supervisor({**base, "theme": "벚꽃", "origin": "강남구", "dest": "송파구"}) == "route"


def test_new_turn_input_clears_place_fields():
    keys = G.new_turn_input("q")
    assert keys["place"] == "" and keys["place_hits"] is None


def test_e2e_place_resolves_to_district(app, rag_index):
    """'양재천 근처 벚꽃길' — 전에는 자치구를 잃고 서울 전체를 뒤졌다."""
    out = run_one(app, "석촌호수 벚꽃 보고싶어")
    assert "places" in out["visited"] and out["place"] == "석촌호수"
    assert out["district"] == "송파구" and out["hits"]["district"] == "송파구"
    assert out["verdict"] == "match"
    assert "석촌호수" in out["final_answer"] and "송파구" in out["final_answer"]  # 해석을 밝힌다


def test_e2e_place_infers_theme_and_never_picks_avoid(app, rag_index):
    """테마 단서가 없는 '○○동 산책길'도 거절 대신 답한다. 단 '피하는 길'을 권하면 안 된다(DP5)."""
    out = run_one(app, "대치동 산책길 추천해줘")
    assert out["theme"] != "unknown" and out["verdict"] == "match"
    assert out["hits"]["mode"] == "prefer", out["theme"]      # avoid 테마를 '추천'으로 내밀지 않는다
    assert "researcher" in out["visited"]


def test_e2e_place_without_index_degrades_gracefully(app, monkeypatch, tmp_path):
    """인덱스가 없어도 그래프는 죽지 않는다 — 장소만 못 살리고 서울 전체로 답한다."""
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "없는인덱스"))
    out = run_one(app, "석촌호수 벚꽃 보고싶어")
    assert out["place_hits"] == [] and out["district"] == ""
    assert out["verdict"] == "match" and out["hits"]["district"] == "서울 전체"
    assert "석촌호수" not in out["final_answer"]              # 해소 못 했으면 해석을 말하지 않는다


def test_e2e_place_search_exception_falls_back(app, monkeypatch, rag_index):
    import types

    def boom(args):
        raise RuntimeError("테스트: 임베딩 서버 다운")
    monkeypatch.setattr(G, "search_places", types.SimpleNamespace(invoke=boom))
    out = run_one(app, "석촌호수 벚꽃 보고싶어")
    assert out["place_hits"] == [] and out["verdict"] == "match"   # 검색만 실패, 답변은 나온다


def test_e2e_fence_terminates(monkeypatch):
    """resolver가 final_answer를 못 채우는 결함이 있어도 울타리로 끝난다."""
    monkeypatch.setattr(G, "resolver_node", lambda s: {"visited": ["resolver"]})
    monkeypatch.setattr(G, "route_from_supervisor",
                        lambda s: "FINISH" if s.get("visited", []).count("supervisor") >= MAX_HOPS
                        else "researcher")
    app = build_graph()
    out = app.invoke({"question": "x", "season": "autumn", "theme": "벚꽃", "visited": []})
    assert out["visited"].count("supervisor") == MAX_HOPS and "final_answer" not in out
