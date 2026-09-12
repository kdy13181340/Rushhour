"""출발→도착 경로 3가지 — 최단 / 테마 경유 / 회피.  [BE_DESIGN C7 plan_route · DECISIONS DP17]

같은 도로망에서 **가중치만 바꿔** 최단경로를 세 번 푼다.
  최단     w = 길이
  테마 경유 w = 길이 × (1 − α·밀도)   벚꽃이 빽빽한 길은 싸 보이니 돌아가서라도 지난다
  회피     w = 길이 × (1 + β·밀도)   은행 암나무가 많은 길은 비싸 보이니 돌아서 간다
밀도 = 그 간선의 테마 그루수 ÷ (길이÷나무간격), 1에서 자른다. 가득 심긴 길이 1.0.

도로망은 OSM 보행망(scripts/04), 간선별 테마 그루수는 나무 스냅(scripts/05) 산출물을 쓴다.
가로수 데이터만으로 노선을 이어 붙이는 방법은 버렸다 — 300m로 느슨하게 이어도 최대 연결요소가
51%뿐이라 임의의 두 지점을 못 잇는다(DP17에 측정치).

  준비:  python scripts/04_fetch_osm.py && python scripts/05_snap_trees.py
  사용:  plan_routes("강남구", "송파구", season="autumn")
"""

import functools
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
from langchain_core.tools import tool

from themes import THEMES, themes_for_season

ROOT = Path(__file__).resolve().parents[1]
OSM_DIR = Path(os.environ.get("OSM_DIR", ROOT / "data" / "osm"))

ALPHA = 0.55          # 테마 경유: 가득 심긴 길의 체감 길이를 45%로. 최대 우회 배수 ≈ 1/(1−α) ≈ 2.2
BETA = 2.0            # 회피: 가득 심긴 길의 체감 길이를 3배로
SPACING_M = 8.0       # 가로수 간격 — 밀도 1.0의 기준
MAX_DETOUR = 2.2      # 최단 대비 이 배수를 넘으면 그 대안은 내놓지 않는다(너무 돌아감)
MAX_STREETS = 6       # 답변·카드에 적을 도로 이름 수


def _osm_files() -> tuple[Path, Path, Path]:
    return (OSM_DIR / "seoul_walk_nodes.parquet", OSM_DIR / "seoul_walk_edges.parquet",
            OSM_DIR / "seoul_walk_edge_trees.parquet")


def osm_ready() -> bool:
    return all(p.exists() for p in _osm_files())


def osm_status() -> dict:
    """헬스체크용 — 도로망 산출물이 있는지, 얼마나 큰지(그래프는 로드하지 않음)."""
    nodes, edges, trees = _osm_files()
    if not osm_ready():
        missing = [p.name for p in _osm_files() if not p.exists()]
        return {"ready": False, "missing": missing, "dir": str(OSM_DIR),
                "hint": "python scripts/04_fetch_osm.py && python scripts/05_snap_trees.py"}
    return {"ready": True, "dir": str(OSM_DIR),
            "nodes_mb": round(nodes.stat().st_size / 1e6, 1),
            "edges_mb": round(edges.stat().st_size / 1e6, 1)}


@functools.lru_cache(maxsize=1)
def _graph():
    """도로망을 한 번만 읽어 희소행렬 뼈대로 만든다. 가중치 배열만 갈아 끼워 재사용한다.

    반환: dict(n, node_lat/lon, kd, ui, vi, length, bonus{테마: 배열}, geom, name, index)
    """
    from scipy.spatial import cKDTree
    nodes_p, edges_p, trees_p = _osm_files()
    if not osm_ready():
        raise FileNotFoundError(
            f"도로망 없음: {OSM_DIR} — python scripts/04_fetch_osm.py && python scripts/05_snap_trees.py")

    nodes = pd.read_parquet(nodes_p)
    edges = pd.read_parquet(edges_p)
    etrees = pd.read_parquet(trees_p)

    idx = pd.Series(np.arange(len(nodes)), index=nodes["node"].to_numpy())
    edges = edges.assign(a=np.minimum(edges["u"], edges["v"]), b=np.maximum(edges["u"], edges["v"]))
    edges = edges.merge(etrees, on=["a", "b"], how="left")
    for key in THEMES:
        edges[key] = edges[key].fillna(0).to_numpy()
    edges["가로수노선"] = edges["가로수노선"].fillna("")

    ui = idx.reindex(edges["u"].to_numpy()).to_numpy()
    vi = idx.reindex(edges["v"].to_numpy()).to_numpy()
    ok = np.isfinite(ui) & np.isfinite(vi)
    edges, ui, vi = edges[ok].reset_index(drop=True), ui[ok].astype(np.int64), vi[ok].astype(np.int64)

    length = np.maximum(edges["length_m"].to_numpy(dtype=float), 1.0)
    cap = np.maximum(length / SPACING_M, 1.0)                  # 그 길이에 심을 수 있는 그루 수
    bonus = {k: np.clip(edges[k].to_numpy(dtype=float) / cap, 0.0, 1.0) for k in THEMES}
    trees_on = {k: edges[k].to_numpy(dtype=float) for k in THEMES}

    # 같은 (u,v)가 여러 번 있으면(평행 간선) 가장 짧은 것만 남긴다 — 희소행렬은 중복을 더해버린다
    order = np.lexsort((length, vi, ui))
    keep = np.ones(len(order), dtype=bool)
    su, sv = ui[order], vi[order]
    keep[1:] = (su[1:] != su[:-1]) | (sv[1:] != sv[:-1])
    sel = order[keep]

    name = np.where(edges["가로수노선"].to_numpy() != "", edges["가로수노선"].to_numpy(),
                    edges["도로명"].to_numpy())
    return {
        "n": len(nodes),
        "lat": nodes["위도"].to_numpy(), "lon": nodes["경도"].to_numpy(),
        "kd": cKDTree(np.column_stack([nodes["위도"].to_numpy() * 111.32,
                                       nodes["경도"].to_numpy() * 111.32
                                       * math.cos(math.radians(float(nodes["위도"].mean())))])),
        "ui": ui[sel], "vi": vi[sel], "length": length[sel],
        "bonus": {k: v[sel] for k, v in bonus.items()},
        "trees": {k: v[sel] for k, v in trees_on.items()},
        "geom_lat": edges["geom_lat"].to_numpy()[sel], "geom_lon": edges["geom_lon"].to_numpy()[sel],
        "name": name[sel],
        # (u,v) → 간선 행 번호. 경로를 되짚어 형상·나무수를 모을 때 쓴다
        "row": {(int(a), int(b)): i for i, (a, b) in enumerate(zip(ui[sel], vi[sel]))},
    }


def _weights(g: dict, kind: str, theme: str) -> np.ndarray:
    if kind == "theme":
        return g["length"] * (1.0 - ALPHA * g["bonus"][theme])
    if kind == "avoid":
        return g["length"] * (1.0 + BETA * g["bonus"][theme])
    return g["length"]


def _solve(g: dict, w: np.ndarray, src: int, dst: int) -> list[int] | None:
    """가중치 w로 src→dst 최단경로의 노드 번호 목록. 못 가면 None."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra
    m = csr_matrix((w, (g["ui"], g["vi"])), shape=(g["n"], g["n"]))
    _, pred = dijkstra(m, directed=True, indices=src, return_predecessors=True)
    if pred[dst] == -9999 and src != dst:
        return None
    path, cur = [dst], dst
    while cur != src:
        cur = int(pred[cur])
        if cur < 0:
            return None
        path.append(cur)
    return path[::-1]


def _describe(g: dict, path: list[int]) -> dict:
    """경로 노드열 → 실제 거리·형상·지나는 도로 이름·테마별 그루수."""
    rows = [g["row"].get((path[i], path[i + 1])) for i in range(len(path) - 1)]
    rows = [r for r in rows if r is not None]
    dist = float(g["length"][rows].sum()) if rows else 0.0
    trees = {k: int(g["trees"][k][rows].sum()) for k in THEMES} if rows else {k: 0 for k in THEMES}
    # 지나는 도로: 이름별 길이를 더해 긴 순서로
    by_name: dict[str, float] = {}
    for r in rows:
        nm = str(g["name"][r])
        if nm:
            by_name[nm] = by_name.get(nm, 0.0) + float(g["length"][r])
    streets = [n for n, _ in sorted(by_name.items(), key=lambda kv: -kv[1])[:MAX_STREETS]]
    coords: list[list[float]] = []
    for r in rows:
        la, lo = g["geom_lat"][r], g["geom_lon"][r]
        for y, x in zip(la, lo):
            p = [round(float(y), 6), round(float(x), 6)]
            if not coords or coords[-1] != p:
                coords.append(p)
    return {"distance_m": int(round(dist)), "streets": streets, "trees": trees, "path": coords}


def route_plan_for(season: str) -> list[tuple[str, str]]:
    """그 계절에 내놓을 3가지 — (종류, 테마). 순서가 곧 정책이다(DP5와 같은 규칙).

    가을: 최단 · 은행단풍 경유 · 은행회피.  봄: 최단 · 벚꽃 경유 · 이팝 경유.
    """
    season_themes = themes_for_season(season)
    prefer = [t for t in season_themes if THEMES[t]["mode"] == "prefer"]
    avoid = [t for t in season_themes if THEMES[t]["mode"] == "avoid"]
    plans: list[tuple[str, str]] = [("shortest", "")]
    if prefer:
        plans.append(("theme", prefer[0]))
    if avoid:
        plans.append(("avoid", avoid[0]))
    elif len(prefer) > 1:
        plans.append(("theme", prefer[1]))
    return plans[:3]


LABEL = {"shortest": "최단 경로", "theme": "{label} 지나는 길", "avoid": "{label} 피해 가는 길"}


def plan_routes(origin: tuple[float, float], dest: tuple[float, float], season: str = "",
                plans: list[tuple[str, str]] | None = None, max_detour: float = MAX_DETOUR) -> dict:
    """출발·도착 좌표 → 경로 대안 목록. 좌표는 (위도, 경도).

    최단 경로는 항상 첫 번째다. 테마 대안이 최단보다 max_detour 배 넘게 길면 내놓지 않는다 —
    '벚꽃을 지나려고 세 배를 걷는' 추천은 추천이 아니다.
    """
    g = _graph()
    plans = plans or route_plan_for(season)
    (oy, ox_), (dy, dx) = origin, dest
    scale = 111.32 * math.cos(math.radians(float(g["lat"].mean())))
    _, src = g["kd"].query([oy * 111.32, ox_ * scale])
    _, dst = g["kd"].query([dy * 111.32, dx * scale])
    src, dst = int(src), int(dst)
    if src == dst:
        return {"ok": False, "reason": "출발지와 도착지가 같은 지점으로 잡힘 — 더 떨어진 곳으로"}

    base = _solve(g, _weights(g, "shortest", ""), src, dst)
    if base is None:
        return {"ok": False, "reason": "도로망에서 두 지점을 잇는 보행 경로를 찾지 못함"}
    base_info = _describe(g, base)
    out = []
    for kind, theme in plans:
        info = base_info if kind == "shortest" else None
        if info is None:
            p = _solve(g, _weights(g, kind, theme), src, dst)
            if p is None:
                continue
            info = _describe(g, p)
        detour = info["distance_m"] / max(base_info["distance_m"], 1)
        if kind != "shortest" and detour > max_detour:
            continue
        # 약속을 못 지키는 대안은 빼고 준다. '벚꽃길'이라면서 벚꽃 0그루를 최단과 같은 길로
        # 안내하면 선택지가 아니라 잡음이다. 실제로 더 지나거나(theme) 덜 지나야(avoid) 한다.
        if theme:
            got, base_n = info["trees"][theme], base_info["trees"][theme]
            if (kind == "theme" and got <= base_n) or (kind == "avoid" and got >= base_n):
                continue
        spec = THEMES.get(theme, {})
        item = {
            "kind": kind, "theme": theme,
            "label": LABEL[kind].format(label=spec.get("label", theme)),
            "distance_m": info["distance_m"],
            "detour_pct": int(round((detour - 1) * 100)),
            "streets": info["streets"], "path": info["path"],
        }
        if theme:
            item["theme_trees"] = info["trees"][theme]
            item["base_trees"] = base_info["trees"][theme]      # 최단으로 갔을 때와 비교
            item["note"] = spec.get("note", "")
        out.append(item)
    return {"ok": bool(out), "kind": "route_plan",
            "origin": [round(oy, 6), round(ox_, 6)], "dest": [round(dy, 6), round(dx, 6)],
            "season": season, "routes": out,
            "note": "OSM 보행망 위 최단경로. 가로수 그루수는 도로망 간선에 20m 안으로 붙인 값이라 근사임."}


# ── 지점 해소 ────────────────────────────────────────────────────────────────
def _looks_like(query: str, hit: dict, n: int = 2) -> bool:
    """검색 1등이 정말 그 장소인가 — 질의와 후보 이름이 글자 n-gram을 하나라도 공유하는가.

    벡터 검색은 무슨 말을 넣어도 '가장 가까운 것'을 돌려준다. 출발지·도착지에서는 그게 위험하다
    ('없는곳12345'가 조용히 엉뚱한 도로로 해소되면 경로 전체가 거짓이 된다). 유사도 임계값은
    채널마다 분포가 달라(DP14) 쓰지 않고, 표기가 겹치는지만 본다 — 채널과 무관하고 설명 가능하다.
    """
    q = "".join(query.split()).lower()
    cand = ("".join([hit.get("구", ""), hit.get("노선", ""), *hit.get("동", [])])).lower()
    if len(q) < n or len(cand) < n:
        return False
    grams = {q[i:i + n] for i in range(len(q) - n + 1)}
    return any(cand[i:i + n] in grams for i in range(len(cand) - n + 1))


def resolve_point(text: str) -> tuple[tuple[float, float] | None, str]:
    """출발·도착 문자열 → ((위도, 경도), 표시이름). 못 알아들으면 (None, '').

    받는 것: 'lat,lon' · 자치구명('강남구') · 장소 이름('양재천'·'대치동') — 장소는 벡터DB로
    해소한다(DP15의 search_places 재사용). 지어낸 좌표는 만들지 않는다.
    """
    s = (text or "").strip()
    if not s:
        return None, ""
    if "," in s:
        try:
            la, lo = (float(x) for x in s.split(",")[:2])
            return (la, lo), s
        except ValueError:
            pass
    from tools import available_districts, district_centroid
    if s in available_districts():
        return district_centroid(s), s
    try:
        from rag import search_places
        res = search_places.invoke({"query": s, "k": 1})
        if res.get("ok") and res.get("results"):
            top = res["results"][0]
            if _looks_like(s, top):
                return tuple(top["center"]), f"{top['구']} {top['노선']}"
    except Exception:  # noqa: BLE001 — 인덱스·임베딩 서버가 없으면 장소 해소만 포기
        pass
    return None, ""


@tool
def plan_route(origin: str, dest: str, season: str = "", theme: str = "") -> dict:
    """출발지에서 도착지까지 걸어가는 길을 **세 가지**로 제안한다.

    'A에서 B까지 가는데 벚꽃 보면서 갈래'·'은행 열매 밟기 싫어'처럼 이동이 목적인 질문에 쓴다.
    (route_theme_streets가 직선 회랑 주변 도로를 훑는 것과 달리, 실제 보행 도로망 위 경로다.)

    Args:
        origin: 출발지. 서울 자치구명('강남구') · 장소 이름('양재천','대치동') · 'lat,lon'.
        dest: 도착지. 형식은 origin과 같다.
        season: spring|summer|autumn|winter. 비우면 오늘 날짜. 계절이 어떤 3가지를 낼지 정한다 —
            가을이면 최단·은행단풍 경유·은행회피, 봄이면 최단·벚꽃 경유·이팝 경유.
        theme: 사용자가 테마를 콕 집었으면(예 '벚꽃'·'은행회피') 그 테마를 2번 대안으로 올린다.
            비우면 계절 기본. 최단 경로는 무엇을 주든 항상 첫 번째다.

    Returns:
        {ok, origin_name, dest_name, routes:[{kind, theme, label, distance_m, detour_pct,
         theme_trees, streets, path}], note}
        - kind: 'shortest'(거리만) | 'theme'(그 테마 나무를 지나도록 돌아감) | 'avoid'(피해 감)
        - path: [[위도, 경도], ...] 지도에 그릴 선. 최단보다 2.2배 넘게 긴 대안은 빼고 준다.
        - 도로망이 준비 안 됐으면 ok=False와 준비 명령을 돌려준다.
    """
    if not osm_ready():
        st = osm_status()
        return {"ok": False, "reason": f"도로망 준비 안 됨(없는 파일: {', '.join(st['missing'])})",
                "hint": st["hint"]}
    o, o_name = resolve_point(origin)
    d, d_name = resolve_point(dest)
    if o is None or d is None:
        which = "출발지" if o is None else "도착지"
        return {"ok": False, "reason": f"{which}를 알아듣지 못함: "
                                       f"'{origin if o is None else dest}'. 자치구명·장소 이름·'위도,경도'로 주세요."}
    if not season:
        from datetime import date
        from themes import season_of
        season = os.environ.get("RUSHHOUR_SEASON", "").strip().lower() or season_of(date.today().month)
    plans = route_plan_for(season)
    if theme in THEMES:                        # 사용자 요청 테마를 2번으로, 나머지는 계절 기본에서
        kind = "avoid" if THEMES[theme]["mode"] == "avoid" else "theme"
        rest = [p for p in plans if p[0] != "shortest" and p[1] != theme]
        plans = [("shortest", ""), (kind, theme), *rest][:3]
    try:
        res = plan_routes(o, d, season=season, plans=plans)
    except FileNotFoundError as exc:
        return {"ok": False, "reason": str(exc)}
    res["origin_name"], res["dest_name"] = o_name, d_name
    return res
