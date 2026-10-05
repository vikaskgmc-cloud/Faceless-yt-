"""Parallel, resumable video renderer.

The timeline is cut into ~16 s chunks. A pool of worker processes renders each
chunk straight into its own ffmpeg (H.264) process; finished chunks are
concatenated losslessly and muxed with the mixed audio. If a render is
interrupted, re-running skips chunks that are already finished.
"""
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from pathlib import Path

from config import (CPU, CRF, ENGINE_VERSION, END_SCREEN_SECONDS, FPS, H, PRESET, QUALITY, SEGMENT_SECONDS, W,
                    WORKERS)

_STATE = {}


def make_beats(scenes, starts, content_end, media_dir, broll_dir):
    """One beat per visual; each scene's duration is split evenly between its visuals."""
    beats, idx = [], 0
    for s, t0 in zip(scenes, starts):
        vis = s.visuals or [{"type": "text", "data": {"text": s.narration[:80]}}]
        d = s.duration / len(vis)
        for j, v in enumerate(vis):
            beats.append({"start": t0 + j * d, "dur": d, "visual": v, "act": s.act, "idx": idx,
                          "chapter": s.chapter if j == 0 else "", "media_dir": str(media_dir),
                          "broll_dir": str(broll_dir)})
            idx += 1
    beats.append({"start": content_end, "dur": float(END_SCREEN_SECONDS),
                  "visual": {"type": "endscreen", "data": {}}, "act": "outro", "idx": idx, "chapter": "",
                  "media_dir": str(media_dir), "broll_dir": str(broll_dir)})
    return beats


def split_segments(beats):
    """group beats into chunks of roughly SEGMENT_SECONDS; frame ranges are contiguous"""
    segs, cur, t0 = [], [], beats[0]["start"]
    for b in beats:
        cur.append(b)
        if b["start"] + b["dur"] - t0 >= SEGMENT_SECONDS:
            segs.append(cur)
            cur, t0 = [], b["start"] + b["dur"]
    if cur:
        segs.append(cur)
    return segs


def frame_range(beat):
    return round(beat["start"] * FPS), round((beat["start"] + beat["dur"]) * FPS)


def _seg_hash(beats):
    raw = json.dumps([beats, ENGINE_VERSION, W, H, FPS, CRF, PRESET], sort_keys=True, default=str)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _ffmpeg_cmd(out, threads):
    return ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
            "-r", str(FPS), "-i", "-",
            "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
            "-c:v", "libx264", "-preset", PRESET, "-crf", str(CRF), "-tune", "animation",
            "-g", str(FPS * 2), "-keyint_min", str(FPS * 2), "-sc_threshold", "0",
            "-threads", str(threads), "-colorspace", "bt709", "-color_primaries", "bt709",
            "-color_trc", "bt709", "-an", str(out)]


def _init():
    from bg import Background
    _STATE["bg"] = Background()


def render_segment(job):
    """worker: render one chunk to job['out']; returns (index, frames, seconds)"""
    from visuals import Ctx, draw_visual
    t_start = time.time()
    out, beats, threads = Path(job["out"]), job["beats"], job["threads"]
    marker = out.with_suffix(".done")
    h = _seg_hash(beats)
    if marker.exists() and marker.read_text() == h and out.exists() and out.stat().st_size > 0:
        f0, f1 = frame_range(beats[0])[0], frame_range(beats[-1])[1]
        return job["index"], f1 - f0, 0.0, True
    marker.unlink(missing_ok=True)
    if "bg" not in _STATE:
        _init()
    bg = _STATE["bg"]
    proc = subprocess.Popen(_ffmpeg_cmd(out, threads), stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = 0
    try:
        for b in beats:
            f0, f1 = frame_range(b)
            for fi in range(f0, f1):
                gt = fi / FPS
                t = gt - b["start"]
                frame = bg.render(b["act"], gt)
                draw_visual(Ctx(frame, b["act"], max(0.0, t), b["dur"], gt, b), b["visual"])
                proc.stdin.write(memoryview(frame))
                frames += 1
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        rc = proc.wait()
    except BrokenPipeError:
        err = proc.stderr.read().decode(errors="replace")
        rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg failed on chunk {job['index']}: {err[-600:]}")
    marker.write_text(h)
    return job["index"], frames, time.time() - t_start, False


def render_chunks(beats, work_dir, progress):
    segs = split_segments(beats)
    seg_dir = Path(work_dir) / "chunks"
    seg_dir.mkdir(parents=True, exist_ok=True)
    workers = max(1, min(WORKERS, len(segs)))
    threads = max(1, CPU // workers)
    jobs = [{"index": i, "beats": s, "out": str(seg_dir / f"chunk_{i:04d}.mp4"), "threads": threads}
            for i, s in enumerate(segs)]
    total = sum(frame_range(s[-1])[1] - frame_range(s[0])[0] for s in segs)
    done = skipped = 0
    t0 = time.time()
    ctx = mp.get_context("spawn")
    print(f"Rendering {len(segs)} chunks, {total} frames at {W}x{H} {FPS}fps with {workers} worker(s)...", flush=True)
    with ctx.Pool(workers, initializer=_init) as pool:
        for idx, frames, secs, was_cached in pool.imap_unordered(render_segment, jobs):
            done += frames
            skipped += frames if was_cached else 0
            elapsed = time.time() - t0
            rate = (done - skipped) / elapsed if elapsed > 1 and done > skipped else 0
            eta = (total - done) / rate if rate else 0
            progress(100.0 * done / total, f"{done}/{total} frames  ({rate:.1f} fps"
                     f"{f', ~{int(eta // 60)} min left' if rate else ''})")
    return [Path(j["out"]) for j in jobs]


def concat_mux(chunks, audio_wav, out_mp4, work_dir):
    lst = Path(work_dir) / "chunks.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in chunks))
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", str(audio_wav),
           "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-ar", "48000",
           "-movflags", "+faststart", "-shortest", str(out_mp4)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("concat/mux failed: " + r.stderr[-800:])
