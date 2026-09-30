"""Copy built projects into CapCut's draft store (CapCut picks up new folders by itself)."""
from __future__ import annotations

import shutil
import time

from capcut_mcp import paths

from .config import Spec


def install(spec: Spec, ids: list[str]) -> list[str]:
    root = paths.find_draft_root()
    stage = spec.p("out_dir")
    backup = stage / "_backup" / time.strftime("%Y%m%d-%H%M%S")
    done = []
    for _, clip in spec.select(ids):
        src, dest = stage / clip["name"], root / clip["name"]
        if not src.is_dir():
            done.append(f"SKIP (not built): {clip['name']}")
            continue
        if (dest / ".locked").exists():
            done.append(f"SKIP (open in CapCut, close it first): {clip['name']}")
            continue
        if dest.exists():
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copytree(dest, backup / clip["name"])
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        done.append(f"installed: {dest}")
    return done
