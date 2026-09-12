"""LLM tool-calling 에이전트용 도구 레지스트리 + 슬림 컴팩터.

graph.py의 에이전트 경로(agent_node/tool_exec_node)가 쓴다. 규칙 경로는 tools.TOOLS를 그대로 쓴다.

- `AGENT_TOOLS`  : 에이전트에 bind_tools 할 도구(최대 5개, optional 임포트 흡수).
- `compact()`    : 도구 결과 dict → LLM ToolMessage용 슬림 문자열. **좌표 배열(center/focus/
                   bbox/corridor.line/routes[].path)은 절대 넣지 않는다** — 토큰 폭증·불필요.
- `adopt_results`: 이번 라운드 도구 결과들을 RouteState 패치(hits/place_hits/district/verdict)로.
                   hits 우선순위 route_plan/route > find_theme_streets, 그 안에서 마지막 ok.

`_compact_hits`는 여기(에이전트 경로)와 graph.resolver(최종 답변 그라운딩)가 공유한다 —
graph.py가 여기서 import 한다(순환 없음: 이 모듈은 graph를 import 하지 않는다).
"""
from tools import check_coverage, find_theme_streets, route_theme_streets

try:                       # 벡터DB 검색(DP15). 없으면 에이전트 도구 목록에서 빠진다
    from rag import search_places
except Exception:          # noqa: BLE001
    search_places = None

try:                       # 도로망 경로(DP17). osmnx 산출물 없어도 도구 목록에서만 빠짐
    from routing import plan_route
except Exception:          # noqa: BLE001
    plan_route = None


# 에이전트에 노출할 도구(면). None(임포트 실패)은 제외.
AGENT_TOOLS = [t for t in (find_theme_streets, route_theme_streets, check_coverage,
                           search_places, plan_route) if t is not None]


def _compact_hits(hits: dict, place_line: str = "") -> str:
    """LLM에는 도로명·그루수만 간결히 전달(좌표 center/focus/bbox는 UI 전용이라 제외)."""
    lines = "\n".join(f"  - {s['구']} {s['노선']}: {s['그루수']}그루" for s in hits.get("streets", []))
    if hits.get("kind") == "route_plan":
        rows = []
        for r in hits.get("routes", []):
            extra = ""
            if r.get("theme"):
                extra = (f" / {r['theme']} {r.get('theme_trees', 0)}그루"
                         f"(최단으로 가면 {r.get('base_trees', 0)}그루)")
            rows.append(f"  - [{r['label']}] {r['distance_m']}m 걸어서 약 {r.get('minutes', 0)}분, "
                        f"가장 빠른 길 대비 +{r['detour_pct']}%, 큰길 아닌 길 "
                        f"{round(r.get('walk_share', 0) * 100)}%"
                        f"{extra} / 지나는 길: {', '.join(r.get('streets', [])) or '이름 없는 길'}")
        return (f"{place_line}경로={hits.get('origin_name', '')}→{hits.get('dest_name', '')} "
                f"계절={hits.get('season', '')}\n비고={hits.get('note', '')}\n대안 {len(rows)}가지:\n"
                + "\n".join(rows))
    if hits.get("kind") == "route":
        # 출발/도착 자치구는 지오코딩이 준 값만 밝힌다(추측 금지 — 환각 방지, 롯데타워→용산구 이슈)
        od = ""
        if hits.get("origin_district") or hits.get("dest_district"):
            od = (f"출발={hits['origin']}({hits.get('origin_district') or '구 미상'}) "
                  f"도착={hits['dest']}({hits.get('dest_district') or '구 미상'})\n")
        return (f"{place_line}{od}경로={hits['origin']}→{hits['dest']} 테마={hits['theme']} "
                f"방식={hits['mode']} 계절={hits['season']} 회랑±{hits.get('width_m', 500)}m "
                f"총={hits['total_trees']}그루\n비고={hits['note']}\n경유 도로:\n{lines}")
    return (f"{place_line}테마={hits['theme']} 방식={hits['mode']} 계절={hits['season']} "
            f"지역={hits['district']} 총={hits['total_trees']}그루\n비고={hits['note']}\n도로:\n{lines}")


def _compact_search(res: dict) -> str:
    if not res.get("ok") or not res.get("results"):
        return f"장소검색 결과 없음: {res.get('reason', '')}"
    rows = "\n".join(
        f"  - {r['구']} {r['노선']}: {r['그루수']}그루 (테마: {', '.join(r.get('themes', [])) or '-'})"
        for r in res["results"][:5])
    return f"장소검색 후보(유사도순):\n{rows}"


def _compact_coverage(res: dict) -> str:
    if res.get("district"):
        return f"{res['district']} 데이터 {'있음' if res.get('covered') else '없음'}"
    return f"지원 자치구 {res.get('count')}개"


_COMPACTORS = {
    "find_theme_streets": lambda r: _compact_hits(r) if r.get("ok") else f"결과 없음: {r.get('reason', '')}",
    "route_theme_streets": lambda r: _compact_hits(r) if r.get("ok") else f"경로 결과 없음: {r.get('reason', '')}",
    "plan_route": lambda r: _compact_hits(r) if r.get("ok") else f"경로 탐색 실패: {r.get('reason', '')}",
    "search_places": _compact_search,
    "check_coverage": _compact_coverage,
}


def compact(tool_name: str, result: dict) -> str:
    """도구 결과 → LLM ToolMessage용 슬림 문자열(좌표 제외). 예외는 안전하게 문자열화."""
    fn = _COMPACTORS.get(tool_name)
    if fn is None:
        return str(result)[:400]
    try:
        return fn(result)
    except Exception:  # noqa: BLE001 — 컴팩터 실패가 그래프를 죽이지 않게
        return str(result)[:400]


_HITS_TOOLS = ("find_theme_streets", "route_theme_streets", "plan_route")
_KIND_RANK = {"route_plan": 2, "route": 1}       # 경로 결과를 단일 지역 조회보다 우선


def adopt_results(results: list[tuple[str, dict]], state: dict) -> dict:
    """이번 라운드 도구 결과들을 RouteState 패치로 반영.

    - hits: `_HITS_TOOLS` 결과 중 우선순위(route_plan/route>단일) 상, 동급이면 마지막 ok.
      좌표 포함 **full** 그대로 저장(UI 지도용). verdict=match/no_data.
    - search_places: place_hits + (district 미정 시) 1등 후보 구. (places_node와 같은 해소.)
    """
    patch: dict = {}
    best, best_rank = None, -1
    for name, res in results:
        if name in _HITS_TOOLS:
            rank = _KIND_RANK.get(res.get("kind"), 0)
            if res.get("ok") and rank >= best_rank:
                best, best_rank = res, rank
            elif best is None:                    # ok 없으면 마지막 실패라도 사유 전달용
                best = res
    if best is not None:
        # 이미 성공 hits가 있으면 나중 라운드의 실패로 덮어쓰지 않는다(예: route 성공 뒤 plan_route 실패).
        prev = state.get("hits") or {}
        if best.get("ok") or not prev.get("ok"):
            patch["hits"] = best
            patch["verdict"] = "match" if best.get("ok") else "no_data"
    for name, res in results:
        if name == "search_places" and res.get("ok") and res.get("results"):
            hits3 = res["results"][:3]
            patch["place_hits"] = hits3
            if not state.get("district") and not patch.get("district"):
                patch["district"] = hits3[0]["구"]
    return patch
