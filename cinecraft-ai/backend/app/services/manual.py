"""Manual adjustments. Defined behaviour: they LAYER ON TOP of the selected preset and are independent of the
intensity slider (intensity scales the preset only). Changing preset keeps manual values; 'Reset' clears them."""
from dataclasses import replace

from app.services.presets import Look

# name -> (min, max). All sliders use a -100..100 scale unless the effect is one-directional.
LIMITS: dict[str, tuple[float, float]] = {
    "exposure": (-100, 100), "brightness": (-100, 100), "contrast": (-100, 100), "highlights": (-100, 100),
    "shadows": (-100, 100), "temperature": (-100, 100), "tint": (-100, 100), "saturation": (-100, 100),
    "vibrance": (-100, 100), "sharpness": (0, 100), "fade": (0, 100), "vignette": (0, 100), "grain": (0, 100),
    "green_intensity": (-100, 100), "golden_intensity": (-100, 100),
}


def clean(adj: dict | None) -> dict[str, float]:
    out = {}
    for k, v in (adj or {}).items():
        if k in LIMITS and v:
            lo, hi = LIMITS[k]
            v = max(lo, min(hi, float(v)))
            if v:
                out[k] = v
    return out


def is_neutral(adj: dict | None) -> bool:
    return not clean(adj)


def apply_manual(look: Look, adj: dict | None) -> Look:
    a = clean(adj)
    if not a:
        return look
    g = lambda k: a.get(k, 0.0) / 100.0
    return replace(
        look,
        exposure_ev=look.exposure_ev + g("exposure") * 2.0,
        brightness=look.brightness + g("brightness"),
        contrast=look.contrast + g("contrast") * 0.6,
        highlight_recovery=look.highlight_recovery - g("highlights") * 0.8,   # slider down = recover highlights
        shadow_lift=look.shadow_lift + g("shadows") * 0.8,
        warmth=look.warmth + g("temperature") * 0.8,
        tint=look.tint + g("tint"),
        saturation=look.saturation + g("saturation"),
        vibrance=look.vibrance + g("vibrance") * 0.8,
        sharpen=look.sharpen + g("sharpness"),
        fade=look.fade + g("fade") * 0.2,
        vignette=look.vignette + g("vignette"),
        grain=look.grain + g("grain") * 0.6,
        green_hue_shift=look.green_hue_shift + g("green_intensity") * 15,
        green_sat=look.green_sat + g("green_intensity") * 0.5,
        green_lum=look.green_lum - g("green_intensity") * 0.1,
        golden_highlights=look.golden_highlights + g("golden_intensity") * 0.8,
        glow=look.glow + g("golden_intensity") * 0.5,
    )
