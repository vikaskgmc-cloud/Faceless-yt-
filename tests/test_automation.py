"""Offline tests for: auto research, corroboration flags, shot list, review/approval, studio review screen,
and an end-to-end preview render. Run:  QUALITY=preview TTS_ENGINE=test python tests/test_automation.py"""
import os, re, sys, time, json, shutil, tempfile, subprocess, types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(os.environ.get('TA_TMP') or tempfile.mkdtemp())
os.environ['TA_TMP'] = str(TMP)
os.environ.update(DATA_DIR=str(TMP), QUALITY="preview", TTS_ENGINE="test", STUDIO_PASSWORD="pw", INSECURE_COOKIES="1")
sys.modules.setdefault("anthropic", types.ModuleType("anthropic"))

import corroborate, pipeline, research, script, shotlist, webresearch
from models import Fact, facts_from, load_json, save_json
from dataclasses import asdict

FX = ROOT / "tests" / "fixtures"
PASS = FAIL = 0


def check(name, cond, extra=""):
    global PASS, FAIL
    PASS += cond
    FAIL += (not cond)
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{extra}]" if (extra and not cond) else ""))


# ---------------- mocks (no network, no API key) ----------------
def fake_ask(system, user, max_tokens=8000):
    if system.startswith("You plan web research"):
        return ["S2 Capital Scott Everett fund lawsuit", "S2 Capital Everett court filing Capital One"]
    if system.startswith("You extract discrete"):
        out = []
        for s in re.split(r"(?<=[.!?])\s+", user):
            if "in 2012" in s and "found" in s:
                out.append({"claim": "S2 Capital was founded by Scott Everett in 2012", "quote": " ".join(s.split()[:25])})
                continue
            if re.search(r"\d", s) and 8 <= len(s.split()) <= 60:
                out.append({"claim": s.strip(), "quote": " ".join(s.split()[:25])})
        return out[:15]
    words = int(re.search(r"about (\d+) narration words", user).group(1))
    act = re.search(r"Act: (\w+)", user).group(1)
    ids = re.findall(r"^(f\d+):", user, re.M)
    sc = []
    for i in range(max(3, round(words / 26))):
        fid = ids[i % len(ids)]
        sc.append({"narration": " ".join(["Lenders", "claimed", "the", "borrower", "stopped", "paying", "while", "rents"] * 4)[:170],
                   "pace": "normal", "fact_ids": [fid],
                   "visuals": [{"type": "text", "data": {"text": "The *warning* signs"}},
                               {"type": "flow", "data": {"title": "Where the money went", "nodes": ["Investors", "Fund", "Property", "Lender"], "highlight": 3}},
                               {"type": "layer", "data": {"number": 1, "title": "Floating rate", "text": "Payments move with rates."}}]})
    return {"title": "Mock title", "scenes": sc}


for mod in (research, script, webresearch):
    mod.ask_json = fake_ask


class FakeProvider:
    PAGES = {"https://therealdeal.com/texas/2026/08/06/capital-one/": "trd_capital_one.txt",
             "https://therealdeal.com/texas/2026/07/02/first-fund/": "trd_first_fund.txt",
             "https://www.credaily.com/briefs/s2-capital-dissolves/": "credaily_fund.txt",
             "https://www.costar.com/article/1136389620/s2": "costar_interview.txt",
             "https://www.covercy.com/blog/s2": "covercy_blog.txt"}
    JUNK = {"https://www.reddit.com/r/CommercialRealEstate/s2": "x" * 3000,
            "https://example-blog.com/s2": "short"}

    def search(self, q, limit=8):
        urls = list(self.PAGES) + list(self.JUNK)
        return [{"url": u, "title": u.split("/")[-2]} for u in urls]

    def scrape(self, url):
        if url in self.PAGES:
            t = (FX / self.PAGES[url]).read_text().split("\n", 1)[1]
            return "[Skip to content](#x)\n![img](a.png)\nnav\n" + t
        return self.JUNK[url]


def new_project(name="s2"):
    p = TMP / "projects" / name
    (p / "sources").mkdir(parents=True)
    save_json({"topic": "S2 Capital (Scott Everett), Dallas"}, p / "meta.json")
    return p


def main():
    if not (FX / "trd_capital_one.txt").exists():
        print("fixtures missing (see tests/fixtures/README.md) - skipping")
        return
    # ---------------- 1. corroboration rules on synthetic facts ----------------
    print("corroboration")
    S = {"a.txt": {"url": "https://www.sec.gov/litigation/x.pdf", "body": "The complaint says the loan was 531 units."},
         "b.txt": {"url": "https://www.bisnow.com/a", "body": "Bisnow story about the loan."},
         "c.txt": {"url": "https://www.costar.com/a", "body": "CoStar story, according to Bisnow the loan was large."},
         "d.txt": {"url": "https://www.dallasnews.com/a", "body": "Independent reporting."},
         "e.txt": {"url": "https://www.reddit.com/r/x", "body": "rumour"}}
    F = lambda i, claim, quote, src: Fact(i, claim, quote, S[src]["url"], source=src)
    facts = [F("f1", "Richmond Apartments is a 531-unit complex financed with an $85.2 million loan", "531-unit complex ... $85.2 million loan", "a.txt"),
             F("f2", "The loan on the 531-unit Richmond Apartments complex was $85.2 million", "531-unit ... $85.2 million", "b.txt"),
             F("f3", "The Richmond Apartments complex has 513 units and an $85.2 million loan", "513 units", "d.txt"),
             F("f4", "The fund lost $400 million of investor money in the Richmond collapse", "lost $400 million", "b.txt"),
             F("f5", "The fund lost $400 million of investor money in the Richmond collapse", "lost $400 million", "c.txt"),
             F("f6", "Lender claims the guarantor owes $11.5 million on the default", "owes $11.5 million", "d.txt"),
             F("f7", "Management fees were $7 million per year", "fees were reduced", "d.txt"),
             F("f8", "Everett founded the firm in 2012", "founded the firm", "b.txt"),
             F("f9", "Everett founded the firm in 2012", "founded the firm", "d.txt")]
    summ = corroborate.annotate(facts, S)
    by = {f.id: f for f in facts}
    check("primary source flagged", "primary" in by["f1"].flags and by["f1"].tier == 1)
    check("independent news confirms primary claim", "corroborated" in by["f1"].flags and "f2" in by["f1"].support)
    check("conflicting number (531 vs 513) flagged", "conflict" in by["f3"].flags and "conflict" in by["f1"].flags)
    check("conflict -> decide bucket", by["f3"].bucket == "decide" and by["f1"].bucket == "decide")
    check("source that cites the other is NOT independent", "derivative_only" in by["f4"].flags and by["f4"].bucket == "decide", by["f4"].flags)
    check("single source allegation -> decide", "allegation" in by["f6"].flags and by["f6"].bucket == "decide")
    check("number missing from quote flagged", "numbers_not_in_quote" in by["f7"].flags)
    check("year-only claims confirmed by two publishers -> batch", by["f8"].bucket == "batch" and by["f9"].bucket == "batch", by["f8"].flags)
    check("summary counts add up", summ["batch"] + summ["decide"] == len(facts))

    # ---------------- 2. research -> claims -> script -> shot list ----------------
    print("auto research + draft")
    p = new_project()
    logs = []
    summary = pipeline.research_and_draft(p, 22, provider=FakeProvider(), log=logs.append, max_sources=8)
    srcs = sorted(x.name for x in (p / "sources").glob("*.txt"))
    check("saved 4 usable sources (reddit, short page, short vendor blog skipped)", len(srcs) == 4, srcs)
    check("no social/forum source saved", not any("reddit" in s for s in srcs))
    check("at most 2 pages per publisher", sum("therealdeal" in s for s in srcs) == 2)
    check("nav junk stripped from saved text", "Skip to content" not in (p / "sources" / srcs[0]).read_text())
    facts = facts_from(load_json(p / "facts.json"))
    check("claims extracted with source + bucket", len(facts) > 10 and all(f.source and f.bucket for f in facts), len(facts))
    check("every quote exists verbatim in its source", all(research._norm(f.quote) in research._norm((p / "sources" / f.source).read_text()) for f in facts))
    check("CRE Daily facts are derivative of The Real Deal", any("derivative_only" in f.flags for f in facts if "credaily" in f.source))
    check("independent confirmation found somewhere (founded 2012 etc.)", any("corroborated" in f.flags for f in facts))
    check("nothing is verified before the owner reviews", not any(f.verified for f in facts))
    check("script drafted but NOT approved", load_json(p / "script.json")["approved"] is False)
    sl = load_json(p / "shotlist.json")
    check("shot list written (json/csv/md)", all((p / n).exists() for n in ("shotlist.json", "shotlist.csv", "shotlist.md")))
    check("shot list has one row per visual + end screen", sl["summary"]["shots"] == sum(len(s["visuals"]) for s in load_json(p / "script.json")["scenes"]) + 1)
    check("shot list length in the 20-25 min window", 20 * 60 <= sl["summary"]["seconds"] <= 25 * 60, sl["summary"]["length"])
    check("shot list warns about missing music", sl["summary"]["no_music_tracks"] is True)
    check("review state recorded", load_json(p / "review.json")["stage"] == "awaiting_review")

    # ---------------- 3. approval gates ----------------
    print("review + approval")
    decide = [f.id for f in facts if f.bucket != "batch"]
    batch = [f.id for f in facts if f.bucket == "batch"]
    def expect_err(fn, name, frag):
        try:
            fn(); check(name, False, "no error raised")
        except pipeline.ReviewError as e:
            check(name, frag in str(e), str(e))
    expect_err(lambda: pipeline.approve(p, {}, (), confirmed=False), "needs the confirmation tick", "Confirm")
    expect_err(lambda: pipeline.approve(p, {}, (), confirmed=True), "undecided claims block approval", "need your decision")
    check("still nothing verified after failed attempts", not any(f.verified for f in facts_from(load_json(p / "facts.json"))))
    drop_id = next(s["fact_ids"][0] for s in load_json(p / "script.json")["scenes"] if s["fact_ids"][0] in decide)
    d = {i: "ok" for i in decide}
    d[drop_id] = "drop"
    expect_err(lambda: pipeline.approve(p, d, (), confirmed=True), "dropping a claim the script cites blocks approval", "rely on claims you dropped")
    check("script stays unapproved", load_json(p / "script.json")["approved"] is False)
    facts_before = facts_from(load_json(p / "facts.json"))
    check("(the failed attempt did drop that fact, so re-draft is required)", drop_id not in {f.id for f in facts_before})
    # fresh project for the success path
    p2 = new_project("s2b")
    pipeline.research_and_draft(p2, 22, provider=FakeProvider(), log=lambda *_: None)
    f2 = facts_from(load_json(p2 / "facts.json"))
    d2 = {f.id: "ok" for f in f2 if f.bucket != "batch"}
    audit = pipeline.approve(p2, d2, (), confirmed=True)
    f2b = facts_from(load_json(p2 / "facts.json"))
    check("approval verifies every kept claim with an audit trail", all(f.verified and f.how and f.at for f in f2b))
    check("batch/manual counts recorded", audit["batch_approved"] + audit["manually_approved"] == len(f2b) and audit["dropped"] == 0, audit)
    check("script now approved", load_json(p2 / "script.json")["approved"] is True)
    check("no scene cites an unverified claim", script.cited_unverified(p2) == [])

    # ---------------- 4. studio review screen ----------------
    print("studio review screen")
    import studio
    studio.PROJECTS = TMP / "projects"
    c = studio.app.test_client()
    c.post("/login", data={"password": "pw"})
    csrf = re.search(r'name="csrf" value="(\w+)"', c.get("/").get_data(as_text=True)).group(1)
    p3 = new_project("s2c")
    pipeline.research_and_draft(p3, 22, provider=FakeProvider(), log=lambda *_: None)
    page = c.get("/p/s2c/review").get_data(as_text=True)
    check("review page shows decide + batch + script + shot list", all(k in page for k in ("need your decision", "Batch:", "Script (", "Shot list")))
    r = c.post("/p/s2c/review", data={"csrf": csrf, "confirm": "yes"})
    check("posting without decisions does not approve", load_json(p3 / "script.json")["approved"] is False)
    f3 = facts_from(load_json(p3 / "facts.json"))
    form = {"csrf": csrf, "confirm": "yes", **{f"d_{f.id}": "ok" for f in f3 if f.bucket != "batch"}}
    # shrink the script so the produce job's length gate (not the render) is what we observe, quickly
    sj = load_json(p3 / "script.json")
    sj["scenes"] = sj["scenes"][:8]   # short script keeps the test fast
    save_json(sj, p3 / "script.json")
    c.post("/p/s2c/review", data=form)
    check("complete review approves the script", load_json(p3 / "script.json")["approved"] is True)
    job = studio.JOBS.get("s2c")
    check("approval started the produce job", job is not None and job["kind"] == "produce")
    t0 = time.time()
    while job["proc"].poll() is None and time.time() - t0 < 400:
        time.sleep(2)
    print("    produce job finished in", int(time.time() - t0), "s, rc =", job["proc"].returncode)
    check("voice step ran after approval", any((p3 / "audio").glob("*.wav")) if (p3 / "audio").exists() else False)
    log = (p3 / "job.log").read_text()
    check("voice generated before render", "Timing report" in log)
    check("length gate stops a too-short video with a clear message", "target is" in log and job["proc"].returncode != 0, log[-300:])

    # ---------------- 5. end-to-end render of an approved, shortened project ----------------
    print("end-to-end preview render")
    import main as M
    sj = load_json(p2 / "script.json")
    sj["scenes"] = sj["scenes"][:10]
    save_json(sj, p2 / "script.json")
    M.cmd_voice(types.SimpleNamespace(slug="s2b"))
    M.cmd_render(types.SimpleNamespace(slug="s2b", force=True))
    mp4 = p2 / "video.mp4"
    check("video.mp4 produced", mp4.exists() and mp4.stat().st_size > 100_000)
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)], capture_output=True, text=True).stdout)
    exp = sum(s["duration"] for s in load_json(p2 / "script.json")["scenes"]) + 15
    check("video length matches the timeline", abs(dur - exp) < 1.0, f"{dur:.1f} vs {exp:.1f}")
    check("description + thumbnail written", (p2 / "description.txt").exists() and (p2 / "thumbnail.jpg").exists())
    check("shot list refreshes from real timings", shotlist.build(p2)["timed"] is True)

    print("stock footage (clip visuals)")
    import broll, cv2, numpy as np
    pc = new_project("clips")
    sc = {"title": "Clip test", "approved": False, "scenes": [
        {"id": 1, "act": "rise", "narration": "Picture apartment blocks across the Sun Belt.", "pace": "normal", "fact_ids": [],
         "visuals": [{"type": "clip", "data": {"query": "apartment building exterior", "caption": "Apartment buildings in the Sun Belt"}}]},
        {"id": 2, "act": "rise", "narration": "Money moved through a chain.", "pace": "normal", "fact_ids": [],
         "visuals": [{"type": "clip", "data": {"query": "zzz nothing matches", "caption": "Generic caption"}}]}]}
    save_json(sc, pc / "script.json")
    src_clip = pc / "src.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "mandelbrot=size=1280x720:rate=24", "-t", "8",
                    "-pix_fmt", "yuv420p", str(src_clip)], check=True)

    class FakePexels:
        def __init__(self):
            self.downloads = 0

        def search(self, q):
            if "zzz" in q:
                return []
            return [{"id": 1, "duration": 3, "credit": "too short", "files": [{"w": 1920, "h": 1080, "link": "x"}]},
                    {"id": 2, "duration": 12, "credit": "Video by Test Author on Pexels",
                     "files": [{"w": 640, "h": 360, "link": "lo"}, {"w": 1920, "h": 1080, "link": "hi"}]}]

        def download(self, url, dest):
            assert url == "hi", "should pick the HD file"
            self.downloads += 1
            shutil.copy(src_clip, dest)

    fp = FakePexels()
    res = broll.attach(pc, fp, log=lambda *_: None)
    check("query resolved to a downloaded clip (HD file, skips the too-short one)", res == {"resolved": 1, "unresolved": 1} and fp.downloads == 1, res)
    scj = load_json(pc / "script.json")
    fname = scj["scenes"][0]["visuals"][0]["data"]["file"]
    check("clip file saved in project media", (pc / "media" / fname).is_file())
    check("credit recorded", "Test Author" in (pc / "media" / "credits.json").read_text())
    check("unresolved query keeps a caption card, not a failure", "file" not in scj["scenes"][1]["visuals"][0]["data"])
    check("shot list marks the unresolved clip as missing", any("MISSING" in r["assets_needed"] for r in
          (shotlist.build(pc) and load_json(pc / "shotlist.json")["shots"])))
    # the picture really MOVES and is labelled
    import config, bg, visuals
    b = bg.Background()
    beat = {"media_dir": str(pc / "media"), "broll_dir": str(pc), "idx": 0, "chapter": "", "act": "rise", "start": 0, "dur": 4}
    def render(tt, data):
        f = b.render("rise", tt)
        visuals.draw_visual(visuals.Ctx(f, "rise", tt, 4.0, tt, beat), {"type": "clip", "data": data})
        return f.astype(int)
    f0, f1, f2 = (render(tt, {"file": fname, "caption": "Generic"}) for tt in (0.8, 1.6, 2.4))
    check("consecutive frames differ -> footage is moving", np.abs(f0 - f1).mean() > 1.5 and np.abs(f1 - f2).mean() > 1.5)
    chip = f1[config.H * 108 // 1080: config.H * 146 // 1080, int(config.W * 0.80):int(config.W * 0.96)]
    check("'STOCK FOOTAGE' label region is drawn", (chip[..., 0] > 150).mean() > 0.002)
    miss = render(1.0, {"file": "nope.mp4", "caption": "Fallback card"})
    check("missing footage falls back to a caption card (no crash, not blank)", miss.std() > 5)
    check("validator: clip captions may not carry numbers", any("caption must not contain numbers" in p for p in script.validate(
        [type("S", (), dict(id=9, act="rise", narration="Generic words here", fact_ids=[], pace="normal",
                            visuals=[{"type": "clip", "data": {"query": "x", "caption": "Built in 2019"}}]))()], set())))
    check("validator: clip needs a query or file", any("clip needs a search query" in p for p in script.validate(
        [type("S", (), dict(id=9, act="rise", narration="Generic words here", fact_ids=[], pace="normal",
                            visuals=[{"type": "clip", "data": {"caption": "x"}}]))()], set())))
    # credits flow into the YouTube description
    import assemble
    from models import scenes_from
    desc_dir = pc
    assemble.write_description(desc_dir, "Clip test", scenes_from(load_json(pc / "script.json")["scenes"]), [0, 5], [])
    check("stock-footage credit appears in description.txt", "Video by Test Author on Pexels" in (pc / "description.txt").read_text())

    print(f"\n{PASS} passed, {FAIL} failed")
    shutil.rmtree(TMP, ignore_errors=True)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
