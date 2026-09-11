#!/usr/bin/env bash
# [EXEMPT: peripheral]
#
# 서울 가로수길 웹 프론트(FastAPI + 정적 web/)를 9000에 띄운다.
# 8주차 week8/start_api.sh와 같은 형태 — 포트를 먼저 점검하고 로그·pid를 results/에 남긴다.
#
# 사용법: cd /workspace/course && bash final_prj/start_web.sh [--fg] [--port N]
#
# 채팅은 8080 에이전트가 있으면 langgraph 전체 경로를, 없으면 키워드 폴백을 쓴다.
# (8080 없이도 화면·지도·추천이 전부 동작한다.)
set -uo pipefail

VENV=/root/venvs/final
PRJ=/workspace/course/final_prj
RESULTS=/workspace/course/results
PORT="${WEB_PORT:-9000}"
LOG_FILE="${RESULTS}/final-web.log"
PID_FILE="${RESULTS}/final-web.pid"

FG=0
while [ $# -gt 0 ]; do
    case "$1" in
        --fg)   FG=1; shift ;;
        --port) PORT="${2:?--port 뒤에 포트 번호를 줄 것}"; shift 2 ;;
        *) echo "[중단] 모르는 인자: $1"; exit 1 ;;
    esac
done

if [ ! -x "${VENV}/bin/python" ]; then
    echo "[중단] ${VENV} 없음.  조치: bash final_prj/setup_finalprj_venv.sh"; exit 1
fi
mkdir -p "${RESULTS}"

if ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q ":${PORT}"; then
    echo "[안내] ${PORT}이 이미 사용 중임."
    echo "조치: 'bash final_prj/stop_web.sh' 후 다시 실행할 것."
    exit 1
fi

export PYTHONPATH="${PRJ}:${PRJ}/app${PYTHONPATH:+:${PYTHONPATH}}"
export TREE_CSV="${TREE_CSV:-${PRJ}/data/seoul_tree_data.csv}"
export AGENT_CHANNEL="${AGENT_CHANNEL:-local}"
cd "${PRJ}"

ARGS=(-m uvicorn api:app --host 0.0.0.0 --port "${PORT}")

if [ "${FG}" -eq 1 ]; then
    echo "[실행] 포그라운드 — Ctrl+C로 끔. http://localhost:${PORT}"
    exec "${VENV}/bin/python" "${ARGS[@]}"
fi

nohup "${VENV}/bin/python" "${ARGS[@]}" > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"
echo "[실행] pid $(cat "${PID_FILE}") · 로그 ${LOG_FILE}"

for _ in $(seq 1 60); do
    if curl -fsS "http://localhost:${PORT}/api/health" >/dev/null 2>&1; then
        echo "[OK] http://localhost:${PORT} 에서 응답함"
        if ! ss -ltn "sport = :8080" 2>/dev/null | grep -q ":8080"; then
            echo "[안내] 8080이 없음 — 채팅은 키워드 폴백으로 동작함."
            echo "       LLM까지 쓰려면: bash week5/start_agent_server.sh"
        fi
        echo "     끄기: bash final_prj/stop_web.sh"
        exit 0
    fi
    sleep 1
done
echo "[경고] 아직 응답이 없음 — 로그를 볼 것: tail -30 ${LOG_FILE}"
exit 1
