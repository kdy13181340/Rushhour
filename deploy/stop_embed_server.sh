#!/usr/bin/env bash
#
# Rushhour 자체 인프라 — 임베딩 서버 중지 스크립트. 기본 포트 8082.
# 원본: /workspace/course/week4/stop_embed_server.sh 를 참고해 이 저장소 맥락으로 재작성함.
# 실행 중이 아니어도 오류 없이 종료함.
#
# 사용법: bash deploy/stop_embed_server.sh
#
# 환경변수 오버라이드:
#   EMBED_PORT    포트 (기본 8082)
#   RESULTS_DIR   로그·PID 디렉터리 (기본 <repo>/results)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PORT="${EMBED_PORT:-8082}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results}"
PID_FILE="${RESULTS_DIR}/embed-server.pid"

stopped=0

if [ -f "${PID_FILE}" ]; then
    PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
        kill "${PID}" 2>/dev/null || true
        # 정상 종료를 잠시 기다린 뒤 남아 있으면 강제 종료함.
        for _ in $(seq 1 10); do
            kill -0 "${PID}" 2>/dev/null || break
            sleep 0.5
        done
        kill -9 "${PID}" 2>/dev/null || true
        echo "[OK] 임베딩 서버 중지함 (PID ${PID})"
        stopped=1
    else
        echo "[안내] PID 파일은 있으나 프로세스(${PID:-없음})가 이미 종료됨."
    fi
    rm -f "${PID_FILE}"
fi

# PID 파일이 유실된 경우를 위한 폴백 — 포트를 물고 있는 llama-server 만 정리함.
if [ "${stopped}" -eq 0 ]; then
    if pkill -f "llama-server.*--port ${PORT}" 2>/dev/null; then
        echo "[OK] 포트 ${PORT} llama-server 프로세스를 정리함(폴백)."
        stopped=1
    fi
fi

if [ "${stopped}" -eq 0 ]; then
    echo "[안내] 실행 중인 임베딩 서버가 없음 — 조치 불필요."
fi

exit 0
