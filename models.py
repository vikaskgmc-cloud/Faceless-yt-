import json
import pathlib
from dataclasses import dataclass, field, fields, asdict
from typing import Optional

from config import WPS


@dataclass
class Fact:
    id: str
    claim: str
    quote: str            # verbatim excerpt from the source supporting the claim
    source_url: str
    verified: bool = False  # a human sets this after checking the source
    source: str = ""        # source file name (sources/<name>.txt)
    tier: int = 2           # 1 = primary record, 2 = reputable news, 3 = weak
    flags: list = field(default_factory=list)    # corroborated|primary|single_source|allegation|conflict|numbers_not_in_quote|derivative_only
    support: list = field(default_factory=list)  # ids of independent facts that back this one
    bucket: str = ""        # "batch" (one-click review) | "decide" (needs your judgement)
    how: str = ""           # how it became verified: manual | batch
    at: str = ""            # when


@dataclass
class Scene:
    """One narrated line. It carries 1+ visuals; each visual is one 'beat'
    (a cut every ~3-5 s) and the scene's duration is split evenly among them.

    visuals: [{"type": "...", "data": {...}, "sfx": "whoosh|impact|..."}]
    """
    id: int
    act: str
    narration: str
    visuals: list = field(default_factory=list)
    fact_ids: list = field(default_factory=list)
    pace: str = "normal"              # slow | normal | fast
    chapter: str = ""                 # small label shown on the scene's first beat
    audio_path: Optional[str] = None
    duration: Optional[float] = None


PACE_SPEED = {"slow": 0.85, "normal": 1.0, "fast": 1.12}


def est_seconds(text: str, pace: str = "normal") -> float:
    return len(text.split()) / (WPS * PACE_SPEED.get(pace, 1.0))


def save_json(obj, path):
    pathlib.Path(path).write_text(
        json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))


def facts_from(data):
    names = {f.name for f in fields(Fact)}
    return [Fact(**{k: v for k, v in d.items() if k in names}) for d in data]


def scenes_from(data):
    names = {f.name for f in fields(Scene)}
    return [Scene(**{k: v for k, v in s.items() if k in names}) for s in data]


def scenes_to_dicts(scenes):
    return [asdict(s) for s in scenes]
