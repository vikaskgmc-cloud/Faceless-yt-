"""Stock footage for "clip" visuals: turns each clip's search query into a downloaded video file.

Provider: Pexels (free licence; set PEXELS_API_KEY). Any object with
  .search(query) -> [{"id","duration","credit","files":[{"w","h","link"}]}]   and   .download(url, dest)
works, which is how the tests run offline. Credits go to media/credits.json and the video description.
Unresolved clips stay as caption cards - the render never fails because footage was not found.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

from models import load_json, save_json


class Pexels:
    def __init__(self, key=None):
        self.key = key or os.getenv("PEXELS_API_KEY", "")

    def _get(self, url):
        req = urllib.request.Request(url, headers={"Authorization": self.key, "User-Agent": "case-study-studio"})
        return urllib.request.urlopen(req, timeout=60)

    def search(self, query):
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode(
            {"query": query, "per_page": 6, "orientation": "landscape", "size": "medium"})
        data = json.loads(self._get(url).read())
        out = []
        for v in data.get("videos", []):
            files = [{"w": f.get("width", 0), "h": f.get("height", 0), "link": f["link"]}
                     for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("link")]
            out.append({"id": v["id"], "duration": v.get("duration", 0), "files": files,
                        "credit": f"Video by {v.get('user', {}).get('name', 'a Pexels contributor')} on Pexels"})
        return out

    def download(self, url, dest):
        with self._get(url) as r, open(dest, "wb") as f:
            n = 0
            while chunk := r.read(1 << 20):
                n += len(chunk)
                if n > 120 * (1 << 20):
                    raise RuntimeError("clip larger than 120 MB")
                f.write(chunk)


def _pick(results, used):
    """a 5-40 s clip, HD (1280-2560 wide), not already used in this video"""
    best = None
    for r in results:
        if r["id"] in used or not (5 <= r["duration"] <= 40):
            continue
        files = [f for f in r["files"] if 1280 <= f["w"] <= 2560]
        if files:
            f = max(files, key=lambda f: f["w"])
            if best is None or f["w"] > best[1]["w"]:
                best = (r, f)
    return best


def attach(project: Path, provider=None, log=print):
    """resolve every clip visual that has a query but no file; returns {'resolved': n, 'unresolved': n}"""
    path = project / "script.json"
    data = load_json(path)
    todo = [(s, v) for s in data["scenes"] for v in s.get("visuals", [])
            if v.get("type") == "clip" and (v.get("data") or {}).get("query") and not v["data"].get("file")]
    if not todo:
        return {"resolved": 0, "unresolved": 0}
    provider = provider or (Pexels() if os.getenv("PEXELS_API_KEY") else None)
    if provider is None:
        log(f"! {len(todo)} stock clips left as caption cards (set PEXELS_API_KEY to fetch footage)")
        return {"resolved": 0, "unresolved": len(todo)}
    mdir = project / "media"
    mdir.mkdir(exist_ok=True)
    cred_path = mdir / "credits.json"
    credits = json.loads(cred_path.read_text()) if cred_path.exists() else {}
    used = {c["id"] for c in credits.values()}
    cache, ok, bad = {}, 0, 0
    for s, v in todo:
        q = v["data"]["query"].strip()
        try:
            if q not in cache:
                cache[q] = provider.search(q)
            pick = _pick(cache[q], used)
            if not pick:
                raise LookupError("no suitable clip")
            r, f = pick
            name = f"clip_{re.sub(r'[^a-z0-9]+', '-', q.lower())[:30]}_{r['id']}.mp4"
            if not (mdir / name).exists():
                provider.download(f["link"], mdir / name)
            v["data"]["file"] = name
            credits[name] = {"id": r["id"], "credit": r["credit"], "query": q}
            used.add(r["id"])
            ok += 1
        except Exception as e:
            log(f"! no footage for '{q}' ({type(e).__name__}); scene {s['id']} keeps a caption card")
            bad += 1
    cred_path.write_text(json.dumps(credits, indent=2))
    save_json(data, path)
    return {"resolved": ok, "unresolved": bad}
