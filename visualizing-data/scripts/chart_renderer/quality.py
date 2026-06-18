from __future__ import annotations

from pathlib import Path


def ensure_output_exists(path: Path) -> None:
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError(f"chart output was not created: {path}")


def ensure_png_nonblank(path: Path) -> None:
    if path.suffix.lower() != ".png":
        return

    from PIL import Image, ImageChops

    with Image.open(path).convert("RGB") as image:
        diff = ImageChops.difference(image, Image.new("RGB", image.size, (255, 255, 255)))
        if diff.getbbox() is None:
            raise RuntimeError(f"chart output appears blank: {path}")
