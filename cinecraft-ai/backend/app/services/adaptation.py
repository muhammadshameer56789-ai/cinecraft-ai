"""Turns a preset + the photo's analysis into the parameters actually used. This is where analysis changes the edit."""
from dataclasses import replace

from app.services.presets import AUTO_ID, PRESETS, Look, blend


def auto_choice(a: dict) -> tuple[list[str], list[float], str]:
    f, s = a["flags"], a["suggested_adjustments"]
    if f["already_warm"]:
        return ["natural_pro", "cinematic_green"], [0.55, 0.45], "Photo is already warm, so warmth is kept low."
    if f["indoor_likely"]:
        return ["warm_editorial", "natural_pro"], [0.6, 0.4], "Looks indoors, so a restrained look that follows the existing light."
    if f["harsh_light"]:
        return ["cinematic_green", "natural_pro"], [0.55, 0.45], "Harsh light detected, so highlights are protected and warmth is limited."
    if f["outdoor_greenery"]:
        return ["golden_forest", "cinematic_green"], [0.5, 0.5], "Outdoor greenery detected, so golden-green foliage grading."
    if a["exposure"]["label"] == "underexposed":
        return ["natural_pro", "warm_editorial"], [0.6, 0.4], "Underexposed, so brightening with a clean, natural look."
    return ["natural_pro", "warm_editorial"], [0.5, 0.5], "Balanced photo, so a clean look with light warmth."


def resolve(preset_id: str, a: dict) -> tuple[Look, str | None]:
    note = None
    if preset_id == AUTO_ID:
        ids, ws, note = auto_choice(a)
        look = blend([PRESETS[i]["look"] for i in ids], ws)
    else:
        look = PRESETS[preset_id]["look"]

    f, s = a["flags"], a["suggested_adjustments"]
    green_frac = a["foliage"]["green_fraction"]

    ev = look.exposure_ev + s["exposure_ev"] * look.auto_exposure
    if s["noise_caution"]:
        ev = min(ev, 0.7)
    warm_factor = 0.15 + 0.85 * s["warmth_allowed"]
    if f["indoor_likely"]:
        warm_factor *= 0.7
    green_scale = 0.0 if green_frac < 0.03 else min(1.0, max(0.3, green_frac / 0.10))

    shadow_lift = look.shadow_lift + s["shadow_lift"] * 0.4
    if s["noise_caution"]:
        shadow_lift = min(shadow_lift, 0.35)

    look = replace(
        look,
        exposure_ev=ev,
        shadow_lift=shadow_lift,
        highlight_recovery=min(0.8, look.highlight_recovery + s["highlight_recovery"]),
        contrast=look.contrast + s["contrast"] * 0.5,
        warmth=look.warmth * warm_factor,
        golden_highlights=look.golden_highlights * warm_factor * (0.5 if f["indoor_likely"] else 1.0),
        glow=look.glow * warm_factor * (0.0 if f["indoor_likely"] else 1.0),
        highlight_tint=tuple(x * warm_factor for x in look.highlight_tint),
        green_hue_shift=look.green_hue_shift * green_scale * (0.6 if f["already_warm"] else 1.0),
        green_sat=look.green_sat * green_scale,
        green_lum=look.green_lum * green_scale,
        sharpen=0.0 if f["low_resolution"] else look.sharpen,
    )
    return look, note


def white_balance_gains(a: dict, strength: float) -> tuple[float, float]:
    wb = a["suggested_adjustments"]["white_balance_shift"]
    return 1.0 + wb["r"] * strength * 2.0, 1.0 + wb["b"] * strength * 2.0
