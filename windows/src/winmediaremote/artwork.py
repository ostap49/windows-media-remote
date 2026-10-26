"""Cover art -> 45x45 monochrome poster for the Flipper ARTWORK frame."""
from __future__ import annotations

import io
import struct

SIDE = 45
STRIDE = 6
MAX_IMAGE_BYTES = 4 * 1024 * 1024


def _blurred(gray: list[int]) -> list[int]:
    """A small blur removes details that become stray pixels at 45x45."""
    horizontal = [0] * len(gray)
    for y in range(SIDE):
        row = y * SIDE
        for x in range(SIDE):
            left, right = gray[row + max(0, x - 1)], gray[row + min(SIDE - 1, x + 1)]
            horizontal[row + x] = (left + 7 * gray[row + x] + right + 4) // 9
    result = [0] * len(gray)
    for y in range(SIDE):
        for x in range(SIDE):
            top = horizontal[max(0, y - 1) * SIDE + x]
            bottom = horizontal[min(SIDE - 1, y + 1) * SIDE + x]
            result[y * SIDE + x] = (top + 7 * horizontal[y * SIDE + x] + bottom + 4) // 9
    return result


def _grayscale(image_data: bytes) -> list[int] | None:
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(image_data)) as image:
            if not (0 < image.width <= 16384 and 0 < image.height <= 16384):
                return None
            image = image.convert("RGBA")
            background = Image.new("RGBA", image.size, (255, 255, 255, 255))
            flattened = Image.alpha_composite(background, image).convert("L")
            fitted = ImageOps.fit(flattened, (SIDE, SIDE), Image.Resampling.LANCZOS)
            return list(fitted.tobytes())
    except Exception:
        return None


def pixels(image_data: bytes | None) -> bytes | None:
    """270 bytes, rows of 6 bytes, LSB first, 1 = black; None if unusable."""
    if not image_data or len(image_data) > MAX_IMAGE_BYTES:
        return None
    gray = _grayscale(image_data)
    if gray is None:
        return None
    smoothed = _blurred(gray)
    ordered = sorted(smoothed)
    lower = ordered[(len(ordered) - 1) * 12 // 100]
    upper = ordered[(len(ordered) - 1) * 88 // 100]
    # Flat images (all black or all white) would otherwise turn fully black.
    cutoff = (48 * lower + 52 * upper) // 100 if upper - lower >= 16 else 127
    out = bytearray(SIDE * STRIDE)
    for y in range(SIDE):
        for x in range(SIDE):
            if smoothed[y * SIDE + x] <= cutoff:
                out[y * STRIDE + x // 8] |= 1 << (x % 8)
    return bytes(out)


def payload(image_data: bytes | None, epoch: int, revision: int) -> bytes:
    head = struct.pack("<II", epoch, revision)
    bitmap = pixels(image_data)
    if bitmap is None:
        return head + bytes(4)
    return head + bytes((SIDE, SIDE, 1, 0)) + bitmap
