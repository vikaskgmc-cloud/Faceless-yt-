"""Stage 1: turn source documents into a fact sheet, then force a human check.

Put each source in projects/<slug>/sources/*.txt. First line must be
`URL: https://...`, the rest is the pasted text of the filing/article.
"""
import re
from pathlib import Path

from llm import ask_json
from models import Fact, facts_from, save_json, load_json
from dataclasses import asdict

import corroborate

SYSTEM = (
    "You extract discrete factual claims (numbers, dates, parties, outcomes) "
    "from ONE source text. Use only what the text says. Never add outside "
    "knowledge. Return JSON: a list of {\"claim\": str, \"quote\": str} where "
    "quote is a verbatim excerpt (max 25 words) from the text that supports "
    "the claim. Return at most 15 items."
)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _chunks(body, size=12000):
    paras, cur, out = body.split("\n"), "", []
    for p in paras:
        if len(cur) + len(p) > size and cur:
            out.append(cur)
            cur = ""
        cur += p + "\n"
    if cur.strip():
        out.append(cur)
    return out


def _items(body):
    for ch in _chunks(body):
        try:
            for it in ask_json(SYSTEM, ch):
                if isinstance(it, dict) and it.get("claim") and it.get("quote"):
                    yield it
        except ValueError as e:
            print(f"! could not parse one chunk ({e}); skipped")


def extract_facts(project: Path):
    sources = sorted((project / "sources").glob("*.txt"))
    if not sources:
        raise SystemExit(f"No .txt sources found in {project / 'sources'}")
    facts, n, bodies = [], 0, {}
    for src in sources:
        lines = src.read_text(encoding="utf-8").splitlines()
        if not lines or not lines[0].upper().startswith("URL:"):
            print(f"! {src.name}: first line must be 'URL: ...' - skipped")
            continue
        url, body = lines[0][4:].strip(), "\n".join(lines[1:])
        bodies[src.name] = {"url": url, "body": body}
        for item in _items(body):
            # Guard against invented quotes: the quote must exist in the source.
            if _norm(item["quote"]) not in _norm(body):
                print(f"! dropped (quote not found in {src.name}): {item['claim']}")
                continue
            n += 1
            facts.append(Fact(f"f{n:03d}", item["claim"], item["quote"], url, source=src.name))
    summary = corroborate.annotate(facts, bodies)
    save_json([asdict(f) for f in facts], project / "facts.json")
    print(f"Saved {len(facts)} facts: {summary['batch']} corroborated/primary (batch review), "
          f"{summary['decide']} need your decision, {summary['conflicts']} conflicting.")
    return summary


def verify_facts(project: Path):
    path = project / "facts.json"
    facts = facts_from(load_json(path))
    for f in facts:
        if f.verified:
            continue
        print(f"\n[{f.id}] {f.claim}\n  quote: \"{f.quote}\"\n  source: {f.source_url}")
        ans = input("  Checked against the source? [y]es / [n]o drop / [s]kip: ").lower()
        if ans == "y":
            f.verified = True
        elif ans == "n":
            f.claim = ""  # marked for removal
    facts = [f for f in facts if f.claim]
    save_json([asdict(f) for f in facts], path)
    ok = sum(f.verified for f in facts)
    print(f"\n{ok}/{len(facts)} facts verified.")
