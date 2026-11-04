"""AI services return fixed canvas sizes. Letterbox the photo in, crop it back out, so framing is never changed."""
from PIL import Image, ImageFilter

SUPPORTED = [(1024, 1024), (1536, 1024), (1024, 1536)]


def pick_canvas(w: int, h: int) -> tuple[int, int]:
    r = w / h
    return min(SUPPORTED, key=lambda c: abs(c[0] / c[1] - r))


def to_canvas(img: Image.Image, canvas: tuple[int, int]):
    cw, ch = canvas
    k = min(cw / img.width, ch / img.height)
    nw, nh = max(1, round(img.width * k)), max(1, round(img.height * k))
    fitted = img.resize((nw, nh), Image.LANCZOS)
    bg = img.resize(canvas, Image.BILINEAR).filter(ImageFilter.GaussianBlur(40))  # soft fill, no hard borders
    x0, y0 = (cw - nw) // 2, (ch - nh) // 2
    bg.paste(fitted, (x0, y0))
    return bg, (x0, y0, x0 + nw, y0 + nh)


def from_canvas(out: Image.Image, canvas: tuple[int, int], box, final_size: tuple[int, int]) -> Image.Image:
    return out.convert("RGB").resize(canvas, Image.LANCZOS).crop(box).resize(final_size, Image.LANCZOS)
