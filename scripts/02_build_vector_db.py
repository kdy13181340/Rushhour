"""가로수 (구, 노선) 문서 → Chroma 벡터DB 색인.  [BE_DESIGN §4 RAG]

실행:  python scripts/02_build_vector_db.py [--channel hash|st|local|openai|gemini] [--limit N] [--probe]
  --channel  EMBED_CHANNEL을 덮어씀(기본: env, 없으면 local=8082 서버)
  --limit N  앞 N개 문서만(빠른 점검)
  --probe    색인 후 샘플 질의 몇 개를 바로 검색해 보임
  --docs     문서만 만들어 몇 개 출력하고 끝(색인 안 함)

출력: data/chroma/<채널>/ (CHROMA_PATH env로 덮어쓰기). 재실행하면 컬렉션을 지우고 다시 만든다.
"""

import argparse
import os
import sys
import time
from pathlib import Path

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

PROBES = ["양재천 근처 메타세쿼이아", "대치동 산책길", "벚꽃 유명한 하천길", "역삼동 그늘진 길", "세종대로 은행나무"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", choices=["hash", "st", "local", "openai", "gemini"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--docs", action="store_true")
    args = ap.parse_args()
    if args.channel:
        os.environ["EMBED_CHANNEL"] = args.channel

    from embeddings import get_embedder
    from rag import build_index, build_street_docs, chroma_path, search_places

    t0 = time.time()
    docs = build_street_docs()
    if args.limit:
        docs = docs[:args.limit]
    print(f"문서 {len(docs):,}건 (만드는 데 {time.time() - t0:.1f}s). 예:")
    for d in docs[:2]:
        print("  -", d["text"][:160])
    if args.docs:
        return

    emb = get_embedder()
    print(f"임베딩: {emb.signature} → {chroma_path()}")
    last = [0.0]

    def progress(done, total):
        if time.time() - last[0] > 2 or done == total:
            last[0] = time.time()
            print(f"  {done:,}/{total:,}  {time.time() - t0:.0f}s", flush=True)

    info = build_index(emb, docs=docs, progress=progress)
    print(f"색인 완료: {info['count']:,}건 · dim {info['dim']} · {info['elapsed_sec']}s · {info['path']}")

    if args.probe:
        for q in PROBES:
            r = search_places.invoke({"query": q, "k": 3})
            print(f"\nQ {q}")
            if not r["ok"]:
                print("  ✗", r["reason"])
                continue
            for x in r["results"]:
                print(f"  {x['score']:.3f}  {x['구']} {x['노선']}  {x['수종']} {x['그루수']}그루  동={','.join(x['동'])}")


if __name__ == "__main__":
    main()
