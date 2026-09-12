"""경로 가중치 검증 — 세 대안이 '약속'을 지키는지 잰다.  [DECISIONS DP23]

검색과 달리 경로엔 정답이 없다. 대신 각 대안이 내건 약속을 지키는지를 잰다.

  빠른 도보 경로  거리만 볼 때보다 얼마나 더 걷고(walk_cost_pct), 큰길을 얼마나 덜 걷나(walk_share)
  테마 경유      최단보다 그 나무를 몇 배 더 지나나(gain), 그 대가로 몇 % 더 걷나(detour)
  회피          피할 나무를 몇 % 줄이나(cut), 그 대가로 몇 % 더 걷나

표본은 data/eval/route_pairs.jsonl — 도로망의 주거지 노드에서 씨앗 고정으로 무작위로 뽑은
80쌍(0.5~5km, 거리대별). 자치구 중심점끼리(5~15km)는 도보 앱의 실제 쓰임이 아니라서다.
손으로 고른 시연 구간에 계수를 맞추지 않기 위한 표본이다(DP18의 원칙).

실행:
  python scripts/06_eval_routes.py                      # 현재 계수
  python scripts/06_eval_routes.py --sweep walk         # 도보 계수 세기 비교
  python scripts/06_eval_routes.py --sweep alpha        # 테마 계수 비교
  python scripts/06_eval_routes.py --sweep beta         # 회피 계수 비교
  python scripts/06_eval_routes.py --season spring --verbose
"""

import argparse
import json
import statistics as st
import sys
import time
from pathlib import Path

import numpy as np

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
PAIRS = ROOT / "data" / "eval" / "route_pairs.jsonl"

# 미리 정한 합격선 — 결과를 보고 고치면 검증이 아니라 합리화가 된다(DP23)
GOAL = {
    "theme_gain": 2.0,        # 테마 경유는 최단보다 그 나무를 2배 이상 지날 것
    "theme_detour": 15.0,     # 그 대가는 중앙값 15% 이내
    "avoid_cut": 70.0,        # 회피는 피할 나무를 70% 이상 줄일 것
    "walk_share": 80.0,       # 모든 대안의 큰길 아닌 길 비율 80% 이상
    "kept": 80.0,             # 약속을 지켜 살아남는 대안이 80% 이상
}


def load_pairs() -> list[dict]:
    return [json.loads(ln) for ln in PAIRS.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _node(g, pt):
    import math
    scale = 111.32 * math.cos(math.radians(float(g["lat"].mean())))
    _, i = g["kd"].query([pt[0] * 111.32, pt[1] * scale])
    return int(i)


def _run(g, R, weights, src, dst):
    p = R._solve(g, weights, src, dst)
    return None if p is None else R._describe(g, p)


def evaluate(pairs: list[dict], season: str, verbose: bool = False) -> dict:
    """현재 모듈 계수(R.ALPHA/BETA/WALK_GAMMA)로 표본 전체를 잰다."""
    import routing as R  # noqa: F401  (아래 why 판정에서도 쓴다)
    g = R._graph()
    plans = R.route_plan_for(season)
    pure_w = g["length"]

    rows = []
    for pr in pairs:
        src, dst = _node(g, pr["origin"]), _node(g, pr["dest"])
        if src == dst:
            continue
        pure = _run(g, R, pure_w, src, dst)
        short = _run(g, R, R._weights(g, "shortest", ""), src, dst)
        if pure is None or short is None or short["distance_m"] < 100:
            continue
        row = {"id": pr["id"], "band": pr["band"],
               "pure_m": pure["distance_m"], "short_m": short["distance_m"],
               "walk_cost_pct": (short["distance_m"] / max(pure["distance_m"], 1) - 1) * 100,
               "short_share": short["walk_share"] * 100,
               "pure_share": pure["walk_share"] * 100, "alts": []}
        for kind, theme in plans:
            if kind == "shortest":
                continue
            info = _run(g, R, R._weights(g, kind, theme), src, dst)
            if info is None:
                continue
            base = short["trees"][theme]
            got = info["trees"][theme]
            detour = (info["distance_m"] / max(short["distance_m"], 1) - 1) * 100
            # plan_routes와 같은 '약속' 검사
            kept = (detour <= (R.MAX_DETOUR - 1) * 100
                    and (got > base if kind == "theme" else got < base))
            # 왜 빠졌나: 근처에 그 나무가 아예 없으면 계수 탓이 아니다(정직한 '내놓을 게 없음')
            if kept:
                why = "ok"
            elif base == 0 and got == 0:
                why = "nothing"        # 최단 경로 주변에 그 테마 나무가 없음
            elif detour > (R.MAX_DETOUR - 1) * 100:
                why = "too_long"       # 너무 돌아감
            else:
                why = "weak"           # 나무는 있는데 계수가 약해 더 못 지남/못 피함
            row["alts"].append({
                "kind": kind, "theme": theme, "detour": detour, "base": base, "got": got,
                "share": info["walk_share"] * 100, "kept": kept, "why": why,
                "gain": (got / base) if base else (float("inf") if got else 1.0),
                "cut": (1 - got / base) * 100 if base else (0.0 if got else 100.0),
            })
        rows.append(row)
        if verbose:
            alts = " | ".join(f"{a['kind']}:{a['theme']} +{a['detour']:.0f}% {a['base']}→{a['got']}그루"
                              for a in row["alts"])
            print(f"  {row['id']} {row['band']:9s} 순거리 {row['pure_m']:5,}m → 도보 {row['short_m']:5,}m "
                  f"(+{row['walk_cost_pct']:.0f}%) 걷는길 {row['short_share']:.0f}%  {alts}")
    return {"season": season, "rows": rows, "plans": plans}


def _med(xs, default=0.0):
    xs = [x for x in xs if x is not None and np.isfinite(x)]
    return st.median(xs) if xs else default


def summarize(res: dict) -> dict:
    rows = res["rows"]
    theme = [a for r in rows for a in r["alts"] if a["kind"] == "theme"]
    avoid = [a for r in rows for a in r["alts"] if a["kind"] == "avoid"]
    allalts = theme + avoid
    offer = [a for a in allalts if a["why"] != "nothing"]      # 내놓을 게 있었던 경우만
    def p90(xs):
        xs = sorted(x for x in xs if x is not None and np.isfinite(x))
        return xs[int(len(xs) * 0.9)] if xs else 0.0
    return {
        "nothing": 100.0 * sum(a["why"] == "nothing" for a in allalts) / max(len(allalts), 1),
        "weak": 100.0 * sum(a["why"] == "weak" for a in allalts) / max(len(allalts), 1),
        "kept_offerable": 100.0 * sum(a["kept"] for a in offer) / max(len(offer), 1),
        "detour_p90": p90([a["detour"] for a in allalts]),
        "n": len(rows),
        "walk_cost_pct": _med([r["walk_cost_pct"] for r in rows]),
        "pure_share": _med([r["pure_share"] for r in rows]),
        "short_share": _med([r["short_share"] for r in rows]),
        # 나무가 아예 없던 구간(why=nothing)은 빼고 잰다 — 계수 성능이 아니라 데이터 유무다
        "theme_gain": _med([a["gain"] for a in theme if a["why"] != "nothing"], 0.0),
        "theme_detour": _med([a["detour"] for a in theme if a["why"] != "nothing"], 0.0),
        "avoid_cut": _med([a["cut"] for a in avoid if a["why"] != "nothing"], 0.0),
        "avoid_detour": _med([a["detour"] for a in avoid if a["why"] != "nothing"], 0.0),
        "has_avoid": bool(avoid),
        "n_theme": len([a for a in theme if a["why"] != "nothing"]),
        "n_avoid": len([a for a in avoid if a["why"] != "nothing"]),
        "alt_share": _med([a["share"] for a in allalts], 0.0),
        "kept": 100.0 * sum(a["kept"] for a in allalts) / max(len(allalts), 1),
    }


MIN_SAMPLE = 10        # 잴 게 이보다 적으면 판정 보류 — 겨울 메타세쿼이아처럼 데이터가 없는 경우


def verdict(s: dict) -> list[str]:
    bad = []
    if s["n_theme"] < MIN_SAMPLE:
        return [f"표본 부족 — 테마 나무가 있는 구간이 {s['n_theme']}건뿐(판정 보류)"]
    if s["theme_gain"] < GOAL["theme_gain"]:
        bad.append(f"테마 나무 배수 {s['theme_gain']:.1f} < {GOAL['theme_gain']}")
    if s["theme_detour"] > GOAL["theme_detour"]:
        bad.append(f"테마 우회 {s['theme_detour']:.0f}% > {GOAL['theme_detour']:.0f}%")
    if s["has_avoid"] and s["n_avoid"] and s["avoid_cut"] < GOAL["avoid_cut"]:
        bad.append(f"회피 감축 {s['avoid_cut']:.0f}% < {GOAL['avoid_cut']:.0f}%")
    if min(s["short_share"], s["alt_share"]) < GOAL["walk_share"]:
        bad.append(f"걷는 길 비율 {min(s['short_share'], s['alt_share']):.0f}% < {GOAL['walk_share']:.0f}%")
    if s["kept_offerable"] < GOAL["kept"]:
        bad.append(f"내놓을 게 있었는데 못 지킨 비율 {100-s['kept_offerable']:.0f}% "
                   f"(지킴 {s['kept_offerable']:.0f}% < {GOAL['kept']:.0f}%)")
    return bad


HDR = (f"{'설정':22s} {'도보대가':>7s} {'걷는길':>10s} {'테마배수(n)':>13s} {'테마우회':>7s} "
       f"{'회피감축(n)':>13s} {'우회p90':>7s} {'가능분지킴':>10s} {'나무없음':>8s}")


def line(label: str, s: dict) -> str:
    cut = f"{s['avoid_cut']:5.0f}%({s['n_avoid']:2d})" if s["n_avoid"] else "     - ( 0)"
    return (f"{label:22s} {s['walk_cost_pct']:6.1f}% "
            f"{s['pure_share']:3.0f}→{s['short_share']:3.0f}%  "
            f"{s['theme_gain']:6.2f}x({s['n_theme']:2d}) {s['theme_detour']:6.1f}% "
            f"{cut:>13s} {s['detour_p90']:6.1f}% {s['kept_offerable']:9.0f}% {s['nothing']:7.0f}%")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default="autumn", help="회피 대안이 있는 가을이 기본")
    ap.add_argument("--sweep", choices=["walk", "alpha", "beta"], help="계수 하나를 흔들어 비교")
    ap.add_argument("--alpha", type=float, help="테마 계수 지정(기본: routing.ALPHA)")
    ap.add_argument("--beta", type=float, help="회피 계수 지정(기본: routing.BETA)")
    ap.add_argument("--gamma", type=float, help="도보 계수 세기 지정(기본: routing.WALK_GAMMA)")
    ap.add_argument("--all-seasons", action="store_true", help="네 계절 모두 — 계절마다 대안이 다르다")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    import routing as R
    for flag, name in (("alpha", "ALPHA"), ("beta", "BETA"), ("gamma", "WALK_GAMMA")):
        v = getattr(args, flag)
        if v is not None:
            setattr(R, name, v)
    if args.gamma is not None:
        R._graph.cache_clear()            # 체감 길이를 다시 만들어야 한다
    pairs = load_pairs()
    print(f"표본 {len(pairs)}쌍 · 계절 {args.season} · "
          f"현재 계수 α={R.ALPHA} β={R.BETA} walk^{R.WALK_GAMMA}\n")

    sweeps = {
        "walk": ("WALK_GAMMA", [0.0, 0.5, 1.0, 1.5, 2.0]),
        "alpha": ("ALPHA", [0.3, 0.45, 0.55, 0.7, 0.8]),
        "beta": ("BETA", [0.5, 1.0, 2.0, 3.0, 5.0]),
    }
    print(HDR)
    print("-" * len(HDR))
    if not args.sweep:
        t0 = time.time()
        seasons = ["spring", "summer", "autumn", "winter"] if args.all_seasons else [args.season]
        fails = {}
        for season in seasons:
            s = summarize(evaluate(pairs, season, args.verbose))
            print(line(f"{season} a{R.ALPHA} b{R.BETA} g{R.WALK_GAMMA}", s))
            bad = verdict(s)
            if bad:
                fails[season] = bad
        print(f"\n({time.time()-t0:.0f}s)\n합격선 판정:")
        for season in seasons:
            hit = fails.get(season)
            print(f"  {season:7s} " + ("통과" if not hit else "미달 — " + " · ".join(hit)))
        return

    name, values = sweeps[args.sweep]
    original = getattr(R, name)
    results = {}
    for v in values:
        setattr(R, name, v)
        if name == "WALK_GAMMA":
            R._graph.cache_clear()          # 체감 길이를 다시 만들어야 한다
        s = summarize(evaluate(pairs, args.season))
        results[v] = s
        mark = " ←지금" if v == original else ""
        print(line(f"{name}={v}{mark}", s))
    setattr(R, name, original)
    R._graph.cache_clear()

    print("\n합격선:", " · ".join(f"{k} {v}" for k, v in GOAL.items()))
    for v, s in results.items():
        bad = verdict(s)
        print(f"  {name}={v}: " + ("통과" if not bad else "미달 — " + " · ".join(bad)))


if __name__ == "__main__":
    main()
