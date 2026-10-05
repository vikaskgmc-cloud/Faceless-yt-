"""Stage 3: voiceover with edge-tts (cached; falls back to estimated timing)."""
import asyncio
import hashlib
from pathlib import Path

from audio import decode
from config import VOICE, SR, SCENE_TAIL, TTS_ENGINE
from models import est_seconds

RATE = {"slow": "-15%", "normal": "+0%", "fast": "+12%"}  # slow on stats, fast in the collapse


async def _synth(text: str, path: Path, rate: str):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate=rate).save(str(path))


async def _run(scenes, outdir: Path, concurrency=4):
    sem = asyncio.Semaphore(concurrency)

    async def one(s):
        key = hashlib.md5(f"{VOICE}|{s.pace}|{s.narration}".encode()).hexdigest()[:8]
        path = outdir / f"{s.id:03d}_{key}.mp3"
        if not path.exists():
            async with sem:
                try:
                    await _synth(s.narration, path, RATE.get(s.pace, "+0%"))
                except Exception as e:
                    path.unlink(missing_ok=True)
                    print(f"! scene {s.id}: TTS failed ({type(e).__name__}); using estimated timing")
                    s.audio_path = None
                    s.duration = max(2.5, est_seconds(s.narration, s.pace) + SCENE_TAIL)
                    return
        s.audio_path = str(path)
        s.duration = len(decode(path, 1)) / SR + SCENE_TAIL

    await asyncio.gather(*(one(s) for s in scenes))


def _test_voice(scenes, outdir: Path):
    """offline robot voice (flite) - development only"""
    import subprocess
    for s in scenes:
        path = outdir / f"{s.id:03d}_test.wav"
        if not path.exists():
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                            "flite=text='" + s.narration.replace("'", "") + "'", str(path)], check=True)
        s.audio_path = str(path)
        s.duration = len(decode(path, 1)) / SR + SCENE_TAIL


def synth_scenes(scenes, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)
    if TTS_ENGINE == "test":
        _test_voice(scenes, outdir)
        return scenes
    asyncio.run(_run(scenes, outdir))
    missing = [s.id for s in scenes if not s.audio_path]
    if missing:   # never produce a silent video
        raise SystemExit(f"Voice failed for scenes {missing}. Check your internet connection and re-run the voice step.")
    return scenes
