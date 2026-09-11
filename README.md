# Rushhour — 서울 가로수 테마길 추천 에이전트

자연어로 지역·계절·취향을 말하면(예: "강남구에서 봄에 벚꽃 예쁜 길") 서울 가로수
데이터로 **테마 산책길을 추천**하고, 지도를 그 위치로 옮겨 가로수를 표시하는 에이전트.

`/workspace/course`에서 배운 스택 기반: langgraph 에이전트(w5·w6) + @tool + Streamlit(w8).
채점축은 week6과 동일 — **"데이터로 답할 수 없는 것은 지어내지 않고 모른다고 말한다".**

## 구성

```
data/seoul_tree_data.csv     서울 가로수 위치(28.7만 그루, 27자치구, cp949)
app/
  themes.py        테마 6종 정의(선호/회피 수종·계절)          — 공통
  tools.py         CSV 로드 + find_theme_streets/check_coverage(@tool) — A
  map_api.py       지도 마커/히트맵 좌표 헬퍼(@tool 아님, UI용)   — A↔C
  llm.py           get_chat_model (로컬 8080 / Gemini / OpenAI) — 공통
  graph.py         langgraph 에이전트(intake→researcher→resolver) — B
  app_streamlit.py 지도(pydeck)+채팅 UI                          — C
  README.md        상세 문서·결정지점(DP)·팀 인터페이스
```

## 세팅 (팀원 공통)

```bash
# 1) 의존성 (코스 venv 또는 새 venv)
uv pip install -r requirements.txt          # pip install -r requirements.txt 도 가능

# 2) (채팅용) 로컬 에이전트 서버 8080 — 자연어 채팅에 필요
bash /workspace/course/week5/start_agent_server.sh
#    API로 대체 가능:  export AGENT_CHANNEL=gemini GEMINI_API_KEY=...   (또는 openai)
```

데이터는 저장소에 포함(`data/seoul_tree_data.csv`). 원본 xlsx는 서울 열린데이터광장
「2026 서울시 가로수 위치정보」.

## 실행

```bash
cd app

# 에이전트만 CLI로 시험 (샘플 질의 자동 실행)
AGENT_CHANNEL=local python graph.py

# 웹 UI (지도+채팅)
AGENT_CHANNEL=local python -m streamlit run app_streamlit.py \
  --server.port 9000 --server.address 0.0.0.0 --server.headless true \
  --server.enableCORS false --server.enableXsrfProtection false
```

> **Runpod 등 프록시 뒤에서 화면이 빈 채로 뜨면** `--server.enableCORS false
> --server.enableXsrfProtection false`가 필요하다(WebSocket Origin 거부 방지).
> 접속은 노출된 포트(예: 9000)의 프록시 URL로 한다.

사이드바 **‘빠른 추천’**은 LLM 없이 도구만 호출하므로 8080 없이도 지도 데모가 된다.

## 담당

- **A 데이터/도구**: `tools.py`·`map_api.py` (노선 단위 집계 → 추후 좌표 경로탐색 확장)
- **B 에이전트**: `graph.py` (의도추출·라우팅·"모르면 모른다"), `[DP1~3]` 마커 참고
- **C UI**: `app_streamlit.py` (지도 이동·마커·채팅)

벡터DB(RAG) 연동 시 검색 도구 `search_places(@tool)` 하나만 추가 — 상세는 `app/README.md`.
