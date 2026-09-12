"""벡터DB(Chroma) — 도로 문서 색인 + `search_places` 검색 도구.  [BE_DESIGN §4 RAG · app/README 연동 지점]

문서 단위 = (구, 노선) 하나(약 2천 건). 텍스트에는 도로명·동네·수종별 그루수·해당 테마·인근 도로를
담고, 좌표 배열은 넣지 않는다(지도는 map_api가 따로 가져간다). 메타데이터에 구·노선·그루수·중심좌표.

  인덱스 위치:  data/chroma/<EMBED_CHANNEL>/   (CHROMA_PATH env로 덮어쓰기)
  빌드:        python scripts/02_build_vector_db.py [--channel hash|st|local|openai|gemini]
  평가:        python scripts/03_eval_search_places.py
  검색:        search_places.invoke({"query": "양재천 근처 메타세쿼이아", "k": 5})

인덱스에는 만들 때 쓴 임베딩 서명(채널:모델)을 남기고, 질의 시 지금 채널·모델과 다르면 검색을 거절한다.
겨울 조명 문서(find_light_spots)는 같은 클라이언트에 컬렉션을 하나 더 두면 된다(C7).
"""

import math
import os
import time
from pathlib import Path

from langchain_core.tools import tool

from embeddings import channel as embed_channel, configured_model, get_embedder
from themes import THEMES
from tools import _load, data_source

ROOT = Path(__file__).resolve().parents[1]
COLLECTION = "streets"
MIN_TREES = 5          # 이보다 적은 (구,노선)은 문서로 안 만든다 — 잡음
THEME_MIN = 20         # 테마 태그를 붙이는 최소 그루수
MIN_RESULT_TREES = 20  # search_places 기본 하한 — 이보다 작은 골목은 산책길 후보로 보지 않음(호출자가 0으로 풀 수 있음)
MAX_K = 20
RERANK_FETCH = 50      # size_weight 재정렬 때 유사도 상위 몇 개를 가져와 다시 세울지
DEFAULT_SIZE_WEIGHT = 0.02   # score = 유사도 + w·log10(그루수). 산책길 추천이라 큰 길을 앞세운다(DP14 측정: 두 채널 모두 큰 개선)
_DONG_RE = r"서울특별시\s+\S+구\s+(\S+)"        # 지번 '서울특별시 강남구 대치동 513-1' → 대치동
_ROAD_RE = r"^서울특별시\s+\S+구\s+(\S+)"       # 도로명 '서울특별시 강남구 남부순환로 2738-2' → 남부순환로


def chroma_path() -> Path:
    """채널마다 다른 디렉터리 — 채널을 바꾸면 그 채널로 만든 인덱스를 자동으로 본다."""
    env = os.environ.get("CHROMA_PATH", "").strip()
    return Path(env) if env else ROOT / "data" / "chroma" / embed_channel()


# ── 문서 만들기 ──────────────────────────────────────────────────────────────
def _theme_tags(seg) -> tuple[list[str], list[str], list[str]]:
    """(추천 테마 문구, 회피 테마 문구, 테마 키) — 그루수 THEME_MIN(테마별 tag_min이 있으면 그것) 이상인 테마만.

    tag_min: 수종이 겹치는 테마(크리스마스·상록은 둘 다 소나무)를 20그루 문턱으로 붙이면 소나무 몇 그루
    끼어 있는 큰길마다 긴 태그 두 줄이 붙어 지명 신호('석촌호수로')가 묻힌다 — 해시 채널에서 실측
    ('석촌호수' → 송파구 해소 실패). 정말 그 테마의 길인 노선만 태그되게 테마가 스스로 문턱을 올린다.

    추천 테마엔 themes.py의 keywords(꽃구경·플라타너스·시원 …)를 함께 넣어 구어체 질의가 문서에 닿게 한다
    — 테마 어휘의 단일 출처를 재사용하는 것이지 평가 질의에 맞춘 게 아니다. 회피 테마(은행회피)엔
    키워드를 넣지 않는다: '냄새'가 문서에 들어가면 '냄새 안 나는 길' 질의가 은행나무 길로 끌려간다.
    """
    prefer, avoid, keys = [], [], []
    for key, spec in THEMES.items():
        n = int(seg["수종"].isin(spec["species"]).sum())
        if n < spec.get("tag_min", THEME_MIN):
            continue
        keys.append(key)
        if spec["mode"] == "prefer":
            prefer.append(f"{spec['label']}({n}그루; {', '.join(spec['keywords'])})")
        else:
            avoid.append(f"{spec['label']} 테마에서 피하는 길({n}그루)")
    return prefer, avoid, keys


def build_street_docs(df=None, min_trees: int = MIN_TREES) -> list[dict]:
    """가로수 데이터 → (구, 노선) 문서 목록 [{id, text, metadata}]."""
    df = _load() if df is None else df
    d = df.dropna(subset=["노선"])
    d = d.assign(동=d["지번"].str.extract(_DONG_RE)[0],
                 인근=d["도로명"].str.extract(_ROAD_RE)[0])
    docs = []
    for (gu, line), seg in d.groupby(["구", "노선"], sort=True):
        n = len(seg)
        if n < min_trees:
            continue
        species = seg["수종"].value_counts()
        dongs = seg["동"].dropna().value_counts().head(3).index.tolist()
        near = [r for r in seg["인근"].dropna().value_counts().index.tolist() if r != line][:2]
        prefer, avoid, keys = _theme_tags(seg)
        parts = [f"서울 {gu} {line}."]
        if dongs:
            parts.append(f"동네: {', '.join(dongs)}.")
        parts.append(f"가로수 {n}그루: " + ", ".join(f"{s} {c}그루" for s, c in species.head(4).items()) + ".")
        if prefer:
            parts.append("테마: " + ", ".join(prefer) + ".")
        if avoid:
            parts.append("주의: " + ", ".join(avoid) + ".")
        if near:
            parts.append(f"인근 도로: {', '.join(near)}.")
        docs.append({
            "id": f"{gu}|{line}",
            "text": " ".join(parts),
            "metadata": {   # Chroma 메타데이터는 str/int/float/bool만 — 목록은 쉼표로 이어 붙임
                "구": str(gu), "노선": str(line), "그루수": int(n),
                "수종": str(species.index[0]), "동": ",".join(dongs), "themes": ",".join(keys),
                "lat": round(float(seg["위도"].mean()), 6), "lon": round(float(seg["경도"].mean()), 6),
            },
        })
    return docs


# ── 색인 ─────────────────────────────────────────────────────────────────────
def _client(path: Path):
    import chromadb
    from chromadb.config import Settings
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def build_index(embedder=None, docs: list[dict] | None = None, path: Path | None = None,
                batch: int = 128, progress=None) -> dict:
    """문서를 임베딩해 Chroma 컬렉션을 (다시) 만든다. 임베딩 서명을 컬렉션 메타데이터에 남긴다."""
    embedder = embedder or get_embedder()
    docs = build_street_docs() if docs is None else docs
    path = path or chroma_path()
    client = _client(path)
    try:
        client.delete_collection(COLLECTION)
    except Exception:  # noqa: BLE001 — 없으면 그만
        pass
    embedder.fit([d["text"] for d in docs])            # hash: 코퍼스 IDF. 신경망 채널은 no-op
    meta = {"embed_signature": embedder.signature, "embed_channel": embedder.channel,
            "embed_model": embedder.model, "embed_state_file": getattr(embedder, "STATE_FILE", ""),
            "docs": len(docs), "source": data_source(), "built_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    col = client.create_collection(COLLECTION, embedding_function=None,
                                   configuration={"hnsw": {"space": "cosine"}}, metadata=meta)
    t0, dim = time.time(), 0
    for i in range(0, len(docs), batch):
        chunk = docs[i:i + batch]
        embs = embedder.embed_documents([d["text"] for d in chunk])
        dim = len(embs[0])
        col.add(ids=[d["id"] for d in chunk], documents=[d["text"] for d in chunk],
                embeddings=embs, metadatas=[d["metadata"] for d in chunk])
        if progress:
            progress(min(i + batch, len(docs)), len(docs))
    col.modify(metadata={**meta, "dim": dim})
    embedder.save_state(path)                          # hash_idf.npy — 질의 때 같은 IDF를 써야 한다
    _CACHE.clear()
    return {"path": str(path), "count": col.count(), "dim": dim, "signature": embedder.signature,
            "elapsed_sec": round(time.time() - t0, 1)}


# ── 검색 ─────────────────────────────────────────────────────────────────────
_CACHE: dict = {}       # {"col:<path>": collection, "emb:<channel>": embedder}


def _collection(path: Path):
    key = f"col:{path}"
    if key not in _CACHE:
        if not path.exists():
            raise FileNotFoundError(f"인덱스 없음: {path} — python scripts/02_build_vector_db.py 를 먼저 실행할 것")
        _CACHE[key] = _client(path).get_collection(COLLECTION, embedding_function=None)
    return _CACHE[key]


def _embedder(path: Path):
    """채널·모델·인덱스 경로별로 하나. 인덱스 디렉터리의 상태 파일(hash IDF)을 같이 로드한다."""
    key = f"emb:{embed_channel()}:{configured_model()}:{path}"
    if key not in _CACHE:
        emb = get_embedder()
        emb.load_state(path)
        _CACHE[key] = emb
    return _CACHE[key]


def rag_status() -> dict:
    """헬스체크용 — 인덱스 유무·문서 수·인덱스 임베딩 서명·현재 채널 일치 여부(모델은 로드하지 않음)."""
    path = chroma_path()
    try:
        col = _collection(path)
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "reason": f"{type(exc).__name__}: {exc}"[:160],
                "path": str(path), "channel": embed_channel()}
    meta = col.metadata or {}
    return {"ready": meta.get("embed_channel") == embed_channel(), "docs": col.count(),
            "index_embed": meta.get("embed_signature"), "channel": embed_channel(),
            "built_at": meta.get("built_at"), "path": str(path)}


@tool
def search_places(query: str, k: int = 5, district: str = "", min_trees: int = MIN_RESULT_TREES,
                  size_weight: float = DEFAULT_SIZE_WEIGHT) -> dict:
    """자유서술·장소명으로 가로수 도로를 의미검색한다.

    find_theme_streets가 테마 키·자치구로만 찾는 것과 달리, 동네 이름("역삼동"), 하천·지명("양재천 근처"),
    구어체("벚꽃 유명한 길")로 (구, 노선) 후보를 찾는다. 좌표는 돌려주지 않는다 — 후보의 (구, 노선)으로
    find_theme_streets나 map_api.street_points를 이어 부른다.

    Args:
        query: 자연어 질의. 예: '양재천 근처 메타세쿼이아', '대치동 산책길', '벚꽃 유명한 하천길'
        k: 후보 수(1~20)
        district: 자치구로 좁히기(선택). 예: '강남구'
        min_trees: 이 그루수 미만 도로는 제외(기본 20 — 골목길 제외). 작은 길도 보려면 0.
        size_weight: score = 유사도 + size_weight·log10(그루수). 기본 0.02 — 골목보다 대로를 앞세운다
            (DECISIONS DP14: e5-small MRR 0.66→0.87, 해시 0.61→0.70). 유사도만 보려면 0.

    Returns:
        {ok, query, results:[{구, 노선, 그루수, 수종, 동, themes, score, similarity, center}], embed, note}
        - similarity는 코사인 유사도(1에 가까울수록 비슷), score는 재정렬 점수(size_weight=0이면 같음).
          결과는 score 내림차순.
        - 인덱스가 없거나 인덱스의 임베딩 채널·모델이 지금 설정과 다르면 ok=False와 사유(재색인 필요).
    """
    q = (query or "").strip()
    if not q:
        return {"ok": False, "reason": "빈 질의"}
    try:
        col = _collection(chroma_path())
    except ImportError:
        return {"ok": False, "reason": "chromadb 미설치 — pip install chromadb"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    meta = col.metadata or {}
    path = chroma_path()
    if meta.get("embed_channel") != embed_channel():
        return {"ok": False, "reason": f"인덱스 임베딩({meta.get('embed_signature')})과 현재 채널"
                                       f"({embed_channel()})이 다름 — 재색인 필요"}
    state_file = meta.get("embed_state_file") or ""
    if state_file and not (path / state_file).exists():
        return {"ok": False, "reason": f"인덱스 상태 파일 없음({state_file}) — 재색인 필요"}
    try:
        emb = _embedder(path)
        if emb.signature != meta.get("embed_signature"):
            return {"ok": False, "reason": f"인덱스 임베딩({meta.get('embed_signature')})과 현재 모델"
                                           f"({emb.signature})이 다름 — 재색인 필요"}
        conds = []
        if district:
            conds.append({"구": district})
        if int(min_trees) > 0:
            conds.append({"그루수": {"$gte": int(min_trees)}})
        where = None if not conds else (conds[0] if len(conds) == 1 else {"$and": conds})
        k = max(1, min(int(k), MAX_K))
        fetch = max(k, RERANK_FETCH) if size_weight > 0 else k
        res = col.query(query_embeddings=[emb.embed_query(q)], n_results=fetch,
                        where=where, include=["metadatas", "distances"])
    except Exception as exc:  # noqa: BLE001 — 임베딩 서버 다운 등
        return {"ok": False, "reason": f"임베딩/검색 실패 {type(exc).__name__}: {str(exc)[:120]}"}
    results = []
    for m, dist in zip(res["metadatas"][0], res["distances"][0]):
        sim = 1.0 - float(dist)
        score = sim + (size_weight * math.log10(max(int(m["그루수"]), 1)) if size_weight > 0 else 0.0)
        results.append({"구": m["구"], "노선": m["노선"], "그루수": m["그루수"], "수종": m["수종"],
                        "동": [x for x in m["동"].split(",") if x], "themes": [x for x in m["themes"].split(",") if x],
                        "score": round(score, 4), "similarity": round(sim, 4), "center": [m["lat"], m["lon"]]})
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:k]
    return {"ok": bool(results), "query": q, "district": district or "서울 전체", "min_trees": int(min_trees),
            "size_weight": size_weight, "results": results, "embed": meta.get("embed_signature"),
            "note": "score=코사인 유사도. (구,노선)으로 find_theme_streets/street_points를 이어 부를 것."}


if __name__ == "__main__":
    print("인덱스:", rag_status())
    for q in ["양재천 근처 메타세쿼이아", "대치동 산책길", "벚꽃 유명한 하천길", "역삼동 그늘진 길"]:
        r = search_places.invoke({"query": q, "k": 3})
        print(f"\nQ {q}")
        if not r["ok"]:
            print("  ✗", r["reason"])
            continue
        for x in r["results"]:
            print(f"  {x['score']:.3f}  {x['구']} {x['노선']}  {x['수종']} {x['그루수']}그루  동={','.join(x['동'])}")
