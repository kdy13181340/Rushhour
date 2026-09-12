"""중앙 설정 — pydantic-settings 단일 출처.  [FastAPI 관용 config]

레포 루트 `.env` + 프로세스 환경변수를 한곳에서 읽는다. 우선순위(pydantic-settings):
    init 인자 > 환경변수 > .env 파일 > 기본값
따라서 배포 오버라이드와 테스트(`monkeypatch.setenv`)가 .env보다 우선해 그대로 먹는다.

`get_settings()`는 매번 현재 env+.env를 다시 읽는다(캐시 안 함). 값이 런타임에 바뀔 수
있는 곳(테스트·데모의 AGENT_CHANNEL·KAKAO 키 등)을 반영하기 위함이고, 이 앱은 요청량이
작아 .env 재파싱 비용이 무의미하다. 모듈 상단 상수(경로·베이스URL)는 import 시 1회만 읽는다.

새 설정을 추가할 땐: (1) 여기 필드 추가 (2) `.env.example`에 한 줄 추가.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """필드명(소문자)이 곧 환경변수명(대문자, case-insensitive)에 매핑된다."""

    model_config = SettingsConfigDict(
        env_file=ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",              # .env에 무관한 키가 있어도 무시
    )

    # ── LLM 채널 (app/llm.py) ──────────────────────────────────────────────
    agent_channel: str = "local"                 # local | gemini | openai | none
    agent_base_url: str = "http://localhost:8080/v1"
    gemini_model: str = "gemini-2.5-flash-lite"
    gemini_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""

    # ── 외부 API (app/tools.py) ────────────────────────────────────────────
    kakao_rest_api_key: str = ""                 # 경로 출발/도착 장소명 지오코딩

    # ── 임베딩 / RAG (search_places — 동료 배선 후 소비) ──────────────────────
    # 코스 규약: week4/start_embed_server.sh(8082), bge-m3(1024차원).
    # 요청 {"input": [...], "model": <embed_model>} → 응답 {"data":[{"embedding":[...]}]}.
    embed_url: str = "http://localhost:8082/v1/embeddings"
    embed_model: str = "bge-m3"

    # ── 데이터 경로 (app/tools.py) ─────────────────────────────────────────
    tree_parquet: Path = ROOT / "data" / "processed" / "seoul_trees.parquet"
    tree_csv: Path = ROOT / "data" / "seoul_tree_data.csv"

    # ── 백엔드 (backend/) ──────────────────────────────────────────────────
    checkpoint_db: Path = ROOT / "data" / "checkpoints.sqlite"
    trace_backend: str = "jsonl"                 # jsonl | langfuse | none
    trace_path: Path = ROOT / "results" / "rushhour_trace.jsonl"

    # ── UI / 데모 ──────────────────────────────────────────────────────────
    rushhour_api: str = "http://localhost:8000"  # app_streamlit.py → 백엔드
    rushhour_season: str = ""                    # 데모·테스트용 계절 고정


def get_settings() -> Settings:
    """현재 env+.env로 설정을 읽는다(캐시 안 함 — 오버라이드·테스트 반영)."""
    return Settings()
