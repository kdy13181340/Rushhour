"""카카오 지오코딩 라이브 점검 — 레포 루트에서 실행.

    python scripts/check_kakao_geocode.py

키는 .env(KAKAO_REST_API_KEY=...) 또는 환경변수 어느 쪽이든 인식한다(app/config.py).
키 유무·지오코딩 좌표·route_theme_streets 실동작을 한 번에 확인한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import tools  # noqa: E402
from config import get_settings  # noqa: E402
from tools import _resolve_point, route_theme_streets  # noqa: E402

key = get_settings().kakao_rest_api_key.strip()
print(f"[1] 키 인식(.env/환경변수): {'YES (len=%d)' % len(key) if key else 'NO — .env 또는 export 확인'}")
if not key:
    sys.exit(1)

print("\n[2] 장소명 → 좌표(카카오)")
for name in ["올림픽공원", "롯데타워", "강남역", "여의도 한강공원"]:
    print(f"    {name:12s} → {_resolve_point(name)}")

print("\n[3] route_theme_streets: 올림픽공원 → 롯데타워, 테마=벚꽃")
r = route_theme_streets.invoke({"theme": "벚꽃", "origin": "올림픽공원", "dest": "롯데타워"})
print(f"    ok={r.get('ok')}  reason={r.get('reason', '')}")
if r.get("ok"):
    print(f"    corridor.line = {r['corridor']['line']}")
    print(f"    총 {r['total_trees']}그루, 경유 도로 {len(r['streets'])}개:")
    for s in r["streets"]:
        print(f"      - {s['구']} {s['노선']} ({s['그루수']}그루) center={s['center']}")
print("\n완료.")
