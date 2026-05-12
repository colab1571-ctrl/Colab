"""
Image watermarking using PIL ImageDraw.

Renders semi-transparent diagonal text tiled across the full canvas.
Text: "Colab • Generated for {user_a} & {user_b} • {iso_ts}"
Angle: 30° diagonal
Opacity: 80/255 (semi-transparent white)
Original un-watermarked artifact is discarded; only watermarked version stored.
"""

from __future__ import annotations

import io
import math

from PIL import Image, ImageDraw, ImageFont

from app.config import get_ai_settings


def apply_image_watermark(
    image_bytes: bytes,
    user_a: str,
    user_b: str,
    ts: str,
) -> tuple[bytes, dict]:
    """
    Apply diagonal tiled watermark to an image.

    Args:
        image_bytes: Raw PNG/JPEG bytes from Replicate.
        user_a: Display name of party A.
        user_b: Display name of party B.
        ts: ISO 8601 timestamp string.

    Returns:
        (watermarked_jpeg_bytes, watermark_meta_dict)
    """
    settings = get_ai_settings()
    txt = f"Colab • Generated for {user_a} & {user_b} • {ts}"

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    font_size = max(16, img.height // 50)
    try:
        font = ImageFont.truetype(settings.font_path, font_size)
    except (IOError, OSError):
        font = ImageFont.load_default()

    step_x = max(img.width // 3, 50)
    step_y = max(img.height // 3, 50)

    for x in range(-img.width, img.width * 2, step_x):
        for y in range(-img.height, img.height * 2, step_y):
            draw.text((x, y), txt, font=font, fill=(255, 255, 255, 80))

    rotated = overlay.rotate(30, expand=False)
    composite = Image.alpha_composite(img, rotated).convert("RGB")

    out = io.BytesIO()
    composite.save(out, format="JPEG", quality=92)
    jpeg_bytes = out.getvalue()

    meta = {
        "text_template": "Colab • Generated for {user_a} & {user_b} • {ts}",
        "angle_deg": 30,
        "opacity": 80,
        "font": "DejaVuSans-Bold",
        "font_size_ratio": round(font_size / img.height, 4),
        "grid_step_ratio": 0.333,
    }
    return jpeg_bytes, meta
