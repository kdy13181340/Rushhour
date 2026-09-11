import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

os.environ.setdefault("AGENT_CHANNEL", "none")      # 테스트는 LLM 없이
os.environ.setdefault("TRACE_BACKEND", "none")
os.environ.setdefault("RUSHHOUR_SEASON", "autumn")  # 날짜에 따라 결과가 흔들리지 않게 고정
os.environ.setdefault("EMBED_CHANNEL", "hash")      # 벡터DB도 모델·네트워크 없이(문자 n-gram 해싱)


@pytest.fixture(scope="session")
def rag_index(tmp_path_factory):
    """해시 채널로 전체 도로 문서를 임시 디렉터리에 색인(약 10초) — RAG 경로 전체를 모델 없이 돈다.

    CHROMA_PATH를 이 디렉터리로 돌려 rag.search_places·/tools/search_places·/health.rag가 이걸 보게 한다.
    """
    path = tmp_path_factory.mktemp("chroma") / "hash"
    os.environ["CHROMA_PATH"] = str(path)
    import rag
    return rag.build_index(path=path)
