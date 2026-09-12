"""가로수 CSV(cp949) → Parquet 1회 변환 + 데이터 정제.  [BE_DESIGN C2·C6]

하는 일:
  1. cp949 CSV를 읽어 컬럼명을 짧게 표준화 (구·노선·수종·도로명·지번·경도·위도)
  2. '자치구' 컬럼의 관리기관 값(서울시설공단·중부공원여가센터, 12,946행)을
     지번 주소의 '서울특별시 ○○구'로 복원. 원래 값은 '관리기관' 컬럼에 보존.
  3. 좌표 결측 행 제거(위도 결측 1건), 좌표를 float로.
  4. data/processed/seoul_trees.parquet 저장.

실행:  python scripts/01_csv_to_parquet.py [--check]
  --check : 변환 없이 원본 진단만 출력
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # Windows cp949 콘솔에서 '—' 출력 오류 방지

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "seoul_tree_data.csv"
OUT = ROOT / "data" / "processed" / "seoul_trees.parquet"

AGENCIES = ("서울시설공단", "중부공원여가센터")
RENAME = {
    "자치구": "구", "노선": "노선", "수종": "수종", "도로명 주소": "도로명",
    "지번 주소": "지번", "좌표(경도)": "경도", "좌표(위도)": "위도",
}
GU_RE = r"서울특별시\s+(\S+구)"


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """원본 DataFrame → 정제본. tools._load()의 CSV 폴백도 이 함수를 같이 쓴다."""
    df = df.rename(columns=RENAME)
    for c in ("구", "노선", "수종", "도로명", "지번"):
        if c in df.columns:
            df[c] = df[c].astype("string").str.strip()
    # (2) 관리기관 → 구 복원
    agency = df["구"].isin(AGENCIES).fillna(False)
    df["관리기관"] = df["구"].where(agency, "자치구")
    restored = df.loc[agency, "지번"].str.extract(GU_RE)[0]
    df.loc[agency, "구"] = restored
    df = df[df["구"].notna()]
    # (3) 좌표
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    df = df.dropna(subset=["경도", "위도"])
    return df.reset_index(drop=True)


def diagnose(df: pd.DataFrame) -> None:
    print(f"행 {len(df):,} / 컬럼 {list(df.columns)}")
    print(f"'자치구' 고유값 {df['자치구'].nunique()}개 — 관리기관 행: "
          f"{df['자치구'].isin(AGENCIES).sum():,}")
    print("결측:", {k: int(v) for k, v in df.isna().sum().items() if v})


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if not RAW.exists():
        sys.exit(f"원본 없음: {RAW}")
    raw = pd.read_csv(RAW, encoding="cp949")
    diagnose(raw)
    if args.check:
        return
    df = clean(raw)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    print(f"\n저장: {OUT}  ({OUT.stat().st_size/1e6:.1f} MB)")
    print(f"정제 후 행 {len(df):,} / 구 {df['구'].nunique()}개: {sorted(df['구'].unique())}")
    print("관리기관 출처:", df["관리기관"].value_counts().to_dict())


if __name__ == "__main__":
    main()
