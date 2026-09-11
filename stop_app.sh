#!/usr/bin/env bash
# [EXEMPT: peripheral]
#
# 8501 Streamlit 화면을 내림. 쓰고 나면 끄는 것이 코스 규약임.
# 사용법: cd /workspace/course && bash final_prj/stop_app.sh
set -uo pipefail

PID_FILE=/workspace/course/results/final-app.pid
PORT="${1:-8501}"

if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null
    sleep 1
    kill -9 "$(cat "${PID_FILE}")" 2>/dev/null
    echo "[OK] pid $(cat "${PID_FILE}") 종료함"
    rm -f "${PID_FILE}"
else
    echo "[안내] pid 파일이 없음 — 포트로 찾아 봄."
    pkill -f "streamlit run .*final_prj/app/app_streamlit.py" && echo "[OK] 종료함" || echo "[안내] 떠 있는 화면이 없음"
fi

if ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q ":${PORT}"; then
    echo "[경고] ${PORT}이 아직 열려 있음 — 다른 프로세스가 물고 있을 수 있음."
fi
