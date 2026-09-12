#!/usr/bin/env bash
#
# Rushhour 자체 인프라 — 두 서버(에이전트 8080 + 임베딩 8082)를 한 번에 중지.
#
# 사용법: bash deploy/down.sh
# 개별 포트 오버라이드는 각 stop_*.sh 의 AGENT_PORT / EMBED_PORT 를 그대로 사용함.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "### 임베딩 서버 중지 ###"
bash "${SCRIPT_DIR}/stop_embed_server.sh"

echo "### 에이전트 서버 중지 ###"
bash "${SCRIPT_DIR}/stop_agent_server.sh"

echo "[완료] 두 서버 중지 요청 완료."
