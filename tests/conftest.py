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

# 경로 탐색용 OSM 도로망도 마찬가지 — data/osm/ 은 5분짜리 다운로드 산출물이라 gitignore다.
# 비워 두면 osm_ready()가 False라 그래프는 회랑 방식으로 폴백한다(있는 PC와 없는 CI가 같아짐).
OSM_DIR = Path(tempfile.mkdtemp(prefix="rushhour-osm-"))
os.environ["OSM_DIR"] = str(OSM_DIR)


@pytest.fixture(scope="module")
def osm_net(tmp_path_factory):
    """갈래가 둘인 작은 인공 도로망 — 위쪽은 짧고 은행나무, 아래쪽은 길고 벚나무.

        n1 ── 위: 1,000m, 은행 암나무 가득
       ╱  ╲
     n0    n2
       ╲  ╱
        n3 ── 아래: 1,300m, 벚나무 가득

    진짜 서울 도로망 대신 이걸 쓴다 — 어느 갈래를 고르는지가 곧 가중치가 맞는지다.
    """
    import pandas as pd

    import routing as R
    from themes import THEMES

    N = {0: (37.500, 127.000), 1: (37.505, 127.005), 2: (37.500, 127.010), 3: (37.495, 127.005)}
    TOP, BOTTOM = 500.0, 650.0

    def edge(u, v, length, name):
        return {"u": u, "v": v, "length_m": length, "도로명": name,
                "geom_lat": [N[u][0], N[v][0]], "geom_lon": [N[u][1], N[v][1]]}

    d = tmp_path_factory.mktemp("osmnet")
    pd.DataFrame([{"node": k, "위도": v[0], "경도": v[1]} for k, v in N.items()]).to_parquet(
        d / "seoul_walk_nodes.parquet", index=False)
    rows = []
    for u, v, ln, nm in [(0, 1, TOP, "윗길"), (1, 2, TOP, "윗길"),
                         (0, 3, BOTTOM, "아랫길"), (3, 2, BOTTOM, "아랫길")]:
        rows.append(edge(u, v, ln, nm))
        rows.append(edge(v, u, ln, nm))                  # 보행망은 양방향
    pd.DataFrame(rows).to_parquet(d / "seoul_walk_edges.parquet", index=False)
    trees = []
    for a, b, key, n, nm in [(0, 1, "은행회피", int(TOP / 8) + 5, "윗길"),
                             (1, 2, "은행회피", int(TOP / 8) + 5, "윗길"),
                             (0, 3, "벚꽃", int(BOTTOM / 8) + 5, "아랫길"),
                             (3, 2, "벚꽃", int(BOTTOM / 8) + 5, "아랫길")]:
        row = {"a": min(a, b), "b": max(a, b), "나무수": n, "가로수노선": nm}
        row.update({k: 0 for k in THEMES})
        row[key] = n
        trees.append(row)
    pd.DataFrame(trees).to_parquet(d / "seoul_walk_edge_trees.parquet", index=False)

    R._graph.cache_clear()
    old, R.OSM_DIR = R.OSM_DIR, d
    yield {"dir": d, "nodes": N, "top": TOP, "bottom": BOTTOM}
    R.OSM_DIR = old
    R._graph.cache_clear()


@pytest.fixture(scope="session")
def rag_index():
    """해시 채널로 전체 도로 문서를 임시 디렉터리에 색인(약 10초) — RAG 경로 전체를 모델 없이 돈다.

    rag.search_places·/tools/search_places·/health.rag·graph의 places 노드가 모두 이 인덱스를 본다.
    """
    import rag
    return rag.build_index(path=CHROMA_DIR)
