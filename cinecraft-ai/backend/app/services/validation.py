"""Server-side image validation. Never trusts filename, MIME type or client dimensions."""
import io
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

from app import config

Image.MAX_IMAGE_PIXELS = config.MAX_PIXELS  # decompression-bomb guard


class ImageRejected(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ValidatedImage:
    fmt: str  # JPEG / PNG / WEBP
    width: int
    height: int


def validate_image_bytes(data: bytes) -> ValidatedImage:
    if not data:
        raise ImageRejected("The file is empty.")
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ImageRejected(
            f"The file is larger than {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.", 413
        )
    try:
        with Image.open(io.BytesIO(data)) as img:
            fmt = img.format or ""
            if fmt not in config.ALLOWED_FORMATS:
                raise ImageRejected("Unsupported format. Use JPEG, PNG or WebP.", 415)
            w, h = img.size
            if img.getexif().get(0x0112) in (5, 6, 7, 8):
                w, h = h, w
            if w * h > config.MAX_PIXELS:
                raise ImageRejected(
                    f"The image is too large ({w}x{h}). Maximum is "
                    f"{config.MAX_PIXELS // 1_000_000} megapixels.", 413
                )
        # verify() misses truncated JPEGs, so do a full decode (pixel count is already capped above)
        with Image.open(io.BytesIO(data)) as img:
            img.load()
    except ImageRejected:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError, ValueError):
        raise ImageRejected("This file is not a readable image or it is corrupted.", 422)
    return ValidatedImage(fmt=fmt, width=w, height=h)
