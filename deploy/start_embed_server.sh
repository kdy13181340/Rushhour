#!/usr/bin/env bash
#
# Rushhour 자체 인프라 — 임베딩 서버 시작 스크립트. 기본 포트 8082.
# 원본: /workspace/course/week4/start_embed_server.sh 를 참고해 이 저장소 맥락으로 재작성함.
#
# 사용법:
#   bash deploy/start_embed_server.sh [MODEL_PATH]
#     MODEL_PATH 미지정 시 아래 기본값(또는 EMBED_MODEL). 본인 GGUF 를 쓰려면 인자로 넘길 것.
#
# OpenAI 호환 임베딩 엔드포인트: http://localhost:<PORT>/v1/embeddings
#   → app/config.py 의 EMBED_URL(기본 http://localhost:8082/v1/embeddings) 과 일치.
# 모델은 BGE-M3(다국어·한국어 검색, 1024차원). 생성 서버(8080)와 동시 기동을 전제함.
#
# 포트 8082 를 쓰는 이유: 8081 은 일부 호스팅 환경의 nginx 프록시가 점유할 수 있어 8082 로 둠.
#
# 환경변수 오버라이드(기본값은 코스와 동일):
#   EMBED_MODEL       임베딩 모델 경로 (기본 /workspace/models/bge-m3-Q8_0.gguf; 위치 인자 우선)
#   EMBED_PORT        포트 (기본 8082)
#   EMBED_CTX         컨텍스트/배치 크기 (기본 8192)
#   LLAMA_SERVER_BIN  llama-server 바이너리 경로 (기본 /opt/llama.cpp/bin/llama-server)
#   RESULTS_DIR       로그·PID 디렉터리 (기본 <repo>/results)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DEFAULT_MODEL="${EMBED_MODEL:-/workspace/models/bge-m3-Q8_0.gguf}"
MODEL="${1:-${DEFAULT_MODEL}}"
PORT="${EMBED_PORT:-8082}"
CTX="${EMBED_CTX:-8192}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results}"
LOG_FILE="${RESULTS_DIR}/embed-server.log"
PID_FILE="${RESULTS_DIR}/embed-server.pid"

mkdir -p "${RESULTS_DIR}"

echo "=== 사전 점검 ==="

# 이미지에 구운 로컬 빌드를 우선 사용함. (코스 임베딩 스크립트는 /usr/local/bin 을 썼으나,
# 이 저장소는 에이전트 서버와 동일한 /opt/llama.cpp/bin 을 기본으로 두고 폴백을 둔다.)
BIN="${LLAMA_SERVER_BIN:-/opt/llama.cpp/bin/llama-server}"
if [ ! -x "${BIN}" ]; then
    echo "[경고] ${BIN} 없음 — /usr/local/bin/llama-server 로 폴백."
    BIN=/usr/local/bin/llama-server
fi

if [ ! -x "${BIN}" ]; then
    echo "[실패] llama-server 바이너리를 찾지 못함."
    echo "조치: 이미지에 llama-server 가 있는지 확인하거나 LLAMA_SERVER_BIN 으로 경로를 지정할 것."
    exit 1
fi

if [ ! -f "${MODEL}" ]; then
    echo "[실패] 임베딩 모델 파일 없음: ${MODEL}"
    echo "조치: 모델 경로를 확인하거나 EMBED_MODEL 로 지정(또는 인자로 GGUF 경로 전달)할 것."
    exit 1
fi

port_busy() { ss -ltn 2>/dev/null | grep -q ":$1[[:space:]]"; }

if port_busy "${PORT}"; then
    echo "[실패] 포트 ${PORT}이 이미 사용 중임 — 임베딩 서버가 이미 떠 있을 수 있음."
    echo "조치: 'bash deploy/stop_embed_server.sh'로 먼저 중지할 것."
    exit 1
fi

# 생성 서버(8080)는 죽이지 않고 상태만 한 줄로 보고함(임베딩·생성 동시 사용이 정상).
if port_busy 8080; then
    echo "[안내] 포트 8080 에 에이전트(생성) 서버가 떠 있음 — 정상(두 서버 동시 사용)."
else
    echo "[안내] 포트 8080 비어 있음 — 필요하면 'bash deploy/start_agent_server.sh'로 기동할 것."
fi

echo "[OK] 사용할 llama-server: ${BIN}"
echo "[OK] 모델: ${MODEL}"
echo "=== 임베딩 서버 시작 (포트 ${PORT}) ==="

# --embedding       : 임베딩 전용 모드(/v1/embeddings 활성화).
# --pooling cls     : BGE-M3 는 CLS 풀링을 사용함(모델 카드 기준).
# --embd-normalize 2: L2 정규화 → 코사인 유사도와 내적이 동치가 됨.
# -b/-ub = CTX      : 임베딩 모드에서 물리 배치가 한 입력의 상한이 됨. 컨텍스트까지 올려
#                     긴 청크에서 "input is too large to process" 500 오류를 없앰.
nohup "${BIN}" \
    -m "${MODEL}" \
    --host 0.0.0.0 --port "${PORT}" \
    --embedding --pooling cls --embd-normalize 2 \
    --ctx-size "${CTX}" --batch-size "${CTX}" --ubatch-size "${CTX}" --n-gpu-layers 99 \
    > "${LOG_FILE}" 2>&1 &
SERVER_PID=$!
echo "${SERVER_PID}" > "${PID_FILE}"

echo "[OK] 임베딩 서버 시작됨 (PID ${SERVER_PID})"
echo "로그: ${LOG_FILE}"
echo "다음 단계: 'python deploy/wait_server.py --port ${PORT}'로 준비 상태를 확인할 것."
