"""경로 3가지(최단·테마 경유·회피) — 인공 도로망으로 가중치 계산을 직접 검증.

진짜 OSM 도로망(data/osm/)은 5분짜리 다운로드 산출물이라 gitignore다. 테스트가 그걸 요구하면
새 clone·CI에서 못 돈다. 그래서 갈래가 둘인 작은 도로망을 tmp에 만들어 **라우팅 코드 그대로**
돌린다 — 어느 갈래를 고르는지가 곧 가중치가 맞는지다.

    n1 ── 위쪽 갈래: 짧고(1,000m) 나무 없음, 은행나무만 있음
   ╱  ╲
 n0    n2
   ╲  ╱
    n3 ── 아래쪽 갈래: 길지만(1,300m) 벚나무 빽빽
"""
import pytest

import routing as R

N = {0: (37.500, 127.000), 1: (37.505, 127.005), 2: (37.500, 127.010), 3: (37.495, 127.005)}
TOP, BOTTOM = 500.0, 650.0          # 갈래 한 구간의 길이(m). 위 1,000m vs 아래 1,300m


def _by_kind(res):
    return {r["kind"]: r for r in res["routes"]}


# ── 계절이 어떤 3가지를 내는지 (순수 함수) ──────────────────────────────────
def test_route_plan_for_season():
    assert R.route_plan_for("autumn") == [("shortest", ""), ("theme", "은행단풍"), ("avoid", "은행회피")]
    spring = R.route_plan_for("spring")
    assert spring[0] == ("shortest", "") and spring[1] == ("theme", "벚꽃")
    # 회피 테마가 없는 계절은 추천 테마를 하나 더 — '피하는 길'을 억지로 만들지 않는다
    assert all(kind != "avoid" for kind, _ in spring)
    assert all(len(R.route_plan_for(s)) <= 3 for s in ("spring", "summer", "autumn", "winter"))


def test_osm_status_reports_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "OSM_DIR", tmp_path / "없음")
    st = R.osm_status()
    assert st["ready"] is False and len(st["missing"]) == 3 and "scripts/04" in st["hint"]
    assert R.plan_route.invoke({"origin": "강남구", "dest": "송파구"})["ok"] is False


# ── 가중치가 실제로 갈래를 바꾸는가 ─────────────────────────────────────────
def test_shortest_takes_the_short_branch(osm_net):
    res = R.plan_routes(N[0], N[2], plans=[("shortest", "")])
    assert res["ok"]
    r = res["routes"][0]
    assert r["distance_m"] == int(2 * TOP) and r["streets"] == ["윗길"]
    assert r["detour_pct"] == 0 and r["path"][0] == [37.5, 127.0]


def test_theme_route_detours_through_the_trees(osm_net):
    res = R.plan_routes(N[0], N[2], plans=[("shortest", ""), ("theme", "벚꽃")])
    got = _by_kind(res)
    assert got["shortest"]["streets"] == ["윗길"]
    # 벚나무가 가득한 아래 갈래는 30% 더 길지만 체감 길이가 싸서 고른다
    assert got["theme"]["streets"] == ["아랫길"]
    assert got["theme"]["distance_m"] == int(2 * BOTTOM)
    assert got["theme"]["detour_pct"] == 30
    assert got["theme"]["theme_trees"] > 100 and got["theme"]["base_trees"] == 0
    assert "벚꽃" in got["theme"]["label"] or "벚꽃길" in got["theme"]["label"]


def test_avoid_route_goes_around_the_ginkgo(osm_net):
    res = R.plan_routes(N[0], N[2], plans=[("shortest", ""), ("avoid", "은행회피")])
    got = _by_kind(res)
    assert got["shortest"]["streets"] == ["윗길"]          # 최단은 은행나무 길
    assert got["avoid"]["streets"] == ["아랫길"]           # 회피는 돌아서 간다
    assert got["avoid"]["theme_trees"] == 0 and got["avoid"]["base_trees"] > 100


def test_too_long_detour_is_dropped(osm_net):
    """벚꽃을 지나려고 세 배를 걷는 건 추천이 아니다 — max_detour 밖이면 내놓지 않는다."""
    res = R.plan_routes(N[0], N[2], plans=[("shortest", ""), ("theme", "벚꽃")], max_detour=1.1)
    assert [r["kind"] for r in res["routes"]] == ["shortest"]


def test_three_routes_at_once_by_season(osm_net):
    res = R.plan_routes(N[0], N[2], season="autumn")
    kinds = [r["kind"] for r in res["routes"]]
    assert kinds[0] == "shortest" and "avoid" in kinds
    assert all(r["path"] and r["distance_m"] > 0 for r in res["routes"])
    assert res["season"] == "autumn" and "근사" in res["note"]


def test_same_point_and_unreachable_are_honest(osm_net):
    assert R.plan_routes(N[0], N[0])["ok"] is False
    far = R.plan_routes(N[0], (37.4, 126.8))          # 인공망 밖 — 가장 가까운 노드로 붙는다
    assert far["ok"] in (True, False)                  # 붙어서 풀리든 못 풀든 예외는 안 난다


# ── 지점 해소 ───────────────────────────────────────────────────────────────
def test_resolve_point_accepts_coords_and_district():
    pt, name = R.resolve_point("37.5,127.0")
    assert pt == (37.5, 127.0) and name == "37.5,127.0"
    pt, name = R.resolve_point("강남구")
    assert pt is not None and 37 < pt[0] < 38 and name == "강남구"
    assert R.resolve_point("")[0] is None
    assert R.resolve_point("없는곳12345")[0] is None


def test_resolve_point_uses_vector_search_for_places(rag_index):
    pt, name = R.resolve_point("석촌호수")
    assert pt is not None and "송파구" in name
