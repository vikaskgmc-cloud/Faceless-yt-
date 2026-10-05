"""Scene library for the business-case-study look.

Each visual is  v_<type>(c, d)  where c is a Ctx (frame + timing) and d is the
visual's data dict. Layout is in design units (1920x1080). c.p is the reveal
progress (0..1 over the first ~2 s of the beat); after that the scene "holds"
with slow drift, pulsing light and moving particles so it never looks frozen.
"""
import math
import os
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from config import BRAND_DIR, CHANNEL_NAME, DISCLAIMER, H, W
from fx import (BG, COOL, GREY, PANEL, PANEL_HI, RED, SOFT, TEXT, S, blit, circle, clamp, ease_in_out,
                ease_out, ease_out_back, ease_out_expo, fit_size, glow_rect, icon, icon_for, line, measure,
                mix, panel, parse_emphasis, polygon, polyline, rect, seg, spot, text, text_layer, wrap)
from fx import font as fx_font

LM, RM = 150, 1770            # left / right content margins
DIM = (70, 78, 94)


class Ctx:
    def __init__(self, f, act, t, dur, gt, beat):
        self.f, self.act, self.t, self.dur, self.gt, self.beat = f, act, t, dur, gt, beat
        self.R = min(max(dur * 0.6, 0.5), 2.2)
        self.p = clamp(t / self.R)
        self.drift = -10.0 * (t / max(dur, 0.1))
        self.pulse = 0.5 + 0.5 * math.sin(gt * 2.2)


def heading(c, txt, sub=None):
    p = ease_out(seg(c.p, 0, 0.35))
    lines = wrap(txt, "semi", 46, 1500)
    y = 150
    rect(c.f, LM, y - 26, LM + 8, y - 26 + 52 * p * len(lines) ** 0.5, RED)
    for ln in lines:
        text(c.f, ln, LM + 32 - (1 - p) * 30, y, "semi", 46, TEXT, "l", p)
        y += 58
    if sub:
        text(c.f, sub, LM + 32, y - 10, "reg", 28, GREY, "l", p)
        y += 36
    return y


def _num(v, dec):
    return f"{v:,.{dec}f}"


def _decimals(v, given=None):
    if given is not None:
        return int(given)
    if abs(v - round(v)) < 1e-9:
        return 0
    return 1 if abs(v * 10 - round(v * 10)) < 1e-6 else 2


def _nice_max(v):
    if v <= 0:
        return 1
    e = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if v <= m * e:
            return m * e
    return 10 * e


# ------------------------------------------------------------------ text
def v_title(c, d):
    spot(c.f, 960, 500, 1100, 600, RED, 0.07 + 0.03 * c.pulse)
    kick = d.get("kicker", "CASE STUDY")
    ka = ease_out(seg(c.p, 0, 0.3))
    text(c.f, kick, 960, 330, "semi", 28, RED, "c", ka, track=9)
    words = parse_emphasis(d.get("text", ""))
    n = len(words)
    size = 112 if n <= 5 else 96 if n <= 8 else 80
    _kinetic(c, words, 960, 520, size, 1500, 0.1, 0.8)
    rw = 200 * ease_out(seg(c.p, 0.6, 1))
    y = 520 + (len(_layout(words, size, 1500)) * size * 1.2) / 2 + 36
    rect(c.f, 960 - rw / 2, y, 960 + rw / 2, y + 6, RED)
    if d.get("subtitle"):
        text(c.f, d["subtitle"], 960, y + 56, "med", 34, SOFT, "c", ease_out(seg(c.p, 0.7, 1)))


def _layout_once(words, size, max_w):
    space, lines, cur, cw = size * 0.27, [], [], 0
    for w, e in words:
        ww = measure(w, "bold", size)
        if cur and cw + space + ww > max_w:
            lines.append((cur, cw))
            cur, cw = [], 0
        cw += (space if cur else 0) + ww
        cur.append((w, e, ww))
    if cur:
        lines.append((cur, cw))
    return lines


def _layout(words, size, max_w):
    """wrap, then tighten the width while the line count stays the same (balanced lines, no orphans)"""
    lines = _layout_once(words, size, max_w)
    n, w = len(lines), max_w
    if n > 1:
        while w > max_w * 0.5:
            trial = _layout_once(words, size, w - 40)
            if len(trial) != n:
                break
            lines, w = trial, w - 40
    return lines


def _kinetic(c, words, cx, cy, size, max_w, start, span, align="c"):
    lines = _layout(words, size, max_w)
    lh = size * 1.2
    y = cy - len(lines) * lh / 2 + lh / 2 + c.drift * 0.5
    n, k, space = len(words), 0, size * 0.27
    for ln, cw in lines:
        x = cx - cw / 2 if align == "c" else cx
        for w, e, ww in ln:
            st = start + span * k / max(1, n - 1) * 0.7
            loc = ease_out(seg(c.p, st, st + 0.3))
            text(c.f, w, x, y + (1 - loc) * 34, "bold", size, RED if e else TEXT, "l", loc)
            x += ww + space
            k += 1
        y += lh
    return y


def v_text(c, d):
    words = parse_emphasis(d.get("text", ""))
    if not words:
        return
    n = len(words)
    size = 104 if n <= 5 else 90 if n <= 8 else 78 if n <= 12 else 66
    spot(c.f, 960, 540, 1000, 520, RED if c.act in ("cold_open", "collapse") else COOL, 0.05 + 0.02 * c.pulse)
    lines = _layout(words, size, 1560)
    y_end = _kinetic(c, words, 960, 540, size, 1560, 0.0, 0.75)
    rw = 150 * ease_out(seg(c.p, 0.55, 1))
    rect(c.f, 960 - rw / 2, y_end - size * 0.6 + 18, 960 + rw / 2, y_end - size * 0.6 + 24, RED)


# ------------------------------------------------------------------ numbers
def v_stat(c, d):
    spot(c.f, 960, 470, 1050, 560, RED, 0.10 + 0.045 * c.pulse)
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    val = float(d.get("value", 0))
    dec = _decimals(val, d.get("decimals"))
    final = f"{pre}{_num(val, dec)}{suf}"
    size = fit_size(final, "bold", 280, 1640, tabular=True)
    cur = val * ease_out_expo(c.p)
    s = f"{pre}{_num(cur, dec)}{suf}"
    w = measure(final, "bold", size, tabular=True)
    text(c.f, s, 960 - w / 2, 440 + c.drift * 0.4, "bold", size, RED, "l", tabular=True)
    la = ease_out(seg(c.p, 0.3, 0.75))
    y = 440 + size * 0.62 + 40 + (1 - la) * 20
    for ln in wrap(d.get("label", ""), "med", 48, 1400):
        text(c.f, ln, 960, y, "med", 48, TEXT, "c", la)
        y += 62
    if d.get("sub"):
        text(c.f, d["sub"], 960, y + 6, "reg", 32, GREY, "c", ease_out(seg(c.p, 0.5, 0.9)))
    if d.get("chip"):
        a = ease_out(seg(c.p, 0.55, 0.95))
        cw = measure(d["chip"], "semi", 30) + 56
        panel(c.f, 960 - cw / 2, y + 56, 960 + cw / 2, y + 112, 28, fill=None, stroke=RED, sw=3, alpha=a)
        text(c.f, d["chip"], 960, y + 85, "semi", 30, RED, "c", a)


# ------------------------------------------------------------------ charts
def v_bars(c, d):
    heading(c, d.get("title", ""), d.get("subtitle"))
    bars = d.get("bars", [])
    if not bars:
        return
    unit, pre = d.get("unit", ""), d.get("prefix", "")
    top = _nice_max(max(b["value"] for b in bars))
    x0, x1, base, ytop = 260, 1740, 880, 360
    for k in range(5):
        gy = base - (base - ytop) * k / 4
        line(c.f, x0, gy, x1, gy, (52, 58, 72) if k else GREY, 2 if k else 3, 1.0)
        text(c.f, f"{pre}{_num(top * k / 4, _decimals(top * k / 4 if top < 8 else 0))}{unit}", x0 - 22, gy,
             "reg", 24, GREY, "r", ease_out(seg(c.p, 0, .3)))
    n = len(bars)
    slot = (x1 - x0) / n
    bw = min(230, slot * 0.52)
    for i, b in enumerate(bars):
        loc = ease_out(seg(c.p, 0.12 + 0.2 * i / max(1, n - 1), 0.6 + 0.2 * i / max(1, n - 1)))
        cx = x0 + slot * (i + 0.5)
        h = (base - ytop) * (b["value"] / top) * loc
        red = b.get("color") == "red"
        col = RED if red else (150, 158, 176)
        if red and h > 6:
            glow_rect(c.f, cx - bw / 2, base - h, cx + bw / 2, base, RED, 46, 0.30 + 0.1 * c.pulse)
        rect(c.f, cx - bw / 2, base - h, cx + bw / 2, base, col)
        rect(c.f, cx - bw / 2, base - h, cx + bw / 2, base - h + 5, mix(col, (255, 255, 255), 0.35))
        v = b["value"] * loc
        text(c.f, f"{pre}{_num(v, _decimals(b['value'], d.get('decimals')))}{unit}", cx, base - h - 34,
             "bold", 40, RED if red else TEXT, "c", clamp(loc * 2), tabular=True)
        for k, ln in enumerate(wrap(b["label"], "med", 30, slot * 0.92)):
            text(c.f, ln, cx, base + 42 + k * 38, "med", 30, TEXT, "c", ease_out(seg(c.p, 0.1, 0.5)))
    ref = d.get("line")
    if ref:
        gy = base - (base - ytop) * ref["value"] / top
        a = ease_out(seg(c.p, 0.5, 0.9))
        line(c.f, x0, gy, x1, gy, TEXT, 3, a, dash=(18, 12))
        lw = measure(ref.get("label", ""), "semi", 26) + 36
        panel(c.f, x1 - lw, gy - 52, x1, gy - 6, 10, fill=(18, 21, 28), fill_a=0.92, stroke=GREY, sw=2, alpha=a)
        text(c.f, ref.get("label", ""), x1 - lw / 2, gy - 29, "semi", 26, TEXT, "c", a)


def v_line(c, d):
    heading(c, d.get("title", ""), d.get("subtitle"))
    pts = d.get("points", [])
    if len(pts) < 2:
        return
    unit, pre = d.get("unit", ""), d.get("prefix", "")
    red = d.get("color") == "red"
    col = RED if red else TEXT
    ys = [q["y"] for q in pts]
    lo = min(0, min(ys)) if min(ys) >= 0 else min(ys)
    hi = _nice_max(max(ys)) if max(ys) > 0 else 1
    x0, x1, ya, yb = 270, 1740, 340, 860
    for k in range(5):
        gy = yb - (yb - ya) * k / 4
        line(c.f, x0, gy, x1, gy, (52, 58, 72) if k else GREY, 2 if k else 3, 1.0)
        v = lo + (hi - lo) * k / 4
        text(c.f, f"{pre}{_num(v, 0 if hi >= 8 else 1)}{unit}", x0 - 20, gy, "reg", 24, GREY, "r",
             ease_out(seg(c.p, 0, .3)))
    n = len(pts)
    xy = [(x0 + (x1 - x0) * i / (n - 1), yb - (yb - ya) * (q["y"] - lo) / ((hi - lo) or 1)) for i, q in enumerate(pts)]
    reach = ease_in_out(seg(c.p, 0.05, 0.95)) * (n - 1)
    full = int(reach)
    path = xy[:full + 1]
    if full < n - 1:
        f = reach - full
        path.append((xy[full][0] + (xy[full + 1][0] - xy[full][0]) * f, xy[full][1] + (xy[full + 1][1] - xy[full][1]) * f))
    tip = path[-1]
    # area under the curve
    if len(path) >= 2:
        polygon(c.f, [(path[0][0], yb)] + path + [(tip[0], yb)], col, 0.13)
        polyline(c.f, path, col, 7)
    step = max(1, n // 8)
    for i, q in enumerate(pts):
        if i % step == 0 or i == n - 1:
            text(c.f, str(q.get("x", "")), xy[i][0], yb + 40, "med", 26, SOFT, "c", clamp(reach - i + 1))
    for an in d.get("annotations", []):
        i = int(an.get("index", 0))
        if 0 <= i < n and reach >= i:
            a = ease_out(seg(reach - i, 0, 0.8))
            ax, ay = xy[i]
            line(c.f, ax, ay, ax, ya - 20, GREY, 2, a, dash=(8, 8))
            circle(c.f, ax, ay, 9, TEXT, a)
            tw = measure(an.get("text", ""), "semi", 26) + 40
            px0 = clamp(ax - tw / 2, LM, RM - tw)
            panel(c.f, px0, ya - 78, px0 + tw, ya - 22, 12, fill=PANEL_HI, fill_a=0.95, stroke=GREY, sw=2, alpha=a)
            text(c.f, an.get("text", ""), px0 + tw / 2, ya - 50, "semi", 26, TEXT, "c", a)
    ring = 14 + 10 * c.pulse
    circle(c.f, tip[0], tip[1], ring, col, 0.22)
    circle(c.f, tip[0], tip[1], 10, col)
    cur = lo + (hi - lo) * ((yb - tip[1]) / (yb - ya))
    text(c.f, f"{pre}{_num(cur, 0 if hi >= 8 else 1)}{unit}", clamp(tip[0], 340, 1700), tip[1] - 44,
         "bold", 40, col, "c", tabular=True)


def v_gauge(c, d):
    heading(c, d.get("title", ""), d.get("subtitle"))
    mn, mx = float(d.get("min", 0)), float(d.get("max", 2))
    th, val = float(d.get("threshold", 1)), float(d.get("value", 0))
    unit = d.get("unit", "")
    x0, x1, y, h = 260, 1660, 620, 56
    pos = lambda v: x0 + (x1 - x0) * clamp((v - mn) / ((mx - mn) or 1))
    a = ease_out(seg(c.p, 0, 0.3))
    panel(c.f, x0, y - h / 2, x1, y + h / 2, 28, fill=(46, 52, 66), fill_a=1, alpha=a)
    xt = pos(th)
    rect(c.f, x0 + 14, y - h / 2 + 8, xt, y + h / 2 - 8, RED, 0.40 * a)
    rect(c.f, xt, y - h / 2 + 8, x1 - 14, y + h / 2 - 8, (150, 158, 176), 0.28 * a)
    line(c.f, xt, y - 60, xt, y + 60, TEXT, 4, a)
    text(c.f, d.get("threshold_label", f"{th:g}{unit} = break-even"), xt, y - 92, "semi", 28, TEXT, "c", a)
    text(c.f, f"{mn:g}", x0, y + 70, "reg", 24, GREY, "l", a)
    text(c.f, f"{mx:g}", x1, y + 70, "reg", 24, GREY, "r", a)
    prog = ease_out_expo(seg(c.p, 0.15, 0.85))
    cur = mn + (val - mn) * prog
    xm = pos(cur)
    bad = val < th
    mc = RED if bad else TEXT
    if bad:
        glow_rect(c.f, xm - 6, y - 40, xm + 6, y + 40, RED, 40, 0.35 + 0.12 * c.pulse)
    rect(c.f, xm - 5, y - 44, xm + 5, y + 44, mc)
    polygon(c.f, [(xm, y - 46), (xm - 16, y - 76), (xm + 16, y - 76)], mc)
    big = f"{cur:.2f}{unit}"
    w = measure(f"{val:.2f}{unit}", "bold", 190, tabular=True)
    spot(c.f, 960, 330, 760, 260, RED if bad else COOL, 0.09)
    text(c.f, big, 960 - w / 2, 330, "bold", 190, mc, "l", tabular=True)
    y2 = 800
    for ln in wrap(d.get("label", ""), "med", 40, 1400):
        text(c.f, ln, 960, y2, "med", 40, TEXT, "c", ease_out(seg(c.p, 0.4, 0.8)))
        y2 += 54


# ------------------------------------------------------------------ diagrams
def v_flow(c, d):
    heading(c, d.get("title", ""), d.get("subtitle"))
    nodes = d.get("nodes", [])[:5]
    n = len(nodes)
    if not n:
        return
    labels = d.get("labels", [])
    hot = d.get("highlight")
    gap = {1: 190, 2: 230, 3: 200, 4: 170, 5: 140}[n]
    nw = min(340, (1620 - gap * (n - 1)) / n)
    total = nw * n + gap * (n - 1)
    x0, y0, nh = 960 - total / 2, 380, 380
    centers = []
    for i, label in enumerate(nodes):
        loc = ease_out(seg(c.p, 0.1 + 0.55 * i / max(1, n - 1), 0.4 + 0.55 * i / max(1, n - 1)))
        x = x0 + i * (nw + gap)
        yy = y0 + (1 - loc) * 40
        centers.append((x + nw / 2, yy + nh / 2, loc))
        hi = (hot == i)
        if hi:
            glow_rect(c.f, x, yy, x + nw, yy + nh, RED, 50, 0.20 * loc + 0.06 * c.pulse)
        panel(c.f, x, yy, x + nw, yy + nh, 22, fill=PANEL_HI if hi else PANEL, fill_a=0.96,
              stroke=RED if hi else (74, 82, 100), sw=3, alpha=loc)
        icon(c.f, icon_for(label), x + nw / 2, yy + 120, 104, RED if hi else TEXT, loc)
        size = 36 if n <= 3 else 32
        lines = wrap(label, "semi", size, nw - 40)[:3]
        ty = yy + 238 + (3 - len(lines)) * 20
        for ln in lines:
            text(c.f, ln, x + nw / 2, ty, "semi", size, TEXT, "c", loc)
            ty += size * 1.25
    for i in range(n - 1):
        (xa, ya, la), (xb, yb, lb) = centers[i], centers[i + 1]
        ax0, ax1, ay = xa + nw / 2 + 18, xb - nw / 2 - 18, ya
        a = lb
        toward_hot = hot == i + 1
        col = RED if toward_hot else SOFT
        line(c.f, ax0, ay, ax1 - 14, ay, col, 4, a)
        polygon(c.f, [(ax1, ay), (ax1 - 24, ay - 14), (ax1 - 24, ay + 14)], col, a)
        if i < len(labels) and labels[i]:
            lines_ = wrap(labels[i], "semi", 24, max(60, gap - 20))[:2]
            for k, ln_ in enumerate(lines_):
                text(c.f, ln_, (ax0 + ax1) / 2, ay - 34 - (len(lines_) - 1 - k) * 28, "semi", 24, col, "c", a)
        if a > 0.95:  # money packets travelling along the arrow
            for k in range(3):
                ph = ((c.gt * 0.55) + k / 3 + i * 0.17) % 1.0
                circle(c.f, lerp_(ax0, ax1 - 20, ph), ay, 7, col, 0.9 * math.sin(math.pi * ph))


def lerp_(a, b, t):
    return a + (b - a) * t


def v_layer(c, d):
    num = str(d.get("number", ""))
    t1, t2, t3 = (ease_out(seg(c.p, k * 0.22, k * 0.22 + 0.45)) for k in range(3))
    if num:
        text(c.f, num, 1480, 560 + c.drift, "bold", 760, TEXT, "c", 0.045 * t1)
    spot(c.f, 700, 520, 900, 520, RED, 0.06 + 0.02 * c.pulse)
    text(c.f, f"LAYER {num}".strip(), LM + 40, 330 + (1 - t1) * 20, "semi", 34, RED, "l", t1, track=8)
    rect(c.f, LM + 40, 372, LM + 40 + 120 * t1, 378, RED)
    y = 470
    for ln in wrap(d.get("title", ""), "bold", 92, 1250):
        text(c.f, ln, LM + 40, y + (1 - t2) * 30, "bold", 92, TEXT, "l", t2)
        y += 110
    for ln in wrap(d.get("text", ""), "reg", 42, 1150):
        text(c.f, ln, LM + 40, y + 24 + (1 - t3) * 20, "reg", 42, SOFT, "l", t3)
        y += 58


def v_table(c, d):
    y = heading(c, d.get("title", ""), d.get("subtitle")) + 36
    rows = d.get("rows", [])[:6]
    xs = [LM + 30, 1010]
    lw_, rw_ = 1010 - 30 - (LM + 30 + 66), RM - 30 - 1010
    heads = [d.get("left_header", "What they did"), d.get("right_header", "Rule broken")]
    ha = ease_out(seg(c.p, 0, 0.25))
    text(c.f, heads[0].upper(), xs[0] + 66, y, "semi", 26, GREY, "l", ha, track=4)
    text(c.f, heads[1].upper(), xs[1], y, "semi", 26, RED, "l", ha, track=4)
    y += 36
    n = len(rows)
    rh = min(112, (900 - y) / max(1, n) - 14)
    y += max(0, (900 - y - n * (rh + 14))) * 0.35
    for i, row in enumerate(rows):
        loc = ease_out(seg(c.p, 0.15 + 0.7 * i / max(1, n), 0.4 + 0.7 * i / max(1, n)))
        yy = y + i * (rh + 14)
        panel(c.f, LM + 10, yy, RM - 10, yy + rh, 16, fill=PANEL, fill_a=0.85, alpha=loc * 0.9)
        cx, cy = xs[0] + 20, yy + rh / 2
        line(c.f, cx - 11, cy - 11, cx + 11, cy + 11, RED, 5, loc)
        line(c.f, cx - 11, cy + 11, cx + 11, cy - 11, RED, 5, loc)
        for k, cell in enumerate(row[:2]):
            lines = wrap(cell, "med", 32, lw_ if k == 0 else rw_)[:2]
            ty = cy - (len(lines) - 1) * 20
            for ln in lines:
                text(c.f, ln, xs[k] + (66 if k == 0 else 0) + (1 - loc) * 30, ty, "med", 32,
                     TEXT if k == 0 else (255, 150, 150), "l", loc)
                ty += 40


def v_timeline(c, d):
    heading(c, d.get("title", ""), d.get("subtitle"))
    ev = d.get("events", [])[:6]
    n = len(ev)
    if not n:
        return
    x0, x1, y = 240, 1680, 590
    line(c.f, x0, y, x1, y, (60, 67, 82), 5, 1.0)
    prog = ease_in_out(seg(c.p, 0.05, 0.95))
    xe = x0 + (x1 - x0 + 220) * prog
    line(c.f, x0, y, min(xe, x1), y, RED, 5, 1.0)
    slot = (x1 - x0) / max(1, n - 1)
    for i, e in enumerate(ev):
        x = x0 + slot * i if n > 1 else 960
        a = ease_out(clamp((xe - x) / 160 + 0.05))
        if a <= 0:
            continue
        last = i == n - 1
        up = i % 2 == 0
        r = 17 if last else 12
        if last:
            circle(c.f, x, y, 30 + 8 * c.pulse, RED, 0.25 * a)
        circle(c.f, x, y, r, RED if (last or True) else TEXT, a)
        sy = y - 70 if up else y + 70
        line(c.f, x, y + (-r if up else r), x, sy + (28 if up else -28), GREY, 2, a)
        text(c.f, str(e.get("when", "")), x, sy - 8 if up else sy + 8, "bold", 36, RED, "c", a)
        wid = min(330, slot * 1.55) if n > 1 else 500
        lines = wrap(e.get("what", ""), "med", 32, wid)[:3]
        ty = (sy - 56 - (len(lines) - 1) * 38) if up else (sy + 58)
        for ln in lines:
            text(c.f, ln, x, ty, "med", 32, TEXT, "c", a)
            ty += 38


# ------------------------------------------------------------------ evidence
def v_quote(c, d):
    q = " ".join(str(d.get("quote", d.get("text", ""))).split())
    if not q:
        return
    size = 54
    while size > 34:
        lines = wrap(q, "serif", size, 1080)
        if len(lines) * size * 1.42 <= 500:
            break
        size -= 4
    lines = wrap(q, "serif", size, 1080)
    lh = size * 1.42
    ph = 118 + len(lines) * lh + 104
    px0, px1 = 270, 1650
    py0 = 540 - ph / 2 + c.drift * 0.3
    a = ease_out(seg(c.p, 0, 0.3))
    panel(c.f, px0, py0 + (1 - a) * 30, px1, py0 + ph + (1 - a) * 30, 20, fill=(34, 39, 50), fill_a=0.96,
          stroke=(74, 82, 100), sw=2, alpha=a)
    lab = d.get("label", "SOURCE EXCERPT").upper()
    lw = measure(lab, "semi", 22, track=3) + 40
    panel(c.f, px0 + 52, py0 + 34, px0 + 52 + lw, py0 + 76, 21, fill=None, stroke=RED, sw=2, alpha=a)
    text(c.f, lab, px0 + 52 + lw / 2, py0 + 55, "semi", 22, RED, "c", a, track=3)
    icon(c.f, "doc", px1 - 80, py0 + 56, 44, GREY, a)
    text(c.f, "“", px0 + 40, py0 + 150, "serif", 200, RED, "l", 0.45 * a)
    tx, ty = px0 + 100, py0 + 118 + lh / 2
    hl = str(d.get("highlight", "")).strip()
    hs = q.lower().find(hl.lower()) if hl else -1
    pos = 0
    for i, ln in enumerate(lines):
        la = ease_out(seg(c.p, 0.15 + 0.5 * i / max(1, len(lines)), 0.4 + 0.5 * i / max(1, len(lines))))
        ls = q.find(ln, pos)
        pos = ls + len(ln)
        yy = ty + i * lh
        if hs >= 0:
            a0, b0 = max(hs, ls), min(hs + len(hl), ls + len(ln))
            if b0 > a0:
                xa = tx + measure(ln[:a0 - ls], "serif", size) if a0 > ls else tx
                xb = tx + measure(ln[:b0 - ls], "serif", size)
                grow = ease_out(seg(c.p, 0.6, 1.0))
                rect(c.f, xa - 4, yy - size * 0.58, xa - 4 + (xb - xa + 8) * grow, yy + size * 0.42, RED, 0.34)
        text(c.f, ln, tx, yy + (1 - la) * 18, "serif", size, TEXT, "l", la)
    fy = py0 + ph - 46
    line(c.f, px0 + 52, fy - 36, px1 - 52, fy - 36, (62, 69, 84), 2, a)
    src = d.get("source", "")
    if src:
        text(c.f, f"Source: {src}", px0 + 52, fy, "med", 26, SOFT, "l", a)
    if d.get("date"):
        text(c.f, str(d["date"]), px1 - 52, fy, "med", 26, GREY, "r", a)


def v_units(c, d):
    heading(c, d.get("title", ""), d.get("subtitle"))
    total, aff = int(d.get("total", 100)), int(d.get("affected", 0))
    neutral = aff <= 0
    shown = total if neutral else aff
    k = next((m for m in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500) if math.ceil(total / m) <= 360), 1000)
    n, an = math.ceil(total / k), min(math.ceil(total / k), round(aff / k))
    gx0, gx1, gy0, gy1 = 900, 1770, 270, 880
    cols = max(1, math.ceil(math.sqrt(n * (gx1 - gx0) / (gy1 - gy0))))
    rows = math.ceil(n / cols)
    cell = min((gx1 - gx0) / cols, (gy1 - gy0) / rows)
    sq = cell * 0.76
    ox = gx0 + ((gx1 - gx0) - cell * cols) / 2
    oy = gy0 + ((gy1 - gy0) - cell * rows) / 2
    for i in range(n):
        r, cc = divmod(i, cols)
        a = ease_out(seg(c.p, i / n * 0.35, i / n * 0.35 + 0.12))
        if a <= 0:
            continue
        col = DIM
        if i < an:
            m = ease_out(seg(c.p, 0.45 + (i / max(1, an)) * 0.45, 0.55 + (i / max(1, an)) * 0.45))
            col = mix(DIM, RED, m)
        x, y = ox + cc * cell + (cell - sq) / 2, oy + r * cell + (cell - sq) / 2
        rect(c.f, x, y, x + sq, y + sq, col, a)
    spot(c.f, 470, 560, 520, 420, RED, 0.08 + 0.03 * c.pulse)
    cnt = shown * ease_out_expo(seg(c.p, 0.4, 1))
    pre, suf = d.get("prefix", ""), d.get("suffix", "")
    final = f"{pre}{shown:,}{suf}"
    size = fit_size(final, "bold", 190, 700, tabular=True)
    text(c.f, f"{pre}{int(cnt):,}{suf}", LM + 20, 520, "bold", size, TEXT if neutral else RED, "l", tabular=True)
    y = 520 + size * 0.62 + 30
    for ln in wrap(d.get("label", ""), "med", 42, 700):
        text(c.f, ln, LM + 20, y, "med", 42, TEXT, "l", ease_out(seg(c.p, 0.3, 0.7)))
        y += 56
    if d.get("sub"):
        text(c.f, d["sub"], LM + 20, y + 10, "reg", 30, GREY, "l", ease_out(seg(c.p, 0.4, 0.8)))
    text(c.f, f"Each square = {k:,} unit{'s' if k > 1 else ''}" if k > 1 else "Each square = 1 unit", gx1,
         gy1 + 44, "reg", 24, GREY, "r", ease_out(seg(c.p, 0.2, 0.5)))


def v_stack(c, d):
    heading(c, d.get("title", "How the money is stacked"), d.get("subtitle"))
    layers = d.get("layers", [])[:5]
    if not layers:
        return
    total = sum(float(l["share"]) for l in layers) or 100
    sx0, sx1, ytop, ybot = 720, 1250, 300, 890
    hh = ybot - ytop
    v_end = float(d.get("value_drop", 75))
    v = 100 - v_end * ease_in_out(seg(c.p, 0.3, 0.9))   # value_drop = % of value lost
    water = ybot - hh * (v / 100.0)
    y = ytop
    for i, l in enumerate(layers):
        bh = hh * float(l["share"]) / total          # heights are true to the numbers
        loc = ease_out(seg(c.p, 0.05 * i, 0.05 * i + 0.3))
        panel(c.f, sx0, y + 2, sx1, y + bh - 2, 8, fill=PANEL_HI, fill_a=0.96, stroke=(84, 92, 110), sw=2, alpha=loc)
        if water > y + 2:     # the part above the falling value line is wiped out
            rect(c.f, sx0 + 2, y + 4, sx1 - 2, min(y + bh - 4, water), RED, 0.62)
        wiped = water >= y + bh - 2
        mid = y + bh / 2
        text(c.f, l["label"], sx0 - 30, mid - (0 if bh < 90 else 4), "semi", 34, TEXT, "r", loc)
        text(c.f, f"{float(l['share']):g}%", (sx0 + sx1) / 2, mid, "bold", 36 if bh > 70 else 28, TEXT, "c", loc)
        if wiped and bh > 70:
            text(c.f, "WIPED OUT", (sx0 + sx1) / 2, mid + 30, "bold", 20, TEXT, "c", ease_out(seg(c.p, 0.6, 0.9)), track=4)
        if l.get("note"):
            text(c.f, l["note"], sx1 + 30, mid, "reg", 28, SOFT, "l", loc)
        y += bh
    a = ease_out(seg(c.p, 0.25, 0.5))
    line(c.f, sx0 - 40, water, sx1 + 40, water, TEXT, 4, a, dash=(16, 10))
    text(c.f, f"{v:.0f}%", RM, 205, "bold", 84, RED if v < 99.5 else TEXT, "r", a, tabular=True)
    text(c.f, d.get("value_label", "of the original property value"), RM, 268, "med", 28, GREY, "r", a)
    text(c.f, "LOSSES HIT HERE FIRST \u2191", LM + 10, ytop + 10, "semi", 22, RED, "l", a, track=2)
    text(c.f, "PAID FIRST \u2193", LM + 10, ybot - 10, "semi", 22, GREY, "l", a, track=2)


# ------------------------------------------------------------------ photos
_IMG = {}
_VIG = {}


def _load_img(path):
    key = str(path)
    if key in _IMG:
        return _IMG[key]
    im = cv2.imread(key, cv2.IMREAD_COLOR)
    if im is None:
        return None
    im = cv2.cvtColor(im, cv2.COLOR_BGR2RGB)
    h, w = im.shape[:2]
    s = max(W * 1.18 / w, H * 1.18 / h)
    im = cv2.resize(im, (int(w * s) + 1, int(h * s) + 1), interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
    gray = cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    im = cv2.addWeighted(im, 0.72, gray, 0.28, 0)                           # desaturate a touch
    im = cv2.convertScaleAbs(im, alpha=0.78)                                # darken for legibility
    im = cv2.add(im, np.full_like(im, (0, 4, 12)))                          # cool slate tint
    if len(_IMG) > 3:
        _IMG.pop(next(iter(_IMG)))
    _IMG[key] = im
    return im


def _vignette():
    if "v" not in _VIG:
        yy, xx = np.mgrid[0:270, 0:480].astype(np.float32)
        dd = np.sqrt(((xx - 240) / 240) ** 2 + ((yy - 135) / 135) ** 2)
        g = np.clip(1.12 - 0.5 * dd ** 2, 0.35, 1) * 255
        g = cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.uint8)
        _VIG["v"] = cv2.merge([g, g, g])
        yy = np.linspace(0, 1, 270, dtype=np.float32)[:, None] * np.ones((1, 480), np.float32)
        b = np.clip(1.0 - 0.8 * np.clip((yy - 0.55) / 0.45, 0, 1), 0.2, 1) * 255
        b = cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR).astype(np.uint8)
        _VIG["b"] = cv2.merge([b, b, b])
    return _VIG["v"], _VIG["b"]


def resolve_image(d, ctx_beat):
    f = d.get("file")
    if not f:
        return None
    for base in (ctx_beat.get("media_dir"), ctx_beat.get("broll_dir")):
        if base and (Path(base) / f).is_file():
            return Path(base) / f
    return None


def v_image(c, d):
    path = resolve_image(d, c.beat)
    im = _load_img(path) if path else None
    if im is None:                      # missing file: fall back to a clean caption card
        v_text(c, {"text": d.get("caption", "")})
        return
    sh, sw = im.shape[:2]
    z = (1.0 + 0.15 * (c.t / max(c.dur, 0.1))) if c.beat.get("idx", 0) % 2 == 0 else (1.15 - 0.15 * (c.t / max(c.dur, 0.1)))
    ww = min(sw, W * 1.15 / z)
    wh = ww * H / W
    sgn = 1 if c.beat.get("idx", 0) % 3 else -1
    cx = sw / 2 + sgn * (sw - ww) * 0.35 * (c.t / max(c.dur, 0.1) - 0.5)
    cy = sh / 2
    s = W / ww
    M = np.array([[s, 0, -(cx - ww / 2) * s], [0, s, -(cy - wh / 2) * s]], np.float32)
    out = cv2.warpAffine(im, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    vig, bot = _vignette()
    cv2.multiply(out, vig, dst=out, scale=1 / 255.0)
    cv2.multiply(out, bot, dst=out, scale=1 / 255.0)
    a = ease_out(seg(c.t, 0, 0.35))
    cv2.addWeighted(out, a, c.f, 1 - a, 0, dst=c.f)
    cap = d.get("caption", "")
    if cap:
        w = min(1500, measure(cap, "semi", 40) + 90)
        la = ease_out(seg(c.t, 0.25, 0.8))
        panel(c.f, LM, 840 + (1 - la) * 24, LM + w, 920 + (1 - la) * 24, 14, fill=(14, 17, 23), fill_a=0.82, alpha=la)
        rect(c.f, LM, 840 + (1 - la) * 24, LM + 8, 920 + (1 - la) * 24, RED, la)
        text(c.f, cap, LM + 44, 880 + (1 - la) * 24, "semi", 40, TEXT, "l", la)
    if d.get("credit"):
        text(c.f, d["credit"], RM, 1038, "reg", 19, SOFT, "r", 0.8)


_CLIPS = {}


class _Clip:
    """sequential video reader (cached per worker process); loops when the beat is longer than the clip"""
    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 24.0
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        self.last_idx, self.last = -2, None

    def ok(self):
        return self.cap.isOpened() and self.n > 1

    def frame(self, t):
        idx = int(t * self.fps) % self.n
        if idx == self.last_idx and self.last is not None:
            return self.last
        if idx != self.last_idx + 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, bgr = self.cap.read()
        if not ok:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, bgr = self.cap.read()
            idx = 0
        if not ok:
            return self.last
        self.last_idx, self.last = idx, cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        return self.last


def _clip(path):
    key = str(path)
    if key not in _CLIPS:
        _CLIPS[key] = _Clip(path)
    return _CLIPS[key]


def _grade(im):
    """match footage to the channel look: slightly desaturated, darker, cool slate tint"""
    gray = cv2.cvtColor(cv2.cvtColor(im, cv2.COLOR_RGB2GRAY), cv2.COLOR_GRAY2RGB)
    im = cv2.addWeighted(im, 0.72, gray, 0.28, 0)
    im = cv2.convertScaleAbs(im, alpha=0.8)
    return cv2.add(im, np.full_like(im, (0, 4, 12)))


def v_clip(c, d):
    path = resolve_image(d, c.beat)
    clip = _clip(path) if path else None
    if clip is None or not clip.ok():           # missing/unreadable footage: clean caption card, never a blank frame
        v_text(c, {"text": d.get("caption", "")})
        return
    src = clip.frame(float(d.get("start", 0)) + c.t)
    if src is None:
        v_text(c, {"text": d.get("caption", "")})
        return
    sh, sw = src.shape[:2]
    zoom = 1.04 + 0.05 * (c.t / max(c.dur, 0.1))             # slow push-in keeps stock footage feeling shot, not pasted
    cw, ch = sw / zoom, sh / zoom
    if cw / ch > W / H:                                       # cover-fit to 16:9
        cw = ch * W / H
    else:
        ch = cw * H / W
    x0, y0 = (sw - cw) / 2, (sh - ch) / 2
    s = W / cw
    M = np.array([[s, 0, -x0 * s], [0, s, -y0 * s]], np.float32)
    out = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    out = _grade(out)
    vig, bot = _vignette()
    cv2.multiply(out, vig, dst=out, scale=1 / 255.0)
    cv2.multiply(out, bot, dst=out, scale=1 / 255.0)
    a = ease_out(seg(c.t, 0, 0.3))
    cv2.addWeighted(out, a, c.f, 1 - a, 0, dst=c.f)
    cap = d.get("caption", "")
    if cap:
        w = min(1500, measure(cap, "semi", 40) + 90)
        la = ease_out(seg(c.t, 0.25, 0.8))
        panel(c.f, LM, 840 + (1 - la) * 24, LM + w, 920 + (1 - la) * 24, 14, fill=(14, 17, 23), fill_a=0.82, alpha=la)
        rect(c.f, LM, 840 + (1 - la) * 24, LM + 8, 920 + (1 - la) * 24, RED, la)
        text(c.f, cap, LM + 44, 880 + (1 - la) * 24, "semi", 40, TEXT, "l", la)
    if d.get("credit"):
        text(c.f, d["credit"], RM, 1038, "reg", 19, SOFT, "r", 0.8)


def v_endscreen(c, d):
    spot(c.f, 960, 540, 1100, 560, COOL, 0.07)
    a = ease_out(seg(c.p, 0, 0.4))
    text(c.f, d.get("text", "Keep watching"), 960, 170, "bold", 64, TEXT, "c", a)
    for i, (x0, lab) in enumerate(((220, "Next video"), (1010, "More case studies"))):
        la = ease_out(seg(c.p, 0.15 + 0.15 * i, 0.5 + 0.15 * i))
        glow = 0.2 + 0.2 * c.pulse
        panel(c.f, x0, 290, x0 + 690, 290 + 388, 16, fill=(24, 28, 37), fill_a=0.8,
              stroke=mix(GREY, RED, glow), sw=3, alpha=la)
        text(c.f, lab.upper(), x0 + 345, 740, "semi", 26, SOFT, "c", la, track=5)


VISUALS = {"title": v_title, "text": v_text, "stat": v_stat, "bars": v_bars, "line": v_line, "gauge": v_gauge,
           "flow": v_flow, "layer": v_layer, "table": v_table, "timeline": v_timeline, "quote": v_quote,
           "units": v_units, "stack": v_stack, "image": v_image, "clip": v_clip, "endscreen": v_endscreen}


# ------------------------------------------------------------------ overlays
@lru_cache(maxsize=1)
def _logo():
    p = BRAND_DIR / "logo.png"
    if not p.is_file():
        return None
    im = Image.open(p).convert("RGBA")
    h = S(46)
    im = im.resize((max(1, int(im.width * h / im.height)), h), Image.LANCZOS)
    from fx import Layer
    return Layer(np.asarray(im))


def overlays(c, beat, d):
    f, t = c.f, c.t
    ch = beat.get("chapter")
    if ch:
        a = ease_out(seg(t, 0, 0.35)) * (1 - ease_out(seg(t, 3.0, 3.6)))
        rect(f, LM, 62, LM + 12, 86, RED, a)
        text(f, ch.upper(), LM + 30, 74, "semi", 22, SOFT, "l", a, track=5)
    lg = _logo()
    if lg is not None:
        blit(f, lg, S(RM) - lg.w, S(52), 0.55)
    elif CHANNEL_NAME:
        text(f, CHANNEL_NAME.upper(), RM, 74, "semi", 22, SOFT, "r", 0.55, track=4)
    if d.get("illustrative") or d.get("stock"):
        lab = "STOCK FOOTAGE" if d.get("stock") == "video" else ("ILLUSTRATIVE IMAGE" if d.get("stock") else "ILLUSTRATIVE EXAMPLE")
        lw = measure(lab, "semi", 18, track=2) + 34
        panel(f, RM - lw, 108, RM, 146, 8, fill=(14, 17, 23), fill_a=0.78, stroke=RED, sw=2)
        text(f, lab, RM - lw / 2, 127, "semi", 18, RED, "c", track=2)
    if d.get("source"):
        text(f, f"Source: {d['source']}", LM, 1038, "reg", 19, SOFT, "l", ease_out(seg(t, 0.4, 0.9)))
    text(f, DISCLAIMER, RM, 1038, "reg", 17, (92, 99, 114), "r")


def draw_visual(c, visual):
    d = visual.get("data") or {}
    fn = VISUALS.get(visual.get("type", "text"), v_text)
    if fn is v_clip and not d.get("own"):       # stock footage is always labelled; "own": true for footage you shot
        d = {**d, "stock": "video"}
    fn(c, d)
    overlays(c, c.beat, d)
