"""벡터DB(Chroma) + search_places — 임베딩 모델·네트워크 없이(EMBED_CHANNEL=hash, conftest.rag_index)."""
import pytest

import rag as R
from embeddings import HashEmbedder

HASH_SIG = "hash:char-ngram-8192"


def _sim(u, v):
    return sum(x * y for x, y in zip(u, v))


# ── 해시 임베더 ──────────────────────────────────────────────────────────────
def test_hash_embedder_deterministic_unit_norm_and_lexical_similarity():
    e = HashEmbedder()
    a, b = e.embed_query("양재천 메타세쿼이아"), e.embed_query("양재천 메타세쿼이아")
    assert a == b and len(a) == e.dim and abs(_sim(a, a) - 1.0) < 1e-4
    d1, d2 = e.embed_documents(["서울 강남구 양재천로. 메타세쿼이아 732그루", "서울 강동구 아리수로. 벚나무류 628그루"])
    assert _sim(a, d1) > _sim(a, d2)                       # 표기가 겹치는 문서가 더 가깝다
    assert e.signature == HASH_SIG


def test_hash_embedder_idf_fit_and_state_roundtrip(tmp_path):
    e = HashEmbedder()
    e.fit(["벚꽃 벚꽃 강남구", "벚꽃 서초구", "은행나무 종로구"])
    assert e.idf is not None and e.idf.shape == (e.dim,) and e.idf.min() >= 1.0
    e.save_state(tmp_path)
    f = HashEmbedder()
    assert f.load_state(tmp_path) is True and (f.idf == e.idf).all()
    assert HashEmbedder().load_state(tmp_path / "없음") is False
    # IDF가 있으면 흔한 낱말('벚꽃')보다 드문 낱말('종로구')이 더 큰 무게를 갖는다
    q_common, q_rare = e.embed_query("벚꽃"), e.embed_query("종로구")
    doc = e.embed_documents(["벚꽃 종로구"])[0]
    assert _sim(q_rare, doc) > _sim(q_common, doc)


# ── 문서 ─────────────────────────────────────────────────────────────────────
def test_build_street_docs_shape():
    docs = R.build_street_docs()
    assert 1500 < len(docs) < 2500
    by_id = {d["id"]: d for d in docs}
    y = by_id["강남구|양재천로"]
    assert "메타세쿼이아" in y["text"] and "대치동" in y["text"] and "메타세쿼이아길" in y["text"]
    m = y["metadata"]
    assert m["그루수"] > 700 and "메타세쿼이아" in m["themes"] and 37 < m["lat"] < 38 and 126 < m["lon"] < 128
    assert all(isinstance(v, (str, int, float)) for v in m.values())   # Chroma 메타데이터 타입 제약
    assert all(d["metadata"]["그루수"] >= R.MIN_TREES for d in docs)
    # 회피 테마엔 키워드('냄새')를 넣지 않는다 — '냄새 안 나는 길'이 은행나무 길로 끌려가지 않게
    ginkgo = by_id["종로구|자하문로"]["text"]
    assert "은행 냄새 회피" in ginkgo and "냄새," not in ginkgo and "냄새;" not in ginkgo


# ── 색인·검색 (세션 픽스처: 임시 디렉터리에 해시 인덱스) ─────────────────────
def test_index_built_with_signature_and_status(rag_index):
    assert rag_index["count"] > 1500 and rag_index["signature"] == HASH_SIG and rag_index["dim"] == 8192
    st = R.rag_status()
    assert st["ready"] and st["docs"] == rag_index["count"] and st["index_embed"] == HASH_SIG
    assert (R.chroma_path() / HashEmbedder.STATE_FILE).exists()          # IDF 상태 파일이 같이 저장됨


@pytest.mark.parametrize("q,gu,line,within", [
    ("석촌호수 벚꽃", "송파구", "석촌호수로", 1),                 # 노선명 그대로
    ("자하문로 은행나무", "종로구", "자하문로", 1),
    ("양재천 근처 메타세쿼이아 길", "강남구", "양재천로", 3),     # 지명 → 노선
    ("대치동 메타세쿼이아", "강남구", "양재천로", 3),           # 동네 이름 → 노선
    ("방화동 메타세쿼이아", "강서구", "개화동로", 3),
])
def test_search_places_lexical(rag_index, q, gu, line, within):
    r = R.search_places.invoke({"query": q, "k": 5})
    assert r["ok"] and r["embed"] == HASH_SIG
    got = [(x["구"], x["노선"]) for x in r["results"]]
    assert (gu, line) in got[:within], got
    scores = [x["score"] for x in r["results"]]
    assert scores == sorted(scores, reverse=True)
    assert all(x["score"] > x["similarity"] for x in r["results"])          # 기본 size_weight(0.02)가 붙음


def test_search_places_filters(rag_index):
    r = R.search_places.invoke({"query": "벚꽃길", "k": 10, "district": "강동구"})
    assert r["ok"] and {x["구"] for x in r["results"]} == {"강동구"}
    assert all(x["그루수"] >= R.MIN_RESULT_TREES for x in r["results"])       # 기본 하한 20
    small = R.search_places.invoke({"query": "벚꽃길", "k": 20, "district": "강동구", "min_trees": 0})
    assert small["ok"] and len(small["results"]) >= len(r["results"])
    assert R.search_places.invoke({"query": "   "})["ok"] is False


def test_search_places_size_weight_prefers_big_streets(rag_index):
    plain = R.search_places.invoke({"query": "세종대로 은행나무", "k": 5, "size_weight": 0})
    assert plain["ok"] and all(x["score"] == x["similarity"] for x in plain["results"])   # 0이면 유사도만
    big = R.search_places.invoke({"query": "세종대로 은행나무", "k": 5})                     # 기본 0.02
    assert big["ok"] and big["size_weight"] == R.DEFAULT_SIZE_WEIGHT
    assert [x["score"] for x in big["results"]] == sorted((x["score"] for x in big["results"]), reverse=True)
    assert sum(x["그루수"] for x in big["results"]) >= sum(x["그루수"] for x in plain["results"])


def test_search_places_refuses_honestly(rag_index, monkeypatch, tmp_path):
    # 인덱스 없음
    monkeypatch.setenv("CHROMA_PATH", str(tmp_path / "없음"))
    r = R.search_places.invoke({"query": "벚꽃"})
    assert r["ok"] is False and "인덱스 없음" in r["reason"] and R.rag_status()["ready"] is False
    monkeypatch.undo()
    # 채널 불일치 — 모델을 로드하지 않고 거절해야 한다
    monkeypatch.setenv("EMBED_CHANNEL", "st")
    r = R.search_places.invoke({"query": "벚꽃"})
    assert r["ok"] is False and "재색인" in r["reason"] and R.rag_status()["ready"] is False
