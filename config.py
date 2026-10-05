import multiprocessing
import os
import pathlib

ROOT = pathlib.Path(__file__).parent
DATA_DIR = pathlib.Path(os.getenv("DATA_DIR", ROOT))          # set DATA_DIR to a persistent disk
PROJECTS = DATA_DIR / "projects"
ASSETS = ROOT / "assets"
FONT_DIR = ASSETS / "fonts"
MUSIC_DIR = pathlib.Path(os.getenv("MUSIC_DIR", ASSETS / "music"))
BROLL_DIR = ASSETS / "broll"
BRAND_DIR = ASSETS / "brand"          # drop logo.png here (shown top-right, 55% opacity)
CHANNEL_NAME = os.getenv("CHANNEL_NAME", "")   # text bug top-right if no logo.png

# Model used for fact extraction and script writing (override with env var).
MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")

# Voice. edge-tts: en-US-GuyNeural, en-US-AndrewMultilingualNeural, hi-IN-MadhurNeural ...
VOICE = os.getenv("TTS_VOICE", "en-US-GuyNeural")
TTS_ENGINE = os.getenv("TTS_ENGINE", "edge")   # "edge" (real) | "test" (offline robot voice, dev only)

# ---- Picture. QUALITY = 4k (final) | 1080 | preview (fast 720p drafts).
# All layout is designed on a 1920x1080 canvas and scaled, so every tier looks the same.
QUALITIES = {"4k": (3840, 2160), "1080": (1920, 1080), "preview": (1280, 720)}
QUALITY = os.getenv("QUALITY", "4k").lower()
if QUALITY not in QUALITIES:
    raise SystemExit(f"QUALITY must be one of {list(QUALITIES)}")
SIZE = QUALITIES[QUALITY]
W, H = SIZE
SCALE = W / 1920.0
FPS = int(os.getenv("FPS", "24"))
CRF = os.getenv("X264_CRF", {"4k": "16", "1080": "17", "preview": "22"}[QUALITY])
PRESET = os.getenv("X264_PRESET", {"4k": "veryfast", "1080": "fast", "preview": "veryfast"}[QUALITY])
CPU = os.cpu_count() or 2
WORKERS = int(os.getenv("RENDER_WORKERS", max(1, min(CPU, 8))))
SEGMENT_SECONDS = 16          # video is rendered in ~16 s chunks (parallel + resumable)
ENGINE_VERSION = "4"          # bump to invalidate cached chunks after changing the renderer

# ---- Length: finished video (including end screen) must land in this window.
MIN_SECONDS = 20 * 60
MAX_SECONDS = 25 * 60
END_SCREEN_SECONDS = 15
WPS = 2.4  # effective narration words per second at normal pace (incl. pauses)

# ---- Six-act structure from the Gemini framework (share of total runtime).
ACT_SHARE = {
    "cold_open": 0.075,
    "rise": 0.175,
    "flaw": 0.30,
    "collapse": 0.225,
    "lesson": 0.175,
    "outro": 0.05,
}
ACT_TITLES = {
    "cold_open": "The collapse",
    "rise": "Why it looked unstoppable",
    "flaw": "The hidden flaw",
    "collapse": "The domino effect",
    "lesson": "What investors should learn",
    "outro": "The final thought",
}
HOT_ACTS = {"cold_open", "collapse"}          # red-tinted lighting + falling ambient chart
# Longest a single visual may stay on screen before a cut (seconds).
MAX_BEAT = {"cold_open": 3.2, "collapse": 3.6}
DEFAULT_MAX_BEAT = 5.5

# ---- Audio
SR = 48000
VOICE_LEAD = 0.10        # silence before each line of narration
SCENE_TAIL = 0.35        # breathing room after each line
MUSIC_RMS = 0.10         # every music track is normalised to this level first
MUSIC_UNDER = 0.16       # music gain while the narrator speaks
MUSIC_OPEN = 0.45        # music gain in pauses / end screen
MUSIC_XFADE = 1.5        # seconds, crossfade between acts
TARGET_LUFS = -14        # YouTube loudness target

PALETTE = {
    "bg": (30, 34, 42),        # slate grey  #1E222A
    "bg_edge": (11, 13, 18),   # vignette edge
    "panel": (41, 47, 59),
    "panel_hi": (54, 61, 76),
    "text": (240, 238, 232),   # off-white
    "soft": (186, 192, 204),
    "red": (224, 49, 49),      # hazard red  #E03131
    "grey": (122, 131, 148),
    "cool": (74, 96, 130),     # slate-blue light for calm acts
}

DISCLAIMER = "Educational content only. Not financial advice."
