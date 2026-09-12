#!/usr/bin/env bash
#
# Rushhour 자체 인프라 — 에이전트(LLM) 서버 시작 스크립트. 기본 포트 8080.
# 원본: /workspace/course/week5/start_agent_server.sh 를 참고해 이 저장소 맥락으로 재작성함
# (course 디렉터리 없이 저장소만 clone 해도 동작하도록 이식). 코스 파일은 수정하지 않음.
#
# 사용법:
#   bash deploy/start_agent_server.sh [--small] [CTX]
#     기본     : 27B (Qwen3.6-27B-UD-Q4_K_XL) — 도구 호출(FC) 신뢰도가 가장 높음
#     --small  : 4B  (Qwen3.5-4B-Q8_0) — VRAM 부족·27B 미기동 시 1차 폴백
#     CTX 미지정 시 16384. VRAM이 모자라면 8192로 낮춰 볼 것.
#
# OpenAI 호환 엔드포인트: http://localhost:<PORT>/v1  (app/config.py 의 AGENT_BASE_URL 과 일치)
#
# 환경변수 오버라이드(기본값은 코스와 동일):
#   AGENT_MODEL         27B 모델 경로 (기본 /workspace/models/Qwen3.6-27B-UD-Q4_K_XL.gguf)
#   AGENT_MODEL_SMALL   4B  모델 경로 (기본 /workspace/models/Qwen3.5-4B-Q8_0.gguf)
#   AGENT_PORT          포트 (기본 8080)
#   AGENT_CTX           컨텍스트 길이 (기본 16384; 위치 인자 CTX 가 우선)
#   LLAMA_SERVER_BIN    llama-server 바이너리 경로 (기본 /opt/llama.cpp/bin/llama-server)
#   RESULTS_DIR         로그·PID 저장 디렉터리 (기본 <repo>/results)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

MODEL="${AGENT_MODEL:-/workspace/models/Qwen3.6-27B-UD-Q4_K_XL.gguf}"
MODEL_SMALL="${AGENT_MODEL_SMALL:-/workspace/models/Qwen3.5-4B-Q8_0.gguf}"
VARIANT_LABEL="27B"
if [ "${1:-}" = "--small" ]; then
    MODEL="${MODEL_SMALL}"
    VARIANT_LABEL="4B(폴백)"
    shift
fi

CTX="${1:-${AGENT_CTX:-16384}}"
PORT="${AGENT_PORT:-8080}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results}"
LOG_FILE="${RESULTS_DIR}/agent-server.log"
PID_FILE="${RESULTS_DIR}/agent-server.pid"

mkdir -p "${RESULTS_DIR}"

echo "=== 사전 점검 ==="

# 이미지에 구운 로컬 빌드를 우선 사용함. /workspace/bin 은 예전 빌드로 glibc 불일치 가능성 있음.
BIN="${LLAMA_SERVER_BIN:-/opt/llama.cpp/bin/llama-server}"
if [ ! -x "${BIN}" ]; then
    echo "[경고] ${BIN} 없음 — /workspace/bin/llama-server 로 폴백(작동하지 않을 수 있음)."
    BIN=/workspace/bin/llama-server
fi

if [ ! -x "${BIN}" ]; then
    echo "[실패] llama-server 바이너리를 찾지 못함."
    echo "조치: 이미지에 llama-server 가 있는지 확인하거나 LLAMA_SERVER_BIN 으로 경로를 지정할 것."
    exit 1
fi

if [ ! -f "${MODEL}" ]; then
    echo "[실패] 에이전트 모델 없음: ${MODEL}"
    echo "조치: 모델 파일 경로를 확인하거나 AGENT_MODEL 로 지정할 것."
    exit 1
fi

port_busy() { ss -ltn 2>/dev/null | grep -q ":$1[[:space:]]"; }

if port_busy "${PORT}"; then
    echo "[실패] 포트 ${PORT}이 이미 사용 중임 — 서버가 이미 떠 있을 수 있음."
    echo "조치: 'bash deploy/stop_agent_server.sh'로 먼저 중지할 것."
    exit 1
fi

# VRAM 여유를 미리 알려 줌 — 27B Q4_K_XL 는 컨텍스트 16384 에서 약 18.5GB 를 씀(실측).
FREE_MIB="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
if [ -n "${FREE_MIB}" ]; then
    if [ "${VARIANT_LABEL}" = "27B" ]; then
        echo "[정보] GPU 여유 메모리: ${FREE_MIB} MiB (27B·16384 컨텍스트 기준 약 18500 MiB 필요함)"
        if [ "${FREE_MIB}" -lt 19000 ]; then
            echo "[경고] 27B 에는 여유가 빠듯함. 두 가지 선택지가 있음."
            echo "       (1) 컨텍스트 낮추기 : bash deploy/start_agent_server.sh 8192"
            echo "       (2) 4B로 폴백      : bash deploy/start_agent_server.sh --small"
        fi
    else
        echo "[정보] GPU 여유 메모리: ${FREE_MIB} MiB (4B 는 약 6000 MiB 로 충분함)"
    fi
fi

echo "[OK] 사용할 llama-server: ${BIN}"
echo "[OK] 모델: ${MODEL} (${VARIANT_LABEL})"
echo "[OK] 컨텍스트: ${CTX}"
echo "=== 에이전트 서버 시작 (포트 ${PORT}, ${VARIANT_LABEL}) ==="

# --jinja        : 도구 호출 템플릿 처리에 필수. 빠지면 tool_calls 가 오지 않음.
# -fa on         : 플래시 어텐션. KV 캐시를 줄여 긴 에이전트 이력을 감당함.
# -np 1          : 서버 슬롯 1개. 컨텍스트 전량을 한 요청에 씀(동시 요청은 서버에서 직렬화됨).
# --spec-type draft-mtp / --spec-draft-n-max 2
#                : GGUF 내장 MTP 헤드를 초안 모델로 쓰는 추측 디코딩. 별도 draft 모델 불필요.
#                  27B(MTP 내장 GGUF)에서만 켬 — 4B 에는 MTP 헤드가 없으므로 빼야 함.
SPEC_ARGS=()
if [ "${VARIANT_LABEL}" = "27B" ]; then
    SPEC_ARGS=(--spec-type draft-mtp --spec-draft-n-max 2)
fi

nohup "${BIN}" \
    -m "${MODEL}" \
    --host 0.0.0.0 --port "${PORT}" \
    -ngl 99 -c "${CTX}" -fa on -np 1 \
    "${SPEC_ARGS[@]}" \
    --jinja \
    > "${LOG_FILE}" 2>&1 &
SERVER_PID=$!
echo "${SERVER_PID}" > "${PID_FILE}"

echo "[OK] 에이전트 서버 시작됨 (PID ${SERVER_PID})"
echo "로그: ${LOG_FILE}"
echo "다음 단계: 'python deploy/wait_server.py --port ${PORT} --timeout 300'로 준비 상태를 확인할 것."
echo "           27B 로딩은 4B보다 오래 걸림 — 타임아웃을 넉넉히 줄 것."
