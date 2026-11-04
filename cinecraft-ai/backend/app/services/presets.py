"""Preset library. A Look is the full-strength parameter set; intensity scales it from neutral."""
from dataclasses import dataclass, field, fields, replace

Tint = tuple[float, float, float]


@dataclass(frozen=True)
class Look:
    exposure_ev: float = 0.0
    wb_strength: float = 0.0        # how much of the analysis white-balance correction to apply (0..1)
    warmth: float = 0.0             # -1 cool .. +1 warm
    tint: float = 0.0               # -1 green .. +1 magenta
    highlight_recovery: float = 0.0
    shadow_lift: float = 0.0
    contrast: float = 0.0
    brightness: float = 0.0         # gamma-style midtone brightness, -1..1
    fade: float = 0.0
    clarity: float = 0.0            # local contrast
    shadow_tint: Tint = (0.0, 0.0, 0.0)
    highlight_tint: Tint = (0.0, 0.0, 0.0)
    saturation: float = 0.0
    vibrance: float = 0.0
    green_hue_shift: float = 0.0    # degrees; greens move toward yellow-gold
    green_sat: float = 0.0
    green_lum: float = 0.0          # negative = deeper greens
    golden_highlights: float = 0.0
    glow: float = 0.0               # directional warm light
    vignette: float = 0.0
    grain: float = 0.0
    sharpen: float = 0.0
    auto_exposure: float = 0.8      # how much of the analysed exposure correction this look accepts
    glow_x: float = 0.85            # light direction (0..1 image coordinates)
    glow_y: float = 0.1


NEUTRAL = Look(auto_exposure=0.0)
_META = {"auto_exposure", "glow_x", "glow_y"}  # not interpolated by intensity

PRESETS: dict[str, dict] = {
    "golden_hour": dict(name="Golden Hour", purpose="Warm, sunlit outdoor portraits",
        look=Look(warmth=0.55, contrast=0.24, fade=0.0, clarity=0.18, highlight_recovery=0.25, shadow_lift=0.05,
                  highlight_tint=(0.03, 0.012, -0.03), shadow_tint=(-0.004, 0.0, 0.01), saturation=0.05, vibrance=0.18,
                  green_hue_shift=20, green_sat=0.3, green_lum=-0.06, golden_highlights=0.8, glow=0.45, vignette=0.14, wb_strength=0.3)),
    "cinematic_green": dict(name="Cinematic Green", purpose="Outdoor portraits with trees and vegetation",
        look=Look(warmth=0.2, contrast=0.27, clarity=0.22, shadow_lift=0.03, highlight_tint=(0.02, 0.008, -0.015),
                  shadow_tint=(-0.006, 0.006, 0.0), saturation=-0.03, vibrance=0.1, green_hue_shift=6, green_sat=0.35,
                  green_lum=-0.22, golden_highlights=0.3, vignette=0.2, wb_strength=0.4)),
    "warm_editorial": dict(name="Warm Editorial", purpose="Professional lifestyle photography",
        look=Look(warmth=0.3, contrast=0.1, fade=0.04, clarity=0.05, highlight_recovery=0.35, saturation=-0.12, vibrance=0.08,
                  highlight_tint=(0.02, 0.01, -0.01), shadow_tint=(0.01, 0.004, 0.0), green_hue_shift=8, green_sat=-0.15,
                  vignette=0.08, wb_strength=0.5)),
    "moody_cinema": dict(name="Moody Cinema", purpose="Dramatic outdoor portraits",
        look=Look(exposure_ev=-0.18, contrast=0.35, fade=0.02, clarity=0.2, saturation=-0.2, shadow_tint=(-0.012, 0.0, 0.014),
                  highlight_tint=(0.02, 0.008, -0.01), green_hue_shift=4, green_lum=-0.25, vignette=0.35, wb_strength=0.3,
                  auto_exposure=0.3)),
    "natural_pro": dict(name="Natural Pro", purpose="Clean, realistic professional look",
        look=Look(wb_strength=1.0, contrast=0.08, clarity=0.12, shadow_lift=0.1, highlight_recovery=0.3, saturation=0.02,
                  vibrance=0.12, sharpen=0.35)),
    "golden_forest": dict(name="Golden Forest", purpose="Parks and wooded areas",
        look=Look(warmth=0.45, contrast=0.3, clarity=0.2, shadow_lift=0.03, highlight_tint=(0.03, 0.014, -0.03), shadow_tint=(-0.004, 0.006, -0.004),
                  vibrance=0.14, green_hue_shift=28, green_sat=0.5, green_lum=-0.08, golden_highlights=0.9, glow=0.5,
                  vignette=0.18, wb_strength=0.3)),
    "dark_luxury": dict(name="Dark Luxury", purpose="Premium fashion and portrait photography",
        look=Look(exposure_ev=-0.12, contrast=0.4, fade=0.0, clarity=0.25, shadow_lift=0.08, highlight_recovery=0.4,
                  saturation=-0.3, shadow_tint=(0.0, 0.0, 0.006), highlight_tint=(0.012, 0.008, 0.0), vignette=0.3,
                  wb_strength=0.5, auto_exposure=0.4)),
    "sunset_glow": dict(name="Sunset Glow", purpose="Warm, atmospheric portraits",
        look=Look(warmth=0.65, contrast=0.2, saturation=0.1, highlight_tint=(0.045, 0.015, -0.02), shadow_tint=(0.012, -0.004, 0.012),
                  green_hue_shift=12, golden_highlights=1.0, glow=0.75, glow_x=0.9, glow_y=0.5, vignette=0.15, wb_strength=0.2)),
    "soft_film": dict(name="Soft Film", purpose="Subtle analog-film look",
        look=Look(warmth=0.1, contrast=-0.08, fade=0.08, clarity=-0.05, shadow_lift=0.15, highlight_recovery=0.3, saturation=-0.1,
                  highlight_tint=(0.012, 0.008, -0.006), shadow_tint=(-0.004, 0.004, 0.01), grain=0.25, vignette=0.1, wb_strength=0.4)),
}
AUTO_ID = "auto_cinematic"
PRESET_ORDER = ["auto_cinematic", "golden_hour", "cinematic_green", "warm_editorial", "moody_cinema",
                "natural_pro", "golden_forest", "dark_luxury", "sunset_glow", "soft_film"]


def _num_fields():
    return [f.name for f in fields(Look) if f.name not in _META]


def blend(looks: list[Look], weights: list[float]) -> Look:
    total = sum(weights) or 1.0
    ws = [w / total for w in weights]
    out = {}
    for f in fields(Look):
        vals = [getattr(l, f.name) for l in looks]
        if isinstance(vals[0], tuple):
            out[f.name] = tuple(sum(w * v[i] for w, v in zip(ws, vals)) for i in range(3))
        else:
            out[f.name] = sum(w * v for w, v in zip(ws, vals))
    return Look(**out)


def scale(look: Look, t: float) -> Look:
    """Intensity: interpolate every parameter from neutral (t=0) to full (t=1). Parameters, not pixels, are blended."""
    out = {}
    for f in fields(Look):
        v = getattr(look, f.name)
        if f.name in _META:
            out[f.name] = v
        elif isinstance(v, tuple):
            out[f.name] = tuple(x * t for x in v)
        else:
            out[f.name] = v * t
    return Look(**out)


def catalog() -> list[dict]:
    items = [{"id": AUTO_ID, "name": "Auto Cinematic", "purpose": "Analyses your photo and chooses the adjustments"}]
    for pid in PRESET_ORDER[1:]:
        items.append({"id": pid, "name": PRESETS[pid]["name"], "purpose": PRESETS[pid]["purpose"]})
    return items
