"""가로수 데이터 접근 도구 (@tool).

에이전트(graph.py)가 호출하는 도구들. week5 도구 설계 원칙에 따라 이름·설명·인자를
명확히 둔다(ex02). 지금은 '노선(도로) 단위 집계'로 동작하는 MVP 구현이며,
실제 좌표 기반 경로탐색은 팀원 A/확장 단계에서 osmnx로 교체한다.

데이터 로드 순서 [BE_DESIGN C2·C5·C6]:
  1) TREE_PARQUET env  2) data/processed/seoul_trees.parquet (scripts/01 산출물)
  3) TREE_CSV env      4) data/seoul_tree_data.csv (cp949) — 같은 정제(clean)를 즉석 적용
경로는 저장소 루트 기준 상대경로라 clone 위치가 달라도 동작한다.
컬럼(정제 후): 구 · 노선 · 수종 · 도로명 · 지번 · 경도 · 위도 · 관리기관
"""

import functools
import math
import sys
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from langchain_core.tools import tool

from config import ROOT, get_settings
from themes import THEMES

PARQUET_PATH = Path(get_settings().tree_parquet)   # import 시 1회(정적 경로)
CSV_PATH = Path(get_settings().tree_csv)


@functools.lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    """데이터를 한 번만 읽어 캐시. Parquet 우선, 없으면 CSV를 읽어 같은 정제를 적용."""
    if PARQUET_PATH.exists():
        return pd.read_parquet(PARQUET_PATH)
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"가로수 데이터 없음: {PARQUET_PATH} / {CSV_PATH}. "
            "python scripts/01_csv_to_parquet.py 를 먼저 실행할 것.")
    sys.path.insert(0, str(ROOT / "scripts"))
    from importlib import import_module
    clean = import_module("01_csv_to_parquet").clean
    return clean(pd.read_csv(CSV_PATH, encoding="cp949"))


def data_source() -> str:
    """헬스체크용 — 지금 어떤 파일을 쓰는지."""
    return str(PARQUET_PATH if PARQUET_PATH.exists() else CSV_PATH)


@functools.lru_cache(maxsize=1)
def available_districts() -> tuple[str, ...]:
    """데이터에 존재하는 자치구 목록(커버리지). '모르면 모른다'의 근거. 정제 후 25개."""
    return tuple(sorted(_load()["구"].dropna().unique()))


def match_district(text: str) -> str:
    """자유 텍스트에서 자치구 이름을 찾는다(규칙 intake·폴백용). 없으면 ''."""
    for gu in available_districts():
        if gu in text or gu[:-1] in text:      # '강남구' 또는 '강남'
            return gu
    return ""


def _strip_suffix(name: str) -> str:
    """도로·행정동 접미사를 하나만 뗀 어간. 긴 접미사 우선. 해당 없으면 ''."""
    for sfx in ("고속도로", "대로", "로", "길", "동", "가"):
        if name.endswith(sfx):
            return name[:-len(sfx)]
    return ""


@functools.lru_cache(maxsize=1)
def place_names() -> tuple[str, ...]:
    """데이터에 실제로 있는 '자치구가 아닌' 장소 이름 — 동 이름 + 노선 이름.  [DECISIONS DP15]

    규칙 intake(LLM 없이)가 '대치동'·'양재천로' 같은 장소 표현을 알아보는 데 쓴다. 긴 이름부터
    돌려주어 '양재천로'가 '양재천'보다 먼저 잡히게 한다. 지어낸 지명 목록이 아니라 데이터에서 뽑는다.
    """
    df = _load()
    dong = df["지번"].str.extract(r"서울특별시\s+\S+구\s+(\S+)")[0].dropna().unique()
    lines = df["노선"].dropna().unique()
    gus = set(available_districts())
    names = {str(x).strip() for x in list(dong) + list(lines)}
    # 사람은 '양재천로'를 '양재천', '여의도동'을 '여의도'라 부른다 — 접미사를 뗀 형태도 같이 넣는다.
    # 긴 접미사 먼저 하나만 뗀다('강남대로'에서 '로'를 떼면 '강남대' 같은 조각이 생김).
    # 3글자 이상만 남긴다(‘종로’→‘종’, ‘역삼동’→‘역삼’ 같은 조각의 오탐을 피함).
    names |= {st for n in names if (st := _strip_suffix(n)) and len(st) >= 3 and not st[-1].isdigit()}
    names = {n for n in names if len(n) >= 2 and n not in gus and not n.endswith("구")}
    return tuple(sorted(names, key=len, reverse=True))


def match_place(text: str) -> str:
    """자유 텍스트에서 자치구가 아닌 장소 이름을 찾는다(가장 긴 것 하나). 없으면 ''.

    '양재천 근처 벚꽃길' → '양재천로'가 아니라 '양재천'? — 데이터의 노선명 '양재천로'가 더 길어
    먼저 잡힌다. 텍스트에 '양재천'만 있으면 부분 문자열이라 '양재천로'는 안 잡히고 동 이름 등에서 찾는다.
    자치구가 이미 잡힌 질문에는 부르지 않는다(graph.rule_intake).
    """
    for name in place_names():
        if name in text:
            return name
    return ""


def _hotspot_focus(seg, cell: float = 0.004) -> dict:
    """도로 나무 좌표에서 가장 밀집한 ~1km 격자를 찾아 지도 focus(center·bbox) 반환.

    긴 대로도 걷기 좋은 밀집 구간으로 좁힌다. cell≈0.004°≈400~450m, 창은 ±1칸.
    """
    gy = (seg["위도"] / cell).round()
    gx = (seg["경도"] / cell).round()
    (by, bx) = gy.astype(str).str.cat(gx.astype(str), sep=",").mode().iloc[0].split(",")
    by, bx = float(by), float(bx)
    win = seg[(gy >= by - 1) & (gy <= by + 1) & (gx >= bx - 1) & (gx <= bx + 1)]
    return {
        "center": [round(float(win["위도"].mean()), 6), round(float(win["경도"].mean()), 6)],
        "bbox": [[round(float(win["위도"].min()), 6), round(float(win["경도"].min()), 6)],
                 [round(float(win["위도"].max()), 6), round(float(win["경도"].max()), 6)]],
    }


@tool
def find_theme_streets(theme: str, district: str = "", top_only: bool = False) -> dict:
    """특정 테마에 맞는(또는 회피할) 가로수가 밀집한 도로를 찾는다.

    Args:
        theme: 테마 키. 다음 중 하나 —
            은행회피 · 벚꽃 · 그늘 · 이팝 · 은행단풍 · 메타세쿼이아
        district: 자치구 이름(예: '강남구'). 비우면 서울 전체에서 찾는다.
        top_only: '가장 큰/제일 좋은 길 하나'처럼 단일 도로를 원할 때 True.
            True면 1등 도로만 반환하고 지도 focus도 그 도로로 좁힌다.

    Returns:
        {ok, theme, mode, season, district, streets:[{구,노선,그루수,center}], focus, note}
        - mode가 'prefer'면 streets는 '걷기 좋은 추천 길',
          'avoid'면 '피하는 게 좋은 길'이다.
        - 데이터에 없는 테마/자치구면 ok=False 와 사유·후보를 돌려준다.
    """
    if theme not in THEMES:
        return {"ok": False, "reason": f"모르는 테마: {theme}",
                "valid_themes": list(THEMES.keys())}
    df = _load()
    if district:
        if district not in available_districts():
            return {"ok": False, "reason": f"데이터에 없는 자치구: {district}",
                    "valid_districts_sample": list(available_districts())[:8],
                    "coverage": f"총 {len(available_districts())}개 자치구"}
        df = df[df["구"] == district]

    spec = THEMES[theme]
    hit = df[df["수종"].isin(spec["species"])]
    if hit.empty:
        return {"ok": False, "reason": "해당 지역에 이 테마의 가로수 데이터가 없음",
                "theme": theme, "district": district or "서울 전체"}

    # 노선 결측 행은 groupby에서 자동 제외됨(좌표 기반 경로로 가면 다시 살아남)
    ranked = (
        hit.groupby(["구", "노선"]).size()
        .sort_values(ascending=False).reset_index(name="그루수")
    )
    top = ranked.head(1 if top_only else 6)
    streets = []
    for _, r in top.iterrows():
        seg = hit[(hit["구"] == r["구"]) & (hit["노선"] == r["노선"])]
        streets.append({
            "구": str(r["구"]), "노선": str(r["노선"]), "그루수": int(r["그루수"]),
            # 지도 이동용 중심좌표(가벼움). 마커 점 배열은 map_api.street_points()로 UI가 따로 가져감.
            "center": [round(float(seg["위도"].mean()), 6), round(float(seg["경도"].mean()), 6)],
        })
    # 지도 뷰(pan/zoom 대상) = 1등 도로에서 나무가 가장 몰린 ~1km 핫스팟.
    # 도로 전체 bbox를 쓰면 올림픽대로처럼 도시를 가로지르는 대로에서 지도가 서울 전체로
    # 확대돼 버린다. 걷기 좋은 밀집 구간으로 좁힌다.
    r0 = top.iloc[0]
    primary_seg = hit[(hit["구"] == r0["구"]) & (hit["노선"] == r0["노선"])]
    focus = _hotspot_focus(primary_seg)
    focus["primary"] = {"구": str(r0["구"]), "노선": str(r0["노선"])}
    return {
        "ok": True, "theme": theme, "mode": spec["mode"], "season": spec["season"],
        "district": district or "서울 전체", "total_trees": int(len(hit)),
        "streets": streets, "focus": focus, "note": spec["note"],
    }


@tool
def check_coverage(district: str = "") -> dict:
    """가로수 데이터가 어떤 자치구를 포함하는지 확인한다.

    Args:
        district: 확인할 자치구. 비우면 전체 목록을 돌려준다.
    Returns:
        {covered: bool, districts: [...]} — 답할 수 있는 범위를 정직하게 알려준다.
    """
    dists = list(available_districts())
    if district:
        return {"covered": district in dists, "district": district, "districts": dists}
    return {"covered": None, "count": len(dists), "districts": dists}


@functools.lru_cache(maxsize=64)
def district_centroid(gu: str):
    """자치구 가로수들의 평균 좌표(대표 지점). 없으면 None."""
    sub = _load()[_load()["구"] == gu]
    if sub.empty:
        return None
    return (round(float(sub["위도"].mean()), 6), round(float(sub["경도"].mean()), 6))


# 카카오 로컬 키워드검색 — 장소명/랜드마크 → 좌표. REST 키 없으면 건너뜀.
KAKAO_LOCAL_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"


@functools.lru_cache(maxsize=512)
def _geocode_kakao(query: str):
    """장소명·랜드마크(예: '올림픽공원','롯데타워','강남역') → (위도, 경도).

    카카오 로컬 키워드검색으로 해소한다. 서울 안 결과를 우선 채택(회랑이 데이터
    범위 안에 들게). 키(KAKAO_REST_API_KEY) 없음·네트워크 실패·결과 없음이면 None —
    예외를 던지지 않아 오프라인/테스트에서도 조용히 기존 폴백으로 빠진다.
    """
    key = get_settings().kakao_rest_api_key.strip()
    query = (query or "").strip()
    if not key or not query:
        return None
    try:
        resp = httpx.get(
            KAKAO_LOCAL_URL,
            params={"query": query, "size": 15},
            headers={"Authorization": f"KakaoAK {key}"},
            timeout=4.0,
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
    except Exception as exc:  # noqa: BLE001 — 네트워크·스키마 실패는 None으로 폴백
        print(f"  [geocode 폴백] 카카오 실패({type(exc).__name__}) query={query!r}")
        return None
    if not docs:
        return None
    # 서울 소재 결과 우선(없으면 최상위). address_name/road_address_name로 판별.
    def _is_seoul(d: dict) -> bool:
        addr = (d.get("address_name") or "") + (d.get("road_address_name") or "")
        return addr.startswith("서울")
    pick = next((d for d in docs if _is_seoul(d)), docs[0])
    try:
        return (round(float(pick["y"]), 6), round(float(pick["x"]), 6))  # y=위도, x=경도
    except (KeyError, TypeError, ValueError):
        return None


def _resolve_point(s: str):
    """'lat,lon' · 서울 자치구명 · 장소명(카카오 지오코딩) → (위도, 경도). 해석 불가면 None."""
    s = (s or "").strip()
    if "," in s:
        try:
            la, lo = [float(x) for x in s.split(",")[:2]]
            return (la, lo)
        except ValueError:
            pass
    if s in available_districts():
        return district_centroid(s)          # 자치구는 데이터 centroid(오프라인·안정)
    if not s:
        return None
    return _geocode_kakao(s)                  # 랜드마크·역명·건물명은 지오코딩으로 해소


def _seg_dist_km(lat, lon, a, b):
    """각 점(lat,lon 시리즈)에서 선분 a→b까지 수직거리(km). 위경도 평면 근사."""
    lat0 = (a[0] + b[0]) / 2.0
    kx = 111.32 * math.cos(math.radians(lat0))
    ky = 111.32
    ax, ay, bx, by = a[1] * kx, a[0] * ky, b[1] * kx, b[0] * ky
    px, py = lon.to_numpy() * kx, lat.to_numpy() * ky
    dx, dy = bx - ax, by - ay
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return np.hypot(px - ax, py - ay)
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / l2, 0.0, 1.0)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


@tool
def route_theme_streets(origin: str, dest: str, theme: str, width_m: int = 500) -> dict:
    """출발→도착 직선 회랑(±width_m) 안에서 지나가는 테마 가로수길을 찾는다.

    'A에서 B 가는 길에 어떤 테마 가로수길이 있나'에 답할 때 쓴다. 정확한 도보경로가
    아니라 두 지점을 잇는 직선 주변(회랑)에서 만나는 도로다.

    Args:
        origin: 출발지. 서울 자치구명(예: '강남구')·장소명/랜드마크(예: '올림픽공원',
            '롯데타워', '강남역')·'lat,lon' 좌표. 장소명은 카카오 지오코딩으로 좌표 해소.
        dest: 목적지. 형식은 origin과 같다.
        theme: 은행회피·벚꽃·그늘·이팝·은행단풍·메타세쿼이아 중 하나.
        width_m: 회랑 반폭(m). 기본 500.

    Returns:
        {ok, kind:'route', theme, origin, dest, streets:[{구,노선,그루수,center}],
         corridor:{line:[[lat,lon],[lat,lon]], bbox}, focus, note}
        해석 불가/경유 나무 없음이면 ok=False 와 사유.
    """
    if theme not in THEMES:
        return {"ok": False, "reason": f"모르는 테마: {theme}",
                "valid_themes": list(THEMES.keys())}
    a, b = _resolve_point(origin), _resolve_point(dest)
    if a is None or b is None:
        bad = [x for x, p in [(origin, a), (dest, b)] if p is None]
        return {"ok": False, "kind": "route",
                "reason": f"출발/도착을 좌표로 해석 못함: {bad}",
                "hint": "서울 자치구명 또는 'lat,lon'으로 주세요",
                "valid_districts_sample": list(available_districts())[:8]}
    spec = THEMES[theme]
    hit = _load()[_load()["수종"].isin(spec["species"])]
    dist = _seg_dist_km(hit["위도"], hit["경도"], a, b)
    within = hit[dist <= width_m / 1000.0]
    if within.empty:
        return {"ok": False, "kind": "route", "theme": theme,
                "origin": origin, "dest": dest,
                "reason": f"가는 길(±{width_m}m)에 {theme} 가로수가 거의 없음"}
    top = (within.groupby(["구", "노선"]).size()
           .sort_values(ascending=False).head(6).reset_index(name="그루수"))
    streets = []
    for _, r in top.iterrows():
        seg = within[(within["구"] == r["구"]) & (within["노선"] == r["노선"])]
        streets.append({
            "구": str(r["구"]), "노선": str(r["노선"]), "그루수": int(r["그루수"]),
            "center": [round(float(seg["위도"].mean()), 6), round(float(seg["경도"].mean()), 6)],
        })
    lats, lons = [a[0], b[0]], [a[1], b[1]]
    bbox = [[round(min(lats), 6), round(min(lons), 6)],
            [round(max(lats), 6), round(max(lons), 6)]]
    return {
        "ok": True, "kind": "route", "theme": theme, "mode": spec["mode"],
        "season": spec["season"], "origin": origin, "dest": dest, "width_m": width_m,
        "total_trees": int(len(within)), "streets": streets,
        "corridor": {"line": [[round(a[0], 6), round(a[1], 6)],
                              [round(b[0], 6), round(b[1], 6)]], "bbox": bbox},
        "focus": {"center": [round(sum(lats) / 2, 6), round(sum(lons) / 2, 6)],
                  "bbox": bbox, "primary": {"구": str(top.iloc[0]["구"]),
                                            "노선": str(top.iloc[0]["노선"])}},
        "note": spec["note"],
    }


# 에이전트에 넘길 도구 묶음
TOOLS = [find_theme_streets, check_coverage, route_theme_streets]


if __name__ == "__main__":
    # 도구 단독 점검
    print("데이터:", data_source())
    print("커버리지:", check_coverage.invoke({})["count"], "개 자치구")
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "강동구"}))
    print(find_theme_streets.invoke({"theme": "은행단풍", "district": "종로구"})["streets"][:2])
    print(find_theme_streets.invoke({"theme": "벚꽃", "district": "없는구"}))
