"""Animated background shared by every beat (continuous across cuts).

static base : slate vignette + faint grid + dither (built once)
animated    : drifting light, floating particles and a faint scrolling "market
              line" - drawn into a tiny 1/8-size buffer, upscaled and added.
"""
import math

import cv2
import numpy as np

from config import H, HOT_ACTS, PALETTE, W

LW, LH = 480, 270          # low-res light buffer
GRID_U = 120               # grid spacing in design units (1920 wide)


class Background:
    def __init__(self):
        self.base = self._build_base()
        rng = np.random.default_rng(7)
        n = 70
        self.px = rng.uniform(0, LW, n)
        self.py = rng.uniform(0, LH, n)
        self.vx = rng.uniform(-0.5, 0.5, n)
        self.vy = rng.uniform(-3.2, -0.8, n)
        self.pr = rng.choice([0.6, 0.8, 1.0, 1.3, 1.7], n)
        self.pi = rng.uniform(14, 52, n)
        self.pph = rng.uniform(0, 6.28, n)
        self.pw = rng.uniform(0.4, 1.4, n)
        self.hot_part = rng.random(n) < 0.35
        # ambient "price chart": random walk, scrolls sideways
        steps = rng.normal(0, 1, 1400)
        self.walk = np.cumsum(steps)
        self.walk = (self.walk - self.walk.mean()) / (self.walk.std() + 1e-6)
        self.trend = np.linspace(0, 1, 1400)
        yy, xx = np.mgrid[0:LH, 0:LW].astype(np.float32)
        d = np.sqrt(((xx - LW * 0.5) / (LW * 0.62)) ** 2 + ((yy - LH * 0.42) / (LH * 0.7)) ** 2)
        self.glow = (np.clip(1 - d, 0, 1) ** 2).astype(np.float32)

    def _build_base(self):
        lw, lh = 960, 540
        yy, xx = np.mgrid[0:lh, 0:lw].astype(np.float32)
        d = np.sqrt(((xx - lw * 0.5) / (lw * 0.5)) ** 2 + ((yy - lh * 0.46) / (lh * 0.5)) ** 2)
        t = np.clip(d / 1.42, 0, 1)[..., None] ** 1.35
        c0 = np.array(PALETTE["bg"], np.float32)
        c1 = np.array(PALETTE["bg_edge"], np.float32)
        small = c0 * (1 - t) + c1 * t
        base = cv2.resize(small, (W, H), interpolation=cv2.INTER_CUBIC)
        # faint grid
        step = max(2, int(round(GRID_U * W / 1920.0)))
        lw_px = max(1, int(round(W / 1920.0)))
        fade = 1.0 - 0.75 * np.clip(cv2.resize(d, (W, H), interpolation=cv2.INTER_LINEAR) / 1.3, 0, 1)
        grid = np.zeros((H, W), np.float32)
        for x in range(step, W, step):
            grid[:, x:x + lw_px] = 1
        for y in range(step, H, step):
            grid[y:y + lw_px, :] = 1
        base += (grid * fade * 5.5)[..., None]
        # dither (kills 8-bit banding in the gradient)
        rng = np.random.default_rng(3)
        base += rng.uniform(-1.4, 1.4, (H, W, 1)).astype(np.float32)
        return np.clip(base, 0, 255).astype(np.uint8)

    def render(self, act, t):
        hot = act in HOT_ACTS
        lo = np.zeros((LH, LW, 3), np.float32)
        # breathing light
        pulse = 0.88 + 0.12 * math.sin(t * 0.7)
        tint = np.array((224, 49, 49) if hot else PALETTE["cool"], np.float32) / 255.0
        lo += self.glow[..., None] * (tint * (46 if hot else 52) * pulse)
        # particles
        lo8 = np.clip(lo, 0, 255).astype(np.uint8)
        x = (self.px + self.vx * t) % LW
        y = (self.py + self.vy * t) % LH
        tw = 0.65 + 0.35 * np.sin(t * self.pw + self.pph)
        for i in range(len(x)):
            v = self.pi[i] * tw[i]
            col = (v, v * 0.35, v * 0.35) if (hot and self.hot_part[i]) else (v, v, v * 1.05)
            cv2.circle(lo8, (int(x[i] * 4), int(y[i] * 4)), int(self.pr[i] * 4), col, -1, cv2.LINE_AA, 2)
        # ambient chart line (rising when calm, falling when hot)
        n = LW + 4
        off = int(t * 5) % 700
        w = self.walk[off:off + n]
        tr = (1 - self.trend[:n]) if hot else self.trend[:n]
        yv = LH * 0.93 - (tr * 0.5 + 0.12 * w) * LH * 0.30
        pts = np.stack([np.arange(n) * 4, yv * 4], axis=1).astype(np.int32)
        cv2.polylines(lo8, [pts], False, (104, 30, 30) if hot else (58, 66, 82), 1, cv2.LINE_AA, 2)
        up = cv2.resize(lo8, (W, H), interpolation=cv2.INTER_LINEAR)
        frame = self.base.copy()
        cv2.add(frame, up, dst=frame)
        return frame
