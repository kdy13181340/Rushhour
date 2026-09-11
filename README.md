# Rushhour — 서울 가로수 테마길 추천 에이전트

자연어로 지역·계절·취향을 말하면(예: "강남구에서 봄에 벚꽃 예쁜 길") 서울 가로수
데이터로 **테마 산책길을 추천**하고, 지도를 그 위치로 옮겨 가로수를 표시하는 에이전트.

`/workspace/course`에서 배운 스택 기반: langgraph 에이전트(w5·w6) + @tool + Streamlit(w8).
채점축은 week6과 동일 — **"데이터로 답할 수 없는 것은 지어내지 않고 모른다고 말한다".**

## 구성

```
data/seoul_tree_data.csv     서울 가로수 위치(28.7만 그루, 27자치구, cp949)
app/
  themes.py        테마 8종 정의(선호/회피 수종·계절)          — 공통
  tools.py         CSV 로드 + find_theme_streets/check_coverage(@tool) — A
  map_api.py       지도 마커/히트맵 좌표 헬퍼(@tool 아님, UI용)   — A↔C
  llm.py           get_chat_model (로컬 8080 / Gemini / OpenAI) — 공통
  graph.py         langgraph 에이전트(intake→researcher→resolver) — B
  app_streamlit.py 지도(pydeck)+채팅 UI (Streamlit, 초기 버전)   — C
  README.md        상세 문서·결정지점(DP)·팀 인터페이스
api.py             FastAPI — web/에 데이터·에이전트를 연결 (/api/*)   — C
web/               Figma 디자인을 옮긴 정적 프론트(Leaflet, 바닐라 JS) — C
figma/             Figma Make에서 내려받은 디자인 원본(React+Vite) — 참고용
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
# 웹 UI (Figma 디자인) — 9000
cd /workspace/course && bash final_prj/start_web.sh        # 끄기: bash final_prj/stop_web.sh

# 에이전트만 CLI로 시험 (샘플 질의 자동 실행)
cd final_prj/app && AGENT_CHANNEL=local python graph.py

# (초기 버전) Streamlit UI
AGENT_CHANNEL=local python -m streamlit run app_streamlit.py \
  --server.port 9000 --server.address 0.0.0.0 --server.headless true \
  --server.enableCORS false --server.enableXsrfProtection false
```

### 웹 UI와 Figma 디자인의 관계

`figma/서울 벚꽃길 추천 시스템/`은 Figma Make가 만든 React+Vite 앱이다. 파드에 Node가 없어
빌드하지 않고, `App.tsx`의 화면·인라인 스타일을 `web/index.html`·`styles.css`·`app.js`로,
`TreeMarkers.tsx`의 수종 SVG를 `web/trees.js`로 손으로 옮겼다. 색·치수·동작은 시안 그대로다.

시안에 박혀 있던 목업은 쓰지 않는다 — 전부 `api.py`가 원자료에서 만든다:

| 시안 목업 | 실제 값의 출처 |
|---|---|
| 가로수 총계 219,447 · 커버 구 25 | CSV 집계 (287,635그루 · 25개 자치구) |
| 노선당 4~5점짜리 직선 폴리라인 | 그 노선의 나무 좌표를 주축(PCA)에 세워 접은 중심선 (`api.centerline`) |
| 하드코딩된 자치구·노선·그루 수 | `tools.find_theme_streets` 상위 노선 |
| 키워드 매칭 챗봇 | langgraph 에이전트(8080) → 없으면 키워드 폴백 |
| 나무 그림을 선 위에 흩뿌림 | 그림은 시안 SVG, **위치는 실제 나무 좌표** (배율 따라 솎음) |

시안과 달리한 곳: CARTO 타일은 이제 키 없이는 워터마크가 찍혀 Esri Light Gray Canvas로
바꿨고, 에이전트가 자치구를 집어내면(예: "강남구 벚꽃길") 지도도 그 구로 좁혀 그린다.

> **Runpod 등 프록시 뒤에서 화면이 빈 채로 뜨면** `--server.enableCORS false
> --server.enableXsrfProtection false`가 필요하다(WebSocket Origin 거부 방지).
> 접속은 노출된 포트(예: 9000)의 프록시 URL로 한다.

웹 UI는 8080이 없어도 화면·지도·추천이 전부 동작한다(채팅만 키워드 폴백으로 내려간다).

## 담당

- **A 데이터/도구**: `tools.py`·`map_api.py` (노선 단위 집계 → 추후 좌표 경로탐색 확장)
- **B 에이전트**: `graph.py` (의도추출·라우팅·"모르면 모른다"), `[DP1~3]` 마커 참고
- **C UI**: `api.py` + `web/` (Figma 디자인 이식·지도·채팅), `app_streamlit.py`(초기 버전)

벡터DB(RAG) 연동 시 검색 도구 `search_places(@tool)` 하나만 추가 — 상세는 `app/README.md`.
