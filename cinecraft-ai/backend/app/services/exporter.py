"""Export: full-quality render in the requested format, with honest size handling."""
import io
import math
import re
from dataclasses import dataclass

from PIL import Image, ImageCms

from app import config
from app.services import engine
from app.services.limits import heavy

FORMATS = {"jpeg": ("JPEG", "jpg", "image/jpeg"), "png": ("PNG", "png", "image/png"), "webp": ("WEBP", "webp", "image/webp")}


def _srgb_icc() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def source_size(data: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
        if im.getexif().get(0x0112) in (5, 6, 7, 8):  # rotated orientations swap the axes
            w, h = h, w
    return w, h


@dataclass
class ExportResult:
    data: bytes
    filename: str
    mime: str
    width: int
    height: int
    notes: list[str]


def export_image(data, analysis, preset, intensity, adjustments, fmt, quality, max_side, stem) -> ExportResult:
    if fmt not in FORMATS:
        raise ValueError("Unsupported export format.")
    pil_fmt, ext, mime = FORMATS[fmt]
    w, h = source_size(data)
    long_side = max(w, h)
    notes: list[str] = []

    target = long_side
    if max_side:
        if max_side >= long_side:
            notes.append("Not upscaled: exporting at the original size, since upscaling would not add real detail.")
        else:
            target = max_side
    ratio = target / long_side
    if w * h * ratio * ratio > config.EXPORT_MAX_PIXELS:  # memory guard
        target = int(long_side * math.sqrt(config.EXPORT_MAX_PIXELS / (w * h)))
        notes.append(f"Reduced to {target}px on the long edge to stay within the server's {config.EXPORT_MAX_PIXELS // 1_000_000} MP export limit.")

    with heavy():
        x, _ = engine.edit(data, analysis, preset, intensity, None if target >= long_side else target, adjustments)
        img = Image.fromarray((x * 255 + 0.5).astype("uint8"))
        del x
    buf = io.BytesIO()
    icc = _srgb_icc()
    q = max(1, min(100, int(quality)))
    if pil_fmt == "JPEG":
        img.save(buf, "JPEG", quality=q, optimize=True, subsampling=0 if q >= 90 else 2, icc_profile=icc)
    elif pil_fmt == "WEBP":
        img.save(buf, "WEBP", quality=q, method=4, icc_profile=icc)
    else:
        img.save(buf, "PNG", compress_level=6, icc_profile=icc)
    name = f"{stem}-cinecraft-{preset.replace('_', '-')}-{int(round(intensity))}pct.{ext}"
    return ExportResult(buf.getvalue(), name, mime, img.width, img.height, notes)
