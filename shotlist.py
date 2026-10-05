"""Shot list: a production sheet for every visual in the script (what is on screen, when, which sound,
which music, which assets are needed). Works from an estimate before voice and from real timings after it.
Writes shotlist.json, shotlist.csv and shotlist.md in the project folder."""
import csv
import io
import json
from pathlib import Path

from audio import ALWAYS_SFX_TYPES, DEFAULT_SFX, find_tracks
from config import ACT_TITLES, END_SCREEN_SECONDS, MAX_BEAT, DEFAULT_MAX_BEAT, MUSIC_DIR
from models import est_seconds, load_json


def _mmss(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def _summary(v):
    d = v.get("data") or {}
    t = v.get("type")
    pick = {"title": d.get("text"), "text": d.get("text"), "stat": f"{d.get('prefix', '')}{d.get('value', '')}{d.get('suffix', '')} {d.get('label', '')}",
            "bars": d.get("title"), "line": d.get("title"), "flow": " -> ".join(map(str, d.get("nodes", []))),
            "table": d.get("title"), "layer": f"Layer {d.get('number', '')}: {d.get('title', '')}", "timeline": d.get("title"),
            "gauge": d.get("title"), "units": d.get("title"), "stack": d.get("title"),
            "quote": f"\"{d.get('quote', '')}\" - {d.get('source', '')}",
            "clip": f"[stock footage] {d.get('query') or d.get('file', '')} - {d.get('caption', '')}", "image": f"{d.get('file', '')} {d.get('caption', '')}"}
    return str(pick.get(t) or "").replace("*", "").strip()[:140]


def build(project: Path):
    data = load_json(project / "script.json")
    scenes = data["scenes"]
    tracks = find_tracks(MUSIC_DIR)
    media = {p.name for p in (project / "media").iterdir()} if (project / "media").is_dir() else set()
    timed = all(s.get("duration") for s in scenes)
    rows, t = [], 0.0
    for s in scenes:
        dur = s["duration"] if timed else est_seconds(s["narration"], s.get("pace", "normal")) + 0.35
        vis = s.get("visuals") or [{"type": "text", "data": {"text": s["narration"][:80]}}]
        beat = dur / len(vis)
        for j, v in enumerate(vis):
            sfx = v.get("sfx") or (DEFAULT_SFX.get(v.get("type", "text"))
                                   if (j == 0 or v.get("type") in ALWAYS_SFX_TYPES) else None)
            d = v.get("data") or {}
            need = []
            if v.get("type") == "clip":
                need.append(f"clip {d.get('file') or d.get('query')}" + ("" if d.get("file") in media or d.get("file") else " MISSING"))
            if v.get("type") == "image":
                need.append(f"image {d.get('file')}" + ("" if d.get("file") in media else " MISSING"))
            music = tracks.get(s["act"]) or tracks.get("default")
            rows.append({"shot": len(rows) + 1, "scene": s["id"], "act": ACT_TITLES.get(s["act"], s["act"]),
                         "start": _mmss(t + j * beat), "start_s": round(t + j * beat, 1), "seconds": round(beat, 1),
                         "visual": v.get("type"), "on_screen": _summary(v), "narration": s["narration"] if j == 0 else "",
                         "sfx": (sfx if sfx and sfx != "none" else ""), "music": music.name if music else "NONE (add a licensed track)",
                         "source_credit": d.get("source", ""), "illustrative": bool(d.get("illustrative")),
                         "fact_ids": ",".join(s.get("fact_ids", [])) if j == 0 else "", "assets_needed": "; ".join(need),
                         "too_long": beat > MAX_BEAT.get(s["act"], DEFAULT_MAX_BEAT)})
        t += dur
    rows.append({"shot": len(rows) + 1, "scene": 0, "act": "End screen", "start": _mmss(t), "start_s": round(t, 1),
                 "seconds": END_SCREEN_SECONDS, "visual": "endscreen", "on_screen": "Next video / more case studies slots",
                 "narration": "", "sfx": "", "music": "", "source_credit": "", "illustrative": False, "fact_ids": "",
                 "assets_needed": "", "too_long": False})
    total = t + END_SCREEN_SECONDS
    kinds = {}
    for r in rows:
        kinds[r["visual"]] = kinds.get(r["visual"], 0) + 1
    summary = {"shots": len(rows), "length": _mmss(total), "seconds": round(total), "timed": timed,
               "visual_types": kinds, "too_long": sum(r["too_long"] for r in rows),
               "missing_assets": [r["assets_needed"] for r in rows if "MISSING" in r["assets_needed"]],
               "no_music_tracks": not tracks, "text_only_shots": sum(r["visual"] in ("text", "title") for r in rows)}
    (project / "shotlist.json").write_text(json.dumps({"summary": summary, "shots": rows}, indent=2, ensure_ascii=False), encoding="utf-8")
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    (project / "shotlist.csv").write_text(buf.getvalue(), encoding="utf-8")
    md = [f"# Shot list - {data.get('title', project.name)}", "",
          f"{summary['shots']} shots, {summary['length']} ({'real voice timings' if timed else 'estimated timings'})", "",
          "| # | Time | Act | Visual | On screen | SFX | Facts |", "|---|---|---|---|---|---|---|"]
    md += [f"| {r['shot']} | {r['start']} | {r['act']} | {r['visual']} | {r['on_screen'].replace('|', '/')} | {r['sfx']} | {r['fact_ids']} |"
           for r in rows]
    (project / "shotlist.md").write_text("\n".join(md), encoding="utf-8")
    return summary
