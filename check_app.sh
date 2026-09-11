#!/usr/bin/env bash
# [EXEMPT: peripheral]
# LLM(8080) 없이 데이터·도구 계층만 점검함. 화면을 띄우기 전에 여기부터 통과시킬 것.
# 사용법: cd /workspace/course && bash final_prj/check_app.sh
set -uo pipefail
PRJ=/workspace/course/final_prj
export PYTHONPATH="${PRJ}/app"
export TREE_CSV="${PRJ}/data/seoul_tree_data.csv"
cd "${PRJ}/app"
/root/venvs/final/bin/python tools.py && echo && /root/venvs/final/bin/python map_api.py
