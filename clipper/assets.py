"""B-roll preparation and the synthetic SFX kit."""
from __future__ import annotations

import wave
from pathlib import Path

from .config import Spec


def prep_broll(spec: Spec) -> list[str]:
    """Fit every photo in broll_src to the canvas: cover-crop tall ones, blurred fill for wide ones."""
    from PIL import Image, ImageEnhance, ImageFilter

    W, H = spec["canvas"]
    src, dst = spec.p("broll_src"), spec.p("broll_dir")
    dst.mkdir(parents=True, exist_ok=True)
    done = []
    for f in sorted([*src.glob("*.jpg"), *src.glob("*.jpeg"), *src.glob("*.png")]):
        im = Image.open(f).convert("RGB")
        if im.height / im.width >= (H / W) * 0.7:
            s = max(W / im.width, H / im.height)
            im2 = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
            left, top = (im2.width - W) // 2, (im2.height - H) // 2
            out = im2.crop((left, top, left + W, top + H))
        else:
            s = H / im.height
            bg = im.resize((round(im.width * s), H), Image.LANCZOS)
            left = (bg.width - W) // 2
            bg = bg.crop((left, 0, left + W, H)).filter(ImageFilter.GaussianBlur(40))
            bg = ImageEnhance.Brightness(bg).enhance(0.55)
            fg = im.resize((W, round(im.height * W / im.width)), Image.LANCZOS)
            bg.paste(fg, (0, (H - fg.height) // 2))
            out = bg
        target = dst / f"{f.stem}.jpg"
        out.save(target, quality=92)
        done.append(str(target))
    return done


def make_sfx(out_dir: Path) -> list[str]:
    """Synthesise a small royalty-free SFX kit (44.1 kHz stereo WAV)."""
    import numpy as np

    sr = 44100
    rng = np.random.default_rng(7)
    out_dir.mkdir(parents=True, exist_ok=True)

    def t(d):
        return np.arange(int(sr * d)) / sr

    def save(name, x):
        x = x / (np.max(np.abs(x)) + 1e-9) * 0.9
        with wave.open(str(out_dir / f"{name}.wav"), "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((np.stack([x, x], 1) * 32767).astype(np.int16).tobytes())

    def sweep_noise(d, f0, f1, q=6.0):
        """Band-passed noise whose centre sweeps f0 -> f1 (biquad, per sample)."""
        n = rng.standard_normal(int(sr * d))
        out = np.zeros_like(n)
        fc = np.geomspace(f0, f1, len(n))
        y1 = y2 = 0.0
        for i in range(len(n)):
            w0 = 2 * np.pi * fc[i] / sr
            a = np.sin(w0) / (2 * q)
            y = (a * n[i] + 2 * np.cos(w0) * y1 - (1 - a) * y2) / (1 + a)
            y2, y1 = y1, y
            out[i] = y
        return out

    d = 0.55; tt = t(d); save("whoosh_soft", sweep_noise(d, 300, 2500) * np.sin(np.pi * tt / d) ** 2)
    d = 0.35; tt = t(d); save("whoosh_fast", sweep_noise(d, 600, 5000, 4) * np.sin(np.pi * tt / d) ** 3)
    d = 0.12; tt = t(d); f = 900 * np.exp(-tt * 25) + 300
    save("pop", np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt * 40))
    d = 1.1; tt = t(d); f = 90 * np.exp(-tt * 6) + 38
    boom = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt * 4.5)
    boom[: int(0.01 * sr)] += rng.standard_normal(int(0.01 * sr)) * 0.6
    save("boom", boom)
    d = 1.6; tt = t(d); env = (tt / d) ** 2
    save("riser", sweep_noise(d, 200, 6000, 8) * env
         + 0.3 * np.sin(2 * np.pi * np.cumsum(np.geomspace(200, 900, len(tt))) / sr) * env)
    d = 1.0; tt = t(d)
    save("ding", sum(a * np.sin(2 * np.pi * f * tt) for f, a in [(1318, 1), (2637, .4), (3951, .2)])
         * np.exp(-tt * 5))
    d = 0.04; tt = t(d)
    save("click", rng.standard_normal(len(tt)) * np.exp(-tt * 250) + np.sin(2 * np.pi * 2200 * tt) * np.exp(-tt * 150))
    return sorted(str(p) for p in out_dir.glob("*.wav"))
