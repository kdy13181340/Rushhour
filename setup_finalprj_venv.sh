#!/usr/bin/env bash
# [EXEMPT: peripheral]
#
# 최종 프로젝트 전용 venv 생성·복구 스크립트. 멱등임(여러 번 실행해도 안전함).
# 6주차 week6/setup_midterm_venv.sh와 같은 방식임 — 경로와 점검 대상만 다름.
#
# 하는 일:
#   1) course venv를 '동결'해 목록으로 남김          -> final_prj/venv/inherited.txt (볼륨)
#   2) 같은 파이썬으로 빈 venv를 새로 만듦            -> /root/venvs/final  (컨테이너 디스크)
#   3) 동결 목록을 그 venv에 설치함                   -> course venv와 같은 출발선
#   4) requirements.txt(레포 공용) -> venv/extras.txt(내 추가) 순으로 설치함
#
# course venv(/root/venvs/course)는 읽기만 함 — 한 글자도 건드리지 않음.
#
# 사용법:
#   cd /workspace/course
#   bash final_prj/setup_finalprj_venv.sh              # 생성 또는 복구
#   bash final_prj/setup_finalprj_venv.sh --refresh    # 동결 목록을 다시 뜸
#   bash final_prj/setup_finalprj_venv.sh --recreate   # venv를 지우고 처음부터
#   bash final_prj/setup_finalprj_venv.sh --no-base-check
set -uo pipefail

VENV=/root/venvs/final
COURSE_VENV=/root/venvs/course
RECIPE_DIR=/workspace/course/final_prj/venv
INHERITED="${RECIPE_DIR}/inherited.txt"
EXTRAS="${RECIPE_DIR}/extras.txt"

REFRESH=0; RECREATE=0; BASE_CHECK=1
for arg in "$@"; do
    case "$arg" in
        --refresh)        REFRESH=1 ;;
        --recreate)       RECREATE=1 ;;
        --no-base-check)  BASE_CHECK=0 ;;
        *) echo "[중단] 모르는 인자: $arg"; exit 1 ;;
    esac
done

export UV_CACHE_DIR="${UV_CACHE_DIR:-/opt/uv-cache}"
export HF_HOME="${HF_HOME:-/workspace/hf}"

START_TS=$(date +%s)
echo "=== 1/5 사전 점검 ==="

if [ ! -f "pyproject.toml" ] || [ ! -d "final_prj" ]; then
    echo "[중단] /workspace/course에서 실행할 것."
    echo "조치: cd /workspace/course && bash final_prj/setup_finalprj_venv.sh"
    exit 1
fi
if ! command -v uv >/dev/null 2>&1; then
    echo "[중단] uv를 찾지 못함 — 이 파드의 이미지가 코스 이미지가 맞는지 확인할 것."
    exit 1
fi
if [ ! -x "${COURSE_VENV}/bin/python" ]; then
    echo "[중단] ${COURSE_VENV}/bin/python 없음 — course venv가 이 파드에 없음."
    exit 1
fi
echo "[OK] course venv : ${COURSE_VENV}  ($("${COURSE_VENV}/bin/python" -V))"
echo "[OK] uv 캐시     : ${UV_CACHE_DIR}"

# 프론트 계층이 기대는 것은 pandas임 — 없으면 상속해 봐야 반쪽이므로 여기서 잡아 줌.
if [ "${BASE_CHECK}" -eq 1 ]; then
    if ! "${COURSE_VENV}/bin/python" -c "import pandas" >/dev/null 2>&1; then
        echo
        echo "[중단] course venv에 pandas가 없음."
        echo "조치: bash week4/setup_week4.sh 등으로 코스 환경을 먼저 복구할 것."
        echo "      (강사용: --no-base-check 로 건너뛸 수 있음)"
        exit 1
    fi
    echo "[OK] pandas 확인됨 ($("${COURSE_VENV}/bin/python" -c 'import pandas;print(pandas.__version__)'))"
fi

# 자료가 없으면 화면을 띄워도 볼 것이 없음 — 미리 알려 줌.
CSV=/workspace/course/final_prj/data/seoul_tree_data.csv
if [ -f "${CSV}" ]; then
    echo "[OK] 자료 확인됨  : ${CSV} ($(du -h "${CSV}" | cut -f1))"
else
    echo "[경고] ${CSV} 없음 — 화면은 뜨지만 집계가 비게 됨."
fi

mkdir -p "${RECIPE_DIR}"

echo
echo "=== 2/5 course venv 동결 ==="
if [ -f "${INHERITED}" ] && [ "${REFRESH}" -eq 0 ]; then
    echo "[건너뜀] ${INHERITED} 가 이미 있음($(grep -cv '^\s*#' "${INHERITED}") 줄)."
    echo "         course venv가 바뀌어 다시 뜨려면 --refresh 를 줄 것."
else
    if ! uv pip freeze --python "${COURSE_VENV}/bin/python" > "${INHERITED}.tmp" 2>/dev/null; then
        echo "[실패] course venv 동결에 실패함."
        rm -f "${INHERITED}.tmp"; exit 1
    fi
    {
        echo "# course venv 동결 목록 — $(date '+%Y-%m-%d %H:%M')"
        echo "# 출처: ${COURSE_VENV}  ($("${COURSE_VENV}/bin/python" -V))"
        echo "# 이 파일은 손으로 고치지 말 것. 추가 패키지는 extras.txt에 적을 것."
        cat "${INHERITED}.tmp"
    } > "${INHERITED}"
    rm -f "${INHERITED}.tmp"
    echo "[OK] ${INHERITED} 작성($(grep -cv '^\s*#' "${INHERITED}") 종)"
fi

if [ ! -f "${EXTRAS}" ]; then
    printf '# 최종 프로젝트 추가 패키지 목록임.\nstreamlit>=1.63.0\n' > "${EXTRAS}"
    echo "[OK] ${EXTRAS} 생성(streamlit)"
fi

echo
echo "=== 3/5 최종 프로젝트 venv 준비 ==="
if [ "${RECREATE}" -eq 1 ] && [ -d "${VENV}" ]; then
    echo "[정보] --recreate — 기존 ${VENV} 삭제함"
    rm -rf "${VENV}"
fi
if [ -x "${VENV}/bin/python" ]; then
    echo "[건너뜀] ${VENV} 가 이미 있음"
else
    if ! uv venv "${VENV}" --python "${COURSE_VENV}/bin/python" >/dev/null 2>&1; then
        echo "[실패] venv 생성 실패 — 디스크 여유를 확인할 것(df -h /)."
        exit 1
    fi
    echo "[OK] ${VENV} 생성(course venv와 같은 파이썬)"
fi

echo
echo "=== 4/5 설치 ==="
echo "  (1) 상속분 — inherited.txt"
if ! uv pip install --python "${VENV}/bin/python" -r "${INHERITED}" 2>&1 | tail -2; then
    echo "[실패] 상속분 설치 실패."; exit 1
fi

REQS=/workspace/course/final_prj/requirements.txt
if [ -f "${REQS}" ]; then
    echo "  (2) 레포 공용 — requirements.txt"
    if ! uv pip install --python "${VENV}/bin/python" -r "${REQS}" 2>&1 | tail -2; then
        echo "[실패] requirements.txt 설치 실패."; exit 1
    fi
else
    echo "  (2) 레포 공용 — requirements.txt 없음"
fi

EXTRA_COUNT=$(grep -cve '^\s*#' -e '^\s*$' "${EXTRAS}" || true)
if [ "${EXTRA_COUNT}" -gt 0 ]; then
    echo "  (3) 추가분 — extras.txt (${EXTRA_COUNT}종)"
    if ! uv pip install --python "${VENV}/bin/python" -r "${EXTRAS}" 2>&1 | tail -2; then
        echo "[실패] 추가분 설치 실패 — extras.txt의 이름과 철자를 확인할 것."
        exit 1
    fi
else
    echo "  (3) 추가분 — 없음(extras.txt가 비어 있음)"
fi

echo
echo "=== 5/5 검증 ==="
"${VENV}/bin/python" - <<'PY'
import importlib, sys
need = ["pandas", "streamlit", "altair", "pydeck", "langgraph",
        "langchain_core", "langchain_openai"]
missing = []
for name in need:
    try:
        mod = importlib.import_module(name)
        print(f"  [OK]   {name} {getattr(mod, '__version__', '')}")
    except Exception as exc:
        print(f"  [경고] {name} — {type(exc).__name__}")
        missing.append(name)
sys.exit(1 if ("pandas" in missing or "streamlit" in missing) else 0)
PY
RC=$?

if "${COURSE_VENV}/bin/python" -c "import pandas" >/dev/null 2>&1; then
    echo "  [OK]   course venv 정상(건드리지 않았음)"
fi

ELAPSED=$(( $(date +%s) - START_TS ))
echo
echo "════════════════════════════════════════════════════════"
if [ "${RC}" -ne 0 ]; then
    echo "[경고] 필수 패키지를 임포트하지 못함 — 위 목록을 확인할 것."
fi
echo "[완료] 최종 프로젝트 venv 준비 완료 (소요 ${ELAPSED}초)"
echo "  인터프리터: ${VENV}/bin/python"
echo
echo "  이번 세션에서 'pyf' 별칭을 쓰려면:"
echo "    source final_prj/env_final.sh"
echo "  도구만 점검(LLM 불필요):"
echo "    bash final_prj/check_app.sh"
echo "  화면 띄우기(8501):"
echo "    bash final_prj/start_app.sh"
echo "════════════════════════════════════════════════════════"
