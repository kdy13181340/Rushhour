"""임베딩 채널 — llm.py의 채널 추상화를 임베딩에 옮긴 것.  [BE_DESIGN §4 RAG]

  EMBED_CHANNEL=local  (기본) → OpenAI 호환 /v1/embeddings — 코스 임베딩 서버(8082). EMBED_BASE_URL
  EMBED_CHANNEL=openai         → OPENAI_API_KEY · 기본 text-embedding-3-small
  EMBED_CHANNEL=gemini         → GEMINI_API_KEY · 기본 gemini-embedding-001 (OpenAI 호환 엔드포인트)
  EMBED_CHANNEL=st             → sentence-transformers 로컬 모델(CPU). 기본 intfloat/multilingual-e5-small
  EMBED_CHANNEL=hash           → 문자 n-gram 해싱(모델 없음). 테스트·CI·모델 없는 PC용.
                                 의미 검색이 아니라 '표기가 겹치는' 검색이다 — 동네·도로명엔 맞고 구어체엔 약함.
  EMBED_MODEL                  → 채널 기본 모델 덮어쓰기

인덱스는 어떤 채널·모델로 만들었는지 컬렉션 메타데이터에 남기고(signature), 질의 시 지금 채널·모델과
다르면 검색을 거절한다 — 다른 모델의 벡터 공간을 섞으면 결과가 조용히 망가진다(rag.py).
"""

import hashlib
import math
import os
from pathlib import Path

EMBED_BASE_URL = os.environ.get("EMBED_BASE_URL", "http://localhost:8082/v1")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
HASH_DIM = 8192
DEFAULT_MODEL = {
    "local": "",                                  # 서버의 /v1/models 첫 모델
    "openai": "text-embedding-3-small",
    "gemini": "gemini-embedding-001",
    "st": "intfloat/multilingual-e5-small",
    "hash": f"char-ngram-{HASH_DIM}",
}
CHANNELS = tuple(DEFAULT_MODEL)


def channel() -> str:
    return os.environ.get("EMBED_CHANNEL", "local").strip().lower()


def configured_model(ch: str | None = None) -> str:
    return os.environ.get("EMBED_MODEL", "").strip() or DEFAULT_MODEL.get(ch or channel(), "")


class Embedder:
    """embed_documents / embed_query. `signature`(채널:모델)로 인덱스와 질의의 일치를 검사한다."""

    channel: str = ""
    model: str = ""

    @property
    def signature(self) -> str:
        return f"{self.channel}:{self.model}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    # 코퍼스 통계가 필요한 채널만 구현한다(hash의 IDF). 신경망 임베딩은 상태가 없다.
    def fit(self, texts: list[str]) -> None:
        return None

    def save_state(self, directory) -> None:
        return None

    def load_state(self, directory) -> bool:
        return True


class HashEmbedder(Embedder):
    """모델 없는 결정적 임베딩 — 어절 안의 문자 2·3-gram과 어절 자체를 해싱해 부호 있는 √빈도로 쌓고 L2 정규화.

    코사인 유사도 = 표기 n-gram 겹침. '양재천'↔'양재천로'처럼 표기가 겹치면 잡고, '더운데 시원한 길'처럼
    의미만 같은 건 못 잡는다. 테스트가 모델·네트워크 없이 파이프라인 전체를 돌리기 위한 채널.
    설계 근거(DECISIONS DP14): 어절을 이어 붙인 n-gram·1024차원은 충돌 잡음과 짧은 문서 편향으로
    eval MRR 0.24 → 어절 내 n-gram·√빈도·8192차원으로 0.64. 문서에 테마 키워드를 넣자 모든 벚꽃 문서에
    같은 낱말이 들어가 0.50으로 떨어짐 → 코퍼스 IDF(fit)로 0.61 회복. IDF는 인덱스 디렉터리의
    hash_idf.npy 로 저장되어 질의 때 같이 로드된다(없으면 검색 거절, 재색인).
    """

    channel = "hash"
    STATE_FILE = "hash_idf.npy"
    _PUNCT = ".,:;()[]·—-"

    def __init__(self, dim: int = HASH_DIM, ngrams: tuple[int, ...] = (2, 3), word_weight: float = 2.0):
        self.dim, self.ngrams, self.word_weight = dim, ngrams, word_weight
        self.model = f"char-ngram-{dim}"
        self.idf = None                                # fit() 또는 load_state() 후 np.ndarray(dim)

    @staticmethod
    def _slot(key: str, dim: int) -> tuple[int, float]:
        h = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(h[:4], "little") % dim, (1.0 if h[4] & 1 else -1.0)

    def _counts(self, text: str) -> dict[str, float]:
        counts: dict[str, float] = {}
        for w in text.lower().split():
            w = w.strip(self._PUNCT)
            if not w:
                continue
            counts[f"w:{w}"] = counts.get(f"w:{w}", 0.0) + self.word_weight
            for n in self.ngrams:                       # 어절 안에서만 — 어절을 넘는 n-gram은 잡음
                for i in range(len(w) - n + 1):
                    k = f"{n}:{w[i:i + n]}"
                    counts[k] = counts.get(k, 0.0) + 1.0
        return counts

    def _vec(self, text: str) -> list[float]:
        import numpy as np
        v = np.zeros(self.dim, dtype=np.float32)
        for k, c in self._counts(text).items():
            idx, sign = self._slot(k, self.dim)
            w = math.sqrt(c)                            # √빈도: 반복 어절이 벡터를 독점하지 않게
            if self.idf is not None:
                w *= float(self.idf[idx])               # 흔한 낱말(테마 키워드·'그루')의 무게를 낮춤
            v[idx] += sign * w
        norm = float(np.linalg.norm(v)) or 1.0
        return (v / norm).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def fit(self, texts: list[str]) -> None:
        """코퍼스 IDF(해시 슬롯 단위): idf = ln((N+1)/(df+1)) + 1. 색인 전에 한 번."""
        import numpy as np
        df = np.zeros(self.dim, dtype=np.float32)
        for t in texts:
            seen = {self._slot(k, self.dim)[0] for k in self._counts(t)}
            df[list(seen)] += 1.0
        self.idf = (np.log((len(texts) + 1.0) / (df + 1.0)) + 1.0).astype(np.float32)

    def save_state(self, directory) -> None:
        import numpy as np
        if self.idf is not None:
            np.save(Path(directory) / self.STATE_FILE, self.idf)

    def load_state(self, directory) -> bool:
        import numpy as np
        p = Path(directory) / self.STATE_FILE
        if not p.exists():
            self.idf = None
            return False
        self.idf = np.load(p)
        return True


class OpenAICompatEmbedder(Embedder):
    """OpenAI 호환 /v1/embeddings — 코스 8082 서버(local)·OpenAI·Gemini 공용."""

    def __init__(self, ch: str, base_url: str | None, api_key: str, model: str, batch: int = 64):
        from openai import OpenAI
        self.channel, self.batch = ch, batch
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model or self.client.models.list().data[0].id     # local 서버는 모델 하나

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch):
            r = self.client.embeddings.create(model=self.model, input=texts[i:i + self.batch])
            out.extend(d.embedding for d in sorted(r.data, key=lambda d: d.index))
        return out


class SentenceTransformerEmbedder(Embedder):
    """sentence-transformers 로컬 모델(CPU). e5 계열은 'query: '/'passage: ' 접두어를 붙인다."""

    channel = "st"

    def __init__(self, model: str):
        from sentence_transformers import SentenceTransformer
        self.model = model
        self._m = SentenceTransformer(model, device="cpu")
        self._e5 = "e5" in model.lower()

    def _encode(self, texts: list[str]) -> list[list[float]]:
        return self._m.encode(texts, normalize_embeddings=True, batch_size=32,
                              show_progress_bar=False).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts] if self._e5 else texts)

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}" if self._e5 else text])[0]


def get_embedder(ch: str | None = None) -> Embedder:
    ch = (ch or channel())
    model = configured_model(ch)
    if ch == "hash":
        return HashEmbedder()
    if ch == "st":
        return SentenceTransformerEmbedder(model)
    if ch == "openai":
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise RuntimeError("EMBED_CHANNEL=openai 인데 OPENAI_API_KEY가 비어 있음")
        return OpenAICompatEmbedder("openai", None, key, model)
    if ch == "gemini":
        key = os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise RuntimeError("EMBED_CHANNEL=gemini 인데 GEMINI_API_KEY가 비어 있음")
        return OpenAICompatEmbedder("gemini", GEMINI_BASE_URL, key, model)
    if ch == "local":
        return OpenAICompatEmbedder("local", EMBED_BASE_URL, "sk-noop", model)
    raise ValueError(f"모르는 EMBED_CHANNEL: {ch} (가능: {', '.join(CHANNELS)})")


if __name__ == "__main__":
    e = get_embedder()
    print("채널:", e.signature)
    q = e.embed_query("양재천 근처 메타세쿼이아")
    d = e.embed_documents(["서울 강남구 양재천로. 메타세쿼이아 732그루", "서울 강동구 아리수로. 벚나무류 628그루"])
    dot = lambda a, b: sum(x * y for x, y in zip(a, b))  # noqa: E731
    print("dim:", len(q), "| 유사도 양재천로:", round(dot(q, d[0]), 3), "아리수로:", round(dot(q, d[1]), 3))
