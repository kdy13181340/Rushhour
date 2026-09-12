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
data/eval/search_places.jsonl  검색 품질 평가 질의 18건(표기 15·의미 3)
data/chroma/<채널>/            벡터DB 인덱스(scripts/02 산출물, gitignore)
scripts/01_csv_to_parquet.py   CSV→Parquet + 관리기관 행 12,946건의 구 복원      — A
scripts/02_build_vector_db.py  (구,노선) 문서 1,780건 → Chroma 색인               — BE
scripts/03_eval_search_places.py  검색 품질 hit@k·MRR                              — BE
scripts/04_fetch_osm.py        서울 보행 도로망(OSM) 1회 내려받기 → data/osm/       — BE
scripts/05_snap_trees.py       나무 28만을 도로 간선에 붙여 간선별 테마 점수         — BE
app/
  themes.py        테마 8종 정의(선호/회피 수종·계절 키·키워드)     — 공통
  tools.py         데이터 로드 + find_theme_streets/check_coverage(@tool) — A
  map_api.py       지도 마커/히트맵 좌표 헬퍼(@tool 아님, UI용)      — A↔C
  llm.py           get_chat_model (로컬 8080 / Gemini / OpenAI)    — 공통
  embeddings.py    임베딩 채널(local 8082 / openai / gemini / st / hash)  — BE
  rag.py           Chroma 색인 + search_places(@tool) 의미검색          — BE
  routing.py       plan_route(@tool) 경로 3가지 — 최단·테마 경유·회피     — BE
  graph.py         langgraph supervisor 그래프(season·intake·researcher·light·resolver) — B
  app_streamlit.py 지도(pydeck)+채팅 UI — FastAPI 클라이언트          — C
backend/
  main.py          FastAPI: /chat(SSE) /tools/* /health /threads   — BE
  trace.py         궤적: JSONL(기본) | Langfuse
tests/             LLM·임베딩 모델·도로망 없이 도는 75건 (도구·라우터·API·멀티턴·벡터DB·경로)
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

# 4) 벡터DB 색인 (search_places용, 선택). 채널: local(8082 임베딩 서버) | st(로컬 모델) | hash(모델 없음)
EMBED_CHANNEL=local $PY scripts/02_build_vector_db.py --probe     # 8082 있을 때
$PY scripts/02_build_vector_db.py --channel hash                  # 서버·모델 없이 — 표기(동네·노선명) 검색만
$PY scripts/03_eval_search_places.py --channel hash               # 품질 평가(hit@k·MRR)

# 5) 경로 추천(출발→도착 3가지)용 도로망 (선택, 1회 약 5분 + 30초)
uv pip install --python $PY osmnx
$PY scripts/04_fetch_osm.py && $PY scripts/05_snap_trees.py        # → data/osm/
```

**Windows(PowerShell)** 에서는 파드 venv 대신 저장소 루트에 `.venv`를 만든다(`.gitignore`에 있음).
Store 스텁만 있으면 `python --version`이 비어 나오니 먼저 설치하고 **새 터미널**에서 진행한다.

```powershell
winget install Python.Python.3.12
python -m venv .venv; .venv\Scripts\python -m pip install -r requirements.txt
$env:PYTHONUTF8 = "1"                          # cp949 콘솔에서 한글·기호 출력 오류 방지
.venv\Scripts\python scripts\01_csv_to_parquet.py
$env:AGENT_CHANNEL = "none"; .venv\Scripts\python -m pytest tests -q
$env:AGENT_CHANNEL = "none"; .venv\Scripts\python -m uvicorn backend.main:app --port 8000
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
- `/chat`은 같은 `thread_id`로 계속 물어도 된다 — 턴마다 그래프 상태를 비우고 처음부터 돈다(`docs/DECISIONS.md` DP13).
- **경로 3가지**: `POST /tools/plan_route {origin, dest, season, theme}` — 빠른 도보 경로 · 그 계절 테마 경유 · 회피.
  **도보 기준**이다 — 거리에 도로 종류별 계수(보도 1.0 · 간선 2.3)를 곱한 체감 길이로 길을 고르고,
  답변에는 실제 미터·소요 시간(4km/h)·큰길 아닌 길 비율을 준다(DP19).
  지도에 그리는 선도 실제 보행 도로 형상이다(DP20).
  `data/osm/`가 없으면 `/health`의 `osm.ready`가 false이고, 채팅은 기존 회랑 방식으로 답한다(DP17).
- `EMBED_CHANNEL`: `local`(OpenAI 호환 `/v1/embeddings`, 기본)·`openai`·`gemini`·`st`(sentence-transformers, 별도 설치)·`hash`(모델 없음).
  인덱스는 채널별 `data/chroma/<채널>/`. `/health`의 `rag.ready`가 false면 그 채널로 `scripts/02`를 돌리고,
  `embed.reachable`이 false면 임베딩 서버가 죽은 것. `POST /tools/search_places {query, k, district, min_trees, size_weight}` — 결정·측정은 DP14.
- **팀 임베딩 서버(bge-m3, llama-server)**: 파드 안에서는 `EMBED_BASE_URL=http://localhost:30000/v1`, 밖에서는
  `https://i3pdrbs4uwzc7r-30000.proxy.runpod.net/v1`. `EMBED_MODEL=bge-m3`로 고정(비우면 서명이 GGUF 경로가 됨).
  ```bash
  export EMBED_CHANNEL=local EMBED_MODEL=bge-m3 EMBED_BASE_URL=http://localhost:30000/v1
  $PY scripts/02_build_vector_db.py --probe && $PY scripts/03_eval_search_places.py   # 색인 ~1분, 18건 MRR 0.81
  ```

> **Runpod 등 프록시 뒤에서 화면이 빈 채로 뜨면** `--server.enableCORS false
> --server.enableXsrfProtection false`가 필요하다(WebSocket Origin 거부 방지).

## 담당

- **A 데이터/도구**: `scripts/01`·`tools.py`·`map_api.py` (노선 단위 집계 → 추후 osmnx 좌표 경로 `plan_route`)
- **B 에이전트**: `graph.py` (supervisor 규칙 라우터·intake·resolver·"모르면 모른다"), `[DP]` 마커 참고
- **BE**: `backend/` (SSE·체크포인트·폴백·궤적) + 벡터DB(`embeddings.py`·`rag.py`·`scripts/02`·`03`), 이후 `find_light_spots`(Chroma)
- **C UI**: `app_streamlit.py` (지도 이동·마커·채팅)

벡터DB(RAG) 검색 도구 `search_places(@tool)`는 구현됨(`app/rag.py`) — 그래프 배선 지점은 `app/README.md`.
