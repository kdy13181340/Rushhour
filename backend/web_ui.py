"""Leaflet 웹 UI용 읽기 모델.

에이전트/도구 계약(한국어 키·SSE)은 바꾸지 않는다. 이 모듈은 그 결과를 화면이 쓰는
영문 필드와 가벼운 지도 폴리라인으로만 변환한다.
"""

from __future__ import annotations

import math

import numpy as np

from map_api import street_points
from themes import THEMES
from tools import _load, available_districts, find_theme_streets


PRESENTATION = {
    "벚꽃": {"id": "cherry", "emoji": "🌸", "color": "#e8a0b0"},
    "그늘": {"id": "shade", "emoji": "🌳", "color": "#2d6a4f"},
    "이팝": {"id": "ipaeb", "emoji": "❄️", "color": "#7fb99a"},
    "은행회피": {"id": "ginkgo-avoid", "emoji": "🍂", "color": "#f4a261"},
    "은행단풍": {"id": "ginkgo-enjoy", "emoji": "🟡", "color": "#f9c74f"},
    "메타세쿼이아": {"id": "metasequoia", "emoji": "🌲", "color": "#40916c"},
}
BY_ID = {v["id"]: key for key, v in PRESENTATION.items()}


def _centerline(points: list[list[float]], max_nodes: int = 32) -> list[list[float]]:
    """나무 좌표를 지도 표시용 중심선으로 축약한다. 보행 경로는 아니다."""
    if len(points) < 2:
        return points
    arr = np.asarray(points, dtype=float)
    scale = np.array([1.0, math.cos(math.radians(float(arr[:, 0].mean())))])
    centered = (arr - arr.mean(axis=0)) * scale
    _, _, vectors = np.linalg.svd(centered, full_matrices=False)
    order = np.argsort(centered @ vectors[0])
    ordered = arr[order]
    n = min(max_nodes, len(ordered))
    bins = np.array_split(ordered, n)
    return [[round(float(b[:, 0].mean()), 6), round(float(b[:, 1].mean()), 6)] for b in bins if len(b)]


def _ui_streets(theme: str, streets: list[dict], include_points: bool) -> tuple[list[dict], list[list[list[float]]], list[list[float]]]:
    """도구 street 결과를 UI 카드·선·선택 시 마커 좌표로 변환한다."""
    ui_streets, paths, points = [], [], []
    for rank, street in enumerate(streets[:6], 1):
        gu, line = street["구"], street["노선"]
        # 비활성 테마의 첫 화면은 선만, 활성 테마만 마커 좌표를 싣는다.
        line_points = street_points(gu, line, theme, limit=450 if include_points else 180)
        centerline = _centerline(line_points)
        if len(centerline) >= 2:
            paths.append(centerline)
        if include_points:
            points.extend(line_points)
        ui_streets.append({"rank": rank, "gu": gu, "line": line,
                           "count": street["그루수"], "center": street.get("center"),
                           "paths": [centerline] if len(centerline) >= 2 else []})
    return ui_streets, paths, points


def theme_payload(theme: str, district: str = "", *, include_points: bool = False,
                  hits: dict | None = None) -> dict | None:
    """현재 도구 결과만으로 Leaflet 테마 객체를 만든다."""
    if theme not in PRESENTATION:
        return None
    hits = hits or find_theme_streets.invoke({"theme": theme, "district": district})
    if not hits.get("ok"):
        return None
    streets, paths, points = _ui_streets(theme, hits.get("streets", []), include_points)
    meta, spec = PRESENTATION[theme], THEMES[theme]
    districts = []
    for street in streets:
        if street["gu"] not in districts:
            districts.append(street["gu"])
    return {
        "id": meta["id"], "key": theme, "name": spec["label"], "emoji": meta["emoji"],
        "color": meta["color"], "mode": spec["mode"], "season": spec["seasons"][0],
        "seasonLabel": spec["season"], "district": district or " · ".join(districts) or "서울 전역",
        "roads": [street["line"] for street in streets[:2]], "treeCount": hits.get("total_trees", 0),
        "streets": streets, "paths": paths, "points": points if include_points else [],
        "focus": hits.get("focus", {}), "note": hits.get("note", ""),
    }


def overview_payload() -> dict:
    """초기 화면용: 테마별 가벼운 선만 만든다(마커 점은 클릭 뒤 지연 조회)."""
    themes = [theme_payload(key) for key in PRESENTATION]
    return {"themes": [item for item in themes if item],
            "totals": {"themes": len(PRESENTATION), "trees": int(len(_load())),
                       "districts": len(available_districts())}}


ROUTE_PRESENTATION = {
    # 경로 대안의 화면 표현. 최단은 테마가 없으므로 중립색을 준다.
    "shortest": {"id": "route-shortest", "emoji": "🧭", "color": "#4a5b6b"},
    "theme": {"id": "route-theme", "emoji": "🌳", "color": "#2d6a4f"},
    "avoid": {"id": "route-avoid", "emoji": "🚫", "color": "#e2574c"},
}


def route_plan_payload(hits: dict, season: str = "") -> list[dict]:
    """plan_route 결과(경로 3가지) → 화면이 그대로 그리는 카드 목록.

    기존 테마 카드와 같은 모양(paths·color·name)이라 UI JS를 고치지 않아도 선이 그려진다.
    경로는 이미 좌표열이므로 중심선 계산(_centerline)이 필요 없다.
    """
    out = []
    for r in hits.get("routes", []):
        meta = ROUTE_PRESENTATION.get(r["kind"], ROUTE_PRESENTATION["theme"])
        spec = THEMES.get(r.get("theme") or "", {})
        if r.get("theme") and r["theme"] in PRESENTATION and r["kind"] == "theme":
            meta = {**meta, "color": PRESENTATION[r["theme"]]["color"],
                    "emoji": PRESENTATION[r["theme"]]["emoji"]}
        detour = f" · 최단 대비 +{r['detour_pct']}%" if r["detour_pct"] else " · 최단"
        trees = ""
        if r.get("theme"):
            verb = "피함" if r["kind"] == "avoid" else "지남"
            trees = f" · {r['theme']} {r.get('theme_trees', 0)}그루 {verb}"
        out.append({
            "id": meta["id"], "key": r["kind"], "name": r["label"], "emoji": meta["emoji"],
            "color": meta["color"], "mode": "route",
            "season": (spec.get("seasons") or [season or "autumn"])[0],
            "seasonLabel": f"{r['distance_m']:,}m{detour}{trees}",
            "district": f"{hits.get('origin_name', '')} → {hits.get('dest_name', '')}",
            "roads": r.get("streets", [])[:3], "treeCount": r.get("theme_trees", 0),
            "streets": [], "paths": [r["path"]] if r.get("path") else [], "points": [],
            "focus": {}, "note": r.get("note", "") or hits.get("note", ""),
        })
    return out


def result_routes(final: dict) -> list[dict]:
    """SSE final의 hits를 지도 카드로 변환한다. 실패/거절은 빈 목록이다."""
    hits = final.get("hits") or {}
    theme = final.get("theme")
    if hits.get("ok") and hits.get("kind") == "route_plan":
        return route_plan_payload(hits, final.get("season", ""))
    if not hits.get("ok") or theme not in PRESENTATION:
        return []
    # route 결과도 streets 배열은 find_theme_streets와 같은 한국어 키를 유지한다.
    payload = theme_payload(theme, final.get("district") or "", include_points=True, hits=hits)
    return [payload] if payload else []
