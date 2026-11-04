"""Local image-processing engine (NumPy + OpenCV). All steps are deterministic."""
import io

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageOps

from app.services.adaptation import resolve, white_balance_gains
from app.services.manual import apply_manual, is_neutral
from app.services.presets import Look, scale


def _smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0.0, 1.0)
    return t * t * (3 - 2 * t)


def _blur(a: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur; wide blurs run on a downscaled copy (same look, far faster on large photos)."""
    if sigma <= 3.0:
        return cv2.GaussianBlur(a, (0, 0), sigma)
    f = int(sigma / 3.0)
    h, w = a.shape[:2]
    small = cv2.resize(a, (max(1, w // f), max(1, h // f)), interpolation=cv2.INTER_AREA)
    small = cv2.GaussianBlur(small, (0, 0), sigma / f)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)


def load_rgb(data: bytes, max_side: int | None = None) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as raw:
        icc = raw.info.get("icc_profile")
        img = ImageOps.exif_transpose(raw).convert("RGB")
    if icc:  # work in sRGB so previews, edits and exports share one colour space
        try:
            img = ImageCms.profileToProfile(img, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                            ImageCms.createProfile("sRGB"), outputMode="RGB")
        except Exception:
            pass  # unreadable profile: treat pixels as sRGB
    if max_side and max(img.size) > max_side:
        r = max_side / max(img.size)
        img = img.resize((max(1, round(img.width * r)), max(1, round(img.height * r))), Image.LANCZOS)
    return np.asarray(img, dtype=np.float32) / 255.0


def skin_mask(x: np.ndarray, faces: list[dict] | None = None) -> np.ndarray:
    """Soft 0..1 skin mask from colour rules, boosted inside detected faces."""
    u8 = (np.clip(x, 0, 1) * 255).astype(np.uint8)
    ycc = cv2.cvtColor(u8, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    hsv = cv2.cvtColor(x.astype(np.float32), cv2.COLOR_RGB2HSV)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    m = ((ycc[..., 2] >= 80) & (ycc[..., 2] <= 122) & (ycc[..., 1] >= 138) & (ycc[..., 1] <= 170)
         & (h <= 50) & (s >= 0.16) & (s <= 0.65) & (v >= 0.25) & (x[..., 0] > x[..., 1])).astype(np.float32)
    H, W = m.shape
    for f in faces or []:
        cx, cy = (f["x"] + f["w"] / 2) * W, (f["y"] + f["h"] / 2) * H
        axes = (int(f["w"] * W * 0.7), int(f["h"] * H * 0.8))
        face = np.zeros_like(m)
        cv2.ellipse(face, (int(cx), int(cy)), axes, 0, 0, 360, 1.0, -1)
        m = np.maximum(m, face * 0.8)
    k = max(3, (max(H, W) // 150) | 1)
    return np.clip(cv2.GaussianBlur(m, (k * 2 + 1, k * 2 + 1), 0) * 1.4, 0, 1)


def render(x: np.ndarray, look: Look, analysis: dict, skin_protect: float | None = None) -> np.ndarray:
    """Apply a resolved Look to float RGB (0..1). `look` must already be scaled by intensity."""
    H, W = x.shape[:2]
    scale_px = max(H, W) / 1500.0
    faces = (analysis.get("faces") or {}).get("boxes")
    sp = analysis["suggested_adjustments"]["skin_protection"] if skin_protect is None else skin_protect
    skin = skin_mask(x, faces)[..., None] * sp
    src_luma = 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]  # for the shadow-detail guard below

    # 1. exposure + white balance + warmth, in (approximate) linear light
    lin = np.power(np.clip(x, 0, 1), 2.2)
    lin *= 2.0 ** look.exposure_ev
    gr, gb = white_balance_gains(analysis, look.wb_strength)
    gains = np.array([gr * (1 + look.warmth * 0.12), 1.0 - look.tint * 0.05, gb * (1 - look.warmth * 0.14)], np.float32)
    # skin keeps most of its original balance so warm grading does not turn faces orange
    lin = lin * (1 + (gains - 1) * (1 - 0.55 * skin))
    x = np.power(np.clip(lin, 0, 4), 1 / 2.2)

    luma = lambda a: 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]
    L = luma(np.clip(x, 0, 1))

    # 2. highlight recovery (soft compression) and shadow lift
    x = x * (1 - look.highlight_recovery * 0.5 * _smooth(L, 0.55, 1.0))[..., None]
    L = luma(np.clip(x, 0, 1))
    x = x + (look.shadow_lift * 0.22 * (1 - _smooth(L, 0.0, 0.55)) * (1 - x.mean(-1)))[..., None]
    x = np.clip(x, 0, 1)

    # 3. contrast on luminance (S-curve), preserves hue
    L = luma(x)
    if look.contrast:
        Lc = L + look.contrast * (_smooth(L, 0, 1) - L)
        x = x * np.clip(Lc / np.maximum(L, 1e-4), 0, 3)[..., None]
        x = np.clip(x, 0, 1)

    if look.brightness:
        x = np.power(np.clip(x, 1e-6, 1.0), 2.0 ** (-look.brightness))

    # 4. clarity (local contrast on luminance)
    if look.clarity:
        L = luma(x)
        blur = _blur(L, max(H, W) / 60.0)
        d = (L - blur) * look.clarity * 0.8
        x = np.clip(x * np.clip((L + d) / np.maximum(L, 1e-4), 0, 2)[..., None], 0, 1)

    # 5. fade + split toning
    if look.fade:
        x = look.fade + x * (1 - look.fade)
    L = luma(x)
    ws, wh = (1 - _smooth(L, 0.1, 0.55))[..., None], _smooth(L, 0.45, 0.95)[..., None]
    x = x + ws * np.array(look.shadow_tint, np.float32) + wh * np.array(look.highlight_tint, np.float32) * (1 - 0.5 * skin)
    x = np.clip(x, 0, 1)

    # 5b. shadow-detail guard: tone curves and lifted blacks flatten fine texture in dark areas (black clothing, deep foliage).
    # Restore only what was lost, never more than the original amplitude, so noise is not amplified.
    for sig in (max(1.0, max(H, W) / 400.0), max(2.0, max(H, W) / 80.0), max(4.0, max(H, W) / 20.0)):  # texture, folds, shading
        L = luma(x)
        hp_in = src_luma - _blur(src_luma, sig)
        hp_out = L - _blur(L, sig)
        deficit = np.where(np.abs(hp_in) > np.abs(hp_out), hp_in - hp_out, 0.0)
        w_dark = 1 - _smooth(L, 0.08, 0.45)
        x = np.clip(x * np.clip((L + 0.9 * deficit * w_dark) / np.maximum(L, 1e-4), 0.5, 2.0)[..., None], 0, 1)

    # 6. selective greens (HSV): shift toward golden, adjust saturation and depth
    if look.green_hue_shift or look.green_sat or look.green_lum:
        hsv = cv2.cvtColor(x.astype(np.float32), cv2.COLOR_RGB2HSV)
        h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        wg = _smooth(h, 55, 85) * (1 - _smooth(h, 150, 175)) * _smooth(s, 0.08, 0.3)
        wg = wg * (1 - skin[..., 0])
        hsv[..., 0] = h - look.green_hue_shift * wg
        hsv[..., 1] = np.clip(s * (1 + look.green_sat * wg), 0, 1)
        hsv[..., 2] = np.clip(v * (1 + look.green_lum * wg), 0, 1)
        x = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    # 7. golden highlights + directional glow
    L = luma(x)
    if look.golden_highlights:
        w = (look.golden_highlights * _smooth(L, 0.45, 0.95) * (1 - 0.6 * skin[..., 0]))[..., None]
        x = x * (1 + w * np.array([0.2, 0.1, -0.18], np.float32))
    if look.glow:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        d = np.sqrt(((xx / W) - look.glow_x) ** 2 + ((yy / H) - look.glow_y) ** 2)
        g = np.clip(1 - d / 0.9, 0, 1) ** 1.6
        g = (g * look.glow * (1 - 0.5 * skin[..., 0]))[..., None]
        x = x + g * np.array([0.16, 0.085, 0.0], np.float32) * (1 - x * 0.6)
    x = np.clip(x, 0, 1)

    # 8. saturation / vibrance
    if look.saturation or look.vibrance:
        hsv = cv2.cvtColor(x.astype(np.float32), cv2.COLOR_RGB2HSV)
        s = hsv[..., 1]
        s = s * (1 + look.saturation) * (1 + look.vibrance * (1 - s) * (1 - 0.5 * skin[..., 0]))
        hsv[..., 1] = np.clip(s, 0, 1)
        x = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    # 9. vignette, sharpen, grain
    if look.vignette:
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r2 = ((xx / W - 0.5) ** 2 + (yy / H - 0.5) ** 2) * 2
        x = x * (1 - look.vignette * 0.5 * np.clip(r2, 0, 1) ** 1.5)[..., None]
    if look.sharpen:
        blur = cv2.GaussianBlur(x, (0, 0), 1.0 * max(scale_px, 0.5))
        x = x + (x - blur) * look.sharpen * 0.8
    if look.grain:
        rng = np.random.default_rng(1234)
        n = rng.normal(0, 1, (H, W)).astype(np.float32)
        n = cv2.GaussianBlur(n, (0, 0), 0.6 * max(scale_px, 0.5))
        L = luma(np.clip(x, 0, 1))
        x = x + (n * look.grain * 0.05 * (1 - np.abs(L - 0.5) * 1.2))[..., None]
    return np.clip(x, 0, 1)


def edit(data: bytes, analysis: dict, preset_id: str, intensity: float, max_side: int | None = None,
         adjustments: dict | None = None) -> tuple[np.ndarray, dict]:
    """Full pipeline. Order: preset (adapted to the photo, scaled by intensity) -> manual adjustments layered on top.
    intensity is 0..100 and scales the preset only. With intensity 0 and no manual changes the original is returned."""
    x = load_rgb(data, max_side)
    t = float(np.clip(intensity, 0, 100)) / 100.0
    look, note = resolve(preset_id, analysis)
    info = {"preset": preset_id, "intensity": intensity, "mode": "local", "auto_note": note}
    if t == 0 and is_neutral(adjustments):
        return x, info
    final = apply_manual(scale(look, t), adjustments)
    out = render(x, final, analysis)
    # denoise only when we lifted a dark, noisy image
    if analysis["suggested_adjustments"]["noise_caution"] and final.shadow_lift > 0.12:
        u8 = (out * 255 + 0.5).astype(np.uint8)
        u8 = cv2.bilateralFilter(u8, 5, 18, 5)
        out = u8.astype(np.float32) / 255.0
        info["denoise"] = True
    return out, info


def to_jpeg(x: np.ndarray, quality: int = 90) -> bytes:
    buf = io.BytesIO()
    Image.fromarray((np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)).save(buf, "JPEG", quality=quality, subsampling=0)
    return buf.getvalue()
