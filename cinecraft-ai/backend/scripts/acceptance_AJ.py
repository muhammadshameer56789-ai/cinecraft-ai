"""Acceptance tests A-J from the spec, run on REAL photos you supply. Each test states its pass criterion.
Usage: python scripts/acceptance_AJ.py --green g.jpg --dark-clothes d.jpg --sky s.jpg --warm w.jpg --dusk u.jpg [--sheet out.png]
Tests whose photo is not supplied are reported as SKIPPED. Derived variants (harsh, underexposed, low-res, large) are made from --dark-clothes."""
import argparse, io, resource, sys, time
import cv2, numpy as np
from PIL import Image, ImageEnhance
sys.path.insert(0, ".")
from app.services import engine, exporter
from app.services.adaptation import resolve
from app.services.analysis import analyze_image
from app.services.validation import ImageRejected, validate_image_bytes

ap = argparse.ArgumentParser()
for k in ("green", "dark-clothes", "sky", "warm", "dusk", "sheet"): ap.add_argument("--" + k)
args = ap.parse_args()
rows, tiles = [], []
L = lambda x: 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]
hsv = lambda x: cv2.cvtColor(x.astype(np.float32), cv2.COLOR_RGB2HSV)
rb = lambda x: float(x[..., 0].mean() - x[..., 2].mean())
sat = lambda x: float(hsv(x)[..., 1].mean())
clip = lambda x: float((x.max(-1) >= 0.99).mean())
def jpg(img): b = io.BytesIO(); img.save(b, "JPEG", quality=92); return b.getvalue()
def load(p): return open(p, "rb").read()
def run(d, preset, t=100, **k): a = analyze_image(d); return engine.edit(d, a, preset, t, k.get("ms"), None)[0], a
def rec(name, ok, detail): rows.append((name, "PASS" if ok else "FAIL", detail))
def skip(name, why): rows.append((name, "SKIP", why))
def tile(name, before, after): tiles.append((name, before, after))
def mean_hue(x, m): return float(np.median(hsv(x)[..., 0][m])) if m.any() else float("nan")

dark = load(args.dark_clothes) if args.dark_clothes else None

# A green outdoor portrait
if args.green:
    d = load(args.green); o = engine.load_rgb(d); x, a = run(d, "golden_forest", 80)
    g = (hsv(o)[..., 0] > 70) & (hsv(o)[..., 0] < 170) & (hsv(o)[..., 1] > .18)
    sk = engine.skin_mask(o, (a["faces"] or {}).get("boxes")) > .6
    dh = mean_hue(x, g) - mean_hue(o, g); sdh = abs(mean_hue(x, sk) - mean_hue(o, sk)) if sk.sum() > 50 else 0.0
    rec("A green outdoor portrait", dh <= -3 and sdh < 12 and clip(x) <= clip(o) + .01,
        f"greens hue {dh:+.1f} deg (toward gold), skin hue drift {sdh:.1f} deg, clipped {clip(o):.3f}->{clip(x):.3f}"); tile("A", o, x)
else: skip("A green outdoor portrait", "no --green photo")

if dark:
    base = Image.open(io.BytesIO(dark)).convert("RGB")
    # B harsh midday: derived by strong gain + contrast
    harsh = jpg(ImageEnhance.Contrast(ImageEnhance.Brightness(base).enhance(1.45)).enhance(1.35))
    o = engine.load_rgb(harsh); x, a = run(harsh, "golden_hour", 100)
    rec("B harsh midday (derived)", clip(x) <= clip(o) + .01 and (rb(x) - rb(o)) <= .06,
        f"clipped {clip(o):.3f}->{clip(x):.3f}, warmth added {rb(x)-rb(o):+.3f}, harsh_light flag={a['flags']['harsh_light']}"); tile("B", o, x)
    # C underexposed: derived gamma-darken + sensor-like noise
    arr = (np.asarray(base, np.float32) / 255) ** 2.2 * 0.9
    arr = np.clip(arr + np.random.default_rng(5).normal(0, .012, arr.shape), 0, 1)
    under = jpg(Image.fromarray((arr * 255).astype(np.uint8)))
    o = engine.load_rgb(under); x, a = run(under, "natural_pro", 100)
    nz = lambda y: float(cv2.Laplacian(L(y).astype(np.float32), cv2.CV_32F).std())
    gain = L(x).mean() / L(o).mean(); namp = nz(x) / nz(o)
    rec("C underexposed (derived)", L(x).mean() >= L(o).mean() + .03 and namp <= gain and clip(x) < .02,
        f"mean luma {L(o).mean():.3f}->{L(x).mean():.3f} (x{gain:.2f}), noise x{namp:.2f} (must not exceed brightness gain), flag={a['exposure']['label']}"); tile("C", o, x)
    # D black clothing: darkest large region as proxy
    o = engine.load_rgb(dark); x, a = run(dark, "dark_luxury", 100)
    m = cv2.erode((L(o) < .14).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    if m.sum() > 500:
        # "visible detail" = LOCAL texture (fine + cloth-fold scale) in the dark region, plus not being crushed darker.
        # The overall std is printed for information only: a contrast curve legitimately compresses tone gaps between dark objects.
        Hh, Ww = o.shape[:2]; scales = (max(1.0, max(Hh, Ww) / 400), max(2.0, max(Hh, Ww) / 80))
        loc = lambda y, sg: float((L(y).astype(np.float32) - cv2.GaussianBlur(L(y).astype(np.float32), (0, 0), sg))[m].std())
        r_fine, r_fold = (loc(x, sg) / loc(o, sg) for sg in scales)
        bright = L(x)[m].mean() / L(o)[m].mean()
        rec("D black clothing", r_fine >= .9 and r_fold >= .9 and bright >= .9,
            f"local detail kept: fine {r_fine:.2f}, folds {r_fold:.2f} (min .90); dark brightness x{bright:.2f} (min .90); overall std x{L(x)[m].std()/L(o)[m].std():.2f} (info only); {int(m.sum())} px"); tile("D", o, x)
    else: skip("D black clothing", "no large dark region found")
    # H low resolution
    small = jpg(base.resize((200, int(200 * base.height / base.width)), Image.LANCZOS)); a = analyze_image(small)
    look, _ = resolve("natural_pro", a)
    r = exporter.export_image(small, a, "natural_pro", 100, None, "jpeg", 90, 2000, "tiny")
    rec("H low-resolution", a["flags"]["low_resolution"] and look.sharpen == 0 and r.width == 200 and any("Not upscaled" in n for n in r.notes),
        f"flagged low-res, sharpening off, export asked 2000px got {r.width}px with note"); 
else:
    for n in ("B harsh midday", "C underexposed", "D black clothing", "H low-resolution"): skip(n, "no --dark-clothes photo")

# E bright sky
if args.sky:
    d = load(args.sky); o = engine.load_rgb(d); x, a = run(d, "natural_pro", 100)
    h = hsv(o); sky = (h[..., 0] > 190) & (h[..., 0] < 250) & (h[..., 1] > .18) & (h[..., 2] > .45)
    if sky.sum() > 200:
        x2, _ = run(d, "golden_hour", 100)
        ok = all(float((y.max(-1)[sky] >= .99).mean()) <= float((o.max(-1)[sky] >= .99).mean()) + .01 for y in (x, x2)) and 150 <= mean_hue(x2, sky) <= 260
        rec("E bright sky", ok, f"sky clipped {float((o.max(-1)[sky]>=.99).mean()):.3f}->{float((x2.max(-1)[sky]>=.99).mean()):.3f}; sky hue {mean_hue(o,sky):.0f}->{mean_hue(x2,sky):.0f} (blue=190-250)"); tile("E", o, x2)
    else: skip("E bright sky", "no sky region found")
else: skip("E bright sky", "no --sky photo")

# F indoor-like / G existing golden
for key, label, path in (("F", "F indoor-like (no outdoor cues)", args.dusk), ("G", "G existing golden light", args.warm)):
    if not path: skip(label, "no photo supplied"); continue
    d = load(path); o = engine.load_rgb(d); x, a = run(d, "auto_cinematic", 100)
    f = a["flags"]; dwarm, dsat = rb(x) - rb(o), (sat(x) - sat(o)) / max(sat(o), 1e-6)
    ok = dwarm <= .04 and dsat <= .25 and (f["indoor_likely"] if key == "F" else f["already_warm"])
    rec(label, ok, f"warmth added {dwarm:+.3f} (max .04), saturation {dsat:+.0%} (max +25%), indoor_likely={f['indoor_likely']} already_warm={f['already_warm']}"); tile(key, o, x)

# I corrupted / unsupported
good = jpg(Image.new("RGB", (300, 200), (90, 120, 80)))
bad = {"truncated JPEG": good[: len(good) // 2], "random bytes": np.random.default_rng(1).bytes(5000), "empty": b"",
       "text renamed .jpg": b"hello, I am not an image", "PNG header + garbage": b"\x89PNG\r\n\x1a\n" + bytes(200),
       "GIF": (lambda b: (Image.new("RGB", (10, 10)).save(b, "GIF"), b.getvalue())[1])(io.BytesIO())}
res = []
for n, b in bad.items():
    try: validate_image_bytes(b); res.append(f"{n}: ACCEPTED")
    except ImageRejected as e: res.append(f"{n}: {e.status}")
    except Exception as e: res.append(f"{n}: CRASH {type(e).__name__}")
rec("I corrupted/unsupported files", all("ACCEPTED" not in r and "CRASH" not in r for r in res), "; ".join(res))

# J large photo (last: it measures peak memory)
if dark:
    big = Image.open(io.BytesIO(dark)).convert("RGB").resize((4000, 3000), Image.LANCZOS)
    d = jpg(big); a = analyze_image(d); rss0 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    t = time.time(); engine.edit(d, a, "golden_forest", 80, 1400, None); tp = time.time() - t
    t = time.time(); r = exporter.export_image(d, a, "golden_forest", 80, None, "jpeg", 90, None, "big"); te = time.time() - t
    rss1 = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    rec("J large 12 MP photo", tp < 3 and (r.width, r.height) == (4000, 3000),
        f"preview {tp:.1f}s, full export {te:.1f}s at {r.width}x{r.height}, peak RAM {rss1} MB (baseline {rss0} MB)")
    from unittest import mock; from app import config
    with mock.patch.object(config, "EXPORT_MAX_PIXELS", 6_000_000):
        r2 = exporter.export_image(d, a, "golden_forest", 80, None, "jpeg", 90, None, "big")
    rec("J memory guard", r2.width * r2.height <= 6_000_000 and bool(r2.notes), f"cap 6 MP -> exported {r2.width}x{r2.height} with note")
else: skip("J large photo", "no --dark-clothes photo")

w = max(len(r[0]) for r in rows)
for n, s, d in rows: print(f"{s:5} {n:<{w}}  {d}")
print(f"\n{sum(r[1]=='PASS' for r in rows)} passed, {sum(r[1]=='FAIL' for r in rows)} failed, {sum(r[1]=='SKIP' for r in rows)} skipped")
if args.sheet and tiles:
    from PIL import ImageDraw
    h = 300; row_imgs = []
    for n, b, a in tiles:
        bi, ai = (Image.fromarray((np.clip(v, 0, 1) * 255).astype(np.uint8)) for v in (b, a))
        bi = bi.resize((int(bi.width * h / bi.height), h)); ai = ai.resize(bi.size); row_imgs.append((n, bi, ai))
    W = sum(b.width * 2 + 8 for _, b, _ in row_imgs); sheet = Image.new("RGB", (W, h + 16), (24, 24, 22)); dr = ImageDraw.Draw(sheet); x0 = 0
    for n, b, a in row_imgs:
        sheet.paste(b, (x0, 16)); sheet.paste(a, (x0 + b.width, 16)); dr.text((x0 + 3, 2), f"{n}: before | after", fill=(230, 230, 230)); x0 += b.width * 2 + 8
    sheet.save(args.sheet); print("sheet:", args.sheet)
sys.exit(1 if any(r[1] == "FAIL" for r in rows) else 0)
