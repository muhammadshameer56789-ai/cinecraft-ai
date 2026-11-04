import numpy as np
from PIL import Image

from app import config
from app.services.ai.base import ProviderError


def _lum(img: Image.Image, n: int = 48) -> np.ndarray:
    a = np.asarray(img.convert("L").resize((n, n), Image.BILINEAR), dtype=np.float32)
    return a - a.mean()


def composition_similarity(a: Image.Image, b: Image.Image) -> float:
    """Normalised correlation of coarse luminance layouts. Colour grading keeps it high; a different scene drops it."""
    x, y = _lum(a), _lum(b)
    d = float(np.sqrt((x * x).sum() * (y * y).sum()))
    return float((x * y).sum() / d) if d > 1e-6 else 0.0


def check_composition(original: Image.Image, result: Image.Image) -> float:
    s = composition_similarity(original, result)
    if s < config.AI_MIN_SIMILARITY:
        raise ProviderError("invalid_output", f"The AI result no longer matches your photo's composition (similarity {s:.2f}).")
    return s
