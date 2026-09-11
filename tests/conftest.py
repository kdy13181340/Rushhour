import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

os.environ.setdefault("AGENT_CHANNEL", "none")      # 테스트는 LLM 없이
os.environ.setdefault("TRACE_BACKEND", "none")
os.environ.setdefault("RUSHHOUR_SEASON", "autumn")  # 날짜에 따라 결과가 흔들리지 않게 고정
