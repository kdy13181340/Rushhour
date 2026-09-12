#!/usr/bin/env bash
#
# Rushhour 자체 인프라 — 에이전트(LLM) 서버 중지 스크립트. 기본 포트 8080.
# 원본: /workspace/course/week5/stop_agent_server.sh 를 참고해 이 저장소 맥락으로 재작성함.
#
# 사용법: bash deploy/stop_agent_server.sh
# 원칙: 쓰고 나면 끔. 다음 사람(다음 작업)이 GPU 를 쓸 수 있어야 함.
#
# 환경변수 오버라이드:
#   AGENT_PORT    포트 (기본 8080)
#   RESULTS_DIR   로그·PID 디렉터리 (기본 <repo>/results)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PORT="${AGENT_PORT:-8080}"
RESULTS_DIR="${RESULTS_DIR:-${REPO_ROOT}/results}"
PID_FILE="${RESULTS_DIR}/agent-server.pid"

stopped=0

if [ -f "${PID_FILE}" ]; then
    PID="$(cat "${PID_FILE}" 2>/dev/null || true)"
    if [ -n "${PID}" ] && kill -0 "${PID}" 2>/dev/null; then
        kill "${PID}" 2>/dev/null || true
        # 정상 종료를 잠시 기다린 뒤에도 살아 있으면 강제 종료함.
        for _ in $(seq 1 10); do
            kill -0 "${PID}" 2>/dev/null || break
            sleep 1
        done
        if kill -0 "${PID}" 2>/dev/null; then
            kill -9 "${PID}" 2>/dev/null || true
            echo "[OK] 에이전트 서버 강제 종료함 (PID ${PID})"
        else
            echo "[OK] 에이전트 서버 종료함 (PID ${PID})"
        fi
        stopped=1
    else
        echo "[안내] PID 파일은 있으나 해당 프로세스가 없음 — 이미 종료된 상태임."
    fi
    rm -f "${PID_FILE}"
else
    echo "[안내] PID 파일 없음: ${PID_FILE}"
fi

# PID 파일을 신뢰하지 않고 포트를 기준으로 한 번 더 확인함.
# 손으로 띄웠거나·파드 재시작으로 파일만 남았거나·랩퍼 셸 PID 가 기록된 경우 PID 파일이
# 어긋날 수 있음. 포트가 사실의 기준임.
port_pids() {
    ss -ltnpH "sport = :${PORT}" 2>/dev/null \
        | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u || true
}

LEFTOVER="$(port_pids)"
if [ -n "${LEFTOVER}" ]; then
    echo "[안내] 포트 ${PORT}을 아직 잡고 있는 프로세스가 있음: ${LEFTOVER//$'\n'/ }"
    for pid in ${LEFTOVER}; do
        # 엉뚱한 프로세스를 죽이지 않도록 llama-server 인지 확인한 뒤에만 종료함.
        name="$(ps -p "${pid}" -o comm= 2>/dev/null || true)"
        case "${name}" in
            *llama-server*)
                kill "${pid}" 2>/dev/null && echo "  종료 요청: ${name} (PID ${pid})" || true
                stopped=1
                ;;
            *)
                echo "  건너뜀: ${name:-알 수 없음} (PID ${pid}) — llama-server 가 아님"
                ;;
        esac
    done
    # 포트가 실제로 풀릴 때까지 기다림(프로세스 종료와 포트 해제는 별개임).
    for _ in $(seq 1 15); do
        [ -z "$(port_pids)" ] && break
        sleep 1
    done
    for pid in $(port_pids); do
        name="$(ps -p "${pid}" -o comm= 2>/dev/null || true)"
        case "${name}" in
            *llama-server*) kill -9 "${pid}" 2>/dev/null && echo "  강제 종료: PID ${pid}" || true ;;
        esac
    done
    sleep 1
fi

if [ -n "$(port_pids)" ]; then
    echo "[경고] 포트 ${PORT}이 아직 점유되어 있음."
    echo "조치: 'ss -ltnp | grep :${PORT}'로 확인한 뒤 해당 PID 를 직접 종료할 것."
    exit 1
fi

if [ "${stopped}" -eq 1 ]; then
    FREE_MIB="$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null | head -n1 || true)"
    [ -n "${FREE_MIB}" ] && echo "[정보] GPU 여유 메모리: ${FREE_MIB} MiB"
fi

echo "[완료] 포트 ${PORT} 비어 있음."
