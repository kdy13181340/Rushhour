# deploy/ — Rushhour 자체 인프라 (로컬 LLM · 임베딩 서버)

이 저장소만 clone 하면(모델 파일과 llama.cpp 바이너리는 이미지에 이미 있다는 전제)
`/workspace/course` 디렉터리 없이도 로컬 LLM(에이전트) 서버와 임베딩 서버를 띄울 수 있다.
스크립트는 코스(`week4`·`week5`)의 기동/중지/대기 스크립트를 이 저장소 맥락으로 이식한 것이다.

- **에이전트(LLM) 서버**: 포트 8080, OpenAI 호환 `http://localhost:8080/v1`
  → `app/config.py` 의 `AGENT_BASE_URL` 과 일치.
- **임베딩 서버**: 포트 8082, OpenAI 호환 `http://localhost:8082/v1/embeddings`, 모델 BGE-M3(1024차원)
  → `app/config.py` 의 `EMBED_URL` / `EMBED_MODEL` 과 일치.

## 사전조건

- `llama-server` 바이너리: 기본 `/opt/llama.cpp/bin/llama-server` (없으면 폴백 경로 시도).
- 모델 GGUF 파일(기본 경로, `/workspace/models/` 아래):
  - 에이전트 27B: `Qwen3.6-27B-UD-Q4_K_XL.gguf` (기본, 도구 호출 신뢰도 최상)
  - 에이전트 4B(폴백): `Qwen3.5-4B-Q8_0.gguf` (`--small`)
  - 임베딩: `bge-m3-Q8_0.gguf`
- GPU(권장): 27B·16384 컨텍스트 기준 약 18.5GB VRAM.
- `wait_server.py` 는 `requests` 가 있으면 쓰고, 없으면 표준 라이브러리로 폴백한다.

## 실행 / 중지 / 대기

```bash
# 두 서버 한 번에 기동 + 준비 대기
bash deploy/up.sh                # 에이전트 27B + 임베딩
bash deploy/up.sh --small        # 에이전트를 4B 폴백으로
bash deploy/up.sh --agent-only   # 에이전트만
bash deploy/up.sh --embed-only   # 임베딩만

# 두 서버 한 번에 중지
bash deploy/down.sh

# 개별 기동
bash deploy/start_agent_server.sh            # 27B, 컨텍스트 16384
bash deploy/start_agent_server.sh 8192       # 27B, 컨텍스트 8192 (VRAM 부족 시)
bash deploy/start_agent_server.sh --small    # 4B 폴백
bash deploy/start_embed_server.sh            # 임베딩(BGE-M3)
bash deploy/start_embed_server.sh /path/to/other.gguf   # 다른 임베딩 GGUF

# 개별 중지
bash deploy/stop_agent_server.sh
bash deploy/stop_embed_server.sh

# 준비 상태 폴링(개별 기동 후)
python deploy/wait_server.py --port 8080 --timeout 300   # 에이전트
python deploy/wait_server.py --port 8082 --timeout 180   # 임베딩
```

로그·PID 는 기본적으로 `<repo>/results/` 아래에 남는다
(`agent-server.log`/`agent-server.pid`, `embed-server.log`/`embed-server.pid`).

## 환경변수 (기본값은 코스와 동일)

| 변수 | 대상 | 기본값 | 설명 |
|------|------|--------|------|
| `AGENT_MODEL` | 에이전트 | `/workspace/models/Qwen3.6-27B-UD-Q4_K_XL.gguf` | 27B 모델 경로 |
| `AGENT_MODEL_SMALL` | 에이전트 | `/workspace/models/Qwen3.5-4B-Q8_0.gguf` | `--small` 모델 경로 |
| `AGENT_PORT` | 에이전트 | `8080` | 포트(config `AGENT_BASE_URL` 과 맞출 것) |
| `AGENT_CTX` | 에이전트 | `16384` | 컨텍스트 길이(위치 인자 `CTX` 가 우선) |
| `EMBED_MODEL` | 임베딩 | `/workspace/models/bge-m3-Q8_0.gguf` | 임베딩 모델 경로(위치 인자 우선) |
| `EMBED_PORT` | 임베딩 | `8082` | 포트(config `EMBED_URL` 과 맞출 것) |
| `EMBED_CTX` | 임베딩 | `8192` | 컨텍스트/배치 크기 |
| `LLAMA_SERVER_BIN` | 공통 | `/opt/llama.cpp/bin/llama-server` | llama-server 바이너리 경로 |
| `RESULTS_DIR` | 공통 | `<repo>/results` | 로그·PID 저장 위치 |

예)
```bash
AGENT_CTX=8192 bash deploy/start_agent_server.sh
LLAMA_SERVER_BIN=/usr/local/bin/llama-server bash deploy/start_embed_server.sh
AGENT_PORT=9080 bash deploy/start_agent_server.sh   # config AGENT_BASE_URL 도 함께 바꿀 것
```

> 포트를 바꾸면 `app/config.py`(또는 `.env` 의 `AGENT_BASE_URL`/`EMBED_URL`)도 같은 포트를
> 가리키도록 맞춰야 한다. 스크립트 포트와 config 포트가 어긋나면 앱이 서버를 못 찾는다.

## 트러블슈팅

- **포트 점유(`포트 8080이 이미 사용 중`)**: 서버가 이미 떠 있을 수 있다.
  `bash deploy/stop_agent_server.sh`(또는 `stop_embed_server.sh`)로 먼저 중지한다.
  중지 스크립트는 PID 파일이 어긋나도 포트를 잡은 `llama-server` 만 안전하게 정리한다.
- **VRAM 부족**: 두 가지 선택지.
  1. 컨텍스트 축소: `bash deploy/start_agent_server.sh 8192`
  2. 4B 폴백: `bash deploy/start_agent_server.sh --small` (또는 `bash deploy/up.sh --small`)
- **`llama-server 바이너리를 찾지 못함`**: 이미지에 바이너리가 없거나 경로가 다르다.
  `LLAMA_SERVER_BIN` 으로 실제 경로를 지정한다.
- **모델 파일 없음**: `AGENT_MODEL` / `EMBED_MODEL` 로 실제 GGUF 경로를 지정한다.
- **준비가 안 됨(`wait_server.py` 타임아웃)**: `results/agent-server.log` 또는
  `results/embed-server.log` 의 마지막 줄을 확인한다(대개 VRAM/모델 로딩 문제).
- **도달 확인**: 앱 백엔드의 `GET /health` 가 8080·8082 도달 여부를 함께 본다.

## 출처

코스의 `week5/{start,stop}_agent_server.sh`·`week4/{start,stop}_embed_server.sh`·
`wait_server.py` 를 **읽고** 이 저장소 맥락(자체 경로·환경변수 오버라이드·`set -euo pipefail`)에
맞게 재작성했다. 코스 파일 자체는 수정하지 않았다.
