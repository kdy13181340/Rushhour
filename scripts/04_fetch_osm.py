"""서울 보행 도로망(OSM) 1회 내려받기 → Parquet.  [BE_DESIGN C7 plan_route · DECISIONS DP17]

경로 추천(출발→도착)은 진짜 도로망이 있어야 한다. 가로수 데이터만으로 노선을 이어 붙여
보면 300m로 느슨하게 이어도 최대 연결요소가 전체의 51%뿐이라 임의의 두 지점을 잇지 못한다
(가로수가 있는 길만으로는 도시가 연결되지 않음). 그래서 OSM 보행망을 쓴다.

산출물(data/osm/, gitignore — 재생성 가능):
  seoul_walk_nodes.parquet   node, 위도, 경도
  seoul_walk_edges.parquet   u, v, length_m, 도로명, geom_lat[], geom_lon[]   (양방향 1행씩)

GraphML 대신 Parquet으로 저장한다 — 서버 기동 때 빠르게 읽고, 라우팅은 scipy 희소행렬로 한다
(networkx 그래프를 통째로 들고 있을 이유가 없다).

실행:  python scripts/04_fetch_osm.py [--bbox 최소경도,최소위도,최대경도,최대위도] [--network walk|drive]
       기본 bbox는 가로수 데이터의 좌표 범위 + 여유 0.02도. 약 3분, osmnx 캐시가 남아 재실행은 빠름.
"""

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
TREES = ROOT / "data" / "processed" / "seoul_trees.parquet"
OUT_DIR = ROOT / "data" / "osm"
MARGIN = 0.02          # 가로수 좌표 범위 밖으로 둘 여유(도) — 경계 근처 출발·도착도 붙게


def tree_bbox() -> tuple[float, float, float, float]:
    """(최소경도, 최소위도, 최대경도, 최대위도) — 가로수 데이터가 실제로 덮는 범위 + 여유."""
    df = pd.read_parquet(TREES, columns=["경도", "위도"])
    return (float(df["경도"].min()) - MARGIN, float(df["위도"].min()) - MARGIN,
            float(df["경도"].max()) + MARGIN, float(df["위도"].max()) + MARGIN)


def to_frames(G) -> tuple[pd.DataFrame, pd.DataFrame]:
    """osmnx 그래프 → (노드, 간선) DataFrame. 간선 geometry는 좌표 배열 두 개로 편다."""
    nodes = pd.DataFrame(
        [{"node": n, "위도": d["y"], "경도": d["x"]} for n, d in G.nodes(data=True)])
    rows = []
    for u, v, d in G.edges(data=True):
        geom = d.get("geometry")
        if geom is not None:                       # simplify=True면 굽은 길에 LineString이 붙는다
            lon, lat = geom.xy
            gla, glo = list(lat), list(lon)
        else:                                      # 직선 간선은 양 끝점만
            gla = [G.nodes[u]["y"], G.nodes[v]["y"]]
            glo = [G.nodes[u]["x"], G.nodes[v]["x"]]
        name = d.get("name")
        if isinstance(name, list):                 # OSM은 이름이 여러 개일 수 있다
            name = name[0]
        rows.append({"u": u, "v": v, "length_m": float(d.get("length", 0.0)),
                     "도로명": str(name) if name else "", "geom_lat": gla, "geom_lon": glo})
    return nodes, pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bbox", help="최소경도,최소위도,최대경도,최대위도 (기본: 가로수 데이터 범위)")
    ap.add_argument("--network", default="walk", choices=["walk", "drive", "bike", "all"])
    args = ap.parse_args()

    import osmnx as ox
    ox.settings.use_cache = True                   # 재실행 시 Overpass를 다시 때리지 않는다
    ox.settings.log_console = False

    bbox = tuple(float(x) for x in args.bbox.split(",")) if args.bbox else tree_bbox()
    print(f"bbox(경도/위도) {bbox} · network={args.network}")
    t0 = time.time()
    G = ox.graph_from_bbox(bbox=bbox, network_type=args.network, simplify=True)
    print(f"내려받음: 노드 {G.number_of_nodes():,} 간선 {G.number_of_edges():,} ({time.time()-t0:.0f}s)")

    nodes, edges = to_frames(G)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    nodes.to_parquet(OUT_DIR / "seoul_walk_nodes.parquet", index=False)
    edges.to_parquet(OUT_DIR / "seoul_walk_edges.parquet", index=False)
    named = int((edges["도로명"] != "").sum())
    print(f"저장: {OUT_DIR}  노드 {len(nodes):,} / 간선 {len(edges):,} "
          f"(도로명 있는 간선 {named:,} = {named/len(edges)*100:.0f}%)")
    print(f"간선 길이 m: 중앙값 {edges['length_m'].median():.0f} · 총 {edges['length_m'].sum()/1000:,.0f}km")
    print(f"총 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
