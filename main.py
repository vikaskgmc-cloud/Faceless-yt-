"""CLI for the faceless-channel pipeline (20-25 minute videos, 4K).

  python main.py new <slug> --topic "..."   create a project folder
  python main.py facts <slug>               extract facts from sources/*.txt
  python main.py verify <slug>              YOU check each fact against its source
  python main.py script <slug> [--minutes 22]   (20-25)
  python main.py approve <slug>             YOU read and approve the script
  python main.py voice <slug>               narration audio + real timings
  python main.py check <slug>               does it land in 20-25 min?
  python main.py render <slug> [--force]    video.mp4 + description.txt (chapters, sources)
  python main.py auto <slug>               research -> claims -> cross-checks -> script -> shot list
  python main.py produce <slug>            voice + render after approval
  python main.py demo                       short offline test of every visual + audio
"""
import argparse
from pathlib import Path

from config import PROJECTS, MIN_SECONDS, MAX_SECONDS
from models import Scene, load_json, save_json, scenes_from, scenes_to_dicts


def proj(slug) -> Path:
    p = PROJECTS / slug
    if not p.exists():
        raise SystemExit(f"No such project: {slug}. Run: python main.py new {slug}")
    return p


def cmd_new(a):
    p = PROJECTS / a.slug
    (p / "sources").mkdir(parents=True, exist_ok=True)
    save_json({"topic": a.topic or a.slug}, p / "meta.json")
    print(f"Created {p}. Add sources as {p / 'sources'}/*.txt "
          f"(first line 'URL: https://...'), then run: python main.py facts {a.slug}")


def cmd_facts(a):
    from research import extract_facts
    extract_facts(proj(a.slug))


def cmd_verify(a):
    from research import verify_facts
    verify_facts(proj(a.slug))


def cmd_script(a):
    from script import write_script
    p = proj(a.slug)
    write_script(p, load_json(p / "meta.json")["topic"], a.minutes)


def cmd_approve(a):
    from script import approve_script
    approve_script(proj(a.slug))


def _load_approved(p):
    data = load_json(p / "script.json")
    if not data.get("approved"):
        raise SystemExit("Script not approved. Run the approve step first.")
    return data


def cmd_voice(a):
    from voice import synth_scenes
    from report import timing_report
    p = proj(a.slug)
    data = _load_approved(p)
    scenes = synth_scenes(scenes_from(data["scenes"]), p / "audio")
    data["scenes"] = scenes_to_dicts(scenes)
    save_json(data, p / "script.json")
    timing_report(scenes)


def _timed_scenes(p):
    data = _load_approved(p)
    scenes = scenes_from(data["scenes"])
    if any(s.duration is None for s in scenes):
        raise SystemExit("Run the voice step first.")
    return data, scenes


def cmd_check(a):
    from report import timing_report
    _, scenes = _timed_scenes(proj(a.slug))
    timing_report(scenes)


def cmd_render(a):
    from assemble import build_video
    from report import timing_report
    p = proj(a.slug)
    data, scenes = _timed_scenes(p)
    total, ok, _ = timing_report(scenes)
    if not ok and not a.force:
        raise SystemExit(f"\nVideo is {int(total // 60)}:{int(total % 60):02d}; the target is "
                         f"{MIN_SECONDS // 60}-{MAX_SECONDS // 60} minutes. Fix the script "
                         f"(re-run `script` with a different --minutes or add facts) or use --force.")
    build_video(scenes, p / "video.mp4", title=data.get("title", a.slug))


def cmd_auto(a):
    """research -> claims -> cross-checks -> script -> shot list; then wait for the owner's review"""
    import pipeline
    p = proj(a.slug)
    pipeline.research_and_draft(p, a.minutes)
    print("Open the Review screen to approve. Nothing is voiced or rendered until you do.")


def cmd_produce(a):
    """voice + render in one go (refuses unless the script is approved)"""
    import argparse
    cmd_voice(a)
    cmd_render(argparse.Namespace(slug=a.slug, force=False))


def cmd_demo(a):
    from assemble import build_video
    from demo_content import DEMO
    from report import timing_report
    from voice import synth_scenes
    p = PROJECTS / "demo"
    p.mkdir(parents=True, exist_ok=True)
    (p / "media").mkdir(exist_ok=True)
    if not (p / "media" / "demo_clip.mp4").exists():     # synthetic moving footage so the demo shows a real video clip
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                        "mandelbrot=size=1280x720:rate=24,hue=h=t*20", "-t", "8", "-pix_fmt", "yuv420p",
                        str(p / "media" / "demo_clip.mp4")], check=True)
    scenes = [Scene(i, act, nar, vis, [], pace, chapter="Demo" if i == 1 else "")
              for i, (act, pace, nar, vis) in enumerate(DEMO, 1)]
    scenes = synth_scenes(scenes, p / "audio")
    timing_report(scenes)
    build_video(scenes, p / "video.mp4", title="Demo")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("new", cmd_new), ("facts", cmd_facts), ("verify", cmd_verify),
                     ("script", cmd_script), ("approve", cmd_approve), ("voice", cmd_voice),
                     ("check", cmd_check), ("render", cmd_render), ("demo", cmd_demo),
                     ("auto", cmd_auto), ("produce", cmd_produce)]:
        sp = sub.add_parser(name)
        if name != "demo":
            sp.add_argument("slug")
        if name == "new":
            sp.add_argument("--topic")
        if name == "auto":
            sp.add_argument("--minutes", type=int, default=22, choices=range(20, 26), metavar="20-25")
        if name == "script":
            sp.add_argument("--minutes", type=int, default=22, choices=range(20, 26),
                            metavar="20-25")
        if name == "render":
            sp.add_argument("--force", action="store_true")
        sp.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
