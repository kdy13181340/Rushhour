# [EXEMPT: peripheral]
#
# 최종 프로젝트 전용 셸 환경. 실행하지 말고 'source' 할 것 — 별칭은 자식 프로세스에 남지 않음.
#   source final_prj/env_final.sh
#
# 6주차 week6/env_midterm.sh와 같은 구조임. 다른 것은 venv 경로와 별칭 이름뿐임.
#   pyc = 코스 공용 venv (10주 전체가 공유 — 건드리지 않음)
#   pym = 6주차 미드텀 venv
#   pyf = 최종 프로젝트 venv  ← 이 파일이 선언하는 것
FINAL_VENV=/root/venvs/final

if [ ! -x "${FINAL_VENV}/bin/python" ]; then
    echo "[안내] ${FINAL_VENV} 가 없음."
    echo "  조치: cd /workspace/course && bash final_prj/setup_finalprj_venv.sh"
else
    alias pyf="${FINAL_VENV}/bin/python"
    export UV_CACHE_DIR="${UV_CACHE_DIR:-/opt/uv-cache}"
    export HF_HOME="${HF_HOME:-/workspace/hf}"
    # final_prj/의 모듈(tree_themes 등)을 /workspace/course에서 실행해도 임포트되게 함.
    export PYTHONPATH="/workspace/course/final_prj${PYTHONPATH:+:${PYTHONPATH}}"
    echo "[OK] pyf -> ${FINAL_VENV}/bin/python"
    echo "     실행은 /workspace/course 에서 'pyf final_prj/....py' 형태로 할 것."
    echo "     화면: bash final_prj/start_app.sh   (8501)"
fi
