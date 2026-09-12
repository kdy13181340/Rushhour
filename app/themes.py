"""테마 정의 — A(데이터)·B(에이전트)·C(UI)가 공유하는 단일 출처.

각 테마는 '어떤 수종을 선호(prefer)하거나 회피(avoid)하는가'로 정의된다.
수종 문자열은 「2026 서울시 가로수 위치정보」의 실제 수종값과 정확히 일치해야 한다.
(예: '벚나무류', '양버즘나무', '은행나무 암나무')

필드:
  season   사람이 읽는 시기 설명(답변에 그대로 씀)
  seasons  코드용 계절 키 목록(spring|summer|autumn|winter) — season 노드가 후보를 좁힐 때 씀
  keywords 규칙 intake(LLM 없이)와 LLM 실패 폴백이 쓰는 단서 낱말
"""

# key: 사용자·에이전트가 쓰는 테마 식별자
THEMES: dict[str, dict] = {
    "은행회피": {
        "label": "은행 냄새 회피",
        "mode": "avoid",                       # 이 수종이 많은 길을 '피함'
        "species": ["은행나무 암나무", "은행나무"],
        "season": "가을",
        "seasons": ["autumn"],
        "keywords": ["냄새", "열매", "밟", "회피", "피하", "피할"],
        "note": "열매는 암나무만 열림. 데이터엔 암나무가 일부만 라벨링(약 1.5만/9.9만)이라 "
                "'은행나무 암나무'를 우선 회피 대상으로 보고, 나머지 은행나무는 보조 근사임.",
    },
    "벚꽃": {
        "label": "봄 벚꽃길",
        "mode": "prefer",                      # 이 수종이 많은 길을 '추천'
        "species": ["벚나무류"],
        "season": "봄(3~4월)",
        "seasons": ["spring"],
        "keywords": ["벚꽃", "벚나무", "꽃구경", "꽃길"],
        "note": "벚나무류 약 3.2만 그루.",
    },
    "그늘": {
        "label": "여름 그늘길",
        "mode": "prefer",
        "species": ["양버즘나무", "느티나무", "회화나무"],
        "season": "여름",
        "seasons": ["summer"],
        "keywords": ["그늘", "더워", "더운", "시원", "햇빛", "플라타너스"],
        "note": "플라타너스(양버즘)·느티나무 등 큰 활엽수의 그늘.",
    },
    "이팝": {
        "label": "이팝 흰꽃길",
        "mode": "prefer",
        "species": ["이팝나무"],
        "season": "늦봄(5월)",
        "seasons": ["spring"],
        "keywords": ["이팝", "흰꽃", "흰 꽃"],
        "note": "이팝나무 약 2.7만 그루, 5월 흰 꽃.",
    },
    "은행단풍": {
        "label": "가을 은행 단풍길",
        "mode": "prefer",
        "species": ["은행나무", "은행나무 암나무"],
        "season": "가을",
        "seasons": ["autumn"],
        "keywords": ["단풍", "노란", "노랑", "은행나무길", "은행길"],
        "note": "노란 단풍이 목적. 냄새를 감수하는 테마.",
    },
    "메타세쿼이아": {
        "label": "메타세쿼이아길",
        "mode": "prefer",
        "species": ["메타세쿼이아"],
        "season": "사계",
        "seasons": ["spring", "summer", "autumn", "winter"],
        "keywords": ["메타세쿼이아", "메타세콰이아", "메타"],
        "note": "약 4.7천 그루. 특정 구간(예: 강남 양재천로)에 밀집.",
    },
    # ── 2026-09-12 figma2 시안이 추가한 두 테마. 둘 다 소나무 계열이라 수종이 겹친다 —
    #    '크리스마스'는 겨울 한 계절짜리 축제 프레임, '상록'은 사계절 프레임으로 갈라 둔다.
    #    데이터에 전나무는 없다. 소나무 5.2천·반송 0.9천이 대부분이고 중구(퇴계로·다산로·을지로)에 몰려 있다.
    "크리스마스": {
        "label": "크리스마스 축제길",
        "mode": "prefer",
        "species": ["소나무", "반송", "잣나무류", "구상나무", "히말라야시다", "코니카가문비"],
        "season": "겨울(12월)",
        "seasons": ["winter"],
        "keywords": ["크리스마스", "성탄", "축제", "연말", "트리", "조명"],
        "tag_min": 100,                        # RAG 문서 태그 문턱(rag._theme_tags) — 소나무가 주인공인 길만
        "note": "연말 조명이 붙는 도심 상록 침엽수(소나무·반송·잣나무·구상나무 등). 중구 을지로·소공로에 밀집.",
    },
    "상록": {
        "label": "사철 상록 소나무길",
        "mode": "prefer",
        "species": ["소나무", "반송", "선주목", "잣나무류", "향나무", "측백나무"],
        "season": "사계",
        "seasons": ["spring", "summer", "autumn", "winter"],
        "keywords": ["상록", "소나무", "솔길", "사철", "늘푸른", "푸른", "침엽"],
        "tag_min": 100,
        "note": "겨울에도 푸른 소나무·반송 등 약 6.5천 그루. 중구 퇴계로·다산로에 가장 많다.",
    },
}

# intake 구조화 출력에서 쓸 허용값(+ 판별 불가)
THEME_KEYS = list(THEMES.keys()) + ["unknown"]

SEASON_KEYS = ["spring", "summer", "autumn", "winter"]
SEASON_LABEL = {"spring": "봄", "summer": "여름", "autumn": "가을", "winter": "겨울"}
# 사용자가 계절을 말로 지정할 때(intake override·규칙 intake)
SEASON_WORDS = {
    "spring": ["봄", "3월", "4월", "5월"],
    "summer": ["여름", "6월", "7월", "8월"],
    "autumn": ["가을", "9월", "10월", "11월"],
    "winter": ["겨울", "12월", "1월", "2월"],
}


def season_of(month: int) -> str:
    """월 → 계절 키. season 노드(코드)가 쓴다.  [BE_DESIGN C3]"""
    if 3 <= month <= 5:
        return "spring"
    if 6 <= month <= 8:
        return "summer"
    if 9 <= month <= 11:
        return "autumn"
    return "winter"


def themes_for_season(season: str) -> list[str]:
    """그 계절에 맞는 테마 키 목록. 추천(prefer) 테마를 먼저, 회피(avoid) 테마를 뒤에.

    '지금 볼만한 길'처럼 테마 단서가 없을 때 첫 번째를 기본값으로 쓰므로 순서가 곧 정책이다.
    """
    keys = [k for k, v in THEMES.items() if season in v["seasons"]]
    return sorted(keys, key=lambda k: THEMES[k]["mode"] != "prefer")


def theme_menu(season: str | None = None) -> str:
    """프롬프트에 넣을 테마 목록. season을 주면 그 계절 테마를 먼저 놓고 '[지금 시기]'로 표시."""
    keys = list(THEMES.keys())
    if season:
        now = themes_for_season(season)
        keys = now + [k for k in keys if k not in now]
    lines = []
    for k in keys:
        v = THEMES[k]
        tag = " [지금 시기]" if season and season in v["seasons"] else ""
        lines.append(
            f"  - {k}: {v['label']} ({v['season']}){tag} — 선호/회피: {v['mode']}, 수종 {v['species']}"
        )
    return "\n".join(lines)
