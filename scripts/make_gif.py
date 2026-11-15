"""Assemble docs/demo/frames/*.png into the README demo GIF (docs/images/demo.gif) with Pillow."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    frames = sorted((ROOT / "docs" / "demo" / "frames").glob("*.png"))
    imgs = [Image.open(f).convert("RGB").resize((960, 600)) for f in frames]
    pal = [im.quantize(colors=128, method=Image.Quantize.MEDIANCUT) for im in imgs]
    out = ROOT / "docs" / "images" / "demo.gif"
    pal[0].save(out, save_all=True, append_images=pal[1:], duration=2500, loop=0, optimize=True)
    print(out, len(frames), "frames", round(out.stat().st_size / 1e6, 2), "MB")
