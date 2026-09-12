"""search_places 검색 품질 평가 — data/eval/search_places.jsonl 의 질의로 hit@k·MRR을 낸다.  [DECISIONS DP14]

실행:  python scripts/03_eval_search_places.py [--channel hash|st|local|openai|gemini] [--k 10] [--verbose]
  현재 EMBED_CHANNEL(또는 --channel)의 인덱스(data/chroma/<채널>/)를 쓴다. 없으면 먼저 02를 실행.

질의 파일 한 줄: {"q": 질의, "expect": [[구, 노선], ...](정답 후보), "kind": lexical|semantic, "note": ...}
  lexical  = 질의와 문서의 표기가 겹침(동네·노선명) — 해시 채널도 잡아야 함
  semantic = 표기가 안 겹치고 의미로만 이어짐 — 진짜 임베딩 모델이 필요한 부분
데모 질의에 맞춰 임계값을 손보지 않는다(BE_DESIGN DP16의 원칙). 결과는 DECISIONS.md DP14에 기록.
"""

import argparse
import json
import os
import sys
from pathlib import Path

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
EVAL_PATH = ROOT / "data" / "eval" / "search_places.jsonl"


def load_queries(path: Path = EVAL_PATH) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def evaluate(queries: list[dict], k: int = 10, min_trees: int | None = None,
             size_weight: float | None = None) -> dict:
    """각 질의의 정답 순위와 hit@1/3/5/k, MRR. search_places를 그대로 부른다(도구와 같은 경로)."""
    from rag import rag_status, search_places
    status = rag_status()
    if not status.get("ready"):
        raise SystemExit(f"인덱스 준비 안 됨: {status}")
    rows = []
    for e in queries:
        args = {"query": e["q"], "k": k}
        if min_trees is not None:
            args["min_trees"] = min_trees
        if size_weight is not None:
            args["size_weight"] = size_weight
        r = search_places.invoke(args)
        got = [(x["구"], x["노선"]) for x in r.get("results", [])] if r.get("ok") else []
        exp = {tuple(x) for x in e["expect"]}
        rank = next((i + 1 for i, g in enumerate(got) if g in exp), None)
        rows.append({"q": e["q"], "kind": e.get("kind", ""), "rank": rank,
                     "top": [f"{g} {l}" for g, l in got[:3]], "expect": [f"{g} {l}" for g, l in e["expect"]]})

    def agg(sub):
        n = len(sub)
        if not n:
            return {}
        ranks = [x["rank"] for x in sub]
        return {"n": n, "hit@1": sum(r == 1 for r in ranks), "hit@3": sum(r is not None and r <= 3 for r in ranks),
                "hit@5": sum(r is not None and r <= 5 for r in ranks), f"hit@{k}": sum(r is not None for r in ranks),
                "mrr": round(sum(1 / r for r in ranks if r) / n, 3)}
    return {"embed": status.get("index_embed"), "docs": status.get("docs"), "k": k, "min_trees": min_trees,
            "size_weight": size_weight, "rows": rows,
            "all": agg(rows), "lexical": agg([x for x in rows if x["kind"] == "lexical"]),
            "semantic": agg([x for x in rows if x["kind"] == "semantic"])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=["hash", "st", "local", "openai", "gemini"])
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--min-trees", type=int, default=None, help="도구 기본값(20) 대신 쓸 그루수 하한. 0이면 필터 없음")
    ap.add_argument("--size-weight", type=float, default=None, help="유사도 + w·log10(그루수) 재정렬. 도구 기본 0.02, 0이면 유사도만")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.channel:
        os.environ["EMBED_CHANNEL"] = args.channel
    res = evaluate(load_queries(), k=args.k, min_trees=args.min_trees, size_weight=args.size_weight)
    print(f"임베딩 {res['embed']} · 문서 {res['docs']:,} · k={res['k']} · "
          f"min_trees={'도구 기본(20)' if res['min_trees'] is None else res['min_trees']} · "
          f"size_weight={'도구 기본(0.02)' if res['size_weight'] is None else res['size_weight']}")
    for name in ("all", "lexical", "semantic"):
        a = res[name]
        if a:
            print(f"  {name:9s} n={a['n']:2d}  hit@1 {a['hit@1']:2d}  hit@3 {a['hit@3']:2d}  hit@5 {a['hit@5']:2d}  "
                  f"hit@{res['k']} {a[f'hit@{res['k']}']:2d}  MRR {a['mrr']:.3f}")
    print()
    for x in res["rows"]:
        mark = "✓" if x["rank"] == 1 else ("~" if x["rank"] else "✗")
        line = f"  {mark} {x['kind'][:3]} rank={str(x['rank']):>4}  {x['q']}"
        if args.verbose or x["rank"] != 1:
            line += f"\n        top3={x['top']}  expect={x['expect']}"
        print(line)


if __name__ == "__main__":
    main()
