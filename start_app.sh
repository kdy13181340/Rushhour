#!/usr/bin/env bash
# [EXEMPT: peripheral]
#
# Rushhour 테마길 화면(app/app_streamlit.py)을 8501에 띄움. 최종 프로젝트 venv(pyf)로 구동함.
# 8주차 week8/start_api.sh와 같은 형태임 — 포트를 먼저 점검하고, 로그와 pid를 results/에 남김.
#
# 사용법: cd /workspace/course && bash final_prj/start_app.sh [--fg] [--port N]
#   --fg       포그라운드(Ctrl+C로 끔). 기본은 백그라운드임.
#   --port N   기본 8501. 레포 README와 팀 데모는 9000을 씀 — 비교할 때는 --port 9000.
# 채팅(LLM)에는 8080이 필요함 — 없어도 사이드바 '빠른 추천'과 지도는 동작함.
set -uo pipefail

VENV=/root/venvs/final
PRJ=/workspace/course/final_prj
RESULTS=/workspace/course/results
PORT="${APP_PORT:-8501}"
LOG_FILE="${RESULTS}/final-app.log"
PID_FILE="${RESULTS}/final-app.pid"


FG=0
while [ $# -gt 0 ]; do
    case "$1" in
        --fg)   FG=1; shift ;;
        --port) PORT="${2:?--port 뒤에 포트 번호를 줄 것}"; shift 2 ;;
        *) echo "[중단] 모르는 인자: $1"; exit 1 ;;
    esac
done

if [ ! -x "${VENV}/bin/python" ]; then
    echo "[중단] ${VENV} 없음."
    echo "조치: bash final_prj/setup_finalprj_venv.sh"
    exit 1
fi
if [ ! -f "${PRJ}/app/app_streamlit.py" ]; then
    echo "[중단] ${PRJ}/app/app_streamlit.py 를 찾지 못함."; exit 1
fi

mkdir -p "${RESULTS}"

if ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q ":${PORT}"; then
    echo "[안내] ${PORT}이 이미 사용 중임."
    echo "조치: 'bash final_prj/stop_app.sh' 후 다시 실행할 것."
    exit 1
fi

# app/ 안의 모듈(themes·tools·graph)이 서로 임포트되므로 app/을 경로에 넣음.
export PYTHONPATH="${PRJ}/app${PYTHONPATH:+:${PYTHONPATH}}"
# .streamlit/config.toml(테마)은 실행 디렉터리 기준으로 읽힌다 — 프로젝트 루트에서 띄운다.
cd "${PRJ}"
export TREE_CSV="${TREE_CSV:-${PRJ}/data/seoul_tree_data.csv}"
export AGENT_CHANNEL="${AGENT_CHANNEL:-local}"

# 프록시 뒤(Runpod)에서 WebSocket Origin 거부로 화면이 비는 것을 막음 — 레포 README 주의사항.
ARGS=(-m streamlit run "${PRJ}/app/app_streamlit.py"
      --server.port "${PORT}"
      --server.address 0.0.0.0
      --server.headless true
      --server.enableCORS false
      --server.enableXsrfProtection false
      --browser.gatherUsageStats false)

if [ "${FG}" -eq 1 ]; then
    echo "[실행] 포그라운드 — Ctrl+C로 끔. http://localhost:${PORT}"
    exec "${VENV}/bin/python" "${ARGS[@]}"
fi

nohup "${VENV}/bin/python" "${ARGS[@]}" > "${LOG_FILE}" 2>&1 &
echo $! > "${PID_FILE}"
echo "[실행] pid $(cat "${PID_FILE}") · 로그 ${LOG_FILE}"

for _ in $(seq 1 40); do
    if ss -ltn "sport = :${PORT}" 2>/dev/null | grep -q ":${PORT}"; then
        echo "[OK] http://localhost:${PORT} 에서 응답함  (AGENT_CHANNEL=${AGENT_CHANNEL})"
        if ! ss -ltn "sport = :8080" 2>/dev/null | grep -q ":8080"; then
            echo "[안내] 8080이 없음 — 채팅은 실패함. 사이드바 '빠른 추천'과 지도는 동작함."
            echo "       채팅까지 쓰려면: bash week5/start_agent_server.sh"
        fi
        echo "     끄기: bash final_prj/stop_app.sh"
        exit 0
    fi
    sleep 1
done
echo "[경고] ${PORT}이 아직 열리지 않음 — 로그를 볼 것: tail -30 ${LOG_FILE}"
exit 1
