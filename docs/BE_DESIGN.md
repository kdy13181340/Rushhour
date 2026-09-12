# Rushhour BE 구성안 v2 — develop 초안(ade7f13) 기준 변경안

작성: 2026-09-11 · 기준: `origin/develop` ade7f13 (honeyuheony) · 참조: `system.png`, `week6/pj02_agent_graph.py`

## 진행 상황 (2026-09-11)

C1~C6 구현 완료(서버 없이 검증, tests 75건 통과). C7 중 `search_places`(벡터DB, RAG)와
**`plan_route`(경로 3가지)**는 구현·배선 완료(DP14·DP15·DP17), `find_light_spots`는 스텁만 배선됨.
**제보 등록(register_report)·HITL은 팀 결정으로 범위에서 제외**(DP8).
같은 thread의 다음 질문이 이전 답을 되돌려주던 결함 수정(DP13), 폴백 ③ 도구 예외 구현(DP10 보강).
임베딩은 팀 bge-m3 서버(llama-server)로 색인·평가 완료, 8080 LLM(27B) 종단 확인(DP14·DP15).
결정은 `DECISIONS.md` DP4~DP15.

**BE 남은 것**:
- 경로 가중치 α·β·도보 계수를 경로 eval 질의로 재보기(지금은 실측 몇 건으로 고른 값) — DP17·DP19
- 나무 마커 좌표도 도로에 스냅해서 줄지(지금은 원본 좌표) — DP20 남은 것
- `size_weight` 모델 독립 정규화 — 후보 안에서 유사도를 정규화한 뒤 더하기(DP14 후속)
- 평가 질의 확충 — 현재 18건. 채널 비교를 판단하기엔 얇다
- C7 `find_light_spots` — 같은 Chroma 클라이언트에 컬렉션 추가. **겨울 조명 문서 소스 미정(팀 결정 대기)**
- LLM 폴백 ①(구조화 출력 실패) 실발동 확인 — 정상 경로는 8080으로 확인됨
- Langfuse 콜백 검증(서버 필요) · vLLM 7B A/B(DP7)
- 장소 해소를 동/도로 단위로 좁히기 — 지금은 자치구 단위(DP15 남은 한계)

## 0. 초안 평가 — 살릴 것과 바꿀 것

### 살릴 것 (그대로 채택)

| 파일 | 이유 |
|---|---|
| `app/themes.py` | 테마 6종을 단일 출처로 둔 것이 좋음. 수종 문자열이 실제 데이터값과 일치함을 확인 |
| `app/tools.py` 도구 계약 | `find_theme_streets(theme, district) → {ok, streets, focus, note}` 시그니처는 고정. 내부만 교체 |
| `app/map_api.py` | 좌표 배열을 에이전트 컨텍스트에 안 넣고 UI가 따로 가져가는 분리가 옳음 |
| `app/llm.py` | 채널 추상화가 이미 env 기반이라 vLLM 전환 시 `AGENT_BASE_URL`만 바꾸면 됨 |
| "모르면 모른다" 3분기 | 판별불가·커버리지 밖·데이터 없음을 코드로 거절하는 구조는 week6 축 그대로 |
| resolver의 LLM 입력 압축 | 좌표 제외하고 도로명·그루수만 넘기는 것. 7B로 가면 더 중요해짐 |

### 바꿀 것 (우선순위 순)

| # | 무엇 | 왜 | 어디 |
|---|---|---|---|
| C1 | 선형 그래프 → **supervisor 규칙 라우터 + MAX_HOPS** | 커밋 메시지는 supervisor라 하지만 배선은 `intake→(조건부)→researcher→resolver→END` 선형임. 노드가 4개(season·light·report)가 늘어나면 선형 배선은 조건부 엣지가 노드마다 붙어 감당이 안 됨. 팀 합의(week6 오케스트레이션)와도 어긋남 | `graph.py` |
| C2 | **관리기관 행 12,946건의 구 복원** | `자치구` 컬럼에 `서울시설공단`(12,221)·`중부공원여가센터`(725)가 들어 있음. 세종대로 은행나무가 "중부공원여가센터" 소속이라 "종로구 은행단풍" 질의에서 빠짐. `지번 주소`의 "서울특별시 ○○구"로 100% 복원 가능함을 확인. 커버리지 안내도 "27개 자치구"가 아니라 25개가 맞음 | `tools.py _load()` |
| C3 | **season 노드 추가(코드)** | 다이어그램 첫 단계가 "계절 판단"임. 지금은 intake LLM이 테마와 계절을 한 번에 추론함. 날짜로 계절을 먼저 정하고 그 계절의 테마만 후보로 주면 7B의 intake 정확도가 오르고, "지금 뭐 볼만해?"처럼 테마가 없는 질의도 답할 수 있음 | `graph.py` |
| C4 | **FastAPI 층 신설, Streamlit은 HTTP 클라이언트로** | 초안은 Streamlit이 `build_graph()`를 직접 import함. 다이어그램의 SSE 스트리밍·폴백·저장은 프로세스 경계가 있어야 성립함. Langfuse 콜백도 UI(TODO-UI3)가 아니라 BE에 붙어야 함 | `backend/` 신설 |
| C5 | **데이터 경로 하드코딩 제거** | `/workspace/Rushhour/data/...` 절대경로. 이 파드에선 clone 위치가 `/workspace/course/Rushhour`라 그대로 깨짐. `Path(__file__).parents[1]/"data"` + `TREE_CSV` env 유지 | `tools.py` |
| C6 | **CSV → Parquet 사전 변환** | cp949 CSV 33MB를 매 프로세스 기동마다 파싱함. FastAPI 워커·Streamlit·테스트가 각각 읽으면 낭비. 1회 변환 스크립트 + 구 복원(C2)을 여기서 함 | `scripts/01_csv_to_parquet.py` |
| C7 | 다이어그램의 나머지 툴 | `plan_route`(OSM) · `find_light_spots`(Chroma) 미구현. 초안 README도 osmnx 확장을 예고함. 아래 §4 로드맵 | 신규 |

## 1. C1 — 그래프 재구성 (graph.py)

week6 `route_from_supervisor`의 "울타리 먼저, 그다음 빈 칸 순서" 규칙을 그대로 옮긴다. LLM은 intake·resolver 두 곳만(초안과 동일). (아래 스케치는 초안 시점의 것이며 report 관련 줄은 제외 결정으로 실제 코드에서 빠졌다. 실제 배선은 `app/graph.py`.)

```python
MAX_HOPS = 10

class RouteState(TypedDict, total=False):
    question: str
    season: str                 # season 노드(코드): spring|summer|autumn|winter
    theme: str                  # intake: 테마 키 | 'unknown'
    district: str               # intake: 자치구 | ''
    hits: dict                  # researcher: find_theme_streets 결과
    light_spots: list | None    # light: 겨울만 (C7)
    verdict: str                # 'match' | 'no_data' | 'unknown_intent' | 'out_of_coverage'
    final_answer: str
    visited: Annotated[list, operator.add]

def route_from_supervisor(s: RouteState) -> str:
    if s.get("visited", []).count("supervisor") >= MAX_HOPS:
        return "FINISH"                                   # 울타리 먼저
    if not s.get("season"):            return "season"    # 코드, LLM 없음
    if not s.get("theme"):             return "intake"
    if s["theme"] == "unknown" or s.get("verdict") == "out_of_coverage":
        return "resolver"                                 # 정직한 거절 (초안 3분기 유지)
    if s.get("hits") is None:          return "researcher"
    if s["season"] == "winter" and s.get("light_spots") is None:
        return "light"                                    # C7 전까지는 빈 리스트 반환 스텁
    if not s.get("final_answer"):      return "resolver"
    return "FINISH"

def build_graph(checkpointer=None):
    g = StateGraph(RouteState)
    g.add_node("supervisor", lambda s: {"visited": ["supervisor"]})
    for name, fn in [("season", season_node), ("intake", intake_node),
                     ("researcher", researcher_node), ("light", light_node),
                     ("resolver", resolver_node)]:
        g.add_node(name, fn)
    g.add_edge(START, "supervisor")
    g.add_conditional_edges("supervisor", route_from_supervisor,
        {"season": "season", "intake": "intake", "researcher": "researcher",
         "light": "light", "resolver": "resolver", "FINISH": END})
    for name in ("season", "intake", "researcher", "light"):
        g.add_edge(name, "supervisor")
    g.add_edge("resolver", END)
    return g.compile(checkpointer=checkpointer)
```

- 초안의 `route_after_intake` 3분기는 `verdict` 값으로 흡수한다. intake가 커버리지 밖 자치구를 뽑으면 `verdict="out_of_coverage"`를 함께 채운다.
- 울타리 종료는 `final_answer` 부재로 식별한다(week6 DP9).
- **season_node(C3)**: `date.today().month`로 계절을 정하고, `THEMES`에 `seasons: list[str]` 필드를 추가해 intake 프롬프트의 테마 목록을 그 계절 것부터 나열한다. 사용자가 "봄에"라고 명시하면 intake가 `season_override`를 뽑아 덮어쓴다. 계절 밖 테마 요청(9월에 벚꽃)은 거절이 아니라 "지금은 벚꽃 시기가 아니다"를 resolver가 한 문장 덧붙이는 정도로 둔다.
- `run_one(app, question)` 시그니처는 유지해 C(UI)와 CLI 시험이 깨지지 않게 한다.

## 2. C2·C5·C6 — 데이터 수정 (tools.py, scripts/)

```python
# scripts/01_csv_to_parquet.py (1회)
df = pd.read_csv(RAW, encoding="cp949")
agency = df["자치구"].isin(["서울시설공단", "중부공원여가센터"])
df["관리기관"] = df["자치구"].where(agency, "자치구")          # 출처 보존
df.loc[agency, "자치구"] = df.loc[agency, "지번 주소"].str.extract(r"서울특별시\s+(\S+구)")[0]
df = df.dropna(subset=["좌표(경도)", "좌표(위도)"])            # 위도 결측 1건
df.to_parquet(OUT)   # UTF-8, 컬럼명 짧게: 구·노선·수종·도로명·지번·경도·위도·관리기관
```

- `_load()`는 Parquet가 있으면 그것을, 없으면 CSV를 읽되 같은 변환을 적용한다.
- `available_districts()`는 25개가 된다. `check_coverage`의 안내 문구도 따라 바뀐다.
- 노선 결측 1,741건은 `groupby("노선")`에서 자동 제외되므로 노선 집계 MVP에는 영향 없음. 좌표 기반 경로(C7)로 가면 다시 살아난다.

## 3. C4 — FastAPI 층 (backend/)

| 엔드포인트 | 설명 |
|---|---|
| `POST /chat` | `{thread_id, message}` → SSE. `graph.astream(..., stream_mode="updates")`로 노드마다 `{type:"node", name, patch}` 전송. 마지막 `{type:"final", final_answer, hits, light_spots}` |
| `GET /threads/{thread_id}` | 체크포인트 조회. FE 새로고침 복구 |
| `POST /tools/find_theme_streets` | 사이드바 "빠른 추천"용. LLM 없이 도구만 호출하는 초안의 장점을 API로도 유지 |
| `GET /health` | 8080 모델·Parquet·그래프 로드 여부. Streamlit이 첫 화면에서 호출해 "채팅 불가·빠른 추천만 가능" 배지 표시 |

- 체크포인터는 `langgraph-checkpoint-sqlite`. 용도는 `/threads` 상태 복구(HITL은 범위 제외). `thread_id`는 Streamlit `session_state`의 uuid. 같은 thread_id의 다음 질문은 `graph.new_turn_input`으로 턴 상태를 비우고 season부터 다시 돈다(DP13) — 그냥 question만 바꾸면 라우터가 바로 FINISH해 이전 답을 되돌려준다.
- 폴백 3단(초안의 try/except 한 줄을 BE로 옮김): ① 구조화 출력 실패 → 오류 되먹임 재시도 1회 후 `theme="unknown"` ② 모델 서버 다운 → intake를 키워드 규칙(테마 라벨·자치구 명 매칭)으로 대체, resolver는 템플릿 문장. **지도는 LLM 없이도 반드시 나온다** ③ 도구 예외 → `verdict="no_data"` + 사유(`hits.tool_error`; researcher_node try/except — 구현됨).
- 관측: `Tracer` 인터페이스 하나에 Langfuse `CallbackHandler` 구현과 week6 `TraceWriter` JSONL 구현. env `TRACE_BACKEND=langfuse|jsonl`. Langfuse 서버가 없어도 JSONL로 궤적이 남아야 한다.
- Streamlit(`app_streamlit.py`)은 `get_app()` 대신 `requests`/`httpx`로 `/chat` SSE를 읽는다. pydeck 지도 코드는 그대로.

## 4. C7 — 다이어그램의 나머지 툴 로드맵

| 툴 | 데이터 | 노드 | 선행 작업 |
|---|---|---|---|
| `plan_route(origin, dest, season, theme)` | **구현됨** `app/routing.py` — OSM 보행망(노드 23.8만·간선 68만, scripts/04) + 나무 스냅(97.2%, scripts/05) | `route` 노드가 고정 호출 | 가중치만 바꿔 다익스트라 3번(0.2초). α=0.55·β=2.0. 도로망 없으면 회랑 폴백 (DP17) |
| `find_light_spots(near, radius_m)` | Chroma(겨울 조명 문서) + 좌표 필터 | `light` (겨울에만 라우팅) | 4주차 임베딩 서버(8082) 재사용. Chroma distance는 툴 안에서 similarity로 뒤집음. 임계값은 eval 질의 20건으로 정함 |
| `search_places(query, k, district, min_trees, size_weight)` | **구현됨** `app/rag.py` — Chroma (구,노선) 문서 1,780건, 임베딩 채널 5종(`app/embeddings.py`), 채널별 `data/chroma/<채널>/` | intake가 자치구를 못 뽑을 때 researcher가 호출(배선은 B) | eval 18건: e5-small MRR 0.87 · hash(IDF) 0.72 (DP14). 조명 문서는 같은 클라이언트에 컬렉션 추가 |

`light` 노드는 C1 시점에 **빈 스텁**(빈 리스트 반환)으로 먼저 배선해 두었으므로, 나중에 툴만 채워도 라우터를 다시 건드리지 않는다.

## 5. 모델 결정 — llama-server 27B(현재) vs vLLM 7B(다이어그램)

| | llama-server 27B (초안, 8080) | vLLM Qwen 7B (다이어그램) |
|---|---|---|
| 준비 | 지금 바로 됨. GGUF 있음 | `/root/venvs/vllm`에 0.25.1 설치됨. HF safetensors 다운로드 필요(GGUF 불가) |
| JSON 강제 | `with_structured_output(json_schema)` 동작 확인됨(week6) | `response_format json_schema` 지원. `guided_json`도 가능 |
| 동시성 | `-np 1` 슬롯 1개. SSE 다중 사용자면 직렬화 | 연속 배칭. 데모 다중 접속에 유리 |
| 툴 재량 | 27B는 bind_tools 재량 신뢰 가능 | 7B는 재량 신뢰 낮음 → 라우터 고정 호출(초안도 이미 코드 직접 호출) |

실측(2026-09-11): 에이전트 개발자 파드(`i3pdrbs4uwzc7r`)의 8080은 **llama-server**로 `Qwen3.6-27B-UD-Q4_K_XL.gguf`(format gguf)를 서빙 중 — vLLM이 아님(vLLM은 GGUF 27B를 이 형태로 못 올리고 `/props`가 없음). 9000은 Streamlit.

제안: **1차는 초안대로 8080 llama-server로 개발**하고, C4 완료 후 `AGENT_BASE_URL`만 vLLM으로 바꿔 A/B. `llm.py`는 손댈 것 없음. 7B로 갈 때 intake 정확도가 떨어지면 C3(계절로 테마 후보 축소)가 완충이 된다. 이걸 DP로 기록.

## 6. 디렉터리 (초안 유지 + 추가)

```
Rushhour/
  app/                      # 초안 그대로 (에이전트·툴·UI)
    themes.py tools.py map_api.py llm.py graph.py app_streamlit.py
    nodes/season.py light.py                 # C1·C3·C7 추가
    tools_ext/plan_route.py find_light_spots.py   # C7
    embeddings.py rag.py                     # DP14(구현됨): 임베딩 채널 · Chroma 색인 + search_places
    routing.py                               # DP17(구현됨): OSM 보행망 위 경로 3가지 plan_route
  backend/                  # C4 신설
    main.py  api/chat.py api/tools.py api/health.py
    trace.py                # Tracer: langfuse | jsonl
  scripts/01_csv_to_parquet.py 02_build_vector_db.py 03_eval_search_places.py 04_fetch_osm.py 05_snap_trees.py
  data/ (raw csv · processed/ parquet · eval/ · chroma/<채널>/ · osm/)      (예정: ingest_light_docs)
  tests/test_tools.py test_router.py test_api.py test_rag.py test_routing.py   # LLM·임베딩·도로망 없이 돌아가야 함
  docs/BE_DESIGN.md DECISIONS.md
  requirements.txt          # + fastapi uvicorn sse-starlette httpx pyarrow langgraph-checkpoint-sqlite langfuse
```

## 7. 결정 지점(DP) — 초안 DP1~3 유지 + 추가

| DP | 질문 | 1차 결정 |
|---|---|---|
| DP1 (초안) | intake 추출 정확도 | few-shot + 계절별 테마 후보 축소(C3) |
| DP2 (초안) | 자치구 미지정 시 | 서울 전체 조회(초안 유지). 결과 상위 3개 구를 resolver가 언급 |
| DP3 (초안) | resolver 그라운딩 | 도구 결과만. 은행회피 근사 고지 유지 |
| DP4 | 툴 호출 주체 | 라우터 고정. 7B 전환 대비 |
| DP5 | 계절 판정 | 코드(날짜) + 사용자 override |
| DP6 | 관리기관 행 처리 | 지번 주소로 구 복원. `관리기관` 컬럼으로 출처 보존 |
| DP7 | 모델 서버 | 1차 llama-server 27B, C4 후 vLLM 7B A/B |
| DP8 | 제보 등록·HITL | 범위에서 제외(팀 결정) |
| DP9 | MAX_HOPS | 10. 울타리 종료는 final_answer 부재로 식별 |
| DP10 | 폴백 정책 | LLM 실패→규칙 intake·템플릿 resolver, 도구 예외→no_data(`tool_error`). 지도는 LLM 없이도 |
| DP11 | SSE 구현 | 동기 `graph.stream` + StreamingResponse (SqliteSaver async 미지원) |
| DP12 | develop 병합 | 추천 미션·superlative·핫스팟 focus 이식 |
| DP13 | 같은 thread 다음 질문 | `new_turn_input`으로 턴 상태 리셋, visited 리듀서 `_add_or_reset` |
| DP14 | 벡터DB·임베딩·search_places | Chroma (구,노선) 문서, 채널 5종 + 서명 검사, hash IDF, size_weight 0.02, eval 18건 |
| DP15 | 장소 해소(places 노드) | 자치구가 아닌 장소는 벡터DB로 자치구를 정한 뒤 기존 경로. 해석을 답변에 밝힘 |
| DP16 | 검색 결과 신뢰 | 출발·도착은 질의와 표기가 겹칠 때만 채택. 유사도 임계값은 채널 의존이라 안 씀 |
| DP17 | 경로 3가지 | OSM 보행망 + 가중치 3종. 계절이 대안을 정함. 약속 못 지키는 대안은 뺌 |
| DP19 | 도보 기준 | 도로 종류별 도보 계수로 체감 길이를 만들어 푼다. 시간·큰길 비율도 답변에 |
| DP20 | 지도 선 | 나무 좌표 근사 직선 → 실제 보행 도로 형상. overview는 캐시 |
| DP21 | 밑그림 타일 | Esri는 서울 z16부터 빈 타일 → OSM 표준 + CSS 회색 필터(키 불필요) |
| DP18 | 조명 스팟 임계값 | eval 질의로 분포 확인 후. 데모 질의로 맞추지 않음 (C7, 미정) |

## 8. 작업 순서와 분담 제안 (초안의 A/B/C 유지)

| 순서 | 작업 | 담당 | LLM 필요 |
|---|---|---|---|
| 1 | C2·C5·C6 Parquet 변환 + `_load()` 교체 + `tests/test_tools.py` | A | X |
| 2 | C1·C3 supervisor 재배선 + season 노드 + light/report 스텁 + `tests/test_router.py` | B | X (라우터는 순수 함수) |
| 3 | C4 FastAPI `/chat` SSE + `/tools/find_theme_streets` + `/health` + JSONL Tracer | BE(신규 또는 B) | X |
| 4 | Streamlit → HTTP 클라이언트 전환 | C | X |
| 5 | 8080 기동 후 intake/resolver 종단 시험, 폴백 3단 확인 | B | O |
| 6 | C7 plan_route(OSM) → find_light_spots(Chroma) 순 | A / A | 부분 |
| 7 | Langfuse 서버 + 콜백, vLLM A/B, DECISIONS.md 마감 | 전원 | O |

1~4는 모델 서버 없이 병렬로 진행할 수 있다.

## 9. 환경 메모

- 이 파드의 clone은 `/workspace/course/Rushhour`. 초안 README·코드의 `/workspace/Rushhour` 경로는 C5로 해소.
- course venv(`/root/venvs/course`)에 현재 `langgraph`·`chromadb`가 없음(파드 재배포). `bash week5/setup_week5.sh`로 복구 후 `week6/setup_midterm_venv.sh` 방식으로 프로젝트 venv 복제 권장. `requirements.txt`를 그 venv에 추가 설치.
- 포트: 8080 모델, 8082 임베딩, FastAPI 8000, Streamlit 9000(초안 README 기준).
