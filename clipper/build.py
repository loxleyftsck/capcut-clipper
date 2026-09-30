"""Build one 9:16 CapCut project per clip in the spec, plus an ffmpeg preview.

Per clip: clone a real CapCut project with fresh ids, lay the speaker ranges
back to back (jump cuts), centre-crop to 9:16, normalise loudness, add
punch-in zooms until no stretch exceeds `max_visual_gap`, word-by-word
highlighted captions, a hook title, optional credit, B-roll photos and SFX.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from capcut_mcp import edits, ir, paths, preview

from . import media
from .config import WHITE, YELLOW, Spec


# ------------------------------------------------------------------ project

def clone_template(spec: Spec, name: str, stage: Path) -> Path:
    """Copy an existing CapCut project under fresh ids so CapCut sees a new project."""
    root = paths.find_draft_root()
    template = root / spec["template_project"]
    dest = stage / name
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(template, dest, ignore=shutil.ignore_patterns(".locked", ".mcp_backups"))

    content = json.loads((template / "draft_content.json").read_text(encoding="utf-8"))
    meta = json.loads((template / "draft_meta_info.json").read_text(encoding="utf-8"))
    project = json.loads((template / "Timelines" / "project.json").read_text(encoding="utf-8"))
    old_tl, new_tl = content["id"], str(uuid.uuid4()).upper()
    replacements = {
        old_tl: new_tl,
        project["id"]: str(uuid.uuid4()).upper(),
        meta["draft_id"]: str(uuid.uuid4()).upper(),
        meta["draft_fold_path"]: (root / name).as_posix(),
    }
    (dest / "Timelines" / old_tl).rename(dest / "Timelines" / new_tl)
    for f in dest.rglob("*"):
        if f.is_file() and (f.suffix in {".json", ".tmp", ".bak", ".extra"} or f.name == "draft_settings"):
            try:
                text = f.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for old, new in replacements.items():
                text = text.replace(old, new)
            f.write_text(text, encoding="utf-8")
    meta = json.loads((dest / "draft_meta_info.json").read_text(encoding="utf-8"))
    meta["draft_name"] = name
    (dest / "draft_meta_info.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return dest


def write_content(project: Path, data: dict) -> None:
    """Write the timeline plus the sidecar copies CapCut 9.x keeps in sync."""
    text = json.dumps(data, ensure_ascii=False)
    (project / "draft_content.json").write_text(text, encoding="utf-8")
    for extra in [project / "template-2.tmp", *(project / "Timelines").glob("*/draft_content.json"),
                  *(project / "Timelines").glob("*/template*.tmp")]:
        if extra.exists():
            extra.write_text(text, encoding="utf-8")
    meta_p = project / "draft_meta_info.json"
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    meta["tm_duration"] = data["duration"]
    meta_p.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ captions

def word_times(caption: list, spoken: list[dict]) -> list[tuple[str, float, float]]:
    """Split a hand-corrected caption into words carrying their spoken timing.

    Whisper mishears often, so the caption text wins and Whisper only supplies
    timing: when the word counts match each word takes its Whisper start,
    otherwise the caption span is shared out by word length.
    """
    text, s, e = caption[0], caption[1], caption[2]
    words = text.split()
    heard = [w for w in spoken if s - 0.05 <= w["s"] < e - 0.05]
    if len(heard) == len(words):
        starts = [max(s, min(w["s"], e)) for w in heard]
        starts[0] = s
    else:
        weights = [len(w) + 1 for w in words]
        acc, starts = s, []
        for wgt in weights:
            starts.append(acc)
            acc += (e - s) * wgt / sum(weights)
    return list(zip(words, starts, starts[1:] + [e]))


def chunk(words: list, max_words: int = 3, max_chars: int = 16) -> list[list]:
    """Group words into 1-3 word lines short enough to stay on one line."""
    out, cur = [], []
    for w in words:
        line = " ".join(x[0] for x in cur + [w])
        if cur and (len(cur) >= max_words or len(line) > max_chars):
            out.append(cur)
            cur = []
        cur.append(w)
    return out + [cur] if cur else out


def style_runs(material: dict, colors: list[tuple[int, int, tuple]]) -> None:
    """Rewrite a text material as rich text: one style per (start, end, colour) range."""
    payload = json.loads(material["content"])
    base = payload["styles"][0]
    styles = []
    for a, b, col in colors:
        st = json.loads(json.dumps(base))
        st["range"] = [a, b]
        st["fill"]["content"]["solid"]["color"] = list(col)
        styles.append(st)
    payload["styles"] = styles
    material["content"] = json.dumps(payload, ensure_ascii=False)


# ------------------------------------------------------------------ build

def build_clip(spec: Spec, clip: dict, spoken: list[dict]) -> dict:
    stage = spec.p("out_dir")
    stage.mkdir(parents=True, exist_ok=True)
    source = spec.p("source")
    font = spec["font"]
    project = clone_template(spec, clip["name"], stage)
    data = json.loads((project / "draft_content.json").read_text(encoding="utf-8"))
    for track in data["tracks"]:
        track["segments"] = []
    data["tracks"] = [t for t in data["tracks"] if t.get("type") == "video"][:1]
    cw, ch = spec["canvas"]
    data["canvas_config"].update({"width": cw, "height": ch, "ratio": "9:16" if cw * 16 == ch * 9 else "original"})
    # 0 speaker (muted), 1 B-roll, 2 hook title, 3 captions, 4 credit, 5 voice, 6/7 SFX (alternating).
    for kind in ("video", "text", "text", "text", "audio", "audio", "audio"):
        data["tracks"].append({"attribute": 0, "flag": 0, "id": edits.guid(), "is_default_name": True,
                               "name": "", "segments": [], "type": kind})

    ranges = [tuple(r) for r in clip["ranges"]]
    offsets, total = [], 0.0
    for a, b in ranges:
        offsets.append((a, b, total))
        total += b - a

    def to_tl(s: float) -> float:
        for a, b, off in offsets:
            if a - 1e-6 <= s <= b + 1e-6:
                return off + (s - a)
        raise ValueError(f"{clip['name']}: {s}s is outside every range")

    # ---- crop the source to the canvas aspect, centred on the speaker
    info = edits.probe_media(str(source))
    sw, sh = info["width"] or 1920, info["height"] or 1080
    crop_w = min(1.0, (sh * cw / ch) / sw)
    crop_x = clip.get("crop_x", (1 - crop_w) / 2)

    # ---- voice: the speaker ranges rendered as one loudness-normalised, peak-limited track
    voice = stage / f"{clip['name']}.voice.wav"
    loud = media.render_voice(source, ranges, voice, lufs=spec["target_lufs"])

    # ---- visual events: cuts + B-roll in/out; punch-ins are added until no gap > max_visual_gap
    broll = [(stem, to_tl(s), to_tl(e)) for stem, s, e in clip.get("broll", [])]

    def in_broll(x: float) -> bool:
        return any(a - 0.3 <= x <= b + 0.3 for _, a, b in broll)

    captions = clip["captions"]
    events = {0.0, total} | {off for _, _, off in offsets[1:]} | {x for _, a, b in broll for x in (a, b)}
    punches = [(to_tl(c[1]), min(to_tl(c[2]), to_tl(c[1]) + 1.8), 0.12)
               for c in captions if len(c) > 3 and c[3] and not in_broll(to_tl(c[1]))]
    events |= {p[0] for p in punches}
    starts = sorted(to_tl(c[1]) for c in captions)
    while True:
        ev = sorted(events)
        gap, a, b = max((y - x, x, y) for x, y in zip(ev, ev[1:]))
        if gap <= spec["max_visual_gap"]:
            break
        mid = (a + b) / 2
        cands = [c for c in starts if a + 1.0 < c < b - 1.0 and not in_broll(c)] or [mid]
        at = min(cands, key=lambda c: abs(c - mid))
        punches.append((at, min(at + 1.6, b - 0.2), 0.07))
        events.add(at)
    punches.sort()
    ev = sorted(events)
    max_gap = max(y - x for x, y in zip(ev, ev[1:]))

    # ---- speaker ranges
    for i, (a, b) in enumerate(ranges):
        dur, off = b - a, to_tl(a)
        seg = edits.add_clip(data, str(source), start=off, duration=dur, source_start=a, track_index=0,
                             volume=0.0)
        edits.set_crop(data, seg["clip_id"], crop_x, 0.0, crop_w, 1.0)
        base0 = 1.0 if i % 2 == 0 else 1.12          # alternate framing so each jump cut reads as intended

        def base(x: float, base0=base0, dur=dur) -> float:   # slow push-in across the segment
            return base0 + 0.06 * x / dur

        pts = [(0.0, base(0.0))]
        for ps, pe, amp in punches:
            ps, pe = ps - off, pe - off
            if ps < 0.15 or pe > dur - 0.15 or ps <= pts[-1][0] + 0.15:
                continue
            pts += [(ps, base(ps)), (ps + 0.08, base(ps) + amp), (pe - 0.08, base(pe) + amp), (pe, base(pe))]
        pts.append((dur, base(dur)))
        kf = [{"time": round(x, 3), "value": round(v, 4)} for x, v in pts]
        for prop in ("KFTypeScaleX", "KFTypeScaleY"):
            edits.set_keyframes(data, seg["clip_id"], prop, kf)

    # ---- hook title: big, top third, first ~3.6 s
    edits.add_text(data, clip["title"], start=0.0, duration=min(3.6, total), font_size=18.0,
                   color=YELLOW, position=(0.0, 0.66), stroke=(0.0, 0.0, 0.0), stroke_width=0.09,
                   font_path=font, track_index=2)

    # ---- captions: 1-3 word lines; the spoken word lights up (accent lines stay fully yellow)
    n_lines = 0
    for cap in captions:
        accent = len(cap) > 3 and cap[3]
        for line in chunk(word_times(cap, spoken)):
            text = " ".join(w for w, _, _ in line)
            n_lines += 1
            for k, (_, ws, _) in enumerate(line):
                seg_end = line[k + 1][1] if k + 1 < len(line) else line[-1][2]
                start = to_tl(ws)
                edits.add_text(data, text, start=start, duration=max(to_tl(seg_end) - start, 0.05),
                               font_size=17.5 if accent else 16.0, color=YELLOW if accent else WHITE,
                               position=(0.0, -0.30), stroke=(0.0, 0.0, 0.0), stroke_width=0.08,
                               font_path=font, track_index=3)
                if accent:
                    continue
                pos, colors = 0, []
                for j, (w, _, _) in enumerate(line):
                    colors.append((pos, pos + len(w), YELLOW if j == k else WHITE))
                    if j + 1 < len(line):
                        colors.append((pos + len(w), pos + len(w) + 1, WHITE))
                    pos += len(w) + 1
                style_runs(data["materials"]["texts"][-1], colors)

    # ---- source credit
    if spec.get("credit"):
        edits.add_text(data, spec["credit"], start=0.0, duration=total, font_size=6.5, color=WHITE,
                       position=(0.0, 0.88), stroke=(0.0, 0.0, 0.0), stroke_width=0.05,
                       font_path=font, track_index=4)

    seg = edits.add_clip(data, str(voice), start=0.0, duration=total, track_index=5, volume=1.0)
    edits.set_denoise(data, seg["clip_id"], True)

    # ---- B-roll + SFX
    sfx_dir = Path(spec["sfx_dir"])
    hits = [(0.0, "pop")] + [(off - 0.15, "whoosh_soft") for _, _, off in offsets[1:]]
    for stem, a, b in broll:
        img = spec.p("broll_dir") / f"{stem}.jpg"
        seg = edits.add_clip(data, str(img), start=a, duration=b - a, track_index=1, volume=0.0)
        kf = [{"time": 0.0, "value": 1.0}, {"time": b - a, "value": 1.08}]
        for prop in ("KFTypeScaleX", "KFTypeScaleY"):
            edits.set_keyframes(data, seg["clip_id"], prop, kf)
        hits.append((a - 0.12, "whoosh_fast"))
    hits.append((to_tl(captions[-1][1]), "boom"))
    for i, (at, name) in enumerate(sorted(hits)):
        edits.add_clip(data, str(sfx_dir / f"{name}.wav"), start=max(0.0, at), track_index=6 + i % 2,
                       volume=spec["sfx_volume"][name])

    ir.recompute_duration(data)
    write_content(project, data)

    out = stage / f"{clip['name']}.mp4"
    preview.render(ir.build(data, clip["name"]), out, height=ch, with_audio=True, font=font)
    report = {"clip": clip["name"], "duration": round(total, 2), "source_lufs": loud["source_lufs"],
              "voice_lufs": loud["lufs"], "voice_true_peak": loud["true_peak"], "caption_lines": n_lines, "punch_ins": len(punches),
              "max_visual_gap": round(max_gap, 2), "broll": len(broll),
              "freezes": media.freezes(out), "project": str(project), "preview": str(out)}
    (stage / f"{clip['name']}.report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def build(spec: Spec, ids: list[str]) -> list[dict]:
    transcript = json.loads(spec.p("transcript").read_text(encoding="utf-8"))
    spoken = transcript.get("words", [])
    return [build_clip(spec, clip, spoken) for _, clip in spec.select(ids)]
