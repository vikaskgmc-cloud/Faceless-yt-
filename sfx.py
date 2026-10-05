"""Procedurally generated sound effects (original, so no licensing issues).

whoosh   - text/graphic pops
riser    - tension build into chapter transitions
sub_drop - low impact on key stats and the opening
impact   - hard hit for titles and layer cards
tick     - clock tick (collapse act bed, timelines)
beep     - digital error beep
"""
import numpy as np

from config import SR

SFX_GAIN = {"whoosh": 0.20, "riser": 0.30, "sub_drop": 0.55,
            "impact": 0.45, "tick": 0.14, "beep": 0.18}

_cache = {}


def _lp_sweep(x, f0, f1):
    """One-pole low-pass whose cutoff sweeps geometrically from f0 to f1."""
    n = len(x)
    f = np.geomspace(f0, f1, n)
    a = 1 - np.exp(-2 * np.pi * f / SR)
    xs = x.astype(np.float64)
    out = np.empty(n, dtype=np.float32)
    y = 0.0
    for i in range(n):
        y += a[i] * (xs[i] - y)
        out[i] = y
    return out


def _norm(x):
    p = float(np.max(np.abs(x)))
    return (x / p).astype(np.float32) if p > 0 else x.astype(np.float32)


def _make(name):
    rng = np.random.default_rng(11)
    if name == "whoosh":
        n = int(0.6 * SR)
        t = np.arange(n) / SR
        y = _lp_sweep(rng.standard_normal(n), 300, 9000)
        return _norm(y * np.sin(np.pi * (t / 0.6) ** 0.8) ** 2)
    if name == "sub_drop":
        n = int(1.6 * SR)
        t = np.arange(n) / SR
        ph = 2 * np.pi * np.cumsum(28 + 70 * np.exp(-3.5 * t)) / SR
        y = np.sin(ph) * np.exp(-2.0 * t)
        y = y + 0.3 * _lp_sweep(rng.standard_normal(n) * np.exp(-t / 0.01), 2000, 2000)
        return _norm(y)
    if name == "impact":
        n = int(1.0 * SR)
        t = np.arange(n) / SR
        burst = _lp_sweep(rng.standard_normal(n), 3000, 3000) * np.exp(-8 * t)
        thud = np.sin(2 * np.pi * 50 * t) * np.exp(-3.5 * t)
        return _norm(0.7 * burst + thud)
    if name == "riser":
        n = int(1.5 * SR)
        t = np.arange(n) / SR
        u = t / 1.5
        noise = _lp_sweep(rng.standard_normal(n), 200, 9000) * u ** 2
        ph = 2 * np.pi * np.cumsum(180 * (1600 / 180) ** u) / SR
        y = _norm(noise) + 0.35 * np.sin(ph) * u ** 2
        y[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
        return _norm(y)
    if name == "tick":
        n = int(0.06 * SR)
        t = np.arange(n) / SR
        click = np.diff(rng.standard_normal(n + 1)) * np.exp(-t / 0.003)
        tone = 0.6 * np.sin(2 * np.pi * 1800 * t) * np.exp(-t / 0.006)
        return _norm(click / (np.max(np.abs(click)) + 1e-9) + tone)
    if name == "beep":
        n = int(0.35 * SR)
        y = np.zeros(n)
        for start in (0.0, 0.17):
            m = int(0.1 * SR)
            tt = np.arange(m) / SR
            env = np.minimum(1, np.minimum(tt / 0.005, (0.1 - tt) / 0.005))
            i = int(start * SR)
            y[i:i + m] += np.sin(2 * np.pi * 880 * tt) * env
        return _norm(y)
    raise KeyError(name)


def sfx_wave(name):
    """Mono float32 array at SR, peak-normalised, scaled by the effect's gain."""
    if name not in _cache:
        _cache[name] = _make(name) * SFX_GAIN[name]
    return _cache[name]
