"""Timing report: does the video land in 20-25 minutes, and is every visual
cut fast enough?"""
from collections import defaultdict

from audio import plan
from config import (MIN_SECONDS, MAX_SECONDS, ACT_SHARE, ACT_TITLES,
                    MAX_BEAT, DEFAULT_MAX_BEAT)


def _mmss(t):
    return f"{int(t) // 60}:{int(t) % 60:02d}"


def timing_report(scenes):
    """Prints the report; returns (total_seconds, in_window, slow_scene_ids)."""
    _, content_end, total = plan(scenes)
    by_act = defaultdict(float)
    for s in scenes:
        by_act[s.act] += s.duration
    print("\nTiming report")
    for act, share in ACT_SHARE.items():
        got = by_act.get(act, 0.0)
        print(f"  {ACT_TITLES[act]:<30} {_mmss(got):>6}   (plan {share * 100:.0f}% = "
              f"{_mmss(share * (total))})")
    slow = []
    for s in scenes:
        beat = s.duration / max(1, len(s.visuals))
        if beat > MAX_BEAT.get(s.act, DEFAULT_MAX_BEAT):
            slow.append(s.id)
    ok = MIN_SECONDS <= total <= MAX_SECONDS
    print(f"  Total incl. end screen: {_mmss(total)}  -> "
          f"{'OK (20-25 min)' if ok else 'OUTSIDE the 20-25 min window'}")
    if slow:
        shown = ", ".join(map(str, slow[:15])) + (" ..." if len(slow) > 15 else "")
        print(f"  ! {len(slow)} scenes keep one visual on screen too long "
              f"(add visuals/beats): {shown}")
    return total, ok, slow
