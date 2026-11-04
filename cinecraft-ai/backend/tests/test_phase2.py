import io
import unittest

import cv2
import numpy as np
from PIL import Image

from app.services import engine
from app.services.adaptation import resolve
from app.services.analysis import analyze_image
from app.services.presets import AUTO_ID, PRESET_ORDER


def scene(sky=(120, 160, 215), grass=(55, 120, 50), skin=(205, 150, 120), shirt=(25, 25, 28), size=(480, 360), warm=False):
    W, H = size
    a = np.zeros((H, W, 3), np.uint8)
    a[: H // 3] = sky
    a[H // 3 :] = grass
    a[H // 3 + 10 : H // 3 + 60, W // 2 - 25 : W // 2 + 25] = skin
    a[H // 3 + 60 : H - 40, W // 2 - 45 : W // 2 + 45] = shirt
    if warm:
        a = np.clip(a.astype(np.float32) * [1.25, 1.05, 0.7], 0, 255).astype(np.uint8)
    rng = np.random.default_rng(0)
    a = np.clip(a.astype(np.int16) + rng.integers(-6, 7, a.shape), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    return buf.getvalue()


def run(data, preset, t, **kw):
    return engine.edit(data, analyze_image(data), preset, t, **kw)[0]


def hue_of(x, box):
    y0, y1, x0, x1 = box
    patch = (x[y0:y1, x0:x1].reshape(-1, 3).mean(0)[None, None] * 255).astype(np.uint8)
    return float(cv2.cvtColor(patch, cv2.COLOR_RGB2HSV)[0, 0, 0]) * 2


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.data = scene()
        self.orig = engine.load_rgb(self.data)

    def test_intensity_zero_is_identical(self):
        for pid in PRESET_ORDER:
            self.assertTrue(np.array_equal(run(self.data, pid, 0), self.orig), pid)

    def test_every_preset_changes_the_image(self):
        for pid in PRESET_ORDER:
            self.assertGreater(float(np.abs(run(self.data, pid, 100) - self.orig).mean()), 0.008, pid)

    def test_intensity_increases_change_monotonically(self):
        for pid in PRESET_ORDER:
            d = [float(np.abs(run(self.data, pid, t) - self.orig).mean()) for t in (0, 25, 50, 75, 100)]
            self.assertTrue(all(b > a for a, b in zip(d, d[1:])), (pid, d))

    def test_presets_are_distinct(self):
        outs = {p: run(self.data, p, 100) for p in PRESET_ORDER}
        ids = list(outs)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                self.assertGreater(float(np.abs(outs[ids[i]] - outs[ids[j]]).mean()), 0.004, (ids[i], ids[j]))

    def test_golden_presets_shift_greens_toward_yellow_but_leave_skin_alone(self):
        grass_box, skin_box = (200, 340, 10, 120), (130, 170, 215, 245)
        for pid in ("golden_forest", "golden_hour"):
            out = run(self.data, pid, 100)
            self.assertLess(hue_of(out, grass_box), hue_of(self.orig, grass_box) - 3, pid)
            self.assertLess(abs(hue_of(out, skin_box) - hue_of(self.orig, skin_box)), 12, pid)

    def test_already_warm_photo_gets_less_warmth(self):
        def rb(x): return float(x[..., 0].mean() - x[..., 2].mean())
        neutral, warm = scene(), scene(warm=True)
        gain_n = rb(run(neutral, "golden_hour", 100)) - rb(engine.load_rgb(neutral))
        gain_w = rb(run(warm, "golden_hour", 100)) - rb(engine.load_rgb(warm))
        self.assertLess(gain_w, gain_n)

    def test_underexposed_is_brightened_without_clipping(self):
        dark = scene(sky=(30, 40, 60), grass=(15, 35, 15), skin=(70, 50, 40), shirt=(8, 8, 9))
        o = engine.load_rgb(dark)
        out = run(dark, "natural_pro", 100)
        self.assertGreater(out.mean(), o.mean() + 0.02)
        self.assertLess(float((out >= 0.99).mean()), 0.01)

    def test_highlights_not_blown_in_bright_scene(self):
        bright = scene(sky=(235, 240, 250), grass=(150, 200, 140), skin=(240, 200, 180), shirt=(90, 90, 95))
        o = engine.load_rgb(bright)
        for pid in ("golden_hour", "natural_pro", "warm_editorial"):
            out = run(bright, pid, 100)
            self.assertLessEqual(float((out >= 0.99).mean()), float((o >= 0.99).mean()) + 0.01, pid)

    def test_black_clothing_keeps_detail(self):
        out = run(self.data, "dark_luxury", 100)
        shirt = out[200:320, 200:280].mean(-1)
        self.assertGreater(float(shirt.std()), 0.0)          # texture retained
        self.assertGreater(float(shirt.mean()), 0.0)

    def test_auto_adapts_per_image(self):
        looks = {k: resolve(AUTO_ID, analyze_image(d))[0] for k, d in
                 {"normal": scene(), "warm": scene(warm=True), "tiny": scene(size=(200, 150))}.items()}
        self.assertNotEqual(looks["normal"], looks["warm"])
        self.assertLess(looks["warm"].warmth, looks["normal"].warmth)
        self.assertEqual(looks["tiny"].sharpen, 0.0)  # low-res: no fake detail

    def test_output_size_matches_and_preview_resize(self):
        big = scene(size=(1600, 1200))
        self.assertEqual(run(big, "natural_pro", 100).shape[:2], (1200, 1600))
        self.assertEqual(max(run(big, "natural_pro", 100, max_side=800).shape[:2]), 800)


if __name__ == "__main__":
    unittest.main()
