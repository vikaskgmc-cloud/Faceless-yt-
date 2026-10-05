# Case Study Studio - faceless finance documentaries, 4K, 20-25 min

Produces business-case-study videos (motion graphics, charts, flow diagrams, capital stacks, evidence
quotes, ticking collapse act, music + sound design) - not caption slides - and lets you **download the MP4**.

## Run it
**Replit:** replace the old app's files with this folder. Secrets (padlock icon): `ANTHROPIC_API_KEY`,
`STUDIO_PASSWORD` (your sign-in), `SECRET_KEY` (any long random text). Press Run, open the web view, sign in.
**Your own computer (best for 4K):** install Python 3.11 + ffmpeg, `pip install -r requirements.txt`,
then `STUDIO_PASSWORD=... INSECURE_COOKIES=1 python studio.py` and open http://localhost:5000.

## Automatic mode (research -> script -> shot list -> ONE review -> video)
Set the secret `FIRECRAWL_API_KEY` (web research) next to `ANTHROPIC_API_KEY`. On a project page press
**Auto research + draft**. The app searches (court/regulator/lender documents first, then reputable news; social
media, forums and paywalled pages are skipped), extracts exact-quote claims, cross-checks them across
independent publishers, writes the script and a shot list, then stops at the **Review screen**:
- *Needs your decision*: single-source claims, party allegations, conflicting figures, numbers missing from the quote.
- *Batch*: primary records or claims confirmed by an independent outlet (a source that only repeats another does not count).
- Script, warnings, shot list (CSV). Tick the confirmation, press **Approve** -> voice + 4K render start by themselves.
Dropping a claim the script relies on blocks approval until the script is re-drafted. Nothing is ever auto-verified.
CLI: `python main.py auto <slug>` then review in the studio, `python main.py produce <slug>`.
Tests: `QUALITY=preview TTS_ENGINE=test python tests/test_automation.py` (45 checks, offline).
Not tested against the live Firecrawl API (written to its documented v2 search/scrape endpoints).

## Real video clips (stock footage)
Scenes can use a `clip` visual: moving stock video (graded to the channel look, slow push-in, always labelled
STOCK FOOTAGE, captions can't contain numbers). Set `PEXELS_API_KEY` (free) and Auto mode downloads HD clips
for each clip's search query and adds the credit to description.txt. Without the key, clip scenes fall back to
caption cards and the shot list marks them MISSING. You can also drop your own .mp4 files into a project's media
folder and set `"file"` (+ `"own": true` to hide the stock label). Tests: 56 checks, offline.

## Workflow (in the browser)
1. New case study -> paste each source (URL + full text) -> *Extract facts* (quotes are checked to exist in the source).
2. Tick every fact you personally checked against the source (drop wrong ones).
3. *Write script* (20-25 min, six acts) -> edit any line -> tick the confirmation -> *Approve*.
4. *Generate voiceover* -> *Render*. When done, the page shows the video, a **Download MP4** button,
   description (chapters + sources) and thumbnail frame. Voice and render stay locked until you approve.

## Speed / limits (honest numbers)
Measured on 2 CPU cores: 4K renders ~10 fps, so a 22-minute video (~32,000 frames) takes ~50 min;
more cores scale almost linearly (`RENDER_WORKERS`). Replit's free/small machines are slower and have
small disks (a 4K file is ~1.5 GB): use a **Reserved VM / Deployment** (4+ vCPU, 8 GB) or your own PC.
`QUALITY=1080` is ~4x faster; `QUALITY=preview` for drafts. Renders resume if interrupted.
Edit-and-re-render only redraws changed 16 s chunks.

## Music, media
Put licensed tracks in `assets/music/` (`cold_open.mp3 rise.mp3 flaw.mp3 collapse.mp3 lesson.mp3 outro.mp3`
or `default.mp3`) and keep the license/credit (it is added to description.txt). Upload document images
or photos you have rights to in the project page; the script can use them as slow-zoom evidence shots.

## Offline test
`QUALITY=preview TTS_ENGINE=test python main.py demo` makes a 1-minute demo of every visual type (robot voice,
dev only). Real projects use edge-tts and fail loudly if voice generation fails - never a silent video.

## Content rules built in
Educational only, no buy/sell advice, on-screen disclaimer, attribution wording, every number needs a verified
fact id or an "illustrative" tag, quotes must be verbatim from a verified fact.
