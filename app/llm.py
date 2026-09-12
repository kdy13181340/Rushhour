"""LLM 획득 — 코스 pj_common.get_chat_model 패턴을 이 프로젝트로 옮긴 것.

기본은 코스 로컬 에이전트 서버(8080). 환경변수로 채널을 바꾼다.
  AGENT_CHANNEL=local  (기본) → http://localhost:8080/v1  (bash week5/start_agent_server.sh)
  AGENT_CHANNEL=gemini         → GEMINI_API_KEY 필요
  AGENT_CHANNEL=openai         → OPENAI_API_KEY 필요
"""

from config import get_settings

AGENT_BASE_URL = get_settings().agent_base_url          # import 시 1회(정적)
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
GEMINI_MODEL = get_settings().gemini_model
OPENAI_MODEL = get_settings().openai_model
NO_THINK = {"chat_template_kwargs": {"enable_thinking": False}}


def _channel() -> str:
    return get_settings().agent_channel.strip().lower()  # 호출 시점(테스트 오버라이드 반영)


def _resolve_local_model() -> str:
    try:
        from openai import OpenAI
        return OpenAI(base_url=AGENT_BASE_URL, api_key="sk-noop").models.list().data[0].id
    except Exception:
        return "local-model"


def get_chat_model(max_tokens: int = 512, temperature: float = 0.0):
    from langchain_openai import ChatOpenAI
    ch = _channel()
    if ch == "gemini":
        key = get_settings().gemini_api_key
        if not key:
            raise RuntimeError("AGENT_CHANNEL=gemini 인데 GEMINI_API_KEY가 비어 있음")
        return ChatOpenAI(api_key=key, base_url=GEMINI_BASE_URL, model=GEMINI_MODEL,
                          temperature=temperature, max_tokens=max_tokens)
    if ch == "openai":
        key = get_settings().openai_api_key
        if not key:
            raise RuntimeError("AGENT_CHANNEL=openai 인데 OPENAI_API_KEY가 비어 있음")
        return ChatOpenAI(api_key=key, model=OPENAI_MODEL,
                          temperature=temperature, max_tokens=max_tokens)
    # local (코스 기본)
    return ChatOpenAI(base_url=AGENT_BASE_URL, api_key="sk-noop",
                      model=_resolve_local_model(), temperature=temperature,
                      max_tokens=max_tokens, extra_body=NO_THINK)
