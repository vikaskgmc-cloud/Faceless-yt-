"""Audio engine: places narration, sound effects and per-act music on one
timeline, ducks the music under the voice, and writes a stereo WAV.

Music: drop licensed tracks in assets/music/. Name a file after an act
(cold_open.mp3, rise.mp3, flaw.mp3, collapse.mp3, lesson.mp3, outro.mp3) to
use it for that act; default.mp3 (or any other file) is the fallback.
"""
import math
import subprocess
import wave
from pathlib import Path

import numpy as np

from config import (SR, VOICE_LEAD, MUSIC_RMS, MUSIC_UNDER, MUSIC_OPEN,
                    MUSIC_XFADE, MUSIC_DIR, END_SCREEN_SECONDS, TARGET_LUFS)
from sfx import sfx_wave

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}

# Default effect for a visual's first beat (script can override per visual,
# or set "sfx": "none"). Other beats are silent unless they ask for one.
DEFAULT_SFX = {"title": "impact", "text": "whoosh", "stat": "sub_drop", "bars": "whoosh", "line": "whoosh",
               "flow": "whoosh", "table": "whoosh", "layer": "impact", "timeline": "tick", "gauge": "whoosh",
               "units": "whoosh", "stack": "whoosh", "quote": "whoosh", "image": "whoosh"}
ALWAYS_SFX_TYPES = {"stat", "layer", "title"}


def plan(scenes):
    """Start time of every scene, end of content, and total incl. end screen."""
    starts, t = [], 0.0
    for s in scenes:
        starts.append(t)
        t += s.duration
    return starts, t, t + END_SCREEN_SECONDS


def decode(path, channels=1):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "f32le",
         "-ac", str(channels), "-ar", str(SR), "-"],
        capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.float32).copy()
    return a.reshape(-1, channels) if channels > 1 else a


def find_tracks(music_dir=MUSIC_DIR):
    d = Path(music_dir)
    if not d.is_dir():
        return {}
    return {p.stem.lower(): p for p in sorted(d.iterdir())
            if p.suffix.lower() in AUDIO_EXT}


def _loop_to(x, n, xf=2 * SR):
    """Loop a stereo track to n samples with a crossfade at each seam."""
    if len(x) >= n:
        return x[:n]
    if len(x) <= 2 * xf:
        return np.tile(x, (math.ceil(n / len(x)), 1))[:n]
    fade = np.linspace(0, 1, xf, dtype=np.float32)[:, None]
    out = x.copy()
    while len(out) < n:
        out[-xf:] = out[-xf:] * (1 - fade) + x[:xf] * fade
        out = np.concatenate([out, x[xf:]])
    return out[:n]


def _put(bus, wave_, at, gain=1.0):
    i = int(round(at * SR))
    if i < 0:
        wave_, i = wave_[-i:], 0
    m = min(len(wave_), len(bus) - i)
    if m > 0:
        bus[i:i + m] += wave_[:m] * gain


def _dip(env, a, b, ramp=0.15):
    """Fade the music envelope to silence between a and b seconds."""
    i0, i1 = int(max(0, a - ramp) * SR), int(min(len(env) / SR, b + ramp) * SR)
    if i1 <= i0:
        return
    t = np.arange(i1 - i0) / SR + max(0, a - ramp)
    bump = np.clip(np.minimum((t - (a - ramp)) / ramp, ((b + ramp) - t) / ramp), 0, 1)
    env[i0:i1] *= (1 - bump).astype(np.float32)


def segments(scenes, starts, content_end, total):
    segs = []
    for s, t0 in zip(scenes, starts):
        if segs and segs[-1][0] == s.act:
            continue
        segs.append([s.act, t0, None])
    for i, seg in enumerate(segs):
        seg[2] = segs[i + 1][1] if i + 1 < len(segs) else total
    return segs


def mix_audio(scenes, out_wav, music_dir=MUSIC_DIR):
    starts, content_end, total = plan(scenes)
    n = int(total * SR)
    segs = segments(scenes, starts, content_end, total)

    # --- narration bus (mono)
    voice = np.zeros(n, dtype=np.float32)
    for s, t0 in zip(scenes, starts):
        if s.audio_path:
            _put(voice, decode(s.audio_path, 1), t0 + VOICE_LEAD)

    # --- sound-effect bus (mono)
    sfx = np.zeros(n, dtype=np.float32)
    _put(sfx, sfx_wave("sub_drop"), 0.0)
    for s, t0 in zip(scenes, starts):
        vis = s.visuals or [{"type": "text"}]
        beat = s.duration / len(vis)
        for j, v in enumerate(vis):
            name = v.get("sfx") or (DEFAULT_SFX.get(v.get("type", "text"))
                                    if (j == 0 or v.get("type") in ALWAYS_SFX_TYPES) else None)
            if name and name != "none":
                _put(sfx, sfx_wave(name), t0 + j * beat)
    for k, (act, a, _) in enumerate(segs):
        if k == 0:
            continue
        _put(sfx, sfx_wave("riser"), a - 1.4)
        _put(sfx, sfx_wave("sub_drop" if segs[k - 1][0] == "cold_open" else "impact"), a)
        if act == "collapse":  # ticking-clock bed at 120 BPM under the collapse act
            for tt in np.arange(a, segs[k][2], 0.5):
                _put(sfx, sfx_wave("tick"), float(tt), 0.8)

    # --- music bed (stereo), ducked under the voice
    tracks = find_tracks(music_dir)
    music = None
    music_used = []
    if tracks:
        music = np.zeros((n, 2), dtype=np.float32)
        runs = []  # merge consecutive acts that use the same track
        for act, a, b in segs:
            path = tracks.get(act) or tracks.get("default") or next(iter(tracks.values()))
            if runs and runs[-1][0] == path:
                runs[-1][2] = b
            else:
                runs.append([path, a, b])
        cache = {}
        xf = MUSIC_XFADE
        for k, (path, a, b) in enumerate(runs):
            if path not in cache:
                x = decode(path, 2)
                cache[path] = x * (MUSIC_RMS / (float(np.sqrt(np.mean(x ** 2))) + 1e-9))
                music_used.append(path.name)
            a0 = max(0.0, a - xf) if k else 0.0
            b0 = min(total, b + xf) if k < len(runs) - 1 else total
            i0, i1 = int(a0 * SR), int(b0 * SR)
            bed = _loop_to(cache[path], i1 - i0)
            fi = int((xf if k else 2.0) * SR)
            fo = int((xf if k < len(runs) - 1 else 4.0) * SR)
            ramp = np.ones(len(bed), dtype=np.float32)
            ramp[:fi] = np.linspace(0, 1, min(fi, len(bed)), dtype=np.float32)
            ramp[-fo:] = np.minimum(ramp[-fo:], np.linspace(1, 0, min(fo, len(bed)), dtype=np.float32))
            music[i0:i1] += bed * ramp[:, None]

        frame = int(SR * 0.02)
        m = n // frame
        rms = np.sqrt(np.mean(voice[:m * frame].reshape(m, frame) ** 2, axis=1))
        active = (rms > 0.01).astype(np.float32)
        k = int(0.6 / 0.02)
        sm = np.clip(np.convolve(active, np.ones(k) / k, mode="same") * 1.6, 0, 1)
        gain_f = MUSIC_OPEN + (MUSIC_UNDER - MUSIC_OPEN) * sm
        env = np.interp(np.arange(n) / SR, (np.arange(m) + 0.5) * 0.02, gain_f).astype(np.float32)
        for k2 in range(1, len(segs)):  # music drops out right before the cold-open impact
            if segs[k2 - 1][0] == "cold_open":
                _dip(env, segs[k2][1] - 0.7, segs[k2][1] + 0.12)
        music *= env[:, None]

    voice += sfx
    del sfx
    master = music if music is not None else np.zeros((n, 2), dtype=np.float32)
    master += voice[:, None]
    del voice
    peak = float(np.max(np.abs(master)))
    if peak > 0.98:
        master *= 0.98 / peak

    out_wav = Path(out_wav)
    pcm = (master * 32767).astype("<i2")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    return music_used, bool(tracks)


def loudnorm(src, dst):
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-af",
         f"loudnorm=I={TARGET_LUFS}:TP=-1.5:LRA=11", "-ar", str(SR), str(dst)],
        check=True)
