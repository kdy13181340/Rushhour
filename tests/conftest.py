import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

os.environ.setdefault("AGENT_CHANNEL", "none")      # 테스트는 LLM 없이
os.environ.setdefault("TRACE_BACKEND", "none")
os.environ.setdefault("RUSHHOUR_SEASON", "autumn")  # 날짜에 따라 결과가 흔들리지 않게 고정
os.environ.setdefault("EMBED_CHANNEL", "hash")      # 벡터DB도 모델·네트워크 없이(문자 n-gram 해싱)

# 인덱스 경로를 임시 디렉터리로 못박는다 — 저장소의 data/chroma/ 가 있는 PC와 없는 CI에서
# 같은 결과가 나와야 한다. 여기에 색인하는 것은 rag_index 픽스처를 요청한 테스트뿐이다.
CHROMA_DIR = Path(tempfile.mkdtemp(prefix="rushhour-chroma-"))
os.environ["CHROMA_PATH"] = str(CHROMA_DIR)


@pytest.fixture(scope="session")
def rag_index():
    """해시 채널로 전체 도로 문서를 임시 디렉터리에 색인(약 10초) — RAG 경로 전체를 모델 없이 돈다.

    rag.search_places·/tools/search_places·/health.rag·graph의 places 노드가 모두 이 인덱스를 본다.
    """
    import rag
    return rag.build_index(path=CHROMA_DIR)
