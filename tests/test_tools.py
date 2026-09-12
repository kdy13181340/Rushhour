"""도구·데이터 계층 — LLM 없이."""
import pandas as pd

import tools
from tools import (_load, _resolve_point, available_districts, check_coverage,
                   find_theme_streets, match_district, route_theme_streets)


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


def test_resolve_point_coord_and_district():
    assert _resolve_point("37.5,127.1") == (37.5, 127.1)
    pt = _resolve_point("강남구")
    assert pt and 37.0 < pt[0] < 38.0 and 126.0 < pt[1] < 128.0
    assert _resolve_point("") is None


def test_resolve_point_landmark_without_key_is_graceful(monkeypatch):
    """카카오 키 없으면 장소명은 None(예외 X) → route는 기존 '해석 못함' 폴백.

    빈 문자열 env는 .env보다 우선하므로(pydantic-settings 우선순위) 로컬에 실제 .env가
    있어도 이 테스트는 '키 없음' 상태를 확정할 수 있다.
    """
    monkeypatch.setenv("KAKAO_REST_API_KEY", "")
    tools._geocode_clear_cache()
    assert _resolve_point("올림픽공원") is None
    r = route_theme_streets.invoke({"theme": "벚꽃", "origin": "올림픽공원", "dest": "롯데타워"})
    assert r["ok"] is False and "해석 못함" in r["reason"]


def test_resolve_point_landmark_geocoded(monkeypatch):
    """키 있으면 장소명 → 카카오 좌표(서울 결과 우선). httpx mock으로 네트워크 없이 검증."""
    monkeypatch.setenv("KAKAO_REST_API_KEY", "dummy")
    tools._geocode_clear_cache()

    class _Resp:
        def raise_for_status(self): pass
        def json(self):
            return {"documents": [
                {"place_name": "해운대", "x": "129.0", "y": "35.1", "address_name": "부산 해운대구"},
                {"place_name": "올림픽공원", "x": "127.121", "y": "37.520", "address_name": "서울 송파구 방이동"},
            ]}

    monkeypatch.setattr(tools.httpx, "get", lambda *a, **k: _Resp())
    assert _resolve_point("올림픽공원") == (37.52, 127.121)  # 부산 아닌 서울 채택
    tools._geocode_clear_cache()
