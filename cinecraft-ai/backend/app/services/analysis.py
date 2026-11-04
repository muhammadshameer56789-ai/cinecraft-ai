"""Real image analysis. Output feeds `suggested_adjustments`, which the Phase 2 engine consumes."""
import io
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from app import config

try:  # optional: Haar face detection
    import cv2

    _FACE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    if _FACE.empty():
        _FACE = None
except Exception:  # pragma: no cover
    cv2 = None
    _FACE = None


def _load(data: bytes) -> tuple[Image.Image, tuple[int, int], str]:
    with Image.open(io.BytesIO(data)) as raw:
        raw_size = raw.size
        img = ImageOps.exif_transpose(raw).convert("RGB")  # orientation correction
    return img, raw_size, "landscape" if img.width > img.height else "portrait" if img.height > img.width else "square"


def _rgb_to_hsv(arr: np.ndarray) -> np.ndarray:
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    mx, mn = arr.max(-1), arr.min(-1)
    d = mx - mn
    h = np.zeros_like(mx)
    m = d > 1e-6
    rm, gm, bm = m & (mx == r), m & (mx == g) & (mx != r), m & (mx == b) & (mx != r) & (mx != g)
    h[rm] = ((g - b)[rm] / d[rm]) % 6
    h[gm] = (b - r)[gm] / d[gm] + 2
    h[bm] = (r - g)[bm] / d[bm] + 4
    s = np.where(mx > 1e-6, d / np.maximum(mx, 1e-6), 0)
    return np.stack([h * 60.0, s, mx], -1)


def _dominant_colors(img: Image.Image, n: int = 5) -> list[dict]:
    small = img.resize((128, 128))
    q = small.quantize(colors=n, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()[: n * 3]
    counts = sorted(q.getcolors() or [], reverse=True)
    total = sum(c for c, _ in counts) or 1
    return [
        {"hex": "#%02x%02x%02x" % tuple(pal[i * 3 : i * 3 + 3]), "share": round(c / total, 3)}
        for c, i in counts
    ]


def analyze_image(data: bytes) -> dict[str, Any]:
    img, raw_size, orientation = _load(data)
    full_w, full_h = img.size
    scale = config.ANALYSIS_MAX_SIDE / max(full_w, full_h)
    if scale < 1:
        img = img.resize((max(1, round(full_w * scale)), max(1, round(full_h * scale))), Image.LANCZOS)

    arr = np.asarray(img, dtype=np.float32) / 255.0
    luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
    h, w = luma.shape

    mean_l = float(luma.mean())
    p1, p5, p95, p99 = (float(np.percentile(luma, p)) for p in (1, 5, 95, 99))
    contrast = float(luma.std())
    highlight_frac = float((luma > 0.94).mean())
    shadow_frac = float((luma < 0.10).mean())
    clipped_white = float((arr.max(-1) >= 0.99).mean())

    # colour balance (gray-world) and temperature
    mean_rgb = arr.reshape(-1, 3).mean(0)
    r, g, b = (float(x) for x in mean_rgb)
    warmth = (r - b) / max(r + b, 1e-6)  # >0 warm, <0 cool
    temp_label = "warm" if warmth > 0.12 else "cool" if warmth < -0.08 else "neutral"
    gray = (r + g + b) / 3
    cast = {"r": round(r - gray, 4), "g": round(g - gray, 4), "b": round(b - gray, 4)}

    hsv = _rgb_to_hsv(arr)
    sat_mean = float(hsv[..., 1].mean())
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green_mask = (hue >= 70) & (hue <= 170) & (sat > 0.18) & (val > 0.12)
    green_frac = float(green_mask.mean())

    # skin regions: HSV + YCbCr + channel ordering (rejects grey, sand and asphalt better than YCbCr alone)
    ycc = np.asarray(img.convert("YCbCr"), dtype=np.float32)
    cb, cr, yy = ycc[..., 1], ycc[..., 2], ycc[..., 0]
    skin_mask = ((cb >= 80) & (cb <= 122) & (cr >= 138) & (cr <= 170) & (yy > 45)
                 & (hue <= 50) & (sat >= 0.16) & (sat <= 0.62) & (val >= 0.25)
                 & (arr[..., 0] > arr[..., 1]) & (arr[..., 1] > arr[..., 2] - 0.02))
    skin_frac = float(skin_mask.mean())
    sky_mask = (hue >= 190) & (hue <= 250) & (sat > 0.18) & (val > 0.45)
    sky_frac = float(sky_mask.mean())

    # faces (Haar) when OpenCV is installed
    faces: list[dict] | None = None
    if _FACE is not None:
        g8 = cv2.equalizeHist(np.asarray(img.convert("L")))
        found = _FACE.detectMultiScale(g8, 1.05, 4, minSize=(max(20, w // 25), max(20, h // 25)))
        if len(found) == 0 and w > 640:  # tiny faces in big frames: retry at native analysis size with smaller minimum
            found = _FACE.detectMultiScale(g8, 1.05, 3, minSize=(18, 18))
        faces = [
            {"x": round(x / w, 4), "y": round(y / h, 4), "w": round(fw / w, 4), "h": round(fh / h, 4)}
            for (x, y, fw, fh) in found
        ]

    # subject/background separation proxy: centre vs border luminance & colour distance
    cy0, cy1, cx0, cx1 = h // 4, 3 * h // 4, w // 4, 3 * w // 4
    centre = arr[cy0:cy1, cx0:cx1].reshape(-1, 3).mean(0)
    border = np.concatenate([arr[: h // 8].reshape(-1, 3), arr[-h // 8 :].reshape(-1, 3),
                             arr[:, : w // 8].reshape(-1, 3), arr[:, -w // 8 :].reshape(-1, 3)]).mean(0)
    separation = float(np.linalg.norm(centre - border))

    # exposure label
    if mean_l < 0.30:
        exposure = "underexposed"
    elif mean_l > 0.68:
        exposure = "overexposed"
    else:
        exposure = "balanced"

    harsh = highlight_frac > 0.05 and shadow_frac > 0.06 and contrast > 0.26
    is_portrait_likely = bool(faces) or skin_frac > 0.04
    outdoor_greenery = green_frac > 0.12
    outdoor_likely = green_frac > 0.08 or sky_frac > 0.10
    already_warm = warmth > 0.12
    dark_clothing_risk = shadow_frac > 0.18
    low_res = (full_w * full_h) < config.LOW_RES_PIXELS

    # parameters the editing engine will use (Phase 2)
    ev = float(np.clip((0.46 - mean_l) * 2.2, -0.8, 1.2))
    suggested = {
        "exposure_ev": round(ev, 3),
        "shadow_lift": round(float(np.clip(0.15 + shadow_frac * 1.5 + (0.1 if exposure == "underexposed" else 0), 0, 0.6)), 3),
        "highlight_recovery": round(float(np.clip(highlight_frac * 6 + (0.2 if harsh else 0), 0, 0.7)), 3),
        "contrast": round(float(np.clip((0.22 - contrast) * 1.5, -0.25, 0.3)), 3),
        "white_balance_shift": {"r": round(-cast["r"] * 0.8, 4), "b": round(-cast["b"] * 0.8, 4)},
        "warmth_allowed": 0.0 if already_warm else (0.5 if is_portrait_likely else 0.8),
        "green_boost": round(float(np.clip(green_frac * 1.6, 0, 0.6)), 3) if outdoor_greenery else 0.0,
        "skin_protection": 1.0 if is_portrait_likely else 0.3,
        "noise_caution": exposure == "underexposed",
        "golden_hour_suitable": not already_warm,
    }

    scene = []
    if outdoor_greenery: scene.append("outdoor greenery")
    if is_portrait_likely: scene.append("portrait likely")
    if harsh: scene.append("harsh light")
    if already_warm: scene.append("already warm")
    if dark_clothing_risk: scene.append("deep shadows / dark areas")
    if low_res: scene.append("low resolution")

    return {
        "dimensions": {"width": full_w, "height": full_h, "megapixels": round(full_w * full_h / 1e6, 2),
                       "orientation": orientation, "analysed_at": {"width": w, "height": h}},
        "exposure": {"label": exposure, "mean_luminance": round(mean_l, 4), "p1": round(p1, 4), "p5": round(p5, 4),
                     "p95": round(p95, 4), "p99": round(p99, 4)},
        "contrast": round(contrast, 4),
        "highlights": {"fraction_over_94pct": round(highlight_frac, 4), "clipped_white_fraction": round(clipped_white, 4)},
        "shadows": {"fraction_under_10pct": round(shadow_frac, 4)},
        "color": {"temperature": temp_label, "warmth_index": round(warmth, 4), "gray_world_cast": cast,
                  "saturation_mean": round(sat_mean, 4), "dominant_colors": _dominant_colors(img)},
        "foliage": {"green_fraction": round(green_frac, 4)},
        "sky": {"fraction": round(sky_frac, 4)},
        "skin": {"fraction": round(skin_frac, 4), "note": "colour-rule estimate; not a person detector"},
        "faces": {"available": _FACE is not None, "count": None if faces is None else len(faces), "boxes": faces},
        "subject_separation": {"score": round(separation, 4), "note": "centre-vs-border colour distance proxy; no segmentation model loaded"},
        "scene": scene,
        "flags": {"low_resolution": low_res, "harsh_light": harsh, "already_warm": already_warm,
                  "outdoor_greenery": outdoor_greenery, "outdoor_likely": outdoor_likely, "indoor_likely": not outdoor_likely, "portrait_likely": is_portrait_likely},
        "suggested_adjustments": suggested,
    }
