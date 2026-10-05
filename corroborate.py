"""Cross-source checks on extracted facts. Deterministic - no AI, so the result is repeatable.

For every fact we decide:
  primary             comes from a primary record (court filing, regulator, government site)
  corroborated        >=1 INDEPENDENT source (other publisher, not just repeating the first) says the same thing
  single_source       nobody independent confirms it
  derivative_only     the only "confirmation" is a source that cites this one
  allegation          a claim by a party ("lender claims", "lawsuit alleges") - must be worded as such
  conflict            another source gives a different number for what looks like the same thing
  numbers_not_in_quote the claim contains a number its own quote does not - extraction error risk

bucket = "batch"  -> (primary or corroborated) and no conflict / number problem / uncorroborated allegation
         "decide" -> everything else: the owner must look at it individually
"""
import re
from urllib.parse import urlparse

PRIMARY_DOMAINS = ("sec.gov", "govinfo.gov", "courtlistener.com", "uscourts.gov", "pacermonitor.com", "nycourts.gov",
                   "justice.gov", "fanniemae.com", "freddiemac.com", "treasury.gov", "federalreserve.gov", "sebi.gov.in",
                   "texasattorneygeneral.gov", "law.cornell.edu")
NEWS_DOMAINS = ("therealdeal.com", "costar.com", "wsj.com", "bloomberg.com", "reuters.com", "bisnow.com", "credaily.com",
                "multifamilydive.com", "dallasnews.com", "connectcre.com", "globest.com", "commercialobserver.com",
                "ft.com", "nytimes.com", "cnbc.com", "forbes.com", "axios.com", "dallasobserver.com", "thepromote.com",
                "texasmonthly.com", "dmagazine.com", "propertyweek.com", "realdeal.com")
EXCLUDED_DOMAINS = ("reddit.com", "facebook.com", "x.com", "twitter.com", "instagram.com", "linkedin.com", "youtube.com",
                    "tiktok.com", "quora.com", "substack.com", "medium.com", "pinterest.com")
PUBLISHER_NAMES = {"therealdeal.com": ["the real deal"], "credaily.com": ["cre daily"], "costar.com": ["costar"],
                   "bisnow.com": ["bisnow"], "wsj.com": ["wall street journal", "wsj"], "bloomberg.com": ["bloomberg"],
                   "reuters.com": ["reuters"], "multifamilydive.com": ["multifamily dive"],
                   "dallasnews.com": ["dallas morning news"], "thepromote.com": ["the promote"],
                   "globest.com": ["globest"], "commercialobserver.com": ["commercial observer"], "ft.com": ["financial times"]}
CITE = re.compile(r"(according to|reported by|reporting from|reported in|per|as reported by|obtained by|shared with|via)\s+(?:the\s+)?$", re.I)
ALLEGATION = re.compile(r"\b(claims?|claimed|alleges?|alleged|allegedly|accus\w+|sues?|sued|lawsuit|suit|complaint|filing|filed|"
                        r"according to (?:capital one|the lender|the bank|a filing|court))\b", re.I)
STOP = set("the and for with that this from has have had was were are been will would into over after before than their its "
           "his her but not all any also more most one two three four five new per who which when what while about said says".split())
MULT = {"thousand": 1e3, "k": 1e3, "million": 1e6, "mm": 1e6, "m": 1e6, "billion": 1e9, "bn": 1e9, "b": 1e9}
NUMRE = re.compile(r"(\$)?\s?(\d[\d,]*(?:\.\d+)?)\s?(%|percent|thousand|million|billion|mm|bn|k|m|b)?(?![A-Za-z])", re.I)


def registrable(url_or_host):
    host = urlparse(url_or_host).netloc if "//" in url_or_host else url_or_host
    host = host.lower().split(":")[0].removeprefix("www.")
    parts = host.split(".")
    return ".".join(parts[-3:]) if len(parts) >= 3 and parts[-2] in ("co", "com", "org", "gov") else ".".join(parts[-2:])


def tier_of(domain):
    if domain.endswith(".gov") or domain in PRIMARY_DOMAINS or any(domain.endswith("." + d) for d in PRIMARY_DOMAINS):
        return 1
    if domain in NEWS_DOMAINS:
        return 2
    return 3


def key_numbers(text):
    """normalised numbers that carry meaning: money, percentages, counts. Years and tiny day-numbers are ignored."""
    out = set()
    for dollar, num, unit in NUMRE.findall(str(text)):
        try:
            v = float(num.replace(",", ""))
        except ValueError:
            continue
        unit = (unit or "").lower()
        if unit in ("%", "percent"):
            out.add(("pct", round(v, 2)))
            continue
        if unit in MULT:
            out.add(("n", round(v * MULT[unit], 2)))
            continue
        if not dollar and v.is_integer() and 1900 <= v <= 2100:
            continue                      # a year
        if v >= 10 or dollar:
            out.add(("n", round(v, 2)))
    return out


def tokens(text):
    return {w for w in re.findall(r"[a-z][a-z'-]{2,}", str(text).lower()) if w not in STOP}


def overlap(a, b):
    return len(a & b) / max(1, min(len(a), len(b)))


def cites(body, domain):
    """does this source text lean on `domain`'s reporting ('according to The Real Deal', a link to it)?"""
    low = body.lower()
    if domain in low:
        return True
    for name in PUBLISHER_NAMES.get(domain, []):
        for m in re.finditer(re.escape(name), low):
            if CITE.search(low[max(0, m.start() - 25):m.start()]):
                return True
    return False


def source_info(sources):
    """sources: {filename: {"url":..., "body":...}} -> adds domain, tier, cites (set of domains it leans on)"""
    info = {}
    for name, s in sources.items():
        d = registrable(s["url"])
        info[name] = {"url": s["url"], "domain": d, "tier": tier_of(d), "body": s.get("body", "")}
    for name, s in info.items():
        s["cites"] = {o["domain"] for on, o in info.items() if on != name and o["domain"] != s["domain"]
                      and cites(s["body"], o["domain"])}
    return info


def _same_claim(fa, fb):
    na, nb = key_numbers(fa.claim), key_numbers(fb.claim)
    ta, tb = tokens(fa.claim), tokens(fb.claim)
    shared = na & nb
    if shared:
        return overlap(ta, tb) >= 0.2
    if not na and not nb:
        return overlap(ta, tb) >= 0.55
    return False


def _conflict(fa, fb):
    """same statement, but a figure differs: e.g. 531-unit vs 513 units, or $85.2M vs $58.2M.
    Conservative on purpose - a false alarm only moves the claim to the 'you decide' list."""
    na, nb = key_numbers(fa.claim), key_numbers(fb.claim)
    if not (na and nb) or overlap(tokens(fa.claim), tokens(fb.claim)) < 0.5:
        return False
    for kind_a, a in na - nb:
        for kind_b, b in nb - na:
            if kind_a == kind_b and a and b and 0.5 <= a / b <= 2:
                return True
    return False


def annotate(facts, sources):
    """sets flags, support, tier, bucket on every fact (in place) and returns a summary dict"""
    info = source_info(sources)
    for f in facts:
        s = info.get(f.source)
        f.tier = s["tier"] if s else 3
        f.flags, f.support = [], []
    for f in facts:
        sa = info.get(f.source)
        if not sa:
            f.flags.append("single_source")
            continue
        if f.tier == 1:
            f.flags.append("primary")
        independent, derivative = [], []
        for g in facts:
            if g is f or g.source == f.source:
                continue
            sb = info.get(g.source)
            if not sb or sb["domain"] == sa["domain"] or g.tier >= 3:
                continue
            if _conflict(f, g):
                if "conflict" not in f.flags:
                    f.flags.append("conflict")
                continue
            if _same_claim(f, g):
                # g only counts as independent if neither source leans on the other's reporting
                if sb["domain"] in sa["cites"] or sa["domain"] in sb["cites"]:
                    derivative.append(g.id)
                else:
                    independent.append(g.id)
        f.support = independent
        if independent:
            f.flags.append("corroborated")
        else:
            f.flags.append("derivative_only" if derivative else "single_source")
        if ALLEGATION.search(f.claim):
            f.flags.append("allegation")
        if not key_numbers(f.claim) <= key_numbers(f.quote):
            f.flags.append("numbers_not_in_quote")
        strong = "primary" in f.flags or "corroborated" in f.flags
        bad = {"conflict", "numbers_not_in_quote"} & set(f.flags)
        f.bucket = "batch" if strong and not bad else "decide"
    n = len(facts)
    return {"facts": n, "batch": sum(f.bucket == "batch" for f in facts), "decide": sum(f.bucket == "decide" for f in facts),
            "conflicts": sum("conflict" in f.flags for f in facts)}


def explain(f):
    """one plain-English line for the review screen"""
    parts = []
    if "primary" in f.flags:
        parts.append("primary record")
    if "corroborated" in f.flags:
        parts.append(f"confirmed independently by {', '.join(f.support)}")
    if "derivative_only" in f.flags:
        parts.append("only repeated by sources that cite this one")
    if "single_source" in f.flags:
        parts.append("one source only")
    if "allegation" in f.flags:
        parts.append("a party's claim - word it as 'according to ...'")
    if "conflict" in f.flags:
        parts.append("another source gives a different figure")
    if "numbers_not_in_quote" in f.flags:
        parts.append("claim has a number its quote lacks")
    return "; ".join(parts)
