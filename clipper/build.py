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

SERIF_BOLD = r"C:\Windows\Fonts\georgiab.ttf"
SERIF_ITALIC = r"C:\Windows\Fonts\georgiai.ttf"
# Track layout shared by both styles.
T = {"speaker": 0, "broll": 1, "matte": 2, "title": 3, "caption": 4, "credit": 5, "moment": 6, "voice": 7, "sfx": 8}


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

def letterbox_matte(path: Path, size: tuple[int, int], bar: int) -> Path:
    """Transparent full-frame PNG with black bars top and bottom (a 'movie' moment)."""
    if not path.exists():
        from PIL import Image, ImageDraw
        im = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([0, 0, size[0], bar], fill=(0, 0, 0, 255))
        d.rectangle([0, size[1] - bar, size[0], size[1]], fill=(0, 0, 0, 255))
        im.save(path)
    return path


def build_clip(spec: Spec, clip: dict, spoken: list[dict]) -> dict:
    stage = spec.p("out_dir")
    stage.mkdir(parents=True, exist_ok=True)
    source = spec.p("source")
    font = spec["font"]
    style = clip.get("style", spec.get("style", "hormozi"))
    cine = style == "cinematic"
    tail = 0.8 if cine else 0.0          # cinematic ending: reverb tail + fade to black
    project = clone_template(spec, clip["name"], stage)
    data = json.loads((project / "draft_content.json").read_text(encoding="utf-8"))
    for track in data["tracks"]:
        track["segments"] = []
    data["tracks"] = [t for t in data["tracks"] if t.get("type") == "video"][:1]
    cw, ch = spec["canvas"]
    data["canvas_config"].update({"width": cw, "height": ch, "ratio": "9:16" if cw * 16 == ch * 9 else "original"})
    for kind in ("video", "video", "text", "text", "text", "text", "audio", "audio", "audio"):
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
    video_src = source
    if cine:
        media.add_reverb_tail(voice, tail)
        # Bake the grade into one back-to-back cut of the ranges (the last one runs `tail` s longer).
        extended = ranges[:-1] + [(ranges[-1][0], ranges[-1][1] + tail)]
        video_src = media.render_graded(source, extended, stage / f"{clip['name']}.graded.mp4")
        data["fps"] = 24.0                # source is 24 fps; a 30 fps timeline judders

    # ---- visual events: cuts + B-roll in/out; punch-ins are added until no gap > max_visual_gap
    broll = [(stem, to_tl(s), to_tl(e)) for stem, s, e in clip.get("broll", [])]

    def in_broll(x: float) -> bool:
        return any(a - 0.3 <= x <= b + 0.3 for _, a, b in broll)

    captions = clip["captions"]

    # ---- cinematic moments: letterbox + serif line + slow push-in, captions hidden (default: last punchline)
    moments = []
    if cine:
        for m in clip.get("moments") or []:
            moments.append((to_tl(m[0]), to_tl(m[1]), m[2], m[3] if len(m) > 3 else ""))
        accents = [c for c in captions if len(c) > 3 and c[3]]
        if not moments and accents:
            c = accents[-1]
            ms = to_tl(c[1])
            moments.append((ms, min(max(to_tl(c[2]), ms + 2.4), total + tail), c[0], ""))

    def in_moment(x: float) -> bool:
        return any(a - 0.2 <= x < b for a, b, _, _ in moments)

    events = {0.0, total} | {off for _, _, off in offsets[1:]} | {x for _, a, b in broll for x in (a, b)}
    punches = [(to_tl(c[1]), min(to_tl(c[2]), to_tl(c[1]) + 1.8), 0.12)
               for c in captions if len(c) > 3 and c[3] and not in_broll(to_tl(c[1]))]
    punches = [p for p in punches if not in_moment(p[0]) and not any(p[0] < a < p[1] for a, _, _, _ in moments)]
    punches += [(a, b, 0.10) for a, b, _, _ in moments]
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
    speaker_ids = []
    for i, (a, b) in enumerate(ranges):
        dur, off = b - a + (tail if i == len(ranges) - 1 else 0.0), to_tl(a)
        seg = edits.add_clip(data, str(video_src), start=off, duration=dur,
                             source_start=off if cine else a, track_index=T["speaker"], volume=0.0)
        speaker_ids.append(seg["clip_id"])
        edits.set_crop(data, seg["clip_id"], crop_x, 0.0, crop_w, 1.0)
        base0 = 1.0 if i % 2 == 0 else 1.12          # alternate framing so each jump cut reads as intended

        def base(x: float, base0=base0, dur=dur) -> float:   # slow push-in across the segment
            return base0 + 0.06 * x / dur

        pts = [(0.0, base(0.0))]
        for ps, pe, amp in punches:
            ps, pe = ps - off, pe - off
            pe = min(pe, dur - 0.2)
            if ps < 0.15 or pe - ps < 0.4 or ps <= pts[-1][0] + 0.15:
                continue
            pts += [(ps, base(ps)), (ps + 0.08, base(ps) + amp), (pe - 0.08, base(pe) + amp), (pe, base(pe))]
        pts.append((dur, base(dur)))
        kf = [{"time": round(x, 3), "value": round(v, 4)} for x, v in pts]
        for prop in ("KFTypeScaleX", "KFTypeScaleY"):
            edits.set_keyframes(data, seg["clip_id"], prop, kf)
    if cine:
        edits.add_fade(data, speaker_ids[-1], fade_out=tail)

    # ---- hook title: big, top third, first ~3.6 s
    edits.add_text(data, clip["title"], start=0.0, duration=min(3.6, total), font_size=18.0,
                   color=YELLOW, position=(0.0, 0.66), stroke=(0.0, 0.0, 0.0), stroke_width=0.09,
                   font_path=font, track_index=T["title"])

    # ---- captions: 1-3 word lines; the spoken word lights up (accent lines stay fully yellow)
    n_lines = 0
    for cap in captions:
        accent = len(cap) > 3 and cap[3]
        for line in chunk(word_times(cap, spoken)):
            text = " ".join(w for w, _, _ in line)
            n_lines += 1
            for k, (_, ws, _) in enumerate(line):
                seg_end = line[k + 1][1] if k + 1 < len(line) else line[-1][2]
                start, end = to_tl(ws), to_tl(seg_end)
                if in_moment(start):
                    continue
                end = min([end] + [a for a, _, _, _ in moments if start < a])
                edits.add_text(data, text, start=start, duration=max(end - start, 0.05),
                               font_size=17.5 if accent else 16.0, color=YELLOW if accent else WHITE,
                               position=(0.0, -0.30), stroke=(0.0, 0.0, 0.0), stroke_width=0.08,
                               font_path=font, track_index=T["caption"])
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
        edits.add_text(data, spec["credit"], start=0.0, duration=total + tail, font_size=6.5, color=WHITE,
                       position=(0.0, 0.88), stroke=(0.0, 0.0, 0.0), stroke_width=0.05,
                       font_path=font, track_index=T["credit"])

    # ---- moments: matte + serif line (the optional second line rides the idle caption track)
    matte = letterbox_matte(stage / "_letterbox.png", (cw, ch), round(ch * 0.172))
    for a, b, line1, line2 in moments:
        edits.add_clip(data, str(matte), start=a, duration=b - a, track_index=T["matte"], volume=0.0)
        edits.add_text(data, line1, start=a + 0.15, duration=b - a - 0.15, font_size=15.5, color=WHITE,
                       position=(0.0, -0.76), stroke=None, font_path=SERIF_BOLD, track_index=T["moment"])
        if line2:
            edits.add_text(data, line2, start=a + 0.5, duration=b - a - 0.5, font_size=13.0, color=YELLOW,
                           position=(0.0, -0.86), stroke=None, font_path=SERIF_ITALIC, track_index=T["caption"])

    seg = edits.add_clip(data, str(voice), start=0.0, duration=total + tail, track_index=T["voice"], volume=1.0)
    edits.set_denoise(data, seg["clip_id"], True)

    # ---- B-roll + SFX
    sfx_dir = Path(spec["sfx_dir"])
    hits = [(0.0, "pop", 1.0)] + [(off - 0.15, "whoosh_soft", 1.0) for _, _, off in offsets[1:]]
    for stem, a, b in broll:
        img = spec.p("broll_dir") / f"{stem}.jpg"
        seg = edits.add_clip(data, str(img), start=a, duration=b - a, track_index=T["broll"], volume=0.0)
        kf = [{"time": 0.0, "value": 1.0}, {"time": b - a, "value": 1.08}]
        for prop in ("KFTypeScaleX", "KFTypeScaleY"):
            edits.set_keyframes(data, seg["clip_id"], prop, kf)
        hits.append((a - 0.12, "whoosh_fast", 1.0))
    if moments:   # a riser builds into each moment and the impact lands on it
        for a, _, _, _ in moments:
            hits += [(a - 1.6, "riser", 1.0), (a, "boom", 0.6)]   # quieter impact under the voice
    else:
        hits.append((to_tl(captions[-1][1]), "boom", 1.0))
    for i, (at, name, gain) in enumerate(sorted(hits)):
        edits.add_clip(data, str(sfx_dir / f"{name}.wav"), start=max(0.0, at), track_index=T["sfx"] + i % 2,
                       volume=spec["sfx_volume"][name] * gain)

    ir.recompute_duration(data)
    write_content(project, data)

    out = stage / f"{clip['name']}.mp4"
    preview.render(ir.build(data, clip["name"]), out, height=ch, with_audio=True, font=font)
    report = {"clip": clip["name"], "style": style, "moments": len(moments), "duration": round(total + tail, 2), "source_lufs": loud["source_lufs"],
              "voice_lufs": loud["lufs"], "voice_true_peak": loud["true_peak"], "caption_lines": n_lines, "punch_ins": len(punches),
              "max_visual_gap": round(max_gap, 2), "broll": len(broll),
              "freezes": media.freezes(out), "project": str(project), "preview": str(out)}
    (stage / f"{clip['name']}.report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    return report


def build(spec: Spec, ids: list[str]) -> list[dict]:
    transcript = json.loads(spec.p("transcript").read_text(encoding="utf-8"))
    spoken = transcript.get("words", [])
    return [build_clip(spec, clip, spoken) for _, clip in spec.select(ids)]
