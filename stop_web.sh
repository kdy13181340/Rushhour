#!/usr/bin/env bash
# [EXEMPT: peripheral]
# 웹 프론트(9000)를 내린다. 쓰고 나면 끄는 것이 코스 규약임.
set -uo pipefail
PID_FILE=/workspace/course/results/final-web.pid
PORT="${1:-9000}"
if [ -f "${PID_FILE}" ] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    kill "$(cat "${PID_FILE}")" 2>/dev/null; sleep 1
    kill -9 "$(cat "${PID_FILE}")" 2>/dev/null
    echo "[OK] pid $(cat "${PID_FILE}") 종료함"; rm -f "${PID_FILE}"
else
    pkill -f "uvicorn api:app" && echo "[OK] 종료함" || echo "[안내] 떠 있는 서버가 없음"
fi
ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q ":${PORT}" && echo "[경고] ${PORT}이 아직 열려 있음"
exit 0
