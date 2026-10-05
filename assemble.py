"""Video assembly: pipes raw frames straight into ffmpeg (no moviepy) with the
mixed, loudness-normalised audio track. Also writes chapters + description."""
import json
import subprocess
from pathlib import Path

from audio import plan, mix_audio, loudnorm
from config import ACT_TITLES, BROLL_DIR, DISCLAIMER, MUSIC_DIR
from models import facts_from, load_json


def _fmt_ts(t):
    t = int(t)
    return f"{t // 60}:{t % 60:02d}"


def write_description(out_dir: Path, title, scenes, starts, music_used):
    lines = [title, "", DISCLAIMER, "", "Chapters:"]
    seen = None
    for s, t0 in zip(scenes, starts):
        if s.act != seen:
            seen = s.act
            lines.append(f"{_fmt_ts(t0)} {ACT_TITLES.get(s.act, s.act)}")
    facts_file = out_dir / "facts.json"
    if facts_file.exists():
        used = {fid for s in scenes for fid in s.fact_ids}
        urls = sorted({f.source_url for f in facts_from(load_json(facts_file)) if f.id in used})
        if urls:
            lines += ["", "Sources:"] + urls
    cred = out_dir / "media" / "credits.json"
    if cred.exists():
        used = {v.get("data", {}).get("file") for s in scenes for v in s.visuals}
        lines_c = sorted({c["credit"] for n, c in json.loads(cred.read_text()).items() if n in used})
        if lines_c:
            lines += ["", "Stock footage: " + "; ".join(lines_c)]
    if music_used:
        lines += ["", "Music: " + ", ".join(music_used) + " (add the credit your license requires)"]
    (out_dir / "description.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_video(scenes, out: Path, title="Video", music_dir=MUSIC_DIR, progress=None):
    """audio mix -> parallel chunk render -> lossless concat + mux. Resumable."""
    import engine
    out = Path(out)
    work = out.parent
    progress = progress or (lambda pct, msg: print(f"  {pct:5.1f}%  {msg}", flush=True))
    starts, content_end, total = plan(scenes)

    print("Mixing audio...", flush=True)
    mixed, norm = work / "mix.wav", work / "mix_norm.wav"
    music_used, had_music = mix_audio(scenes, mixed, music_dir)
    if not had_music:
        print(f"! No music found in {music_dir} - voice and sound effects only", flush=True)
    loudnorm(mixed, norm)

    beats = engine.make_beats(scenes, starts, content_end, work / "media", BROLL_DIR)
    chunks = engine.render_chunks(beats, work, progress)
    engine.concat_mux(chunks, norm, out, work)
    write_description(work, title, scenes, starts, music_used)
    # thumbnail: a frame from the end of the cold open (the title card), 1280x720 JPEG
    t_thumb = max(1.0, next((t0 for s, t0 in zip(scenes, starts) if s.act != "cold_open"), 6.0) - 1.0)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t_thumb:.2f}", "-i", str(out), "-frames:v", "1",
                    "-vf", "scale=1280:720", "-q:v", "2", str(work / "thumbnail.jpg")])
    print(f"Saved {out} ({_fmt_ts(total)}) + description.txt", flush=True)
    return out
