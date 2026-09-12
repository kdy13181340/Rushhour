"""테마길 명소(공공자료 합본) 조회.  [DECISIONS DP24]

`scripts/07_build_theme_spots.py`가 만든 `data/processed/theme_spots.parquet`을 읽어
테마·지역으로 고르고, 지도·답변에 쓸 모양으로 돌려준다.

가로수 대장(`tools.find_theme_streets`)과 무엇이 다른가:
  - 대장은 **서울 도로변 나무 28만 그루**를 좌표까지 들고 있다. 경로·마커의 근거다.
  - 여기는 **공원·하천·등산로와 전국 노선**까지 담은 목록이다. 좌표는 노선당 한 점(또는 시작·종료)뿐이라
    선을 그릴 수 없다 — 지도에는 **점**으로 찍는다. 가짜 도로선을 그리면 실제 경로처럼 보인다.
  - 그루수 근거가 자료마다 다르므로 답변에는 **출처를 함께** 말한다.
"""

import functools
import math
import os
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

ROOT = Path(__file__).resolve().parents[1]
SPOTS_PATH = Path(os.environ.get("THEME_SPOTS", ROOT / "data" / "processed" / "theme_spots.parquet"))
MAX_K = 20000      # 지도에 전국을 통째로 뿌리는 용도까지. @tool 기본은 훨씬 작다(k=8)


@functools.lru_cache(maxsize=1)
def _load() -> pd.DataFrame:
    if not SPOTS_PATH.exists():
        raise FileNotFoundError(
            f"테마길 합본 없음: {SPOTS_PATH} — python scripts/07_build_theme_spots.py 를 먼저 실행할 것")
    df = pd.read_parquet(SPOTS_PATH)
    return df[df["대표"]].reset_index(drop=True)      # 총계·목록은 대표 행만(중복 합산 방지)


def spots_status() -> dict:
    """헬스체크용 — 합본이 있는지, 얼마나 되는지."""
    if not SPOTS_PATH.exists():
        return {"ready": False, "path": str(SPOTS_PATH),
                "hint": "python scripts/07_build_theme_spots.py"}
    try:
        df = _load()
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "path": str(SPOTS_PATH), "reason": f"{type(exc).__name__}: {exc}"[:160]}
    return {"ready": True, "path": str(SPOTS_PATH), "spots": len(df),
            "sido": int(df["시도"].nunique()),
            "seoul": int((df["지역구분"] == "서울").sum()),
            "sources": sorted(df["출처"].unique().tolist())}


def _light_row(r) -> dict:
    """지도에 점만 찍을 때 쓰는 가벼운 모양 — 전국 수천 개를 한 번에 보내야 해서 필드를 줄인다."""
    return {
        "n": r["노선명"], "g": f"{r['시도']} {r['시군구']}".replace("서울특별시 ", ""),
        "k": r["구분"], "s": r["수종"],
        "c": None if pd.isna(r["그루수"]) else int(r["그루수"]),
        "km": None if pd.isna(r["연장_km"]) else round(float(r["연장_km"]), 2),
        "t": [t for t in str(r["테마"]).split(",") if t],
        "ll": [round(float(r["위도"]), 6), round(float(r["경도"]), 6)],
        # 구간 형상이 있으면 함께. 개별 나무 위치가 아니라 '이 구간'이라는 표시다.
        "path": [[[round(float(y), 6), round(float(x), 6)] for y, x in seg]
                 for seg in (r["구간형상"] if r.get("구간형상") is not None else [])] or None,
        # 형상이 없으면 시작~종료 두 점. 화면에서 구간을 따라 나무를 뿌리는 데 쓴다.
        "se": ([[round(float(r["시작위도"]), 6), round(float(r["시작경도"]), 6)],
                [round(float(r["종료위도"]), 6), round(float(r["종료경도"]), 6)]]
               if not pd.isna(r["시작위도"]) and not pd.isna(r["종료위도"]) else None),
        "src": r["출처"],
    }


def all_points(theme: str = "") -> dict:
    """좌표가 있는 행을 전부 — 지도에 나무로 뿌리기 위한 것.  [DP24]

    '명소 고르기'가 아니라 **가진 좌표를 다 보여 주는** 용도다. 그루수 상위만 추리면 전국 분포가
    안 보인다. 필드를 줄여 한 번에 보낸다.
    """
    try:
        df = _load()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    df = df[df["위도"].notna() & df["경도"].notna()]
    if theme:
        df = df[df["테마"].str.contains(theme, na=False)]
    return {"ok": bool(len(df)), "count": len(df), "theme": theme,
            "points": [_light_row(r) for _, r in df.iterrows()],
            "note": "좌표가 있는 모든 노선. 노선당 대표점 하나이고 도로 형상이 아니다. "
                    "그루수는 자료마다 조사가 달라 출처를 함께 봐야 한다."}


def _row(r) -> dict:
    def num(v):
        return None if pd.isna(v) else (round(float(v), 6) if isinstance(v, float) else v)
    line = None
    if not pd.isna(r["시작위도"]) and not pd.isna(r["종료위도"]):
        line = [[num(r["시작위도"]), num(r["시작경도"])], [num(r["종료위도"]), num(r["종료경도"])]]
    return {
        "시도": r["시도"], "시군구": r["시군구"], "구분": r["구분"], "노선명": r["노선명"],
        "구간": r["구간"] or "", "수종": r["수종"], "테마": [t for t in str(r["테마"]).split(",") if t],
        # 그루수가 <NA>면 None으로 — 0으로 바꾸면 '나무가 없다'는 거짓말이 된다
        "그루수": None if pd.isna(r["그루수"]) else int(r["그루수"]),
        "연장_km": num(r["연장_km"]), "특징": (r["특징"] or "")[:200],
        "center": [num(r["위도"]), num(r["경도"])] if not pd.isna(r["위도"]) else None,
        # 시작·종료 두 점뿐이라 '대략 이 구간'이라는 뜻이다. 실제 도로 형상이 아니다.
        "구간선_근사": line,
        "출처": r["출처"], "지역구분": r["지역구분"],
    }


def find_spots(theme: str = "", sido: str = "", sigungu: str = "", kind: str = "",
               k: int = 10, seoul_only: bool = False) -> dict:
    """테마길 합본에서 조건에 맞는 명소를 그루수 순으로."""
    try:
        df = _load()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"[:200]}
    if theme:
        df = df[df["테마"].str.contains(theme, na=False)]
    if sido:
        df = df[df["시도"].str.contains(sido, na=False)]
    if sigungu:
        df = df[df["시군구"].str.contains(sigungu, na=False)]
    if kind:
        df = df[df["구분"] == kind]
    if seoul_only:
        df = df[df["지역구분"] == "서울"]
    if df.empty:
        return {"ok": False, "reason": "조건에 맞는 테마길이 없음",
                "theme": theme, "sido": sido, "sigungu": sigungu}
    # 그루수 미기재는 뒤로(na_position) — 모르는 것을 0으로 봐서 맨 끝에 두는 것과 같지만 명시적으로
    df = df.sort_values("그루수", ascending=False, na_position="last").head(max(1, min(int(k), MAX_K)))
    return {"ok": True, "theme": theme, "count": len(df),
            "spots": [_row(r) for _, r in df.iterrows()],
            "note": "공공자료 합본(가로수 대장·전국 가로수길 표준데이터·서울 단풍길 110선·중구 상세). "
                    "그루수는 자료마다 조사가 달라 출처를 함께 봐야 한다. 좌표는 노선당 한 점이라 "
                    "지도에는 점으로 찍는다."}


@tool
def find_theme_spots(theme: str, region: str = "", k: int = 8) -> dict:
    """공원·하천 산책로까지 포함한 **테마길 명소**를 찾는다(전국).

    `find_theme_streets`가 서울 도로변 가로수만 보는 것과 달리, 이 도구는 공원·하천변·등산로와
    서울 밖 지역까지 담은 공공자료 합본을 본다. 석촌호수 둘레길·양재천·안양천처럼 도로가 아닌
    산책로를 물을 때 쓴다.

    Args:
        theme: 벚꽃 · 은행단풍 · 은행회피 · 그늘 · 이팝 · 메타세쿼이아 중 하나.
        region: 시도나 시군구 이름(예 '서울', '부산광역시', '송파구'). 비우면 전국.
        k: 몇 개까지(1~800, 답변에는 8~10개면 충분).

    Returns:
        {ok, spots:[{시도, 시군구, 구분, 노선명, 수종, 그루수, 연장_km, 특징, center, 출처}], note}
        - 구분: 가로 · 공원 · 하천변 · 등산로
        - center는 노선당 한 점이라 지도에는 점으로 찍는다(도로 형상이 아님).
        - 그루수는 자료마다 조사가 달라 `출처`를 함께 말해야 한다.
        - **경로 찾기(plan_route)는 서울만 된다** — 보행 도로망을 서울만 받았기 때문.
    """
    r = region.strip()
    res = find_spots(theme=theme, sido=r if r.endswith(("도", "시", "구", "군")) and len(r) > 2 else r,
                     k=k)
    if not res.get("ok") and r:
        res = find_spots(theme=theme, sigungu=r, k=k)      # 시도로 못 찾으면 시군구로
    return res
