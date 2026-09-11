"""도구·데이터 계층 — LLM 없이."""
import pandas as pd

from tools import _load, available_districts, check_coverage, find_theme_streets, match_district


def test_load_has_25_districts_and_no_agencies():
    dists = available_districts()
    assert len(dists) == 25
    assert "서울시설공단" not in dists and "중부공원여가센터" not in dists
    assert "종로구" in dists


def test_agency_rows_restored_to_gu():
    df = _load()
    assert "관리기관" in df.columns
    restored = df[df["관리기관"] != "자치구"]
    assert len(restored) > 12_000                      # 12,946건이 구로 복원됨
    assert restored["구"].isna().sum() == 0
    # 세종대로(중부공원여가센터 관리)가 종로구·중구에 잡혀야 함
    assert set(df[df["노선"] == "세종대로"]["구"].unique()) <= {"종로구", "중구"}


def test_coordinates_numeric_and_in_seoul():
    df = _load()
    assert pd.api.types.is_float_dtype(df["경도"]) and pd.api.types.is_float_dtype(df["위도"])
    assert df["경도"].between(126.7, 127.3).all() and df["위도"].between(37.3, 37.8).all()


def test_find_theme_streets_regression_gangdong_cherry():
    res = find_theme_streets.invoke({"theme": "벚꽃", "district": "강동구"})
    assert res["ok"] and res["mode"] == "prefer"
    assert res["streets"][0]["노선"] == "아리수로" and res["streets"][0]["그루수"] == 628  # dev1 README 수치
    assert len(res["streets"]) <= 6 and "focus" in res and "bbox" in res["focus"]


def test_find_theme_streets_jongno_includes_restored_road():
    res = find_theme_streets.invoke({"theme": "은행단풍", "district": "종로구"})
    assert res["ok"]
    assert "종로" in [s["노선"] for s in res["streets"]]    # 복원 전엔 중부공원여가센터 소속이라 빠졌음


def test_find_theme_streets_top_only_and_hotspot_focus():
    res = find_theme_streets.invoke({"theme": "벚꽃", "district": "", "top_only": True})
    assert res["ok"] and len(res["streets"]) == 1
    assert res["focus"]["primary"] == {"구": res["streets"][0]["구"], "노선": res["streets"][0]["노선"]}
    (lat0, lon0), (lat1, lon1) = res["focus"]["bbox"]
    assert lat1 - lat0 < 0.03 and lon1 - lon0 < 0.03      # 핫스팟 ~1km, 도로 전체 bbox가 아님


def test_find_theme_streets_refuses_honestly():
    assert find_theme_streets.invoke({"theme": "벚꽃", "district": "없는구"})["ok"] is False
    assert find_theme_streets.invoke({"theme": "없는테마", "district": ""})["ok"] is False
    assert check_coverage.invoke({"district": "부산진구"})["covered"] is False
    assert check_coverage.invoke({})["count"] == 25


def test_match_district():
    assert match_district("강남구에서 봄에") == "강남구"
    assert match_district("서초 쪽 그늘길") == "서초구"
    assert match_district("부산 해운대") == ""
