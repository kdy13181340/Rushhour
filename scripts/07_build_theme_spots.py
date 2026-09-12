"""테마길 데이터셋 — 공공자료 넷을 합쳐 우리 것으로.  [DECISIONS DP24]

왜 필요했나: 가로수 대장(`seoul_tree_data.csv`)은 **도로변에 심은 나무**만 센다. 그래서 석촌호수
둘레길·양재천·안양천처럼 사람들이 실제로 벚꽃 보러 가는 **공원·하천 산책로**가 통째로 빠져 있었다.

합치는 것 — 넷 다 공공데이터이고, 좌표·수치를 지어내지 않는다:
  A. 서울 가로수 대장(정제본)          (구, 노선)별 수종 집계 · 나무마다 좌표 · 도로변만 · 서울
  B. 서울 단풍길 110선                **공원·하천변·등산로** · 그루수·연장·선정사유 · 좌표 없음
  C. 전국 가로수길 정보 표준데이터        노선별 **시작·종료 좌표** · 수종·수량·길이·소개 · **전국 16개 시도**
  D. 서울시 가로수 / 공원·사유지 수목     수목 단위 상세(수고·흉고) · 좌표 · **중구만**

**지역 범위 주의**: C·D 덕분에 목록과 지도 표시는 전국이 되지만, **경로 찾기는 서울만** 된다 —
보행 도로망(scripts/04)을 서울 bbox로만 받았기 때문이다. `지역구분` 컬럼으로 갈라 둔다.

**합치되 더하지 않는다**: 같은 길이 자료마다 따로 조사돼 있고 그루수도 다르다(개포로: 대장
1,004 / 표준 1,169). 같은 (시군구, 노선명)에는 `대표=True` 한 행만 두고 나머지는 `중복출처`로
표시한다. 총계는 대표 행만 센다 — 단순 합산은 부풀린 숫자다.

산출물: data/processed/theme_spots.parquet (+ 같은 내용 CSV, 사람 확인용)
실행:  python scripts/07_build_theme_spots.py [--check] [--theme 벚꽃] [--seoul-only]
"""

import argparse
import math
import re
import sys
from pathlib import Path

import pandas as pd

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
DATA = ROOT / "data"

TREES = DATA / "processed" / "seoul_trees.parquet"
MAPLE = DATA / "서울 단풍길 110선.csv"
NATION = DATA / "전국가로수길정보표준데이터.csv"
JUNGGU_ST = DATA / "서울시 가로수 위치정보 (좌표계_ WGS1984).csv"
JUNGGU_PARK = DATA / "서울시 공원 및 사유지수목 위치정보 (좌표계_ WGS1984).csv"
OUT = DATA / "processed" / "theme_spots.parquet"
OUT_CSV = DATA / "processed" / "theme_spots.csv"

SRC = {
    "tree": "서울시 가로수 위치정보(가로수 대장)",
    "maple": "서울 단풍길 110선",
    "nation": "전국 가로수길 정보 표준데이터",
    "junggu_st": "서울시 가로수 위치정보 상세(중구)",
    "junggu_park": "서울시 공원 및 사유지수목(중구)",
}
# 같은 길이 여러 자료에 있을 때 어느 것을 대표로 둘지 — '그 자료만 가진 것'이 큰 순서
SRC_RANK = {SRC["maple"]: 0, SRC["junggu_park"]: 1, SRC["nation"]: 2,
            SRC["junggu_st"]: 3, SRC["tree"]: 4}

# 수종 문구 → 우리 테마 키. 자료마다 표기가 달라 낱말로 잡는다
# ('왕벚나무+은행나무', '느티나무, 단풍나무 등' 같은 자유 문자열이 온다).
# **themes.py의 수종 목록을 뿌리로 쓴다** — 테마가 늘어도 여기를 안 고쳐도 따라간다.
# EXTRA_WORDS는 공공자료에만 나오는 이표기·동의어다.
EXTRA_WORDS = {
    "벚꽃": ("왕벚", "양벚", "벚꽃"),
    "은행단풍": ("은행",),
    "은행회피": ("은행",),
    "그늘": ("버즘", "플라타너스", "칠엽수", "백합나무"),
    "메타세쿼이아": ("메타세콰이어", "메타세콰이아"),
    "크리스마스": ("전나무", "가문비", "주목"),
    "상록": ("상록", "전나무"),
}


def _theme_words() -> dict[str, tuple[str, ...]]:
    from themes import THEMES as _T
    out = {}
    for key, spec in _T.items():
        # '은행나무 암나무' → '은행나무'(첫 낱말), '벚나무류' → '벚나무'(접미사 제거).
        # 공공자료는 '왕벚나무+은행나무'처럼 자유 문자열이라 낱말이 짧아야 걸린다.
        words = set()
        for sp in spec["species"]:
            head = sp.split()[0]
            words.add(head)
            for sfx in ("류", "나무류"):
                if head.endswith(sfx) and len(head) - len(sfx) >= 2:
                    words.add(head[: -len(sfx)])
        words |= set(EXTRA_WORDS.get(key, ()))
        out[key] = tuple(sorted(words, key=len, reverse=True))
    return out


THEME_WORDS = _theme_words()
MIN_TREES = 10          # 이보다 적으면 '길'이라 부르기 어렵다
COLS = ["출처", "지역구분", "시도", "시군구", "구분", "노선명", "구간", "수종", "테마",
        "그루수", "연장_km", "특징", "위도", "경도", "시작위도", "시작경도", "종료위도", "종료경도",
        "매칭", "구간형상"]


def themes_of(text) -> list[str]:
    t = str(text)
    return [k for k, words in THEME_WORDS.items() if any(w in t for w in words)]


def _frame(rows: dict) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    for c in COLS:
        if c not in df.columns:
            df[c] = pd.NA
    return df[COLS]


# ── A. 서울 가로수 대장 ──────────────────────────────────────────────────────
def from_trees() -> pd.DataFrame:
    df = pd.read_parquet(TREES).dropna(subset=["노선"])
    g = df.groupby(["구", "노선"]).agg(
        그루수=("수종", "size"), 위도=("위도", "mean"), 경도=("경도", "mean"),
        수종=("수종", lambda s: ", ".join(s.value_counts().head(3).index)),
    ).reset_index()
    g = g[g["그루수"] >= MIN_TREES]
    g["테마"] = g["수종"].map(lambda s: ",".join(themes_of(s)))
    g = g[g["테마"] != ""]
    return _frame({
        "출처": SRC["tree"], "지역구분": "서울", "시도": "서울특별시", "시군구": g["구"],
        "구분": "가로", "노선명": g["노선"], "구간": "", "수종": g["수종"], "테마": g["테마"],
        "그루수": g["그루수"].astype(int), "특징": "",
        "위도": g["위도"].round(6), "경도": g["경도"].round(6), "매칭": "좌표 직접(가로수 대장)",
    })


# ── C. 전국 표준데이터 ───────────────────────────────────────────────────────
def from_nation(seoul_only: bool = False) -> pd.DataFrame:
    df = pd.read_csv(NATION, encoding="cp949", low_memory=False)
    org = df["제공기관명"].astype(str)
    if seoul_only:
        df = df[org.str.startswith("서울특별시")].copy()
        org = df["제공기관명"].astype(str)
    for c in ("가로수길시작위도", "가로수길시작경도", "가로수길종료위도", "가로수길종료경도",
              "가로수수량", "가로수길길이"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    # 좌표가 한반도 밖이면 버린다(입력 오류 5건 관찰)
    ok = (df["가로수길시작위도"].between(33, 39) & df["가로수길시작경도"].between(124, 132))
    df = df[ok].copy()
    df["테마"] = df["가로수종류"].map(lambda x: ",".join(themes_of(x)))
    # 그루수를 '모르는 것'과 '적은 것'은 다르다. 비어 있으면 남긴다 — 제주는 154개 노선이 전부
    # 수량 미기재라, fillna(0)으로 거르면 왕벚나무 원산지가 통째로 사라진다(실측 후 수정).
    known = df["가로수수량"].notna()
    df = df[(df["테마"] != "") & (~known | (df["가로수수량"] >= MIN_TREES))]
    parts = df["제공기관명"].astype(str).str.split(n=1)
    sido = parts.str[0]
    sigungu = parts.str[1].fillna(sido)
    return _frame({
        "출처": SRC["nation"], "지역구분": sido.map(lambda s: "서울" if s == "서울특별시" else "전국"),
        "시도": sido, "시군구": sigungu, "구분": "가로",
        "노선명": df["가로수길명"].astype(str).str.strip(),
        "구간": df["도로구간"].fillna("").astype(str),
        "수종": df["가로수종류"].astype(str), "테마": df["테마"],
        "그루수": df["가로수수량"].round().astype("Int64"),   # 미기재는 0이 아니라 <NA>로 둔다
        "연장_km": df["가로수길길이"],
        "특징": df["가로수길소개"].fillna("").astype(str),
        "위도": df[["가로수길시작위도", "가로수길종료위도"]].mean(axis=1).round(6),
        "경도": df[["가로수길시작경도", "가로수길종료경도"]].mean(axis=1).round(6),
        "시작위도": df["가로수길시작위도"], "시작경도": df["가로수길시작경도"],
        "종료위도": df["가로수길종료위도"], "종료경도": df["가로수길종료경도"],
        "매칭": "좌표 직접(표준데이터 시작·종료)",
    })


# ── D. 중구 상세 두 종 ───────────────────────────────────────────────────────
def from_junggu() -> pd.DataFrame:
    out = []
    st = pd.read_csv(JUNGGU_ST, encoding="cp949", low_memory=False)
    for c in ("경도", "위도"):          # 문자열로 읽히는 행이 섞여 있다
        st[c] = pd.to_numeric(st[c], errors="coerce")
    st = st.dropna(subset=["가로명", "경도", "위도"])
    g = st.groupby(["구명", "가로명"]).agg(
        그루수=("수목명", "size"), 위도=("위도", "mean"), 경도=("경도", "mean"),
        수종=("수목명", lambda s: ", ".join(s.value_counts().head(3).index)),
    ).reset_index()
    g = g[g["그루수"] >= MIN_TREES]
    g["테마"] = g["수종"].map(lambda s: ",".join(themes_of(s)))
    g = g[g["테마"] != ""]
    out.append(_frame({
        "출처": SRC["junggu_st"], "지역구분": "서울", "시도": "서울특별시", "시군구": g["구명"],
        "구분": "가로", "노선명": g["가로명"], "구간": "", "수종": g["수종"], "테마": g["테마"],
        "그루수": g["그루수"].astype(int), "특징": "",
        "위도": g["위도"].round(6), "경도": g["경도"].round(6), "매칭": "좌표 직접(중구 상세)",
    }))

    pk = pd.read_csv(JUNGGU_PARK, encoding="cp949", low_memory=False)
    for c in ("경도", "위도"):
        pk[c] = pd.to_numeric(pk[c], errors="coerce")
    pk["위치"] = pk["위치"].astype(str).str.strip()
    pk = pk[(pk["위치"] != "") & pk["경도"].notna() & pk["위도"].notna()]
    g = pk.groupby(["구명", "위치"]).agg(
        그루수=("수목명", "size"), 위도=("위도", "mean"), 경도=("경도", "mean"),
        수종=("수목명", lambda s: ", ".join(s.value_counts().head(3).index)),
        동=("동명", lambda s: s.value_counts().index[0] if len(s) else ""),
    ).reset_index()
    g = g[g["그루수"] >= MIN_TREES]
    g["테마"] = g["수종"].map(lambda s: ",".join(themes_of(s)))
    g = g[g["테마"] != ""]
    out.append(_frame({
        "출처": SRC["junggu_park"], "지역구분": "서울", "시도": "서울특별시", "시군구": g["구명"],
        "구분": "공원", "노선명": g["위치"], "구간": g["동"], "수종": g["수종"], "테마": g["테마"],
        "그루수": g["그루수"].astype(int), "특징": "",
        "위도": g["위도"].round(6), "경도": g["경도"].round(6), "매칭": "좌표 직접(중구 공원·사유지)",
    }))
    return pd.concat(out, ignore_index=True)


# ── B. 단풍길 110선 — 좌표가 없어 이름을 맞춰 본다 ───────────────────────────
def _strip(name) -> str:
    return re.sub(r"\(.*?\)", "", str(name)).strip()


def _stems(name) -> list[str]:
    base = _strip(name)
    out = [base]
    head = base.split()[0] if base.split() else base
    if head != base:
        out.append(head)
    for s in (base, head):
        for sfx in ("제방길", "변길", "산책로", "둘레길", "순환로", "길", "로", "천", "변", "지구"):
            if s.endswith(sfx) and len(s) - len(sfx) >= 2:
                out.append(s[: -len(sfx)])
    stream = re.search(r"(\w{2,3}천)", base)
    if stream:
        out.append(stream.group(1))
    return list(dict.fromkeys(x for x in out if len(x) >= 2))


# 어간 뒤에 붙어도 같은 길로 볼 수 있는 꼬리. '송정'+'10길'처럼 숫자가 끼면 다른 길이다.
CLEAN_TAIL = ("", "로", "길", "대로", "천로", "천길", "산책로", "둘레길", "순환로", "제방길", "변길")


def _match(cand: str, pool: set[str]) -> str:
    """이름이 같거나 도로 꼬리만 더 붙은 것. 느슨한 부분일치는 '송정제방길'을 '송정10길'에 붙인다."""
    if cand in pool:
        return cand
    for n in sorted(pool):
        if n.startswith(cand) and n[len(cand):] in CLEAN_TAIL:
            return n
    return ""


def from_maple(pools) -> pd.DataFrame:
    mp = pd.read_csv(MAPLE, encoding="cp949")
    rows = []
    for _, r in mp.iterrows():
        raw = str(r["노선명(구간)"])
        themes = themes_of(r["수종"])
        if not themes:
            continue
        gus = {x.strip() for x in re.split(r"[/,]", str(r["자치구(사업소)"])) if x.strip().endswith("구")}
        matched, how, lat, lon = "", "", pd.NA, pd.NA
        for cand in _stems(raw):
            for label, pool, coords in pools:
                hit = _match(cand, pool)
                if not hit:
                    continue
                info = coords.get(hit)
                if info and gus and info.get("gus") and not (gus & info["gus"]):
                    continue                      # 자치구가 어긋나면 동명이인이다
                matched, how = hit, label
                if info:
                    lat, lon = info.get("lat", pd.NA), info.get("lon", pd.NA)
                break
            if matched:
                break
        seg = re.search(r"\((.*?)\)", raw)
        rows.append({
            "출처": SRC["maple"], "지역구분": "서울", "시도": "서울특별시",
            "시군구": str(r["자치구(사업소)"]), "구분": str(r["구분"]),
            "노선명": _strip(raw), "구간": seg.group(1) if seg else "",
            "수종": str(r["수종"]), "테마": ",".join(themes), "그루수": int(r["수량(그루)"]),
            "연장_km": float(r["연장(km)"]) if pd.notna(r["연장(km)"]) else pd.NA,
            "특징": str(r["특징(선정사유)"]), "위도": lat, "경도": lon,
            "매칭": f"이름 매칭({how}:{matched})" if matched else "",
        })
    return _frame(rows)


def fix_length(df: pd.DataFrame) -> pd.DataFrame:
    """연장(km)의 단위 오류를 그 행 자신의 좌표로 검산해 바로잡는다.

    여러 지자체가 미터로 적어 놨다(부평구 길주로 3,400 = 3.4km). 단일 도로 72,400km 같은 값이 남으면
    "10km 코스" 같은 답이 거짓이 된다. 시작~종료 직선거리와 견줘 1000배 어긋나면 미터로 보고 나눈다 —
    지어내는 게 아니라 **그 행이 이미 가진 좌표로 검산**하는 것이다. 판별 못 하면 비운다.
    """
    import numpy as np
    df = df.copy()
    L = pd.to_numeric(df["연장_km"], errors="coerce")
    lat1, lon1 = pd.to_numeric(df["시작위도"], errors="coerce"), pd.to_numeric(df["시작경도"], errors="coerce")
    lat2, lon2 = pd.to_numeric(df["종료위도"], errors="coerce"), pd.to_numeric(df["종료경도"], errors="coerce")
    straight = np.hypot((lat1 - lat2) * 111.32, (lon1 - lon2) * 88.8)      # km, 서울~부산 위도대 근사
    ratio = L / straight.replace(0, np.nan)
    note = pd.Series("", index=df.index, dtype=object)
    # 직선거리의 10배가 넘는데 1000으로 나누면 0.5~20배로 들어오면 미터 표기다
    as_m = L / 1000.0
    m_ok = (ratio > 10) & ((as_m / straight.replace(0, np.nan)).between(0.5, 20))
    L = L.mask(m_ok, as_m)
    note = note.mask(m_ok, "m→km 보정")
    # 그래도 말이 안 되는 값은 비운다(직선거리의 20배 초과, 또는 좌표가 없는데 200km 초과)
    bad = ((ratio > 10) & ~m_ok) | (straight.isna() & (L > 200)) | (L > 500)
    L = L.mask(bad)
    note = note.mask(bad, "값 이상 — 비움")
    df["연장_km"] = L.round(3)
    df["연장보정"] = note
    return df


def _near_row(path, lat, lon, km: float = 1.2) -> bool:
    """얻은 형상이 **그 행이 말하는 그 길**인지. 도로 이름은 전국에서 겹친다(‘중앙로’ 등).

    이름만 믿으면 부산 중앙로의 형상이 대전 행에 붙는다. 실측으로 걸러 보니 이름이 같은데
    딴 동네인 경우가 163/404였다 — 그래서 행 자신의 좌표에서 km 안에 오는 형상만 받는다.
    """
    for seg in path:
        for y, x in seg:
            if math.hypot((y - lat) * 111.32, (x - lon) * 88.8) <= km:
                return True
    return False


def attach_shapes(df: pd.DataFrame) -> pd.DataFrame:
    """행에 **그 길의 실제 보행 형상**을 담는다.  [DP24]

    합본은 노선당 좌표가 한 점뿐이라 '석촌호수 1,660그루'가 점 하나로 찍힌다. 형상이 있으면
    구간을 따라 보여 줄 수 있다 — 개별 나무 위치를 아는 게 아니라 **어느 구간인지**를 표시하는 것이다.
    시작·종료만 있는 행은 화면에서 직선으로 잇는 수밖에 없는데, 직선은 블록을 가로지른다.
    도로망에서 같은 이름을 찾아 두면 굽은 길은 굽은 대로 나온다.

    가로수 대장 행은 건너뛴다 — 나무 한 그루씩 좌표가 있어 지도에 따로 그리고 있다.
    """
    try:
        import routing as R
        if not R.osm_ready():
            return df
    except Exception:  # noqa: BLE001
        return df
    shapes, by_name, hit = [], 0, 0
    for _, r in df.iterrows():
        if "가로수 대장" in str(r.get("출처") or ""):
            shapes.append(None)
            continue
        m = re.search(r"\(([^:]+):(.+)\)", str(r.get("매칭") or ""))
        path = R.way_path(m.group(2), max_paths=2) if m else []
        if not path and str(r.get("노선명") or "") and not pd.isna(r.get("위도")):
            cand = R.way_path(str(r["노선명"]), max_paths=2)
            if cand and _near_row(cand, float(r["위도"]), float(r["경도"])):
                path, by_name = cand, by_name + 1
        if path:
            hit += 1
        shapes.append(path or None)
    df = df.copy()
    df["구간형상"] = shapes
    print(f"  구간 형상을 얻은 노선 {hit}/{len(df)} (이름 매칭 {hit - by_name} · 노선명+거리 {by_name})")
    return df


def _harmonize(df: pd.DataFrame) -> pd.DataFrame:
    """그루수를 nullable 정수로 통일한다 — 미기재(<NA>)와 0을 섞지 않기 위해서."""
    df = df.copy()
    df["그루수"] = pd.to_numeric(df["그루수"], errors="coerce").round().astype("Int64")
    return df


def mark_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    key = list(zip(df["시군구"].astype(str), df["노선명"].astype(str)))
    df["_key"] = key
    seen = {}
    for k, src in zip(key, df["출처"]):
        seen.setdefault(k, set()).add(src)
    df["중복출처"] = [",".join(sorted(seen[k] - {src})) for k, src in zip(key, df["출처"])]
    df["_rank"] = df["출처"].map(SRC_RANK).fillna(9)
    keep = df.sort_values("_rank").drop_duplicates("_key").index
    df["대표"] = df.index.isin(keep)
    return df.drop(columns=["_key", "_rank"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="저장하지 않고 진단만")
    ap.add_argument("--theme", help="이 테마만 요약해 보기")
    ap.add_argument("--seoul-only", action="store_true", help="표준데이터도 서울만")
    args = ap.parse_args()

    a, c, d = from_trees(), from_nation(args.seoul_only), from_junggu()

    # 이름 → 좌표·자치구 사전. 표준데이터(공식 노선명+좌표)를 먼저 본다.
    pools = []
    for label, df in (("표준데이터", c), ("중구 상세", d), ("가로수 대장", a)):
        coords, pool = {}, set()
        for _, r in df.iterrows():
            nm = str(r["노선명"])
            pool.add(nm)
            info = coords.setdefault(nm, {"gus": set(), "lat": r["위도"], "lon": r["경도"]})
            info["gus"].add(str(r["시군구"]))
        pools.append((label, pool, coords))
    try:
        import numpy as np
        import routing as R
        g = R._graph()
        # 이름만 맞추고 좌표를 안 가져오면 지도에 못 올린다(송파나루 근린공원 1,660그루가 그랬다).
        # 그 이름을 가진 간선들의 좌표 평균을 같이 담는다.
        names, osm_coords = g["name"], {}
        lat0 = g["lat"][g["ui"]]                     # 간선 시작 노드 좌표로 대표점을 잡는다
        lon0 = g["lon"][g["ui"]]
        for nm in np.unique(names):
            key = str(nm)
            if key in ("", "nan"):
                continue
            m = names == nm
            osm_coords[key] = {"gus": set(), "lat": round(float(lat0[m].mean()), 6),
                               "lon": round(float(lon0[m].mean()), 6)}
        pools.append(("OSM", set(osm_coords), osm_coords))
    except Exception as exc:  # noqa: BLE001 — 도로망이 없어도 나머지로 만든다
        print(f"(도로망 없음: {type(exc).__name__} — OSM 이름 매칭은 건너뛴다)")

    b = from_maple(pools)
    out = attach_shapes(
        mark_duplicates(fix_length(_harmonize(pd.concat([c, b, d, a], ignore_index=True)))))

    print(f"A 서울 가로수 대장   {len(a):6,}개 · {int(a['그루수'].sum()):9,}그루 (좌표 있음)")
    print(f"C 전국 표준데이터    {len(c):6,}개 · {int(c['그루수'].sum()):9,}그루 · "
          f"시도 {c['시도'].nunique()}곳 (좌표 있음)")
    print(f"D 중구 상세 2종     {len(d):6,}개 · {int(d['그루수'].sum()):9,}그루 (좌표 있음)")
    print(f"B 단풍길 110선     {len(b):6,}개 · {int(b['그루수'].sum()):9,}그루 · "
          f"좌표 얻음 {int(b['위도'].notna().sum())}/{len(b)} · {b['구분'].value_counts().to_dict()}")
    rep = out[out["대표"]]
    print(f"\n합계 {len(out):,}행 · 좌표 있는 행 {int(out['위도'].notna().sum()):,} · "
          f"겹치는 행 {int((out['중복출처'] != '').sum()):,}")
    na = int(rep["그루수"].isna().sum())
    print(f"대표 행(중복 제거) {len(rep):,}개 — 그루수는 이것만 센다 (그루수 미기재 {na:,}개)")
    fixed = int((out["연장보정"] == "m→km 보정").sum())
    blank = int((out["연장보정"] == "값 이상 — 비움").sum())
    print(f"연장 단위 보정 {fixed:,}행(미터로 적힌 것) · 판별 못 해 비운 것 {blank:,}행")
    print(f"  서울 {int((rep['지역구분'] == '서울').sum()):,}개 · 그 외 전국 "
          f"{int((rep['지역구분'] == '전국').sum()):,}개")
    print()
    print(f"{'테마':12s} {'대표':>7s} {'그루수':>12s} {'서울':>7s} {'전국':>7s}")
    for t in THEME_WORDS:
        r = rep[rep["테마"].str.contains(t, na=False)]
        print(f"  {t:10s} {len(r):6,} {int(r['그루수'].sum()):11,} "
              f"{int((r['지역구분'] == '서울').sum()):6,} {int((r['지역구분'] == '전국').sum()):6,}")
    print()
    print("시도별 대표 노선 수:")
    for k, v in rep["시도"].value_counts().items():
        print(f"  {k:14s} {v:5,}")

    if args.theme:
        sub = rep[rep["테마"].str.contains(args.theme, na=False)].sort_values("그루수", ascending=False)
        print(f"\n=== {args.theme} 전국 상위 12 ===")
        print(sub[["시도", "시군구", "구분", "노선명", "그루수", "연장_km"]].head(12).to_string(index=False))

    if args.check:
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT}  ({len(out):,}행)\n      {OUT_CSV}")


if __name__ == "__main__":
    main()
