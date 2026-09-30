"""Clip spec loading. A spec is one JSON file per source video (see examples/)."""
from __future__ import annotations

import json
from pathlib import Path

from . import REPO

DEFAULTS = {
    "canvas": [1080, 1920],
    "font": r"C:\Windows\Fonts\seguibl.ttf",   # Segoe UI Black: heavy, Montserrat-Black-like
    "credit": None,                              # e.g. "Sumber: @akun" -- small top-centre text
    "target_lufs": -14.0,
    "max_visual_gap": 5.0,                       # seconds without a cut/B-roll/punch-in
    "transcript": "transcript.json",
    "broll_src": "broll",
    "broll_dir": "broll/916",
    "out_dir": "out",
    "whisper_model": "base",
    "language": "id",
    "sfx_dir": str(REPO / "assets" / "sfx"),
    "style": "hormozi",                         # or "cinematic"; a clip can override with "style"
    "sfx_volume": {"whoosh_soft": 0.12, "whoosh_fast": 0.12, "pop": 0.10, "boom": 0.18, "riser": 0.12},
    "clips": [],
}

YELLOW = (1.0, 0.82, 0.25)
WHITE = (1.0, 1.0, 1.0)


class Spec(dict):
    """A loaded spec; relative paths resolve against the spec file's folder."""

    def __init__(self, path: str | Path):
        path = Path(path).resolve()
        raw = json.loads(path.read_text(encoding="utf-8"))
        super().__init__({**DEFAULTS, **raw})
        self.path = path
        self.dir = path.parent
        for key in ("source", "template_project"):
            if not self.get(key):
                raise ValueError(f"{path.name}: '{key}' is required")

    def p(self, key: str) -> Path:
        """Resolve a path-valued key relative to the spec folder."""
        value = Path(self[key])
        return value if value.is_absolute() else self.dir / value

    def select(self, ids: list[str]) -> list[tuple[int, dict]]:
        """Pick clips by 1-based number or name prefix; all clips when ids is empty."""
        clips = list(enumerate(self["clips"], 1))
        if not ids:
            return clips
        return [(n, c) for n, c in clips
                if str(n) in ids or any(c["name"].lower().startswith(i.lower()) for i in ids)]
