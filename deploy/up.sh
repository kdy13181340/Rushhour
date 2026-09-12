#!/usr/bin/env bash
#
# Rushhour 자체 인프라 — 두 서버(에이전트 8080 + 임베딩 8082)를 한 번에 기동하고
# 준비 상태까지 확인하는 편의 스크립트.
#
# 사용법:
#   bash deploy/up.sh [--small] [--agent-only] [--embed-only]
#     --small       에이전트 서버를 4B 폴백으로 기동
#     --agent-only  에이전트 서버만 기동
#     --embed-only  임베딩 서버만 기동
#
# 개별 서버의 세부 오버라이드(포트·모델·컨텍스트·바이너리)는 각 start_*.sh 의
# 환경변수를 그대로 사용함. 예) AGENT_CTX=8192 bash deploy/up.sh --small
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SMALL=""
DO_AGENT=1
DO_EMBED=1
for arg in "$@"; do
    case "${arg}" in
        --small)      SMALL="--small" ;;
        --agent-only) DO_EMBED=0 ;;
        --embed-only) DO_AGENT=0 ;;
        *) echo "[경고] 알 수 없는 인자 무시: ${arg}" ;;
    esac
done

AGENT_PORT="${AGENT_PORT:-8080}"
EMBED_PORT="${EMBED_PORT:-8082}"

if [ "${DO_AGENT}" -eq 1 ]; then
    echo "### 에이전트 서버 기동 ###"
    bash "${SCRIPT_DIR}/start_agent_server.sh" ${SMALL:+$SMALL}
fi

if [ "${DO_EMBED}" -eq 1 ]; then
    echo "### 임베딩 서버 기동 ###"
    bash "${SCRIPT_DIR}/start_embed_server.sh"
fi

# 준비 대기 — 에이전트(27B)는 로딩이 길 수 있어 타임아웃을 넉넉히 줌.
if [ "${DO_AGENT}" -eq 1 ]; then
    echo "### 에이전트 서버 준비 대기 (포트 ${AGENT_PORT}) ###"
    python "${SCRIPT_DIR}/wait_server.py" --port "${AGENT_PORT}" --timeout 300
fi
if [ "${DO_EMBED}" -eq 1 ]; then
    echo "### 임베딩 서버 준비 대기 (포트 ${EMBED_PORT}) ###"
    python "${SCRIPT_DIR}/wait_server.py" --port "${EMBED_PORT}" --timeout 180
fi

echo "[완료] 요청한 서버가 준비됨."
