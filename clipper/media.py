"""ffmpeg helpers: tool lookup, loudness, freeze detection."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from capcut_mcp import paths


def ffmpeg() -> str:
    return paths.ffmpeg_exe()


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([ffmpeg(), "-hide_banner", *args], capture_output=True, text=True)


def _loudnorm(stderr: str) -> dict:
    stats = json.loads(re.search(r'\{[^{}]*"input_i"[^{}]*\}', stderr).group(0))
    return {"lufs": float(stats["input_i"]), "true_peak": float(stats["input_tp"])}


def loudness_of_ranges(source: Path, ranges: list) -> dict:
    """Integrated loudness / true peak of several source ranges played back to back."""
    parts = "".join(f"[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS[a{i}];" for i, (a, b) in enumerate(ranges))
    graph = parts + "".join(f"[a{i}]" for i in range(len(ranges))) + \
        f"concat=n={len(ranges)}:v=0:a=1,loudnorm=print_format=json"
    return _loudnorm(run(["-i", str(source), "-filter_complex", graph, "-f", "null", "-"]).stderr)


def render_voice(source: Path, ranges: list, out: Path, lufs: float = -14.0, peak: float = -1.5) -> dict:
    """Cut the speaker ranges back to back and loudness-normalise them (two-pass, linear).

    Boosting quiet speech with clip volume clips its peaks; loudnorm's second
    pass reaches the target loudness while holding true peak under `peak`.
    """
    cut = "".join(f"[0:a]atrim={a}:{b},asetpts=PTS-STARTPTS[a{i}];" for i, (a, b) in enumerate(ranges)) + \
        "".join(f"[a{i}]" for i in range(len(ranges))) + f"concat=n={len(ranges)}:v=0:a=1"
    target = f"I={lufs}:TP={peak}:LRA=11"
    err = run(["-i", str(source), "-filter_complex", f"{cut},loudnorm={target}:print_format=json",
               "-f", "null", "-"]).stderr
    m = json.loads(re.search(r'\{[^{}]*"input_i"[^{}]*\}', err).group(0))
    second = (f"{cut},loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
              f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}"
              f":offset={m['target_offset']}:linear=true,aresample=48000")
    res = run(["-i", str(source), "-filter_complex", second, "-ac", "2", "-y", str(out)])
    if res.returncode != 0 or not out.is_file():
        raise RuntimeError(f"voice render failed: {res.stderr[-800:]}")
    return {"source_lufs": float(m["input_i"]), "source_true_peak": float(m["input_tp"]), **loudness(out)}


def loudness(path: Path) -> dict:
    return _loudnorm(run(["-i", str(path), "-af", "loudnorm=print_format=json", "-f", "null", "-"]).stderr)


def freezes(path: Path, min_seconds: float = 0.5) -> list[float]:
    """Start times of frozen stretches -- a stuck preview shows up here first."""
    err = run(["-i", str(path), "-vf", f"freezedetect=n=0.001:d={min_seconds}", "-map", "0:v",
               "-f", "null", "-"]).stderr
    return [float(x) for x in re.findall(r"freeze_start: ([0-9.]+)", err)]


def frame_sheet(video: Path, times: list[float], out: Path, width: int = 216) -> Path:
    """Tile a few frames side by side for a quick visual QA."""
    height = width * 16 // 9
    inputs, labels = [], []
    for i, t in enumerate(times):
        inputs += ["-ss", f"{t:.2f}", "-i", str(video)]
        labels.append(f"[{i}:v]scale={width}:{height},trim=end_frame=1[f{i}]")
    graph = ";".join(labels) + ";" + "".join(f"[f{i}]" for i in range(len(times))) + \
        f"hstack=inputs={len(times)}" if len(times) > 1 else f"[0:v]scale={width}:{height}"
    run([*inputs, "-filter_complex", graph, "-frames:v", "1", "-y", str(out)])
    return out
