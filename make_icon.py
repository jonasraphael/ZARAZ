"""Generates the ZARAZ application icon (zaraz.ico) without extra packages.

The mark follows the original web logo: a rounded ember square with a white,
blocky "Z". Every size is written as an uncompressed 32-bit BMP inside the
ICO container, which Windows accepts for all common icon sizes.
"""

from __future__ import annotations

import struct
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)

# BGRA colours
BACKGROUND = bytes((0x2A, 0x49, 0xB3, 0xFF))  # ember #b3492a
FOREGROUND = bytes((0xFF, 0xFF, 0xFF, 0xFF))  # white

# Rectangles of the "Z" in the 96.81-unit design space of the logo.
RECTS = (
    (24.67, 24.67, 47.47, 11.87),
    (24.67, 36.54, 11.87, 35.61),
    (40.06, 39.98, 23.74, 11.87),
    (40.06, 51.85, 11.87, 20.30),
)
DESIGN_SIZE = 96.81
CORNER_RADIUS = 18.81


def _inside_rounded_square(x: float, y: float, size: int, radius: float) -> bool:
    if radius <= 0:
        return True
    center_x = min(max(x, radius), size - radius)
    center_y = min(max(y, radius), size - radius)
    return (x - center_x) ** 2 + (y - center_y) ** 2 <= radius**2


def _render(size: int) -> bytes:
    """Renders one icon size as top-down BGRA pixels."""
    scale = size / DESIGN_SIZE
    radius = CORNER_RADIUS * scale
    rects = [
        (x * scale, y * scale, w * scale, h * scale) for x, y, w, h in RECTS
    ]

    rows = bytearray()
    for y in range(size):
        for x in range(size):
            px, py = x + 0.5, y + 0.5
            if not _inside_rounded_square(px, py, size, radius):
                rows += b"\x00\x00\x00\x00"
            elif any(
                rx <= px < rx + rw and ry <= py < ry + rh
                for rx, ry, rw, rh in rects
            ):
                rows += FOREGROUND
            else:
                rows += BACKGROUND
    return bytes(rows)


def _bmp_image(size: int, top_down_bgra: bytes) -> bytes:
    """ICO BMP entry: header + bottom-up BGRA rows + AND mask."""
    stride = size * 4
    bottom_up = b"".join(
        top_down_bgra[row * stride : (row + 1) * stride]
        for row in reversed(range(size))
    )
    mask_stride = ((size + 31) // 32) * 4
    and_mask = b"\x00" * (mask_stride * size)
    header = struct.pack(
        "<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
        len(bottom_up) + len(and_mask), 0, 0, 0, 0,
    )
    return header + bottom_up + and_mask


def build_ico(sizes=SIZES) -> bytes:
    """Builds the complete ICO file as bytes."""
    images = [(size, _bmp_image(size, _render(size))) for size in sizes]

    directory = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    payload = b""
    for size, image in images:
        dimension = 0 if size >= 256 else size
        entries += struct.pack(
            "<BBBBHHII", dimension, dimension, 0, 0, 1, 32, len(image), offset
        )
        offset += len(image)
        payload += image
    return directory + entries + payload


def main() -> Path:
    """Writes zaraz.ico next to this script and returns its path."""
    target = Path(__file__).resolve().parent / "zaraz.ico"
    target.write_bytes(build_ico())
    print(f"Wrote {target} ({target.stat().st_size} bytes)")
    return target


if __name__ == "__main__":
    main()
