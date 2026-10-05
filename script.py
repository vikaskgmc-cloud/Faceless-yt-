"""Stage 2: write the six-act script (20-25 minutes) from VERIFIED facts only.

One Claude call per act, sized from the Gemini framework's time shares, so a
22-minute script never has to fit in a single response.
"""
import math
import re
from pathlib import Path

from config import (ACT_SHARE, ACT_TITLES, WPS, END_SCREEN_SECONDS, MIN_SECONDS,
                    MAX_SECONDS, MAX_BEAT, DEFAULT_MAX_BEAT, DISCLAIMER)
from llm import ask_json
from models import (Scene, facts_from, scenes_to_dicts, save_json, load_json,
                    est_seconds)

VISUAL_TYPES = {"title", "text", "stat", "bars", "line", "flow", "table", "layer", "timeline",
                "gauge", "units", "stack", "quote", "image", "clip"}
SFX_NAMES = {"whoosh", "riser", "sub_drop", "impact", "tick", "beep", "none"}
BANNED = ["thanks for watching", "like and subscribe", "in conclusion",
          "let me know in the comments", "smash the like", "hit the subscribe"]
GREETING = re.compile(r"^\s*(hi|hello|hey|welcome|today)\b", re.I)

BASE = f"""You write scripts for a faceless finance-EDUCATION YouTube channel (documentary
style, like Magnates Media / ColdFusion). The finished video runs 20-25 minutes.

HARD RULES
- Use ONLY the verified facts provided for anything specific to the case (numbers,
  dates, names, amounts, outcomes). Never invent a figure, quote, message or event.
  Every scene containing case-specific details lists the supporting fact ids in fact_ids.
- If the facts run short, add GENERAL educational explainer scenes (how floating-rate
  loans, interest-rate caps, capital stacks, occupancy break-evens work). Those have
  empty fact_ids and any example numbers must be flagged "illustrative": true in the
  visual's data.
- Attribute claims ("according to court filings", "lenders alleged"). Do not assert
  motives, do not say there was or wasn't fraud. Educational only: no buy/sell advice.
- Never use these phrases anywhere: thanks for watching, like and subscribe, in
  conclusion, let me know in the comments.
- Plain English; short punchy sentences; no greeting; no filler.

PACING (retention)
- Each scene is 1-3 sentences of narration, 14-40 words. Spoken speed is ~{WPS} words/second.
- Each scene lists "visuals": one visual per beat. A visual must stay on screen only
  3-5 seconds (2-3 seconds in cold_open and collapse). So visuals per scene ~=
  round(words / {WPS} / 4); in cold_open and collapse use round(words / {WPS} / 2.7).
- Where a scene is atmosphere or context rather than data, use a "clip" (stock video) so the picture MOVES: about one visual in four in rise, flaw and lesson; never two clips in a row; clips are generic stock footage (the caption must not name or imply the real property, person or event, and has no numbers).
- Vary visual types; never use more than two "text" visuals in a row. Prefer diagrams
  and data over words.
- pace: "slow" for key statistics, "normal", "fast" in cold_open and collapse.

VISUAL TYPES and their "data":
 title:    {{"text"}}
 text:     {{"text"}}                       (short phrase, max ~14 words)
 stat:     {{"label","value":number,"prefix","suffix"}}   (1-2 metric callouts per act)
 bars:     {{"title","unit","prefix","bars":[{{"label","value":number,"color":"red"|"grey"}}]}}
 line:     {{"title","unit","prefix","color":"red"|"white","points":[{{"x","y":number}}]}}  (>=3 points)
 flow:     {{"title","nodes":[up to 5 short strings],"highlight":index}}  (how money moves)
 table:    {{"title","left_header","right_header","rows":[[a,b],...up to 6]}}
 layer:    {{"number":int,"title","text"}}  (numbered concept card)
 timeline: {{"title","events":[{{"when","what"}}...up to 6]}}
 gauge:    {{"title","value":number,"threshold":number,"min","max","label","threshold_label"}}  (e.g. debt-service coverage vs 1.0)
 units:    {{"title","total":int,"affected":int,"label","sub"}}  (dot grid: how many units/investors were hit)
 stack:    {{"title","value_drop":number (% of property value LOST),"layers":[{{"label","share":number,"note"}}]}}  (capital stack, top = equity)
 quote:    {{"label":"According to a court filing","date","quote","highlight","source"}}  (quote must be copied VERBATIM from a fact's quote)
 image:    {{"file":"<one of AVAILABLE MEDIA>","caption"}}  (only if media files are listed; otherwise never use)
 clip:     {{"query":"2-5 word stock-footage search, e.g. apartment building exterior","caption":"generic caption, no numbers"}}  (atmosphere/context video: city, buildings, construction, offices, money, screens; never a claim about the real case)
 Kinetic emphasis: in any "text" or "title" phrase wrap the key word in *asterisks* (it turns red).
Any visual's data may also carry "source": short label for on-screen credit, and
"illustrative": true for example numbers. Each visual may set "sfx" to one of
whoosh|impact|sub_drop|riser|tick|beep|none (sub_drop on key stats, beep on failures,
tick for clocks); leave it out for the default.

OUTPUT: JSON only: {{"title": str (only in cold_open), "scenes": [{{"narration": str,
"pace": str, "fact_ids": [str], "visuals": [{{"type": str, "data": obj, "sfx": str}}]}}]}}
"""

ACT_BRIEF = {
    "cold_open": "COLD OPEN CLIMAX. Drop the audience into the catastrophe at its peak: the outcome, the scale of money lost (from facts), then an information gap. No context, no greeting. Fast cuts. End on an unanswered question. Use stat/bars/text; sub_drop on the first scene; title card with the video topic as the last visual.",
    "rise": "THE ILLUSION OF GENIUS. Show why it looked unstoppable before the collapse: the pitch, the growth, who invested and why it seemed safe. Include 1-2 metric callouts (stat visuals) and, if the facts hold a time series, a line chart.",
    "flaw": "THE HIDDEN FLAW. Explain the mechanism in plain English: floating-rate debt, interest-rate caps, occupancy break-even, capital stack. Use flow diagrams (money moving between investors, the operator, lenders, property) and bars (liabilities in red). Break it into EXACTLY three numbered 'layer' visuals ('Layer 1: ...') spread through the act, each followed by diagrams that prove it.",
    "collapse": "THE DOMINO EFFECT. Accelerate. A timeline of what happened (only events in the facts), then rapid cause-and-effect statements ('Because X, Y had to ..., which forced Z ...'). Fast pace, short visuals, tick and beep sfx. No invented hours, messages or quotes.",
    "lesson": "THE RETAIL LESSON. What a retail investor should learn. Use one 'table' visual (what they did vs the fundamental rule broken), then an actionable general checklist (layer/text visuals). Emphasise the capital-stack point: equity sits below the lender and takes losses first. General education only. The act's FINAL scene must be one calm spoken sentence: "
              + DISCLAIMER,
    "outro": "THE NO-DROP OUTRO. Tie back to the cold open and finish on the philosophical punchline (e.g. a failure of incentives, not intelligence). No goodbye. The very last sentence tells viewers to click the video on screen now. 4-8 scenes only.",
}


def _count_words(scenes):
    return sum(len(s["narration"].split()) for s in scenes)


def _gen_act(act, topic, facts_text, words, prev, extra="", media="(none)"):
    n_scenes = max(3, round(words / 26))
    user = (f"Topic: {topic}\nAct: {act} - {ACT_BRIEF[act]}\n"
            f"Write about {words} narration words (~{n_scenes} scenes).\n\n"
            f"VERIFIED FACTS:\n{facts_text}\n\nAVAILABLE MEDIA: {media}\n\n"
            f"Previous narration (for continuity, do not repeat it):\n{prev or '(none, this is the start)'}\n{extra}")
    return ask_json(BASE + "\n" + ACT_BRIEF[act], user, max_tokens=16000)


NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _nums(text):
    out = set()
    for m in NUM.findall(str(text)):
        try:
            out.add(round(float(m.replace(",", "")), 4))
        except ValueError:
            pass
    return out


def _visual_numbers(v):
    """every number a viewer would SEE in one visual (text, labels, values, chart points, table cells)"""
    out = set()

    def walk(x, key=""):
        if isinstance(x, bool) or key in ("illustrative", "number", "highlight", "index", "min", "max"):
            return          # layer numbers, node indexes and axis bounds are layout, not claims
        if isinstance(x, (int, float)):
            out.add(round(float(x), 4))
        elif isinstance(x, str):
            out.update(_nums(x))
        elif isinstance(x, dict):
            for k, val in x.items():
                walk(val, k)
        elif isinstance(x, list):
            for val in x:
                walk(val, key)
    walk(v.get("data") or {})
    return out


def _supported(n, allowed):
    return any(abs(n - a) <= (0.051 if abs(a) < 100 else 0.5) for a in allowed)   # years and big numbers must match exactly


def _has_numbers(v):
    t, d = v.get("type"), v.get("data") or {}
    if t in ("stat", "bars", "line", "gauge", "units", "stack"):
        return True
    return bool(re.search(r"\d", " ".join(str(x) for x in d.values())))


def validate(scenes, valid_ids, quotes=(), media=(), fact_text=None):
    problems = []
    fact_text = fact_text or {}
    nq = [re.sub(r"\s+", " ", q).strip().lower() for q in quotes]
    for s in scenes:
        bad = [x for x in s.fact_ids if x not in valid_ids]
        if bad:
            problems.append(f"scene {s.id}: unknown/unverified fact ids {bad}")
        if not s.narration.strip():
            problems.append(f"scene {s.id}: empty narration")
        low = s.narration.lower()
        for phrase in BANNED:
            if phrase in low:
                problems.append(f"scene {s.id}: banned phrase '{phrase}'")
        illustrative = any((v.get("data") or {}).get("illustrative") for v in s.visuals)
        if not s.fact_ids and not illustrative and (
                re.search(r"\d", s.narration) or any(_has_numbers(v) for v in s.visuals)):
            problems.append(f"scene {s.id}: numbers with no fact id and not marked illustrative")
        # numbers shown on screen must come from the narration or the cited verified facts
        allowed = _nums(s.narration) | {float(w) for t, w in WORDNUM.items() if t in low.split()}
        for fid in s.fact_ids:
            allowed |= _nums(fact_text.get(fid, ""))
        for v in s.visuals:
            if (v.get("data") or {}).get("illustrative") or v.get("type") in ("quote",):
                continue
            bad = sorted(n for n in _visual_numbers(v) if not _supported(n, allowed))
            if bad:
                problems.append(f"scene {s.id}: {v.get('type')} visual shows {bad[:4]} - not in the narration or "
                                f"the cited facts (fix it, cite the fact, or mark illustrative)")
        for v in s.visuals:
            if v.get("type") not in VISUAL_TYPES:
                problems.append(f"scene {s.id}: unknown visual type {v.get('type')!r}")
            d = v.get("data") or {}
            if v.get("type") == "quote":
                q = re.sub(r"\s+", " ", str(d.get("quote", ""))).strip().lower()
                if not any(q and q in f for f in nq) and not d.get("illustrative"):
                    problems.append(f"scene {s.id}: quote is not verbatim from any verified fact")
            if v.get("type") == "clip":
                if not (d.get("query") or d.get("file")):
                    problems.append(f"scene {s.id}: clip needs a search query")
                if re.search(r"\d", str(d.get("caption", ""))):
                    problems.append(f"scene {s.id}: stock-footage caption must not contain numbers")
            if v.get("type") == "image" and d.get("file") not in media:
                problems.append(f"scene {s.id}: image file {d.get('file')!r} is not in the media list")
            if v.get("sfx") and v["sfx"] not in SFX_NAMES:
                problems.append(f"scene {s.id}: unknown sfx {v['sfx']!r}")
        est = est_seconds(s.narration, s.pace)
        beat = est / max(1, len(s.visuals))
        if beat > MAX_BEAT.get(s.act, DEFAULT_MAX_BEAT):
            problems.append(f"scene {s.id}: ~{beat:.1f}s per visual is too slow (needs more visuals)")
    if scenes and GREETING.match(scenes[0].narration):
        problems.append("cold open starts with a greeting/context - must start on the climax")
    return problems


def _to_scenes(act, items, start_id, first_in_act):
    out = []
    for i, it in enumerate(items):
        vis = [v for v in it.get("visuals", []) if isinstance(v, dict)]
        out.append(Scene(
            id=start_id + i, act=act, narration=it["narration"].strip(),
            visuals=vis or [{"type": "text", "data": {"text": it["narration"][:80]}}],
            fact_ids=it.get("fact_ids", []), pace=it.get("pace", "normal"),
            chapter=ACT_TITLES[act] if (first_in_act and i == 0) else ""))
    return out


def write_script(project: Path, topic: str, minutes: int = 22, log=print, draft=False):
    """draft=True: write from all non-dropped facts so the owner can review facts and script together.
    Approval then re-checks that every cited fact ended up verified."""
    facts = [f for f in facts_from(load_json(project / "facts.json")) if f.verified or draft]
    if not facts:
        raise SystemExit("No verified facts. Run the verify step first.")
    need = minutes * 2
    if len(facts) < need:
        print(f"! Only {len(facts)} verified facts for a ~{minutes}-minute video "
              f"(aim for {need}+). The script will lean on general explainers - "
              f"add more sources and re-run facts/verify for a stronger video.")
    facts_text = "\n".join(f"{f.id}: {f.claim}" for f in facts)
    mdir = project / "media"
    media = sorted(p.name for p in mdir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) if mdir.is_dir() else []
    media_txt = ", ".join(media) or "(none)"
    target_total = minutes * 60 - END_SCREEN_SECONDS

    all_scenes, title, nid = [], topic, 1
    for act, share in ACT_SHARE.items():
        words = int(target_total * share * WPS)
        prev = "\n".join(s.narration for s in all_scenes[-6:])
        print(f"Writing {act} (~{words} words)...")
        data = _gen_act(act, topic, facts_text, words, prev, media=media_txt)
        items = data["scenes"]
        if act == "cold_open":
            title = data.get("title", topic)
        for attempt in range(2):  # top up if the act came back short
            got = _count_words(items)
            if got >= 0.92 * words:
                break
            more = _gen_act(act, topic, facts_text, words - got,
                            "\n".join(i["narration"] for i in items[-6:]),
                            extra=f"The act has {got} of {words} words so far. Continue it with NEW scenes only.", media=media_txt)
            items += more["scenes"]
        scenes = _to_scenes(act, items, nid, True)
        nid += len(scenes)
        all_scenes += scenes

    problems = validate(all_scenes, {f.id for f in facts}, [f.quote for f in facts], media,
                        {f.id: f.claim + " " + f.quote for f in facts})
    for p in problems:
        print("! " + p)
    est = sum(est_seconds(s.narration, s.pace) + 0.35 for s in all_scenes) + END_SCREEN_SECONDS
    print(f"\n{len(all_scenes)} scenes, estimated length {int(est // 60)}:{int(est % 60):02d}, "
          f"{len(problems)} problems")
    if not MIN_SECONDS <= est <= MAX_SECONDS:
        print("! Estimated length is outside 20-25 min - adjust --minutes or add facts, then re-run.")

    save_json({"title": title, "approved": False, "minutes": minutes, "problems": problems,
               "scenes": scenes_to_dicts(all_scenes)}, project / "script.json")
    lines = []
    for s in all_scenes:
        lines.append(f"[{s.id:03d}] {s.act:<9} {s.pace:<6} facts={','.join(s.fact_ids) or '-'}\n"
                     f"      {s.narration}")
    (project / "script.txt").write_text(f"{title}\n\n" + "\n".join(lines), encoding="utf-8")
    print(f"Review {project / 'script.txt'}, then: python main.py approve {project.name}")


def approve_script(project: Path):
    data = load_json(project / "script.json")
    scenes = data["scenes"]
    print(f"\n{data['title']}\n{len(scenes)} scenes. Full text: {project / 'script.txt'}\n")
    for act in ACT_SHARE:
        sc = [s for s in scenes if s["act"] == act]
        if sc:
            print(f"-- {ACT_TITLES[act]} ({len(sc)} scenes)")
            print(f"   first: {sc[0]['narration']}\n   last:  {sc[-1]['narration']}")
    if input("\nHave you read script.txt and checked every figure? Approve? [y/N]: ").lower() == "y":
        data["approved"] = True
        save_json(data, project / "script.json")
        print("Approved.")


def set_approved(project: Path, approved: bool = True):
    """Used by the web studio; the human clicks Approve after reading the script."""
    data = load_json(project / "script.json")
    data["approved"] = approved
    save_json(data, project / "script.json")


def cited_unverified(project: Path):
    """scenes that cite a fact the owner did not verify (dropped or never checked) -> must be fixed before approval"""
    ok = {f.id for f in facts_from(load_json(project / "facts.json")) if f.verified}
    data = load_json(project / "script.json")
    return [(s["id"], [x for x in s.get("fact_ids", []) if x not in ok])
            for s in data["scenes"] if any(x not in ok for x in s.get("fact_ids", []))]
