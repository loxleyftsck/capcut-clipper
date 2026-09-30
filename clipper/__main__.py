"""CLI: python -m clipper <command> [spec.json] [clip ids...]

  doctor                      check CapCut, drafts, ffmpeg, fonts, whisper, catalog
  transcribe SPEC             transcript.json (+ .txt) with word timestamps
  broll SPEC                  fit broll_src photos to the canvas -> broll_dir
  build SPEC [ids]            build CapCut projects + previews into out_dir
  audit SPEC [ids]            loudness, freezes, visual gaps, caption stats
  install SPEC [ids]          copy built projects into CapCut (backs up, skips open ones)
  sfx                         regenerate assets/sfx
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from . import REPO


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def doctor() -> dict:
    from capcut_mcp import catalog, paths

    report = paths.probe()
    font = Path(r"C:\Windows\Fonts\seguibl.ttf")
    try:
        import faster_whisper  # noqa: F401
        whisper = True
    except ImportError:
        whisper = False
    catalog.build(force=True)
    report.update({
        "ffmpeg_exe": paths.ffmpeg_exe(),
        "segoe_ui_black": font.is_file(),
        "faster_whisper": whisper,
        "catalog_entries": len(catalog.search("", limit=500)),
        "sfx": sorted(p.name for p in (REPO / "assets" / "sfx").glob("*.wav")),
    })
    if report["catalog_entries"] == 0:
        report.setdefault("warnings", []).append(
            "CapCut catalog is empty: apply one text animation + one transition by hand in any "
            "project, save, close CapCut, then rerun doctor.")
    return report


def audit(spec, ids) -> list[dict]:
    from . import media

    out = []
    for _, clip in spec.select(ids):
        stage = spec.p("out_dir")
        rep_p = stage / f"{clip['name']}.report.json"
        if not rep_p.exists():
            out.append({"clip": clip["name"], "error": "not built"})
            continue
        rep = json.loads(rep_p.read_text(encoding="utf-8"))
        prev = Path(rep["preview"])
        loud = media.loudness(prev)
        issues = []
        if rep["freezes"]:
            issues.append(f"frozen frames at {rep['freezes']}")
        if abs(loud["lufs"] - spec["target_lufs"]) > 2:
            issues.append(f"loudness {loud['lufs']} LUFS (target {spec['target_lufs']})")
        if loud["true_peak"] > -0.5:
            issues.append(f"true peak {loud['true_peak']} dBTP, may clip")
        if rep["max_visual_gap"] > spec["max_visual_gap"] + 0.5:
            issues.append(f"{rep['max_visual_gap']}s without a visual change")
        if not 20 <= rep["duration"] <= 65:
            issues.append(f"duration {rep['duration']}s outside 20-65s")
        if not spec.get("credit"):
            issues.append("no source credit set")
        out.append({**{k: rep[k] for k in ("clip", "duration", "caption_lines", "punch_ins", "broll",
                                            "max_visual_gap")},
                    "preview_lufs": loud["lufs"], "true_peak": loud["true_peak"], "issues": issues or "OK"})
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0] in {"-h", "--help", "help"}:
        print(__doc__)
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "doctor":
        _print(doctor())
        return 0
    if cmd == "sfx":
        from .assets import make_sfx
        _print(make_sfx(REPO / "assets" / "sfx"))
        return 0

    from .config import Spec
    if not rest:
        print(f"usage: python -m clipper {cmd} SPEC.json [clip ids]")
        return 2
    spec, ids = Spec(rest[0]), rest[1:]
    if cmd == "transcribe":
        from .transcribe import transcribe
        _print(transcribe(spec))
    elif cmd == "broll":
        from .assets import prep_broll
        _print(prep_broll(spec))
    elif cmd == "build":
        from .build import build
        _print(build(spec, ids))
    elif cmd == "audit":
        _print(audit(spec, ids))
    elif cmd == "install":
        from .install import install
        _print(install(spec, ids))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
