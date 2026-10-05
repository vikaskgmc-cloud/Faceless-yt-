"""Owner-only web studio: create a project, paste sources, verify facts, write and
approve the script, render 4K, and DOWNLOAD the finished video (Range-capable).

  STUDIO_PASSWORD=...  SECRET_KEY=...  python studio.py        (or gunicorn studio:app)
"""
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from pathlib import Path

from flask import (Flask, abort, flash, jsonify, redirect, render_template, request, send_file, session,
                   url_for)

from config import PROJECTS, QUALITY
import corroborate
import pipeline
from models import facts_from, load_json, save_json

PASSWORD = os.getenv("STUDIO_PASSWORD", "")
if not PASSWORD:
    sys.exit("Set STUDIO_PASSWORD (and SECRET_KEY) before starting the studio - it is owner-only.")
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  SESSION_COOKIE_SECURE=os.getenv("INSECURE_COOKIES") != "1", MAX_CONTENT_LENGTH=60 * 1024 * 1024)
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
JOBS = {}          # slug -> {"proc", "log", "kind", "started"}
LOCK = threading.Lock()


# ---------- auth + CSRF ----------
@app.before_request
def guard():
    if request.endpoint in ("login", "static", "health"):
        return
    if not session.get("ok"):
        return redirect(url_for("login"))
    if request.method == "POST":
        tok = request.form.get("csrf") or request.headers.get("X-CSRF")
        if not tok or not hmac.compare_digest(tok, session.get("csrf", "")):
            abort(400, "bad CSRF token")


@app.context_processor
def inject():
    session.setdefault("csrf", secrets.token_hex(16))
    return {"csrf": session["csrf"], "quality": QUALITY}


@app.route("/health")
def health():
    return "ok"


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        time.sleep(0.6)
        if hmac.compare_digest(request.form.get("password", ""), PASSWORD):
            session.clear()
            session["ok"] = True
            session["csrf"] = secrets.token_hex(16)
            return redirect(url_for("home"))
        flash("Wrong password")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------- helpers ----------
def pdir(slug):
    if not SLUG.match(slug):
        abort(404)
    p = PROJECTS / slug
    if not p.is_dir():
        abort(404)
    return p


def state(p):
    s = {"slug": p.name, "topic": "", "sources": 0, "facts": 0, "verified": 0, "script": False, "approved": False,
         "voiced": False, "shots": (p / "shotlist.csv").exists(), "video": (p / "video.mp4").exists(), "title": p.name}
    if (p / "meta.json").exists():
        s["topic"] = load_json(p / "meta.json").get("topic", "")
    s["sources"] = len(list((p / "sources").glob("*.txt"))) if (p / "sources").is_dir() else 0
    if (p / "facts.json").exists():
        f = facts_from(load_json(p / "facts.json"))
        s["facts"], s["verified"] = len(f), sum(x.verified for x in f)
    if (p / "script.json").exists():
        d = load_json(p / "script.json")
        s["script"], s["approved"], s["title"] = True, bool(d.get("approved")), d.get("title", p.name)
        s["voiced"] = all(x.get("duration") for x in d["scenes"])
    return s


def start_job(slug, kind, args):
    with LOCK:
        j = JOBS.get(slug)
        if j and j["proc"].poll() is None:
            return False
        p = PROJECTS / slug
        log = p / "job.log"
        fh = open(log, "wb")
        proc = subprocess.Popen([sys.executable, "-u", "main.py", *args], cwd=Path(__file__).parent, stdout=fh,
                                stderr=subprocess.STDOUT, env={**os.environ, "PYTHONUNBUFFERED": "1"})
        JOBS[slug] = {"proc": proc, "log": log, "kind": kind, "started": time.time()}
        return True


# ---------- pages ----------
@app.route("/")
def home():
    PROJECTS.mkdir(parents=True, exist_ok=True)
    items = [state(p) for p in sorted(PROJECTS.iterdir()) if p.is_dir() and p.name != "demo"]
    return render_template("home.html", items=items)


@app.route("/new", methods=["POST"])
def new():
    slug = re.sub(r"[^a-z0-9-]+", "-", request.form["slug"].lower()).strip("-")
    if not SLUG.match(slug):
        flash("Use 2+ letters/numbers for the project name")
        return redirect(url_for("home"))
    p = PROJECTS / slug
    (p / "sources").mkdir(parents=True, exist_ok=True)
    save_json({"topic": request.form.get("topic", slug)[:300]}, p / "meta.json")
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>")
def project(slug):
    p = pdir(slug)
    s = state(p)
    facts = [asdict(f) for f in facts_from(load_json(p / "facts.json"))] if (p / "facts.json").exists() else []
    script = load_json(p / "script.json") if (p / "script.json").exists() else None
    media = sorted(m.name for m in (p / "media").iterdir()) if (p / "media").is_dir() else []
    music = sorted(m.name for m in Path(os.getenv("MUSIC_DIR", Path(__file__).parent / "assets/music")).glob("*")
                   if m.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg"))
    return render_template("project.html", s=s, facts=facts, script=script, media=media, music=music,
                           job=job_info(slug), size=(p / "video.mp4").stat().st_size if s["video"] else 0)


@app.route("/p/<slug>/source", methods=["POST"])
def add_source(slug):
    p = pdir(slug)
    url, text = request.form.get("url", "").strip(), request.form.get("text", "").strip()
    if not url.startswith("http") or len(text) < 200:
        flash("Need a source URL and the pasted text (200+ characters)")
        return redirect(url_for("project", slug=slug))
    n = len(list((p / "sources").glob("*.txt"))) + 1
    (p / "sources" / f"src{n:02d}.txt").write_text(f"URL: {url}\n{text}", encoding="utf-8")
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>/media", methods=["POST"])
def add_media(slug):
    p = pdir(slug)
    f = request.files.get("file")
    if f and Path(f.filename).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp"):
        (p / "media").mkdir(exist_ok=True)
        f.save(p / "media" / re.sub(r"[^A-Za-z0-9._-]", "_", Path(f.filename).name))
    else:
        flash("Upload a .jpg/.png/.webp image")
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>/verify", methods=["POST"])
def verify(slug):
    p = pdir(slug)
    facts = facts_from(load_json(p / "facts.json"))
    ok = set(request.form.getlist("ok"))
    drop = set(request.form.getlist("drop"))
    facts = [f for f in facts if f.id not in drop]
    for f in facts:
        f.verified = f.id in ok
    save_json([asdict(f) for f in facts], p / "facts.json")
    flash(f"{sum(f.verified for f in facts)} facts marked as checked against the source")
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>/script", methods=["POST"])
def save_script(slug):
    """edit narration text in the browser; any edit un-approves the script"""
    p = pdir(slug)
    d = load_json(p / "script.json")
    for s in d["scenes"]:
        t = request.form.get(f"n{s['id']}")
        if t is not None and t.strip() and t.strip() != s["narration"]:
            s["narration"], s["audio_path"], s["duration"] = t.strip(), None, None
    d["approved"] = False
    save_json(d, p / "script.json")
    flash("Saved. Read it again and approve.")
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>/approve", methods=["POST"])
def approve(slug):
    from script import set_approved
    p = pdir(slug)
    if request.form.get("confirm") != "yes":
        flash("Tick the box to confirm you read the script and checked the figures")
    else:
        set_approved(p)
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>/auto", methods=["POST"])
def auto(slug):
    pdir(slug)
    if not start_job(slug, "auto", ["auto", slug, "--minutes", request.form.get("minutes", "22")]):
        flash("A job is already running for this project")
    return redirect(url_for("project", slug=slug))


@app.route("/p/<slug>/review", methods=["GET", "POST"])
def review(slug):
    p = pdir(slug)
    if not (p / "facts.json").exists() or not (p / "script.json").exists():
        flash("Nothing to review yet - run Auto research first, or add sources and write a script")
        return redirect(url_for("project", slug=slug))
    facts = facts_from(load_json(p / "facts.json"))
    if request.method == "POST":
        decisions = {f.id: request.form.get(f"d_{f.id}", "") for f in facts if f.bucket != "batch"}
        dropped = request.form.getlist("drop_batch")
        try:
            audit = pipeline.approve(p, decisions, dropped, request.form.get("confirm") == "yes")
        except pipeline.ReviewError as e:
            flash(str(e))
            return redirect(url_for("review", slug=slug))
        started = start_job(slug, "produce", ["produce", slug])
        flash(f"Approved ({audit['batch_approved']} batch, {audit['manually_approved']} individually, "
              f"{audit['dropped']} dropped). " + ("Voice and 4K render started." if started else "A job is already running."))
        return redirect(url_for("project", slug=slug))
    script = load_json(p / "script.json")
    shots = load_json(p / "shotlist.json")["summary"] if (p / "shotlist.json").exists() else None
    batch = [f for f in facts if f.bucket == "batch"]
    decide = [f for f in facts if f.bucket != "batch"]
    return render_template("review.html", s=state(p), batch=batch, decide=decide, script=script, shots=shots,
                           explain=corroborate.explain, job=job_info(slug))


@app.route("/p/<slug>/run/<step>", methods=["POST"])
def run(slug, step):
    p = pdir(slug)
    topic = load_json(p / "meta.json").get("topic", slug)
    if step == "facts":
        args = ["facts", slug]
    elif step == "script":
        if not state(p)["verified"]:
            flash("Verify at least some facts first")
            return redirect(url_for("project", slug=slug))
        args = ["script", slug, "--minutes", request.form.get("minutes", "22")]
    elif step == "voice":
        if not state(p)["approved"]:
            flash("Approve the script first")
            return redirect(url_for("project", slug=slug))
        args = ["voice", slug]
    elif step == "render":
        if not (state(p)["approved"] and state(p)["voiced"]):
            flash("Approve the script and generate the voice first")
            return redirect(url_for("project", slug=slug))
        args = ["render", slug] + (["--force"] if request.form.get("force") else [])
    else:
        abort(404)
    if not start_job(slug, step, args):
        flash("A job is already running for this project")
    return redirect(url_for("project", slug=slug))


def job_info(slug):
    j = JOBS.get(slug)
    if not j:
        return None
    running = j["proc"].poll() is None
    tail = j["log"].read_text(errors="replace")[-3000:] if j["log"].exists() else ""
    return {"kind": j["kind"], "running": running, "rc": j["proc"].returncode, "tail": tail,
            "elapsed": int(time.time() - j["started"])}


@app.route("/p/<slug>/job")
def job(slug):
    pdir(slug)
    return jsonify(job_info(slug) or {"running": False, "kind": None, "tail": ""})


@app.route("/p/<slug>/job/stop", methods=["POST"])
def job_stop(slug):
    j = JOBS.get(slug)
    if j and j["proc"].poll() is None:
        j["proc"].terminate()
    return redirect(url_for("project", slug=slug))


# ---------- downloads (Range supported => resume + big files work) ----------
FILES = {"video": ("video.mp4", "video/mp4"), "description": ("description.txt", "text/plain"),
         "thumbnail": ("thumbnail.jpg", "image/jpeg"), "script": ("script.txt", "text/plain"),
         "shotlist": ("shotlist.csv", "text/csv")}


@app.route("/p/<slug>/download/<what>")
def download(slug, what):
    p = pdir(slug)
    if what not in FILES:
        abort(404)
    name, mime = FILES[what]
    f = p / name
    if not f.exists():
        abort(404)
    return send_file(f, mimetype=mime, as_attachment=True, download_name=f"{slug}-{name}", conditional=True,
                     max_age=0)


@app.route("/p/<slug>/stream")
def stream(slug):
    f = pdir(slug) / "video.mp4"
    if not f.exists():
        abort(404)
    return send_file(f, mimetype="video/mp4", conditional=True, max_age=0)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), threaded=True)
