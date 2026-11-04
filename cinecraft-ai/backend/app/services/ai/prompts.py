"""Prompt builder: adapts to the preset, intensity and what the analysis found."""
from app.services.presets import AUTO_ID, PRESETS

STYLE = {
    "golden_hour": "warm golden-hour sunlight, golden highlights, soft contrast, natural skin tones, rich outdoor colours",
    "cinematic_green": "rich deep natural greens in foliage, slightly warm highlights, deep natural shadows, balanced contrast, editorial look",
    "warm_editorial": "warm neutral colour grading, soft highlight roll-off, muted distracting colours, refined contrast, premium lifestyle editorial finish",
    "moody_cinema": "deeper shadows, restrained saturation, strong but controlled contrast, cinematic tonal separation, atmospheric depth",
    "natural_pro": "corrected white balance, natural contrast, realistic colours, improved exposure, subtle detail enhancement, minimal stylisation",
    "golden_forest": "golden-green foliage, warm sunlight, rich but realistic environmental colours, controlled highlights, cinematic depth",
    "dark_luxury": "deep neutral shadows, refined contrast, controlled highlights, rich dark clothing with visible detail, sophisticated colour grading",
    "sunset_glow": "sunset-inspired warmth, soft golden highlights, warm environmental colours, balanced exposure, subtle cinematic atmosphere",
    "soft_film": "subtle analog-film look, soft contrast, gentle highlight roll-off, slightly lifted shadows, refined palette, very light grain",
    AUTO_ID: "polished cinematic colour correction chosen to suit this photo",
}

IDENTITY = ("Preserve the original person's identity, face, hairstyle, expression, pose, clothing, body proportions, camera angle "
            "and background composition. Do not add objects, remove objects, replace the environment, or alter the person's appearance. "
            "Keep realistic skin texture and avoid excessive skin smoothing. Make the result photorealistic and natural, like professional "
            "photography and colour grading rather than an artificial image.")


def strength_words(intensity: float) -> str:
    if intensity <= 25: return "Apply a subtle enhancement"
    if intensity <= 50: return "Apply a moderate cinematic colour grade"
    if intensity <= 75: return "Apply a strong but controlled cinematic colour grade"
    return "Apply the full cinematic style"


def build_prompt(preset: str, intensity: float, analysis: dict | None, size: tuple[int, int]) -> str:
    if preset != AUTO_ID and preset not in PRESETS:
        raise ValueError("Unknown preset")
    parts = [f"{strength_words(intensity)} to this photograph: {STYLE[preset]}."]
    f = (analysis or {}).get("flags", {})
    exp = ((analysis or {}).get("exposure") or {}).get("label")
    if f.get("already_warm"): parts.append("The photo already has warm lighting, so do not add extra orange or yellow tones.")
    if f.get("indoor_likely"): parts.append("This looks like an indoor photo: follow the existing light source instead of forcing an outdoor golden-hour effect.")
    if f.get("harsh_light"): parts.append("The light is harsh: protect highlights and balance the shadows.")
    if exp == "underexposed": parts.append("The photo is underexposed: recover shadow detail without amplifying noise.")
    if f.get("outdoor_greenery"): parts.append("Enhance the foliage naturally.")
    if f.get("low_resolution"): parts.append("Do not invent fine detail that is not in the photo.")
    parts.append(IDENTITY)
    parts.append(f"Output a photograph with the same framing and aspect ratio ({size[0]}x{size[1]}).")
    return " ".join(parts)
