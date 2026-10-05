"""Drawing toolkit for the motion-graphics renderer.

* Everything is positioned in DESIGN UNITS on a 1920x1080 canvas and scaled to
  the output size (720p / 1080p / 4K), so layouts are identical at every tier.
* Text and panels are rasterised once into cached premultiplied layers; each
  video frame then only blits small regions with cv2 (fast even at 4K).
"""
import math
import re
from functools import lru_cache

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import FONT_DIR, H, PALETTE, SCALE, W

cv2.setNumThreads(1)

RED, TEXT, SOFT, GREY = PALETTE["red"], PALETTE["text"], PALETTE["soft"], PALETTE["grey"]
PANEL, PANEL_HI, COOL = PALETTE["panel"], PALETTE["panel_hi"], PALETTE["cool"]
BG = PALETTE["bg"]


def S(v):
    """design units -> pixels"""
    return int(round(v * SCALE))


def P(v):
    """design units -> pixels, 4 fractional bits (sub-pixel for cv2 shift=4)"""
    return int(round(v * SCALE * 16))


# ------------------------------------------------------------------ easing
def clamp(x, a=0.0, b=1.0):
    return a if x < a else b if x > b else x


def seg(p, a, b):
    """progress of p inside the window [a, b], clamped to 0..1"""
    return clamp((p - a) / (b - a)) if b > a else (1.0 if p >= b else 0.0)


def ease_out(p):
    p = clamp(p)
    return 1 - (1 - p) ** 3


def ease_in_out(p):
    p = clamp(p)
    return 4 * p ** 3 if p < 0.5 else 1 - (-2 * p + 2) ** 3 / 2


def ease_out_expo(p):
    p = clamp(p)
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def ease_out_back(p, s=1.25):
    p = clamp(p)
    return 1 + (s + 1) * (p - 1) ** 3 + s * (p - 1) ** 2


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c0, c1, t):
    return tuple(int(lerp(c0[i], c1[i], t)) for i in range(3))


# ------------------------------------------------------------------- fonts
_FILES = {"bold": "Inter-Bold.otf", "semi": "Inter-SemiBold.otf", "med": "Inter-Medium.otf",
          "reg": "Inter-Regular.otf", "serif": "LiberationSerif-Regular.ttf",
          "serifi": "LiberationSerif-Italic.ttf"}
_FALLBACKS = ["DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "Arial Bold.ttf", "arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf"]


@lru_cache(maxsize=None)
def font(weight, size):
    px = max(8, S(size))
    for cand in [FONT_DIR / _FILES.get(weight, _FILES["bold"]), *_FALLBACKS]:
        try:
            return ImageFont.truetype(str(cand), px)
        except OSError:
            continue
    return ImageFont.load_default()


# ------------------------------------------------------------------ layers
class Layer:
    """Premultiplied RGBA sprite. blit() composites it with integer cv2 maths."""
    __slots__ = ("pm", "inv", "w", "h")

    def __init__(self, rgba):
        rgba = np.ascontiguousarray(rgba)
        a = np.ascontiguousarray(rgba[..., 3])
        a3 = cv2.merge([a, a, a])
        self.pm = cv2.multiply(np.ascontiguousarray(rgba[..., :3]), a3, scale=1 / 255.0)
        self.inv = cv2.subtract(np.full_like(a3, 255), a3)
        self.h, self.w = a.shape


def blit(frame, L, x, y, alpha=1.0):
    """Composite layer L with its top-left at pixel (x, y)."""
    if alpha <= 0.003:
        return
    x, y = int(x), int(y)
    fx0, fy0, fx1, fy1 = max(0, x), max(0, y), min(W, x + L.w), min(H, y + L.h)
    if fx1 <= fx0 or fy1 <= fy0:
        return
    sx0, sy0 = fx0 - x, fy0 - y
    sx1, sy1 = sx0 + (fx1 - fx0), sy0 + (fy1 - fy0)
    roi = frame[fy0:fy1, fx0:fx1]
    pm, inv = L.pm[sy0:sy1, sx0:sx1], L.inv[sy0:sy1, sx0:sx1]
    if alpha < 0.997:
        pm = cv2.convertScaleAbs(pm, alpha=alpha)
        inv = cv2.convertScaleAbs(inv, alpha=alpha, beta=255 * (1 - alpha))
    cv2.multiply(roi, inv, dst=roi, scale=1 / 255.0)
    cv2.add(roi, pm, dst=roi)


def _pil_to_layer(img):
    return Layer(np.asarray(img))


@lru_cache(maxsize=2048)
def text_layer(txt, weight, size, color, tabular=False, track=0.0):
    """Rasterise one line of text. tabular=True gives every digit the same width
    (so counting numbers don't jitter); track is letter-spacing in design units."""
    f = font(weight, size)
    asc, desc = f.getmetrics()
    pad = S(6)
    tr = track * SCALE
    digit_w = max(f.getlength(str(i)) for i in range(10)) if tabular else 0
    simple = not tabular and tr == 0
    if simple:
        width = f.getlength(txt)
    else:
        adv = [(digit_w if (tabular and ch.isdigit()) else f.getlength(ch)) + tr for ch in txt]
        width = sum(adv)
    img = Image.new("RGBA", (int(math.ceil(width)) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    col = tuple(color) + (255,)
    if simple:
        d.text((pad, pad + asc), txt, font=f, fill=col, anchor="ls")
    else:
        x = pad
        for ch, a in zip(txt, adv):
            cw = f.getlength(ch)
            ox = (digit_w - cw) / 2 if (tabular and ch.isdigit()) else 0
            d.text((x + ox, pad + asc), ch, font=f, fill=col, anchor="ls")
            x += a
    return _pil_to_layer(img)


def measure(txt, weight, size, tabular=False, track=0.0):
    """width in design units"""
    return (text_layer(txt, weight, size, TEXT, tabular, track).w - 2 * S(6)) / SCALE


def text(frame, txt, x, y, weight="bold", size=48, color=TEXT, anchor="l", alpha=1.0,
         tabular=False, track=0.0):
    """Draw text. (x, y) in design units; y is the vertical centre of the line."""
    if not txt or alpha <= 0.003:
        return
    L = text_layer(txt, weight, size, tuple(color), tabular, track)
    w = L.w - 2 * S(6)
    px = S(x) - S(6) - (w // 2 if anchor == "c" else w if anchor == "r" else 0)
    py = S(y) - L.h // 2
    blit(frame, L, px, py, alpha)


def wrap(txt, weight, size, max_w, tabular=False):
    """greedy word wrap -> list of lines (max_w in design units)"""
    lines, cur = [], ""
    for word in str(txt).split():
        trial = f"{cur} {word}".strip()
        if measure(trial, weight, size, tabular) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines or [""]


def fit_size(txt, weight, size, max_w, min_size=24, tabular=False):
    while size > min_size and measure(txt, weight, size, tabular) > max_w:
        size -= 4
    return size


def parse_emphasis(txt):
    """'a *b c*, d' -> [('a', False), ('b', True), ('c,', True), ('d', False)]
    (punctuation typed right after a word stays glued to it)"""
    out, emph, glue = [], False, False
    for part in re.split(r"(\*)", str(txt)):
        if part == "*":
            emph = not emph
            continue
        if not part:
            continue
        toks = part.split()
        if not toks:
            glue = False
            continue
        starts_ws = part[0].isspace()
        for k, w in enumerate(toks):
            if k == 0 and out and glue and not starts_ws:
                out[-1] = (out[-1][0] + w, out[-1][1])
            else:
                out.append((w, emph))
        glue = not part[-1].isspace()
    return out


# ------------------------------------------------------------------- shapes
@lru_cache(maxsize=256)
def _panel_layer(w, h, r, fill, fill_a, stroke, sw):
    ss = 2
    img = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    box = [0, 0, w * ss - 1, h * ss - 1]
    d.rounded_rectangle(box, radius=r * ss, fill=(tuple(fill) + (int(255 * fill_a),)) if fill else None,
                        outline=(tuple(stroke) + (255,)) if stroke else None, width=max(1, sw * ss))
    return _pil_to_layer(img.resize((w, h), Image.LANCZOS))


def panel(frame, x0, y0, x1, y1, r=18, fill=PANEL, fill_a=0.92, stroke=None, sw=2, alpha=1.0):
    w, h = max(2, S(x1) - S(x0)), max(2, S(y1) - S(y0))
    blit(frame, _panel_layer(w, h, S(r), tuple(fill) if fill else None, round(fill_a, 2),
                             tuple(stroke) if stroke else None, S(sw)), S(x0), S(y0), alpha)


def rect(frame, x0, y0, x1, y1, color, alpha=1.0):
    ax0, ay0, ax1, ay1 = max(0, S(x0)), max(0, S(y0)), min(W, S(x1)), min(H, S(y1))
    if ax1 <= ax0 or ay1 <= ay0 or alpha <= 0.003:
        return
    roi = frame[ay0:ay1, ax0:ax1]
    if alpha >= 0.997:
        roi[:] = color
    else:
        cv2.addWeighted(roi, 1 - alpha, np.full_like(roi, color), alpha, 0, dst=roi)


def _bbox_px(pts, pad):
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (max(0, int(min(xs)) - pad), max(0, int(min(ys)) - pad),
            min(W, int(max(xs)) + pad), min(H, int(max(ys)) + pad))


def _alpha_draw(frame, bbox, alpha, fn):
    """run fn(canvas, ox, oy) on a copy of the ROI and blend it back at `alpha`."""
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0 or alpha <= 0.003:
        return
    roi = frame[y0:y1, x0:x1]
    if alpha >= 0.997:
        fn(roi, x0, y0)
        return
    tmp = roi.copy()
    fn(tmp, x0, y0)
    cv2.addWeighted(tmp, alpha, roi, 1 - alpha, 0, dst=roi)


def line(frame, x0, y0, x1, y1, color=GREY, w=3, alpha=1.0, dash=None):
    """AA line in design units. dash=(on, off) in design units."""
    pts = [(S(x0), S(y0)), (S(x1), S(y1))]
    bbox = _bbox_px(pts, S(w) + 4)

    def draw(cv, ox, oy):
        if not dash:
            cv2.line(cv, (P(x0) - ox * 16, P(y0) - oy * 16), (P(x1) - ox * 16, P(y1) - oy * 16),
                     color, max(1, S(w)), cv2.LINE_AA, 4)
            return
        L = math.hypot(x1 - x0, y1 - y0) or 1
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        d = 0.0
        while d < L:
            e = min(L, d + dash[0])
            cv2.line(cv, (P(x0 + ux * d) - ox * 16, P(y0 + uy * d) - oy * 16),
                     (P(x0 + ux * e) - ox * 16, P(y0 + uy * e) - oy * 16),
                     color, max(1, S(w)), cv2.LINE_AA, 4)
            d += dash[0] + dash[1]

    _alpha_draw(frame, bbox, alpha, draw)


def polyline(frame, pts, color=TEXT, w=6, alpha=1.0):
    if len(pts) < 2:
        return
    px = [(S(x), S(y)) for x, y in pts]
    bbox = _bbox_px(px, S(w) + 4)

    def draw(cv, ox, oy):
        arr = np.array([[P(x) - ox * 16, P(y) - oy * 16] for x, y in pts], np.int32)
        cv2.polylines(cv, [arr], False, color, max(1, S(w)), cv2.LINE_AA, 4)

    _alpha_draw(frame, bbox, alpha, draw)


def polygon(frame, pts, color, alpha=1.0):
    px = [(S(x), S(y)) for x, y in pts]
    bbox = _bbox_px(px, 4)

    def draw(cv, ox, oy):
        arr = np.array([[P(x) - ox * 16, P(y) - oy * 16] for x, y in pts], np.int32)
        cv2.fillPoly(cv, [arr], color, cv2.LINE_AA, 4)

    _alpha_draw(frame, bbox, alpha, draw)


def circle(frame, cx, cy, r, color=TEXT, alpha=1.0, thickness=-1):
    rp = S(r)
    bbox = (max(0, S(cx) - rp - 4), max(0, S(cy) - rp - 4), min(W, S(cx) + rp + 4), min(H, S(cy) + rp + 4))

    def draw(cv, ox, oy):
        cv2.circle(cv, (P(cx) - ox * 16, P(cy) - oy * 16), int(r * SCALE * 16), color,
                   thickness if thickness < 0 else max(1, S(thickness)), cv2.LINE_AA, 4)

    _alpha_draw(frame, bbox, alpha, draw)


# ------------------------------------------------------------------- light
@lru_cache(maxsize=24)
def _glow_tile(w, h, kind):
    """soft additive blob (uint8 RGB-agnostic gray 0..255); kind 'ellipse' or 'rect'"""
    small_w, small_h = max(4, w // 6), max(4, h // 6)
    yy, xx = np.mgrid[0:small_h, 0:small_w].astype(np.float32)
    if kind == "ellipse":
        d = np.sqrt(((xx - small_w / 2) / (small_w / 2)) ** 2 + ((yy - small_h / 2) / (small_h / 2)) ** 2)
        g = np.clip(1 - d, 0, 1) ** 2
    else:  # rect: bright core fading to the border
        dx = np.minimum(xx, small_w - 1 - xx) / (small_w * 0.5)
        dy = np.minimum(yy, small_h - 1 - yy) / (small_h * 0.5)
        g = np.clip(np.minimum(dx, dy) * 2, 0, 1) ** 1.5
    g = cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)
    return (np.clip(g, 0, 1) * 255).astype(np.uint8)


def _add_tile(frame, tile, x0, y0, color, intensity):
    h, w = tile.shape
    fx0, fy0, fx1, fy1 = max(0, x0), max(0, y0), min(W, x0 + w), min(H, y0 + h)
    if fx1 <= fx0 or fy1 <= fy0 or intensity <= 0.003:
        return
    t = tile[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0]
    roi = frame[fy0:fy1, fx0:fx1]
    col = np.array(color, np.float32) * intensity / 255.0
    lut = [cv2.LUT(t, np.clip(np.arange(256) * c, 0, 255).astype(np.uint8)) for c in col]
    cv2.add(roi, cv2.merge(lut), dst=roi)


def spot(frame, cx, cy, rx, ry, color=RED, intensity=0.2):
    """soft elliptical light centred at (cx, cy) with radii rx, ry (design units)"""
    w, h = S(rx) * 2, S(ry) * 2
    _add_tile(frame, _glow_tile(w, h, "ellipse"), S(cx) - w // 2, S(cy) - h // 2, color, intensity)


def glow_rect(frame, x0, y0, x1, y1, color=RED, spread=40, intensity=0.5):
    """halo around a rectangle; spread in design units"""
    w, h = S(x1 - x0 + 2 * spread), S(y1 - y0 + 2 * spread)
    if w < 8 or h < 8:
        return
    _add_tile(frame, _glow_tile(w, h, "rect"), S(x0 - spread), S(y0 - spread), color, intensity)


# ------------------------------------------------------------------- icons
@lru_cache(maxsize=64)
def icon_layer(kind, size, color):
    """simple vector icons drawn once (supersampled): people, building, bank, doc, dollar, loan"""
    ss, n = 4, S(size)
    img = Image.new("RGBA", (n * ss, n * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = tuple(color) + (255,)
    u = n * ss / 100.0

    def box(a, b, c2, d2, **kw):
        d.rectangle([a * u, b * u, c2 * u, d2 * u], **kw)

    lw = int(5 * u)
    if kind == "people":
        for cx, cy, r in ((50, 30, 15), (20, 40, 11), (80, 40, 11)):
            d.ellipse([(cx - r) * u, (cy - r) * u, (cx + r) * u, (cy + r) * u], fill=c)
        d.pieslice([30 * u, 52 * u, 70 * u, 110 * u], 180, 360, fill=c)
        d.pieslice([2 * u, 58 * u, 38 * u, 112 * u], 180, 360, fill=c)
        d.pieslice([62 * u, 58 * u, 98 * u, 112 * u], 180, 360, fill=c)
    elif kind == "building":
        box(22, 12, 78, 92, outline=c, width=lw)
        for r in range(4):
            for k in range(2):
                box(32 + k * 24, 22 + r * 17, 42 + k * 24, 32 + r * 17, fill=c)
        box(44, 78, 56, 92, fill=c)
        box(8, 92, 92, 96, fill=c)
    elif kind == "bank":
        d.polygon([(50 * u, 8 * u), (94 * u, 34 * u), (6 * u, 34 * u)], fill=c)
        for k in range(4):
            box(14 + k * 21, 42, 24 + k * 21, 76, fill=c)
        box(6, 82, 94, 92, fill=c)
    elif kind == "doc":
        d.polygon([(22 * u, 6 * u), (62 * u, 6 * u), (80 * u, 24 * u), (80 * u, 94 * u), (22 * u, 94 * u)],
                  outline=c, width=lw)
        for k in range(4):
            box(32, 40 + k * 12, 70, 44 + k * 12, fill=c)
    elif kind == "loan":
        d.ellipse([10 * u, 10 * u, 90 * u, 90 * u], outline=c, width=lw)
        d.line([(50 * u, 28 * u), (50 * u, 72 * u)], fill=c, width=lw)
        d.polygon([(34 * u, 56 * u), (50 * u, 74 * u), (66 * u, 56 * u)], fill=c)
    else:  # dollar
        d.ellipse([8 * u, 8 * u, 92 * u, 92 * u], outline=c, width=lw)
        f = ImageFont.truetype(str(FONT_DIR / _FILES["bold"]), int(60 * u))
        d.text((50 * u, 52 * u), "$", font=f, fill=c, anchor="mm")
    return _pil_to_layer(img.resize((n, n), Image.LANCZOS))


def icon_for(label):
    s = label.lower()
    table = (("people", ("investor", "lp ", "lps", "limited partner", "retail", "people", "tenant", "buyer", "family", "doctor", "dentist")),
             ("bank", ("lender", "bank", "arbor", "loan", "credit", "debt fund", "servicer", "mortgage")),
             ("building", ("property", "propert", "apartment", "asset", "building", "complex", "unit", "real estate", "portfolio", "company", "fund", "sponsor", "syndicat", "operator")),
             ("doc", ("filing", "document", "report", "court", "memorandum", "notice", "contract", "regulator", "sebi", "sec ")))
    for kind, keys in table:
        if any(k in s for k in keys):
            return kind
    return "dollar"


def icon(frame, kind, cx, cy, size=96, color=TEXT, alpha=1.0):
    L = icon_layer(kind, size, tuple(color))
    blit(frame, L, S(cx) - L.w // 2, S(cy) - L.h // 2, alpha)
