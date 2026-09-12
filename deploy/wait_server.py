"""서버 준비 상태 폴링 유틸리티 — Rushhour 자체 인프라.

원본: /workspace/course/week{4,5}/wait_server.py 를 참고해 이 저장소로 이식함.
llama-server / vLLM / SGLang 모두 /health 를 제공하므로 포트만 주면 생성(8080)·임베딩(8082)
양쪽에 쓸 수 있음. 27B 로딩은 4B보다 오래 걸리므로 타임아웃을 넉넉히 줄 것(기본 300초).

실행법: python deploy/wait_server.py --port 8080 [--timeout 300]

의존성이 없어도 동작하도록 requests 가 없으면 표준 라이브러리(urllib)로 폴백함.
"""

import argparse
import sys
import time

HEALTH_PATH = "/health"


def _probe(url: str, timeout: float) -> int | None:
    """HTTP 상태 코드를 반환함. 도달 실패면 None."""
    try:
        import requests  # 있으면 사용
    except Exception:
        requests = None

    if requests is not None:
        try:
            return requests.get(url, timeout=timeout).status_code
        except Exception:
            return None

    # 표준 라이브러리 폴백 — requests 미설치 환경에서도 동작.
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return None


def wait_for_server(port: int, timeout: int) -> bool:
    """지정 포트의 서버가 HTTP 200 을 반환할 때까지 폴링함. 준비되면 True."""
    url = f"http://localhost:{port}{HEALTH_PATH}"
    deadline = time.time() + timeout
    started = time.time()
    print(f"포트 {port} 서버 준비 상태 확인 중", end="", flush=True)

    while time.time() < deadline:
        code = _probe(url, timeout=3)
        if code == 200:
            print()
            print(f"[PASS] 포트 {port} 서버 준비 완료 (HTTP {code}, {time.time() - started:.0f}초)")
            return True
        print(".", end="", flush=True)
        time.sleep(2)

    print()
    print(f"[FAIL] 포트 {port} 서버가 {timeout}초 안에 준비되지 않음.")
    print("조치: 'results/agent-server.log' 또는 'results/embed-server.log' 마지막 줄을 확인할 것.")
    print("      VRAM 부족이면 'bash deploy/start_agent_server.sh 8192'로 컨텍스트를 낮출 것.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="서버 준비 상태를 폴링함")
    parser.add_argument("--port", type=int, required=True, help="확인할 포트 번호")
    parser.add_argument("--timeout", type=int, default=300, help="최대 대기 시간(초)")
    args = parser.parse_args()

    sys.exit(0 if wait_for_server(args.port, args.timeout) else 1)


if __name__ == "__main__":
    main()
