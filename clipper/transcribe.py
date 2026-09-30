"""Transcribe the source once, with word timestamps, for clip picking and captions."""
from __future__ import annotations

import json
import os

from . import REPO
from .config import Spec


def transcribe(spec: Spec) -> dict:
    os.environ.setdefault("HF_HOME", str(REPO / "models"))
    from faster_whisper import WhisperModel

    model = WhisperModel(spec["whisper_model"], device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(spec.p("source")), language=spec["language"],
                                      word_timestamps=True, vad_filter=False)
    segs, words = [], []
    for s in segments:
        segs.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
        words += [{"w": w.word.strip(), "s": round(w.start, 2), "e": round(w.end, 2)} for w in s.words]
    out = {"language": info.language, "duration": info.duration, "segments": segs, "words": words}

    target = spec.p("transcript")
    target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    # A plain "mm:ss text" dump is what an agent actually reads to pick clips.
    lines = [f"{int(s['start'] // 60):02d}:{s['start'] % 60:05.2f}  {s['text']}" for s in segs]
    target.with_suffix(".txt").write_text("\n".join(lines), encoding="utf-8")
    return {"transcript": str(target), "text": str(target.with_suffix(".txt")),
            "segments": len(segs), "words": len(words), "duration": round(info.duration, 1)}
