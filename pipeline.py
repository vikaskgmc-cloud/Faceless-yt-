"""Automatic pipeline. Everything up to the review screen runs by itself; the owner approves once; then
voice + 4K render run by themselves.

  research_and_draft : web research -> sources -> claims -> cross-checks -> script -> shot list   (stops here)
  approve            : owner decisions (batch + individual) -> verified facts + approved script
  produce            : voice -> render (only if approved)
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import broll
import corroborate
import research
import script
import shotlist
import webresearch
from models import facts_from, load_json, save_json
from dataclasses import asdict


class ReviewError(Exception):
    pass


def research_and_draft(project: Path, minutes: int = 22, provider=None, log=print, queries=None, max_sources=8):
    topic = load_json(project / "meta.json").get("topic", project.name)
    log("1/5 Researching the web...")
    saved = webresearch.gather(project, topic, provider, max_sources=max_sources, queries=queries, log=log)
    if not list((project / "sources").glob("*.txt")):
        raise SystemExit("No usable sources found. Add source documents by hand, or try a more specific topic.")
    log(f"2/5 Extracting claims from {len(list((project / 'sources').glob('*.txt')))} sources...")
    summary = research.extract_facts(project)
    log("3/5 Writing the script from the claims...")
    script.write_script(project, topic, minutes, draft=True)
    log("3b/5 Fetching stock footage for clip scenes...")
    broll.attach(project, log=log)
    log("4/5 Building the shot list...")
    shots = shotlist.build(project)
    save_json({"stage": "awaiting_review", "at": datetime.now(timezone.utc).isoformat(), "claims": summary,
               "shots": shots["shots"]}, project / "review.json")
    log(f"5/5 Ready for your review: {summary['batch']} claims in the batch, {summary['decide']} need your decision.")
    return summary


def approve(project: Path, decisions: dict, batch_dropped=(), confirmed=False, now=None):
    """decisions: {fact_id: "ok"|"drop"} for every fact in the 'decide' bucket.
    batch facts are approved unless listed in batch_dropped. Raises ReviewError if anything is left undecided."""
    if not confirmed:
        raise ReviewError("Confirm that you read the claims and the script.")
    facts = facts_from(load_json(project / "facts.json"))
    pending = [f.id for f in facts if f.bucket != "batch" and decisions.get(f.id) not in ("ok", "drop")]
    if pending:
        raise ReviewError(f"{len(pending)} claims still need your decision: {', '.join(pending[:8])}")
    stamp = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
    keep = []
    for f in facts:
        drop = f.id in batch_dropped if f.bucket == "batch" else decisions.get(f.id) == "drop"
        if drop:
            continue
        f.verified, f.how, f.at = True, ("batch" if f.bucket == "batch" else "manual"), stamp
        keep.append(f)
    save_json([asdict(f) for f in keep], project / "facts.json")
    bad = script.cited_unverified(project)
    if bad:
        # the owner dropped a claim the script relies on: script must be rewritten, never approved as is
        script.set_approved(project, False)
        raise ReviewError(f"{len(bad)} scenes rely on claims you dropped (e.g. scene {bad[0][0]}). "
                          f"Re-draft the script, then review again.")
    script.set_approved(project, True)
    review = load_json(project / "review.json") if (project / "review.json").exists() else {}
    review.update({"stage": "approved", "approved_at": stamp,
                   "audit": {"batch_approved": sum(f.how == "batch" for f in keep),
                             "manually_approved": sum(f.how == "manual" for f in keep),
                             "dropped": len(facts) - len(keep)}})
    save_json(review, project / "review.json")
    return review["audit"]
