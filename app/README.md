# 서울 가로수 테마길 에이전트 — `app/`

자연어 질문("강남구에서 봄에 벚꽃 예쁜 길")을 받아 가로수 데이터로 테마 산책길을
추천하는 langgraph 에이전트(week6 supervisor+@tool 패턴 이식).
**미션은 "좋은 테마 산책길 추천"**. 환각 방지(없는 도로·좌표를 지어내지 않음)는 품질 원칙으로
유지하고, 서울 밖 등 범위 밖 질문은 차단이 아니라 대안을 제안한다.

## 구조

```
질문 ─► supervisor ─(규칙 라우터: 울타리 → 빈 칸 순서)─► season → intake → researcher → [light] → resolver ─► END
            ▲                                            (코드)  (LLM│규칙)  (도구)     (겨울)   (LLM│템플릿)
            └──────────── 담당자가 끝나면 되돌아옴 ───────────┘
테마 판별불가 / 커버리지 밖 / 서울 밖 → 도구를 부르지 않고 resolver로 (친절 안내·대안 제안)
```
자세한 그림과 결정은 `../docs/BE_DESIGN.md` §1.

| 파일 | 역할 | 담당 |
|---|---|---|
| `themes.py` | 테마 정의(선호/회피 수종·계절) — 단일 출처 | 공통 |
| `tools.py` | 가로수 CSV 로드 + `find_theme_streets`(지오 포함) / `check_coverage` (@tool) | A(데이터) |
| `map_api.py` | 지도 마커/히트맵용 좌표 헬퍼(`street_points`,`theme_points`) — **@tool 아님, UI 전용** | A↔C |
| `llm.py` | `get_chat_model` — 코스 로컬 8080 / Gemini / OpenAI | 공통 |
| `graph.py` | **에이전트 그래프(State·노드·라우팅)** | **B(에이전트, 나)** |
| `app_streamlit.py` | 지도(pydeck)+채팅 UI 골격 | C(UI) |

## 실행

```bash
# 1) 로컬 에이전트 서버(코스 8080) 기동
bash /workspace/course/week5/start_agent_server.sh
# 2) 그래프를 샘플 질의로 시험
cd <repo>
AGENT_CHANNEL=none /root/venvs/rushhour/bin/python app/graph.py   # 서버 없이
AGENT_CHANNEL=local /root/venvs/rushhour/bin/python app/graph.py  # 8080 있을 때
```

API로 돌리려면: `AGENT_CHANNEL=gemini GEMINI_API_KEY=... python graph.py`
(또는 `AGENT_CHANNEL=openai OPENAI_API_KEY=...`).

경로 질의의 출발/도착을 **장소명·랜드마크**('올림픽공원','롯데타워','강남역')로 주려면
카카오 로컬 REST 키가 필요하다: `KAKAO_REST_API_KEY=...`. 없으면 자치구명·`lat,lon`만
해석되고 장소명은 "좌표로 해석 못함"으로 떨어진다(`tools._geocode_kakao`, 서울 결과 우선).

의존성(파드 재배포 시 복구): `uv pip install langchain-core langgraph langchain-openai pandas openpyxl`

## 검증된 것 (LLM 없이)

- 데이터 로드: 27개 자치구 / 컬럼(자치구·노선·수종·경도·위도), cp949
- `find_theme_streets("벚꽃","강동구")` → 아리수로 628그루 … 정상
- 라우팅 3분기: 판별불가→resolver, 커버리지밖→resolver, 정상→researcher
- `build_graph()` 컴파일 OK

LLM 경로(intake 추출·resolver 문장 생성)는 8080 서버 또는 API 키가 있어야 시험 가능.

## 내(B)가 손볼 결정 지점 — graph.py의 [DP] 마커

- **DP1 intake 추출**: 구어체("냄새 안 나게 가을 산책")에서 테마를 얼마나 잘 뽑나.
  프롬프트 예시·few-shot 보강(week2). 다중 테마·모호 질의를 어떻게 처리할지 결정.
- **DP2 라우팅/커버리지 경계**: 자치구 미지정일 때 서울 전체로 조회할지 되물을지.
  테마는 맞는데 그 구에 데이터가 없을 때의 처리.
- **DP3 resolver 그라운딩**: 도구가 준 도로만 말하게 강제(환각 금지). 은행회피의
  '암나무 일부 라벨링 → 근사' 고지를 반드시 포함(채점 가점 포인트).

## UI 실행 (C)

```bash
bash /workspace/course/week5/start_agent_server.sh    # 채팅용 8080
cd <repo>
AGENT_CHANNEL=local /workspace/course/.venv/bin/python -m streamlit run app_streamlit.py
```
사이드바 ‘빠른 추천’은 LLM 없이 도구만 호출 → 8080 없이도 지도 데모 가능. 채팅창은 에이전트 전체 경로 사용.

## 벡터DB(RAG) 연동 지점 — week4

팀원이 CSV로 벡터DB를 구성하면, 에이전트에 **검색 도구 하나(@tool)**로 붙인다(도구 계약만 지키면 됨).
**확정 계약·배선·합의 체크리스트는 `../docs/RAG_SEARCH_PLACES_CONTRACT.md`** 참조(반환은 dict로 확정 —
아래 초안의 `list[dict]`에서 변경됨):
```python
@tool
def search_places(query: str, k: int = 5) -> dict:
    """장소명·구어체·자유서술로 가로수/도로를 의미검색. 예: '강남역 근처 벚꽃', '양재천 산책'.
    반환: {ok, query, top_district, candidates:[{구,노선,수종,score}], reason}
    — top_district로 자치구를 해소한 뒤 find_theme_streets로 좌표를 얻는다."""
```
쓰임새: ① **장소명/구어체 매칭**("강남역 근처", "양재천") → 자치구·도로로 해소(현재 못 하는 부분),
② 테마에 안 잡히는 **자유 질의** 대응. graph.py의 `intake`가 자치구를 못 뽑을 때 researcher가
`search_places`로 후보 도로를 찾는 흐름으로 확장. **도구 개수는 +1**로 충분.

## 팀 인터페이스

- **A(데이터)**: `tools.py`의 두 도구 시그니처는 고정. 내부 구현을 노선 단위 집계 →
  좌표 기반 경로(osmnx)로 교체해도 에이전트는 그대로 동작.
- **C(UI)**: 그래프를 직접 import하지 않고 `backend/main.py`의 API를 부른다.
  `POST /chat`(SSE) → `final` 이벤트의 `final_answer`·`hits["streets"]`,
  `POST /tools/find_theme_streets`(빠른 추천), `GET /map/street_points`(마커).
- **CLI/테스트**: `graph.build_graph()` + `run_one(app, 질문)`은 그대로 유효.
