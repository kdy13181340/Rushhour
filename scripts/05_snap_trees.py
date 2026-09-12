"""가로수 28만 그루를 OSM 보행망 간선에 붙여 '간선별 테마 점수'를 만든다.  [DECISIONS DP17]

경로 추천의 가중치 재료다. 간선마다 "이 길에 벚꽃이 몇 그루 있나"를 세어 두면, 라우팅은
가중치만 바꿔 세 번 풀면 된다(app/routing.py).

방법: 간선 geometry를 일정 간격으로 표본화해 cKDTree를 만들고, 나무마다 가장 가까운 표본점을
찾아 SNAP_M 안이면 그 간선의 나무로 센다. 방향이 다른 두 행(u→v, v→u)은 같은 길이므로
무방향 키로 세고 양쪽에 같은 수를 준다.

산출물: data/osm/seoul_walk_edge_trees.parquet  — a, b(무방향 키), 나무수 + 테마별 그루수

실행:  python scripts/05_snap_trees.py [--snap-m 20] [--sample-m 15]
"""

import argparse
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
OSM_DIR = ROOT / "data" / "osm"
TREES = ROOT / "data" / "processed" / "seoul_trees.parquet"
OUT = OSM_DIR / "seoul_walk_edge_trees.parquet"

SNAP_M = 20.0      # 이보다 먼 나무는 그 간선의 것이 아니다(보도 폭·GPS 오차 고려)
SAMPLE_M = 15.0    # 간선 위 표본점 간격. SNAP_M보다 촘촘해야 중간이 새지 않는다


def _sample_edges(edges: pd.DataFrame, step_m: float, ky: float, kx: float):
    """간선 geometry를 step_m 간격으로 표본화 → (표본점 km좌표, 간선 인덱스)."""
    pts, owner = [], []
    for i, (glat, glon) in enumerate(zip(edges["geom_lat"].to_numpy(), edges["geom_lon"].to_numpy())):
        la = np.asarray(glat, dtype=float)
        lo = np.asarray(glon, dtype=float)
        if len(la) < 2:
            pts.append(np.column_stack([la * ky, lo * kx]))
            owner.append(np.full(len(la), i))
            continue
        y, x = la * ky, lo * kx                                   # km 평면
        seg = np.hypot(np.diff(y), np.diff(x))
        for j in range(len(seg)):
            n = max(1, int(seg[j] * 1000 / step_m))
            t = np.linspace(0.0, 1.0, n, endpoint=False)
            pts.append(np.column_stack([y[j] + t * (y[j + 1] - y[j]), x[j] + t * (x[j + 1] - x[j])]))
            owner.append(np.full(n, i))
        pts.append(np.array([[y[-1], x[-1]]]))                    # 마지막 꼭짓점
        owner.append(np.array([i]))
    return np.vstack(pts), np.concatenate(owner)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap-m", type=float, default=SNAP_M)
    ap.add_argument("--sample-m", type=float, default=SAMPLE_M)
    args = ap.parse_args()

    from themes import THEMES

    t0 = time.time()
    edges = pd.read_parquet(OSM_DIR / "seoul_walk_edges.parquet")
    trees = pd.read_parquet(TREES, columns=["구", "노선", "수종", "경도", "위도"])
    print(f"간선 {len(edges):,} · 나무 {len(trees):,}")

    # 무방향 키로 접어 중복 계산을 없앤다 (u→v, v→u는 같은 길)
    a = np.minimum(edges["u"].to_numpy(), edges["v"].to_numpy())
    b = np.maximum(edges["u"].to_numpy(), edges["v"].to_numpy())
    edges = edges.assign(a=a, b=b)
    uniq = edges.drop_duplicates(subset=["a", "b"]).reset_index(drop=True)
    print(f"무방향 간선 {len(uniq):,}")

    lat0 = float(trees["위도"].mean())
    ky, kx = 111.32, 111.32 * math.cos(math.radians(lat0))        # 도 → km

    pts, owner = _sample_edges(uniq, args.sample_m, ky, kx)
    print(f"표본점 {len(pts):,} ({time.time()-t0:.0f}s) — KD트리 구축")
    tree_idx = cKDTree(pts)

    txy = np.column_stack([trees["위도"].to_numpy() * ky, trees["경도"].to_numpy() * kx])
    dist, near = tree_idx.query(txy, distance_upper_bound=args.snap_m / 1000.0, workers=-1)
    hit = np.isfinite(dist)
    edge_of_tree = np.where(hit, owner[np.clip(near, 0, len(owner) - 1)], -1)
    print(f"붙은 나무 {hit.sum():,}/{len(trees):,} ({hit.mean()*100:.1f}%) — {args.snap_m:.0f}m 안 "
          f"({time.time()-t0:.0f}s)")

    out = pd.DataFrame({"a": uniq["a"], "b": uniq["b"]})
    counts = np.bincount(edge_of_tree[hit], minlength=len(uniq))
    out["나무수"] = counts
    species = trees["수종"].to_numpy()
    for key, spec in THEMES.items():
        m = hit & np.isin(species, spec["species"])
        out[key] = np.bincount(edge_of_tree[m], minlength=len(uniq))
    # 그 간선에 가장 많은 (구, 노선) — 답변에서 '무슨 길'인지 말하고, 화면에 그 도로의 실제
    # 형상을 그릴 때 (구, 노선)으로 간선을 고르기 위해서다(DP20).
    named = pd.DataFrame({"e": edge_of_tree[hit], "구": trees["구"].to_numpy()[hit],
                          "노선": trees["노선"].to_numpy()[hit]}).dropna()
    top = (named.groupby(["e", "구", "노선"]).size().reset_index(name="n")
           .sort_values("n", ascending=False).drop_duplicates("e").set_index("e"))
    out["가로수구"] = pd.Series(out.index.map(top["구"])).fillna("").to_numpy()
    out["가로수노선"] = pd.Series(out.index.map(top["노선"])).fillna("").to_numpy()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    withtree = int((out["나무수"] > 0).sum())
    print(f"\n저장: {OUT}")
    print(f"나무가 붙은 간선 {withtree:,}/{len(out):,} ({withtree/len(out)*100:.1f}%)")
    for key in THEMES:
        c = out[key]
        print(f"  {key:8s} 간선 {int((c > 0).sum()):6,}  총 {int(c.sum()):7,}그루  "
              f"간선당 최대 {int(c.max())}")
    print(f"총 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
