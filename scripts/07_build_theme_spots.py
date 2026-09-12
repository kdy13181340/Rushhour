"""서울 테마길 데이터셋 — 공공 자료 셋을 합쳐 우리 것으로.  [DECISIONS DP24]

왜 필요했나: 가로수 대장(`seoul_tree_data.csv`)은 **도로변에 심은 나무**만 센다. 그래서 석촌호수
둘레길·양재천·안양천처럼 사람들이 실제로 벚꽃 보러 가는 **공원·하천 산책로**가 통째로 빠져 있었다.

합치는 것 — 셋 다 공공데이터이고, 좌표·수치를 지어내지 않는다:
  A. 가로수 대장 정제본              (구, 노선)별 수종 집계 · 좌표 있음 · 도로변만
  B. 서울 단풍길 110선               공원·하천변·등산로 포함 · 그루수·연장·설명 · **좌표 없음**
  C. 전국 가로수길 정보 표준데이터(서울만)  노선별 **시작·종료 좌표** · 수종·수량·길이·소개

같은 길이 자료마다 따로 조사돼 있고 그루수도 다르다(개포로: 대장 1,004 / 표준 1,169). 그래서
합치되 **더하지는 않는다** — 같은 (자치구, 노선명)에는 `대표=True` 한 행을 두고, 나머지 행은
`중복출처`에 어느 자료에도 있는지 적어 남긴다. 총계를 낼 때는 대표 행만 센다.

B는 좌표가 없어 노선명을 C·가로수 데이터·OSM 이름에 맞춰 본다. 못 맞춘 것은 `매칭=''`으로 둔다 —
지도에는 못 올려도 "어디에 몇 그루"는 답할 수 있고, 무엇보다 **지어낸 좌표를 넣지 않는다**.

산출물: data/processed/seoul_theme_spots.parquet (+ 같은 내용 CSV, 사람 확인용)
실행:  python scripts/07_build_theme_spots.py [--check] [--theme 벚꽃]
"""

import argparse
import re
import sys
from pathlib import Path

import pandas as pd

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

TREES = ROOT / "data" / "processed" / "seoul_trees.parquet"
MAPLE = ROOT / "data" / "서울 단풍길 110선.csv"
NATION = ROOT / "data" / "전국가로수길정보표준데이터.csv"
OUT = ROOT / "data" / "processed" / "seoul_theme_spots.parquet"
OUT_CSV = ROOT / "data" / "processed" / "seoul_theme_spots.csv"

SRC = {"tree": "서울시 가로수 위치정보(가로수 대장)",
       "maple": "서울 단풍길 110선",
       "nation": "전국 가로수길 정보 표준데이터(서울)"}

# 수종 문구 → 우리 테마 키. themes.py의 수종 목록이 1차 근거이고, 자료마다 표기가 달라
# 낱말로도 잡는다('왕벚나무+은행나무', '느티나무, 단풍나무 등' 같은 자유 문자열이 온다).
THEME_WORDS = {
    "벚꽃": ("벚나무", "왕벚", "양벚", "벚꽃"),
    "은행단풍": ("은행",),
    "은행회피": ("은행",),
    "이팝": ("이팝",),
    "메타세쿼이아": ("메타세쿼이아", "메타세콰이어", "메타세콰이아"),
    "그늘": ("느티", "버즘", "플라타너스", "회화나무", "칠엽수", "백합나무"),
}
MIN_TREES = 10          # 이보다 적으면 '길'이라 부르기 어렵다


def themes_of(species_text: str) -> list[str]:
    t = str(species_text)
    return [k for k, words in THEME_WORDS.items() if any(w in t for w in words)]


# ── A. 가로수 대장 ───────────────────────────────────────────────────────────
def from_trees() -> pd.DataFrame:
    df = pd.read_parquet(TREES).dropna(subset=["노선"])
    g = df.groupby(["구", "노선"]).agg(
        그루수=("수종", "size"), 위도=("위도", "mean"), 경도=("경도", "mean"),
        수종=("수종", lambda s: ", ".join(s.value_counts().head(3).index)),
    ).reset_index()
    g = g[g["그루수"] >= MIN_TREES]
    g["테마"] = g["수종"].map(lambda s: ",".join(themes_of(s)))
    g = g[g["테마"] != ""]
    return pd.DataFrame({
        "출처": SRC["tree"], "자치구": g["구"], "구분": "가로", "노선명": g["노선"], "구간": "",
        "수종": g["수종"], "테마": g["테마"], "그루수": g["그루수"].astype(int), "연장_km": pd.NA,
        "특징": "", "위도": g["위도"].round(6), "경도": g["경도"].round(6),
        "매칭": "좌표 직접(가로수 대장)",
    })


# ── C. 전국 표준데이터에서 서울만 ────────────────────────────────────────────
def from_nation() -> pd.DataFrame:
    df = pd.read_csv(NATION, encoding="cp949", low_memory=False)
    # 좌표 bbox로 거르면 성남·구리·하남이 섞인다. 제공기관이 '서울특별시'인 것만 쓴다.
    s = df[df["제공기관명"].astype(str).str.startswith("서울특별시")].copy()
    for c in ("가로수길시작위도", "가로수길시작경도", "가로수길종료위도", "가로수길종료경도",
              "가로수수량", "가로수길길이"):
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s = s.dropna(subset=["가로수길시작위도", "가로수길시작경도"])
    s["테마"] = s["가로수종류"].map(lambda x: ",".join(themes_of(x)))
    s = s[(s["테마"] != "") & (s["가로수수량"].fillna(0) >= MIN_TREES)]
    gu = s["제공기관명"].astype(str).str.replace("서울특별시 ", "", regex=False)
    # 중심좌표 = 시작·종료의 중간(종료가 없으면 시작)
    lat = s[["가로수길시작위도", "가로수길종료위도"]].mean(axis=1)
    lon = s[["가로수길시작경도", "가로수길종료경도"]].mean(axis=1)
    return pd.DataFrame({
        "출처": SRC["nation"], "자치구": gu, "구분": "가로",
        "노선명": s["가로수길명"].astype(str).str.strip(),
        "구간": s["도로구간"].fillna("").astype(str),
        "수종": s["가로수종류"].astype(str), "테마": s["테마"],
        "그루수": s["가로수수량"].fillna(0).astype(int),
        "연장_km": s["가로수길길이"], "특징": s["가로수길소개"].fillna("").astype(str),
        "위도": lat.round(6), "경도": lon.round(6), "매칭": "좌표 직접(표준데이터)",
    })


# ── B. 단풍길 110선 — 좌표가 없어 이름을 맞춰 본다 ───────────────────────────
def _strip(name: str) -> str:
    return re.sub(r"\(.*?\)", "", str(name)).strip()


def _stems(name: str) -> list[str]:
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


def from_maple(pools: list[tuple[str, set[str], dict]]) -> pd.DataFrame:
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
                    continue                         # 자치구가 어긋나면 동명이인이다
                matched, how = hit, label
                if info:
                    lat, lon = info.get("lat", pd.NA), info.get("lon", pd.NA)
                break
            if matched:
                break
        seg = re.search(r"\((.*?)\)", raw)
        rows.append({
            "출처": SRC["maple"], "자치구": str(r["자치구(사업소)"]), "구분": str(r["구분"]),
            "노선명": _strip(raw), "구간": seg.group(1) if seg else "",
            "수종": str(r["수종"]), "테마": ",".join(themes),
            "그루수": int(r["수량(그루)"]),
            "연장_km": float(r["연장(km)"]) if pd.notna(r["연장(km)"]) else pd.NA,
            "특징": str(r["특징(선정사유)"]),
            "위도": lat, "경도": lon,
            "매칭": f"이름 매칭({how}:{matched})" if matched else "",
        })
    return pd.DataFrame(rows)


# 같은 길이 자료마다 따로 조사돼 있다. 그루수도 다르다(개포로: 대장 1,004 / 표준 1,169).
# 단순 합산하면 중복이므로, 같은 (자치구, 노선명)에는 대표 행 하나를 정하고 나머지는 표시만 한다.
# 우선순위는 '그 자료만 가진 것'이 큰 순서다 — 단풍길(공원·하천은 여기에만) > 표준(연장·소개) > 대장.
SRC_RANK = {SRC["maple"]: 0, SRC["nation"]: 1, SRC["tree"]: 2}


def mark_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    key = list(zip(df["자치구"].astype(str), df["노선명"].astype(str)))
    df["_key"] = key
    others = {}
    for k, src in zip(key, df["출처"]):
        others.setdefault(k, set()).add(src)
    df["중복출처"] = [",".join(sorted(others[k] - {src})) for k, src in zip(key, df["출처"])]
    df["_rank"] = df["출처"].map(SRC_RANK).fillna(9)
    first = df.sort_values("_rank").drop_duplicates("_key").index
    df["대표"] = df.index.isin(first)
    return df.drop(columns=["_key", "_rank"])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="저장하지 않고 진단만")
    ap.add_argument("--theme", help="이 테마만 요약해 보기")
    args = ap.parse_args()

    a, c = from_trees(), from_nation()

    # 이름 → 좌표·자치구 사전. 표준데이터를 먼저 본다(공식 노선명 + 좌표가 함께 있다).
    pools = []
    for label, df in (("표준데이터", c), ("가로수 대장", a)):
        coords, pool = {}, set()
        for _, r in df.iterrows():
            nm = str(r["노선명"])
            pool.add(nm)
            d = coords.setdefault(nm, {"gus": set(), "lat": r["위도"], "lon": r["경도"]})
            d["gus"].add(str(r["자치구"]))
        pools.append((label, pool, coords))
    try:
        import numpy as np
        import routing as R
        g = R._graph()
        names = {str(x) for x in np.unique(g["name"]) if str(x) not in ("", "nan")}
        pools.append(("OSM", names, {}))
    except Exception as exc:  # noqa: BLE001 — 도로망이 없어도 나머지로 만든다
        print(f"(도로망 없음: {type(exc).__name__} — OSM 이름 매칭은 건너뛴다)")

    b = from_maple(pools)
    out = pd.concat([c, b, a], ignore_index=True)
    out = mark_duplicates(out)

    print(f"A 가로수 대장      {len(a):5,}개 노선 · {a['그루수'].sum():8,}그루 (좌표 있음)")
    print(f"C 표준데이터(서울)  {len(c):5,}개 노선 · {c['그루수'].sum():8,}그루 (좌표 있음)")
    print(f"B 단풍길 110선     {len(b):5,}개 노선 · {b['그루수'].sum():8,}그루 · "
          f"좌표 얻음 {int(b['위도'].notna().sum())}/{len(b)} · 구분 {b['구분'].value_counts().to_dict()}")
    dup = int((out["중복출처"] != "").sum())
    rep = out[out["대표"]]
    print(f"합계 {len(out):,}행 · 좌표 있는 행 {int(out['위도'].notna().sum()):,} · "
          f"다른 자료와 같은 길 {dup:,}행")
    print(f"대표 행(중복 제거) {len(rep):,}개 노선 — 그루수를 셀 때는 이것만 쓴다")
    print()
    print(f"{'테마':10s} {'대표 노선':>9s} {'그루수(대표만)':>14s} {'전체 행':>8s}")
    for t in ("벚꽃", "은행단풍", "그늘", "이팝", "메타세쿼이아"):
        sub = out[out["테마"].str.contains(t, na=False)]
        r = sub[sub["대표"]]
        print(f"  {t:8s} {len(r):7,}개 {r['그루수'].sum():12,}그루 {len(sub):7,}행")
    print()
    print("가로수 대장에 없던 공원·하천·등산로(단풍길 자료가 더해 주는 것) 상위:")
    extra = b[b["구분"] != "가로"].sort_values("그루수", ascending=False)
    for _, r in extra.head(8).iterrows():
        print(f"  {r['자치구']:14s} {r['구분']:4s} {r['노선명'][:20]:20s} {r['그루수']:5,}그루 "
              f"· {r['매칭'] or '좌표 못 찾음'}")

    if args.theme:
        sub = out[out["테마"].str.contains(args.theme, na=False)].sort_values("그루수", ascending=False)
        print(f"\n=== {args.theme} 상위 12 ===")
        print(sub[["출처", "자치구", "구분", "노선명", "그루수", "연장_km"]].head(12).to_string(index=False))

    if args.check:
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(OUT, index=False)
    out.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT}  ({len(out):,}행)")
    print(f"      {OUT_CSV}")


if __name__ == "__main__":
    main()
