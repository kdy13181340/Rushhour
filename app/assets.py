"""지도 마커용 이미지 스프라이트 생성 — UI 전용(C). **LLM 도구 아님.**

외부 이미지를 받아오지 않고 Pillow로 직접 그린다. 이유:
  - 프록시 뒤(Runpod)에서 외부 CDN 이미지는 막히거나 느리다.
  - 라이선스가 걸리지 않는다.
  - 테마별 색·모양을 데이터 의미에 맞춰 통제할 수 있다(회피 테마는 금지 표시 등).

스프라이트는 하나의 아틀라스 PNG로 합쳐 base64 data URI로 만들고, pydeck IconLayer의
iconAtlas/iconMapping에 그대로 넣는다. 네트워크 요청이 0번이다.

  from assets import icon_atlas, sprite_uri
  atlas_uri, mapping = icon_atlas()      # IconLayer용
  sprite_uri("벚꽃")                      # <img src="..."> 용 단일 아이콘
"""

from __future__ import annotations

import base64
import functools
import io
import math

from PIL import Image, ImageDraw, ImageFilter

CELL = 96          # 아틀라스 한 칸(픽셀)
SS = 4             # 수퍼샘플링 배율 — 곡선을 부드럽게 하려고 4배로 그린 뒤 줄인다
S = CELL * SS

# 테마 키 → 지도·UI 색. themes.py의 키와 맞춘다.
THEME_COLOR: dict[str, str] = {
    "벚꽃": "#E06C9B",
    "이팝": "#7B8FB8",
    "그늘": "#2F7A4E",
    "은행단풍": "#D08C00",
    "은행회피": "#C2453A",
    "메타세쿼이아": "#2A6B79",
    "단풍": "#C8442A",
    "상록": "#5C8FB5",
}


def _rgb(hex_: str) -> tuple[int, int, int]:
    hex_ = hex_.lstrip("#")
    return tuple(int(hex_[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _petal(length: float, width: float, fill, angle: float, center, notch: bool = False):
    """꽃잎 하나를 따로 그려 회전해 붙이기 위한 이미지를 만든다."""
    pw, ph = int(width), int(length)
    p = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
    d = ImageDraw.Draw(p)
    d.ellipse([0, 0, pw - 1, ph - 1], fill=fill)
    if notch:  # 벚꽃 특유의 끝 갈라짐
        nw = pw * 0.34
        d.ellipse([pw / 2 - nw / 2, -nw * 0.75, pw / 2 + nw / 2, nw * 0.75], fill=(0, 0, 0, 0))
    return p.rotate(-angle, resample=Image.BICUBIC, expand=True)


def _paste_radial(img, piece, angle_deg, radius, center):
    """중심에서 angle 방향으로 radius만큼 떨어진 곳에 조각을 붙인다."""
    a = math.radians(angle_deg)
    cx = center[0] + radius * math.sin(a)
    cy = center[1] - radius * math.cos(a)
    img.alpha_composite(piece, (int(cx - piece.width / 2), int(cy - piece.height / 2)))


# ── 수종별 그리기 ─────────────────────────────────────────────────────────────
def _cherry() -> Image.Image:
    """벚꽃 — 다섯 장 꽃잎 + 노란 수술."""
    img, d = _canvas()
    c = (S / 2, S / 2 + S * 0.02)
    deep, pale, mid = _rgb("#E885AF"), _rgb("#FBD9E6"), _rgb("#F5AECB")
    for a in range(0, 360, 72):
        _paste_radial(img, _petal(S * 0.46, S * 0.34, deep + (255,), a, c, notch=True),
                      a, S * 0.20, c)
    for a in range(0, 360, 72):
        _paste_radial(img, _petal(S * 0.38, S * 0.27, mid + (255,), a, c, notch=True),
                      a, S * 0.18, c)
    for a in range(36, 396, 72):
        _paste_radial(img, _petal(S * 0.26, S * 0.18, pale + (235,), a, c), a, S * 0.13, c)
    r = S * 0.075
    d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=_rgb("#F6C445") + (255,))
    for a in range(0, 360, 45):  # 수술
        ar = math.radians(a)
        x, y = c[0] + math.sin(ar) * S * 0.115, c[1] - math.cos(ar) * S * 0.115
        d.ellipse([x - S * 0.018, y - S * 0.018, x + S * 0.018, y + S * 0.018],
                  fill=_rgb("#E8A93C") + (255,))
    return img


def _fringe() -> Image.Image:
    """이팝나무 — 네 갈래 흰 꽃(가늘고 길쭉한 꽃잎)."""
    img, d = _canvas()
    c = (S / 2, S / 2)
    white, edge = _rgb("#FDFEFF"), _rgb("#C9D6E4")
    for a in range(0, 360, 45):
        _paste_radial(img, _petal(S * 0.52, S * 0.115, edge + (255,), a, c), a, S * 0.21, c)
    for a in range(0, 360, 45):
        _paste_radial(img, _petal(S * 0.46, S * 0.085, white + (255,), a, c), a, S * 0.20, c)
    r = S * 0.055
    d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=_rgb("#EDE9C8") + (255,))
    return img


def _leaf_polygon(cx, cy, length, width, tilt_deg):
    """잎 윤곽(양끝이 뾰족한 타원) 좌표."""
    pts_up, pts_dn = [], []
    for i in range(41):
        t = i / 40
        x = (t - 0.5) * length
        w = width * math.sin(math.pi * t) ** 0.85 * (1 - 0.22 * t)
        pts_up.append((x, -w / 2))
        pts_dn.append((x, w / 2))
    a = math.radians(tilt_deg)
    out = []
    for x, y in pts_up + pts_dn[::-1]:
        out.append((cx + x * math.cos(a) - y * math.sin(a),
                    cy + x * math.sin(a) + y * math.cos(a)))
    return out


def _shade() -> Image.Image:
    """여름 그늘 — 넓은 활엽 한 장(잎맥 포함)."""
    img, d = _canvas()
    c = (S / 2, S / 2)
    dark, light = _rgb("#2C6F46"), _rgb("#4F9E68")
    d.polygon(_leaf_polygon(c[0], c[1], S * 0.92, S * 0.54, -28), fill=dark + (255,))
    d.polygon(_leaf_polygon(c[0] + S * 0.012, c[1] - S * 0.02, S * 0.84, S * 0.46, -28),
              fill=light + (255,))
    a = math.radians(-28)
    x0, y0 = c[0] - 0.46 * S * math.cos(a), c[1] - 0.46 * S * math.sin(a)
    x1, y1 = c[0] + 0.46 * S * math.cos(a), c[1] + 0.46 * S * math.sin(a)
    d.line([(x0, y0), (x1, y1)], fill=dark + (255,), width=int(S * 0.022))
    for t in (0.28, 0.45, 0.62, 0.78):  # 잎맥
        px, py = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
        for sgn in (1, -1):
            vx = px + math.cos(a + sgn * 1.05) * S * 0.15
            vy = py + math.sin(a + sgn * 1.05) * S * 0.15
            d.line([(px, py), (vx, vy)], fill=dark + (210,), width=int(S * 0.012))
    return img


def _ginkgo_shape(d, c, scale, fill, edge=None):
    """은행잎 부채꼴 — 위쪽 가운데가 갈라진 모양."""
    apex = (c[0], c[1] + S * 0.36 * scale)
    R = S * 0.72 * scale
    pts = [apex]
    for i in range(61):
        a = math.radians(-74 + 148 * i / 60)
        r = R * (1 - 0.20 * math.exp(-((math.degrees(a) / 11) ** 2)))
        pts.append((apex[0] + r * math.sin(a), apex[1] - r * math.cos(a)))
    d.polygon(pts, fill=fill)
    if edge:
        for k in (-0.62, -0.3, 0.0, 0.3, 0.62):
            a = math.radians(74 * k)
            r = R * (0.86 if abs(k) > 0.01 else 0.72)
            d.line([apex, (apex[0] + r * math.sin(a), apex[1] - r * math.cos(a))],
                   fill=edge, width=int(S * 0.014))
    d.line([apex, (apex[0], apex[1] + S * 0.13 * scale)], fill=fill, width=int(S * 0.035))


def _ginkgo_autumn() -> Image.Image:
    """가을 은행 — 황금색 부채잎."""
    img, d = _canvas()
    _ginkgo_shape(d, (S / 2, S / 2 - S * 0.06), 0.92,
                  _rgb("#E9A712") + (255,), _rgb("#C07E05") + (200,))
    return img


def _ginkgo_avoid() -> Image.Image:
    """은행 회피 — 빛바랜 잎 + 붉은 금지 표시. '가지 마세요'가 한눈에 읽혀야 한다."""
    img, d = _canvas()
    _ginkgo_shape(d, (S / 2, S / 2 - S * 0.04), 0.80,
                  _rgb("#B79A5E") + (235,), _rgb("#8E7538") + (190,))
    red = _rgb("#C2453A") + (255,)
    pad, w = S * 0.10, int(S * 0.075)
    d.ellipse([pad, pad, S - pad, S - pad], outline=red, width=w)
    k = S * 0.19
    d.line([(k, S - k), (S - k, k)], fill=red, width=w)
    return img


MAPLE_OUTLINE = [
    (0.00, 1.00), (0.12, 0.62), (0.38, 0.68), (0.30, 0.42), (0.72, 0.50), (0.62, 0.28),
    (0.95, 0.05), (0.52, -0.05), (0.62, -0.30), (0.30, -0.22), (0.22, -0.45),
    (0.06, -0.30), (0.06, -0.98), (-0.06, -0.98), (-0.06, -0.30), (-0.22, -0.45),
    (-0.30, -0.22), (-0.62, -0.30), (-0.52, -0.05), (-0.95, 0.05), (-0.62, 0.28),
    (-0.72, 0.50), (-0.30, 0.42), (-0.38, 0.68), (-0.12, 0.62),
]


def _maple() -> Image.Image:
    """단풍 명소 — 다섯 갈래 단풍잎."""
    img, d = _canvas()
    c, r = (S / 2, S / 2), S * 0.46
    outer = [(c[0] + x * r, c[1] - y * r) for x, y in MAPLE_OUTLINE]
    inner = [(c[0] + x * r * 0.84, c[1] - y * r * 0.84 - S * 0.012) for x, y in MAPLE_OUTLINE]
    d.polygon(outer, fill=_rgb("#A8331D") + (255,))
    d.polygon(inner, fill=_rgb("#D4542A") + (255,))
    return img


def _meta() -> Image.Image:
    """메타세쿼이아 — 곧은 원뿔형 침엽수."""
    img, d = _canvas()
    dark, mid = _rgb("#245C66"), _rgb("#3A8391")
    d.rectangle([S * 0.465, S * 0.66, S * 0.535, S * 0.93], fill=_rgb("#6B5340") + (255,))
    for i, (top, half, y) in enumerate([(0.07, 0.20, 0.40), (0.28, 0.28, 0.60),
                                        (0.47, 0.36, 0.80)]):
        col = mid if i % 2 else dark
        d.polygon([(S * 0.5, S * top), (S * (0.5 - half), S * y), (S * (0.5 + half), S * y)],
                  fill=col + (255,))
    return img


def _snow() -> Image.Image:
    """겨울 상록 — 눈 결정. 흰색만 쓰면 밝은 지도에서 사라지므로 푸른 테두리를 둔다."""
    img, d = _canvas()
    c = (S / 2, S / 2)
    ice, white = _rgb("#5C8FB5"), _rgb("#FBFEFF")
    for pass_, (col, w, grow) in enumerate([(ice + (255,), int(S * 0.075), 1.0),
                                            (white + (255,), int(S * 0.042), 0.97)]):
        for a in range(0, 360, 60):
            ar = math.radians(a)
            ex = c[0] + math.sin(ar) * S * 0.40 * grow
            ey = c[1] - math.cos(ar) * S * 0.40 * grow
            d.line([c, (ex, ey)], fill=col, width=w)
            for t, blen in ((0.52, 0.15), (0.78, 0.10)):  # 곁가지
                bx, by = c[0] + (ex - c[0]) * t, c[1] + (ey - c[1]) * t
                for sgn in (1, -1):
                    br = ar + sgn * 0.95
                    d.line([(bx, by), (bx + math.sin(br) * S * blen,
                                       by - math.cos(br) * S * blen)], fill=col, width=w)
        if pass_ == 0:
            continue
    r = S * 0.085
    d.ellipse([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=white + (255,),
              outline=ice + (255,), width=int(S * 0.03))
    return img


DRAWERS = {
    "벚꽃": _cherry, "이팝": _fringe, "그늘": _shade, "은행단풍": _ginkgo_autumn,
    "은행회피": _ginkgo_avoid, "메타세쿼이아": _meta, "단풍": _maple, "상록": _snow,
}


def _halo(img: Image.Image) -> Image.Image:
    """밝은 지도·어두운 지도 어디에 올려도 형태가 읽히도록 흰 외곽선을 두른다."""
    alpha = img.getchannel("A")
    grown = alpha.filter(ImageFilter.MaxFilter(int(SS * 3) | 1)).filter(
        ImageFilter.GaussianBlur(SS * 0.8))
    halo = Image.new("RGBA", img.size, (255, 255, 255, 0))
    halo.putalpha(grown.point(lambda v: min(255, int(v * 1.25))))
    shadow = Image.new("RGBA", img.size, (28, 38, 32, 0))
    shadow.putalpha(grown.filter(ImageFilter.GaussianBlur(SS * 1.6)).point(
        lambda v: int(v * 0.34)))
    out = Image.alpha_composite(shadow, halo)
    return Image.alpha_composite(out, img)


@functools.lru_cache(maxsize=16)
def sprite(key: str) -> Image.Image:
    """테마 하나의 CELL×CELL 스프라이트(RGBA)."""
    drawer = DRAWERS.get(key)
    if drawer is None:
        img, d = _canvas()
        d.ellipse([S * 0.2, S * 0.2, S * 0.8, S * 0.8], fill=(140, 150, 145, 255))
    else:
        img = drawer()
    return _halo(img).resize((CELL, CELL), Image.LANCZOS)


def _to_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@functools.lru_cache(maxsize=16)
def sprite_uri(key: str, size: int = CELL) -> str:
    """<img src="..."> 에 바로 넣는 단일 아이콘 data URI."""
    img = sprite(key)
    if size != CELL:
        img = img.resize((size, size), Image.LANCZOS)
    return _to_uri(img)


@functools.lru_cache(maxsize=1)
def icon_atlas() -> tuple[str, dict]:
    """pydeck IconLayer용 (아틀라스 data URI, iconMapping). 네트워크 요청 없음."""
    keys = list(DRAWERS)
    atlas = Image.new("RGBA", (CELL * len(keys), CELL), (0, 0, 0, 0))
    mapping = {}
    for i, k in enumerate(keys):
        atlas.paste(sprite(k), (i * CELL, 0))
        mapping[k] = {"x": i * CELL, "y": 0, "width": CELL, "height": CELL,
                      "anchorY": CELL // 2, "mask": False}
    return _to_uri(atlas), mapping


def pydeck_atlas() -> tuple[str, dict]:
    """pydeck IconLayer에 그대로 넘길 (아틀라스, 매핑).

    pydeck 0.9의 Layer는 문자열 kwarg를 전부 JS 표현식(``@@=``)으로 감싼다. 예외는
    '따옴표로 감싼 문자열'과 ``types.Image``인데, Image.validate는 data URI를
    ``data/image``(오타)로 검사해 통과하지 못한다. 그래서 아틀라스를 직접 따옴표로
    감싸 리터럴로 넘긴다 — 이 우회를 빼면 iconAtlas가 ``@@=data:image/...``가 되어
    아이콘이 하나도 그려지지 않는다.
    """
    uri, mapping = icon_atlas()
    return f"'{uri}'", mapping


if __name__ == "__main__":
    # 눈으로 확인할 시트를 뽑는다: 밝은 배경과 어두운 배경 양쪽에서 읽히는지 본다.
    keys = list(DRAWERS)
    pad, cw = 16, CELL + 16
    sheet = Image.new("RGBA", (cw * len(keys) + pad, CELL * 2 + pad * 3), (245, 246, 243, 255))
    ImageDraw.Draw(sheet).rectangle([0, CELL + pad * 2, sheet.width, sheet.height],
                                    fill=(24, 30, 26, 255))
    for i, k in enumerate(keys):
        sheet.alpha_composite(sprite(k), (pad + i * cw, pad))
        sheet.alpha_composite(sprite(k), (pad + i * cw, CELL + pad * 2))
    out = "/tmp/claude-0/-workspace/a909719b-3d9b-428e-9b92-f8bd93e5cbea/scratchpad/sprites.png"
    sheet.convert("RGB").save(out)
    uri, mapping = icon_atlas()
    print(f"시트: {out}")
    print(f"아틀라스: {len(uri) / 1024:.1f} KB (data URI) · 칸 {len(mapping)}개")
    for k in keys:
        print(f"  {k:<8} {len(sprite_uri(k)) / 1024:5.1f} KB")
