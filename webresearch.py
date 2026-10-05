"""Automatic research: search the web, read the best pages, save them as sources.

Search/scrape goes through a provider. Built in: Firecrawl (set FIRECRAWL_API_KEY).
Any object with .search(query, limit) -> [{"url","title","text"?}] and .scrape(url) -> text works,
which is how the tests run offline.

Rules: primary records first, then reputable news; social media, forums and newsletters behind paywalls are
skipped; at most two pages per publisher (independence is judged per publisher later).
"""
import json
import os
import re
import urllib.request
from pathlib import Path

from corroborate import EXCLUDED_DOMAINS, registrable, tier_of
from llm import ask_json

MIN_CHARS = 1500
PAYWALL = re.compile(r"(this post is for (paid )?subscribers|subscribe to (continue|read)|sign in to read|"
                     r"already a subscriber|create a free account to continue)", re.I)


class Firecrawl:
    base = "https://api.firecrawl.dev/v2"

    def __init__(self, key=None):
        self.key = key or os.getenv("FIRECRAWL_API_KEY", "")
        if not self.key:
            raise SystemExit("Set FIRECRAWL_API_KEY to let the studio research the web (or add sources by hand).")

    def _post(self, path, payload):
        req = urllib.request.Request(self.base + path, json.dumps(payload).encode(),
                                     {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            return json.loads(r.read())

    def search(self, query, limit=8):
        d = self._post("/search", {"query": query, "limit": limit}).get("data", [])
        rows = d.get("web", []) if isinstance(d, dict) else d
        return [{"url": r.get("url"), "title": r.get("title", "")} for r in rows if r.get("url")]

    def scrape(self, url):
        d = self._post("/scrape", {"url": url, "formats": ["markdown"], "onlyMainContent": True}).get("data", {})
        return d.get("markdown", "")


def plan_queries(topic, n=8):
    """Claude proposes search queries aimed at primary records first; falls back to simple ones"""
    try:
        q = ask_json("You plan web research for a finance-education documentary. Return a JSON list of search "
                     f"queries (max {n}) that find: court filings, regulator/SEC documents, lender statements, "
                     "company letters to investors, then reputable news. No opinion blogs. Each query under 12 words.",
                     f"Topic: {topic}")
        q = [x for x in q if isinstance(x, str) and x.strip()][:n]
        if q:
            return q
    except Exception as e:      # no API key, bad JSON...
        print(f"! query planning failed ({type(e).__name__}); using basic queries")
    return [topic, f"{topic} lawsuit court filing", f"{topic} investors letter loss", f"{topic} foreclosure lender"]


def clean(md):
    """strip navigation/link clutter from scraped markdown"""
    md = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", md)                      # images
    md = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)                  # links -> text
    lines = [l.strip() for l in md.splitlines()]
    keep = [l for l in lines if len(l) > 40 or l.startswith("#")]     # real sentences, headings
    return "\n".join(keep)


def gather(project: Path, topic: str, provider=None, max_sources=8, queries=None, log=print, per_domain=2):
    provider = provider or Firecrawl()
    src_dir = project / "sources"
    src_dir.mkdir(parents=True, exist_ok=True)
    seen_urls = {l.split("URL:", 1)[1].strip() for p in src_dir.glob("*.txt")
                 for l in p.read_text(errors="ignore").splitlines()[:1] if l.upper().startswith("URL:")}
    cands = []
    for q in queries or plan_queries(topic):
        log(f"search: {q}")
        try:
            cands += provider.search(q, 8)
        except Exception as e:
            log(f"! search failed ({type(e).__name__}: {e})")
    uniq = {}
    for c in cands:
        d = registrable(c["url"])
        if d in EXCLUDED_DOMAINS or c["url"] in seen_urls:
            continue
        uniq.setdefault(c["url"], {**c, "domain": d, "tier": tier_of(d)})
    ranked = sorted(uniq.values(), key=lambda c: (c["tier"], c["url"]))
    used_domains, saved = {}, []
    n = len(list(src_dir.glob("*.txt")))
    for c in ranked:
        if len(saved) >= max_sources:
            break
        if used_domains.get(c["domain"], 0) >= per_domain:
            continue
        try:
            text = clean(provider.scrape(c["url"]))
        except Exception as e:
            log(f"! could not read {c['url']} ({type(e).__name__})")
            continue
        if len(text) < MIN_CHARS or PAYWALL.search(text[:4000]):
            log(f"skip (too short or paywalled): {c['url']}")
            continue
        n += 1
        name = f"src{n:02d}_{c['domain'].split('.')[0]}.txt"
        (src_dir / name).write_text(f"URL: {c['url']}\n{c.get('title', '')}\n\n{text}", encoding="utf-8")
        used_domains[c["domain"]] = used_domains.get(c["domain"], 0) + 1
        saved.append({"file": name, "url": c["url"], "domain": c["domain"], "tier": c["tier"], "title": c.get("title", "")})
        log(f"saved {name} (tier {c['tier']})")
    idx_path = src_dir / "index.json"
    idx = json.loads(idx_path.read_text()) if idx_path.exists() else []
    idx_path.write_text(json.dumps(idx + saved, indent=2))
    return saved
