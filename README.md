# Rushhour — 서울 가로수 테마길 추천 에이전트

자연어로 지역·계절·취향을 말하면(예: "강남구에서 봄에 벚꽃 예쁜 길") 서울 가로수
데이터로 **테마 산책길을 추천**하고, 지도를 그 위치로 옮겨 가로수를 표시하는 에이전트.

`/workspace/course`에서 배운 스택 기반: langgraph 에이전트(w5·w6) + @tool + Streamlit(w8).
**미션은 "좋은 테마 산책길 추천"**이며, 데이터에 없는 도로·좌표를 지어내지 않는 것(환각 방지)은
품질 원칙으로 유지한다. 데이터가 서울뿐이라 범위 밖 질문은 막지 않고 대안을 제안한다.

## 구성

```
data/seoul_tree_data.csv       서울 가로수 위치 원본(28.7만 그루, cp949)
data/processed/*.parquet       scripts/01 산출물(정제본, gitignore)
scripts/01_csv_to_parquet.py   CSV→Parquet + 관리기관 행 12,946건의 구 복원      — A
app/
  themes.py        테마 6종 정의(선호/회피 수종·계절 키·키워드)     — 공통
  tools.py         데이터 로드 + find_theme_streets/check_coverage(@tool) — A
  map_api.py       지도 마커/히트맵 좌표 헬퍼(@tool 아님, UI용)      — A↔C
  llm.py           get_chat_model (로컬 8080 / Gemini / OpenAI)    — 공통
  graph.py         langgraph supervisor 그래프(season·intake·researcher·light·resolver) — B
  app_streamlit.py 지도(pydeck)+채팅 UI — FastAPI 클라이언트          — C
backend/
  main.py          FastAPI: /chat(SSE) /tools/* /health /threads   — BE
  trace.py         궤적: JSONL(기본) | Langfuse
tests/             LLM 없이 도는 25건 (도구·라우터·API)
docs/BE_DESIGN.md  설계 v2 · docs/DECISIONS.md 결정 기록
```

## 세팅 (팀원 공통)

```bash
# 1) 프로젝트 venv (코스 venv는 그대로 두고 별도로)
uv venv --python 3.12 /root/venvs/rushhour
uv pip install --python /root/venvs/rushhour/bin/python -r requirements.txt
PY=/root/venvs/rushhour/bin/python

# 2) 데이터 정제 (1회, 약 10초) → data/processed/seoul_trees.parquet
$PY scripts/01_csv_to_parquet.py

# 3) 테스트 — 모델 서버 없이 전부 통과해야 함
$PY -m pytest tests -q
```

데이터 원본은 저장소에 포함(`data/seoul_tree_data.csv`, 서울 열린데이터광장「2026 서울시 가로수 위치정보」).

## 실행

```bash
# 백엔드 (저장소 루트에서)
AGENT_CHANNEL=none  $PY -m uvicorn backend.main:app --host 0.0.0.0 --port 8000   # 모델 서버 없이: 규칙 intake + 템플릿 답변
AGENT_CHANNEL=local $PY -m uvicorn backend.main:app --host 0.0.0.0 --port 8000   # 8080 모델 서버 있을 때 (bash /workspace/course/week5/start_agent_server.sh)

# UI
RUSHHOUR_API=http://localhost:8000 $PY -m streamlit run app/app_streamlit.py \
  --server.port 9000 --server.address 0.0.0.0 --server.headless true \
  --server.enableCORS false --server.enableXsrfProtection false

# 그래프만 CLI로 (샘플 질의)
AGENT_CHANNEL=none $PY app/graph.py
```

- `AGENT_CHANNEL`: `none`(LLM 안 씀) · `local`(8080) · `gemini` · `openai`. local인데 서버가 죽어 있으면 자동으로 규칙/템플릿 폴백.
- `RUSHHOUR_SEASON=spring|summer|autumn|winter`: 계절을 강제(데모·테스트). 기본은 오늘 날짜.
- `TRACE_BACKEND=jsonl|langfuse|none`: 궤적은 기본 `results/rushhour_trace.jsonl`.
- `/health`의 `chat_mode`가 `rule`이면 UI 사이드바에 규칙 모드 배지가 뜬다. 지도는 어느 모드에서도 나온다.

> **Runpod 등 프록시 뒤에서 화면이 빈 채로 뜨면** `--server.enableCORS false
> --server.enableXsrfProtection false`가 필요하다(WebSocket Origin 거부 방지).

## 담당

- **A 데이터/도구**: `scripts/01`·`tools.py`·`map_api.py` (노선 단위 집계 → 추후 osmnx 좌표 경로 `plan_route`)
- **B 에이전트**: `graph.py` (supervisor 규칙 라우터·intake·resolver·"모르면 모른다"), `[DP]` 마커 참고
- **BE**: `backend/` (SSE·체크포인트·폴백·궤적), 이후 `find_light_spots`(Chroma)
- **C UI**: `app_streamlit.py` (지도 이동·마커·채팅)

벡터DB(RAG) 연동 시 검색 도구 `search_places(@tool)` 하나만 추가 — 상세는 `app/README.md`.
