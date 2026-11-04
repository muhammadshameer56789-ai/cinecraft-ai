import io
import unittest
from unittest import mock

import cv2
import numpy as np
from PIL import Image

from app import config
from app.services import engine, exporter, storage
from app.services.analysis import analyze_image
from app.services.manual import LIMITS, clean, is_neutral
from tests.test_phase2 import scene


def L(x):
    return 0.2126 * x[..., 0] + 0.7152 * x[..., 1] + 0.0722 * x[..., 2]


class ManualTests(unittest.TestCase):
    def setUp(self):
        self.data = scene()
        self.a = analyze_image(self.data)
        self.base = engine.load_rgb(self.data)

    def run_adj(self, **adj):
        return engine.edit(self.data, self.a, "natural_pro", 0, None, adj)[0]

    def test_neutral_adjustments_return_original_at_zero_intensity(self):
        self.assertTrue(np.array_equal(self.run_adj(), self.base))
        self.assertTrue(np.array_equal(self.run_adj(exposure=0, contrast=0), self.base))
        self.assertTrue(is_neutral({"exposure": 0}) and is_neutral(None))

    def test_unknown_and_out_of_range_values_are_clamped(self):
        c = clean({"exposure": 900, "bogus": 5, "sharpness": -50})
        self.assertEqual(c, {"exposure": 100.0})
        self.assertTrue(is_neutral({"sharpness": -50}))

    def test_exposure_and_brightness_direction(self):
        for k in ("exposure", "brightness"):
            self.assertGreater(L(self.run_adj(**{k: 60})).mean(), L(self.base).mean() + 0.02, k)
            self.assertLess(L(self.run_adj(**{k: -60})).mean(), L(self.base).mean() - 0.02, k)

    def test_contrast_direction(self):
        self.assertGreater(L(self.run_adj(contrast=60)).std(), L(self.base).std())
        self.assertLess(L(self.run_adj(contrast=-60)).std(), L(self.base).std())

    def test_highlights_and_shadows(self):
        bright = np.s_[10:60, 10:120]   # sky
        dark = np.s_[220:320, 215:265]  # shirt
        self.assertLess(L(self.run_adj(highlights=-80))[bright].mean(), L(self.base)[bright].mean())
        self.assertGreater(L(self.run_adj(shadows=80))[dark].mean(), L(self.base)[dark].mean())
        self.assertLess(L(self.run_adj(shadows=-80))[dark].mean(), L(self.base)[dark].mean() + 1e-6)

    def test_temperature_and_tint(self):
        rb = lambda x: float(x[..., 0].mean() - x[..., 2].mean())
        self.assertGreater(rb(self.run_adj(temperature=60)), rb(self.base))
        self.assertLess(rb(self.run_adj(temperature=-60)), rb(self.base))
        g = lambda x: float(x[..., 1].mean() - (x[..., 0].mean() + x[..., 2].mean()) / 2)
        self.assertLess(g(self.run_adj(tint=60)), g(self.base))

    def test_saturation_and_vibrance(self):
        sat = lambda x: float(cv2.cvtColor(x.astype(np.float32), cv2.COLOR_RGB2HSV)[..., 1].mean())
        self.assertGreater(sat(self.run_adj(saturation=60)), sat(self.base))
        self.assertLess(sat(self.run_adj(saturation=-60)), sat(self.base))
        self.assertGreater(sat(self.run_adj(vibrance=60)), sat(self.base))

    def test_sharpness_fade_vignette_grain(self):
        edge = lambda x: float(np.abs(cv2.Laplacian(L(x).astype(np.float32), cv2.CV_32F)).mean())
        self.assertGreater(edge(self.run_adj(sharpness=100)), edge(self.base))
        self.assertGreater(float(self.run_adj(fade=80).min()), float(self.base.min()) + 0.05)
        v = self.run_adj(vignette=100)
        self.assertLess(L(v)[:20, :20].mean(), L(self.base)[:20, :20].mean())
        n = lambda x: float(cv2.Laplacian(L(x).astype(np.float32), cv2.CV_32F).std())
        self.assertGreater(n(self.run_adj(grain=100)), n(self.base))

    def test_green_and_golden(self):
        grass = np.s_[200:340, 10:120]
        hue = lambda x: float(cv2.cvtColor(x[grass].mean((0, 1))[None, None].astype(np.float32), cv2.COLOR_RGB2HSV)[0, 0, 0])
        self.assertLess(hue(self.run_adj(green_intensity=100)), hue(self.base) - 3)
        rb = lambda x: float(x[..., 0].mean() - x[..., 2].mean())
        self.assertGreater(rb(self.run_adj(golden_intensity=100)), rb(self.base))

    def test_manual_layers_on_preset_and_ignores_intensity(self):
        p_only = engine.edit(self.data, self.a, "golden_hour", 50, None, None)[0]
        both = engine.edit(self.data, self.a, "golden_hour", 50, None, {"exposure": 50})[0]
        self.assertGreater(L(both).mean(), L(p_only).mean())
        # exposure delta should be the same size whatever the intensity
        d = lambda t: L(engine.edit(self.data, self.a, "natural_pro", t, None, {"exposure": 50})[0]).mean() - \
            L(engine.edit(self.data, self.a, "natural_pro", t, None, None)[0]).mean()
        self.assertAlmostEqual(d(0), d(100), delta=0.06)

    def test_every_slider_has_limits(self):
        self.assertEqual(len(LIMITS), 15)


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.data = scene(size=(1200, 800))
        self.a = analyze_image(self.data)

    def export(self, **kw):
        args = dict(preset="golden_hour", intensity=80, adjustments=None, fmt="jpeg", quality=90, max_side=None, stem="holiday")
        args.update(kw)
        return exporter.export_image(self.data, self.a, args["preset"], args["intensity"], args["adjustments"],
                                     args["fmt"], args["quality"], args["max_side"], args["stem"])

    def test_formats_decode_with_original_dimensions(self):
        for fmt in ("jpeg", "png", "webp"):
            r = self.export(fmt=fmt)
            im = Image.open(io.BytesIO(r.data))
            self.assertEqual(im.size, (1200, 800), fmt)
            self.assertEqual(im.format, {"jpeg": "JPEG", "png": "PNG", "webp": "WEBP"}[fmt])
            self.assertTrue(r.filename.endswith({"jpeg": ".jpg", "png": ".png", "webp": ".webp"}[fmt]))

    def test_quality_changes_file_size(self):
        self.assertLess(len(self.export(quality=40).data), len(self.export(quality=95).data))
        self.assertLess(len(self.export(fmt="webp", quality=40).data), len(self.export(fmt="webp", quality=95).data))

    def test_resized_export_keeps_aspect_and_never_upscales(self):
        r = self.export(max_side=600)
        self.assertEqual((r.width, r.height), (600, 400))
        r = self.export(max_side=5000)
        self.assertEqual((r.width, r.height), (1200, 800))
        self.assertTrue(any("Not upscaled" in n for n in r.notes))

    def test_memory_cap_reduces_with_note(self):
        with mock.patch.object(config, "EXPORT_MAX_PIXELS", 300_000):
            r = self.export()
        self.assertLessEqual(r.width * r.height, 300_000)
        self.assertTrue(any("limit" in n for n in r.notes))

    def test_srgb_profile_embedded(self):
        for fmt in ("jpeg", "png", "webp"):
            self.assertTrue(Image.open(io.BytesIO(self.export(fmt=fmt).data)).info.get("icc_profile"), fmt)

    def test_filename_is_meaningful_and_safe(self):
        self.assertEqual(self.export().filename, "holiday-cinecraft-golden-hour-80pct.jpg")
        self.assertEqual(storage.safe_stem("../../etc/pass wd.JPG"), "pass-wd")
        self.assertEqual(storage.safe_stem(None), "photo")
        self.assertEqual(storage.safe_stem("???.png"), "photo")

    def test_export_matches_preview_look(self):
        r = self.export(fmt="png", intensity=100)
        out = np.asarray(Image.open(io.BytesIO(r.data)).convert("RGB"), np.float32) / 255
        prev, _ = engine.edit(self.data, self.a, "golden_hour", 100, None, None)
        self.assertLess(float(np.abs(out - prev).mean()), 0.01)

    def test_exif_rotated_source_exports_rotated(self):
        img = Image.fromarray(np.full((200, 400, 3), 120, np.uint8))
        exif = Image.Exif(); exif[0x0112] = 6
        buf = io.BytesIO(); img.save(buf, "JPEG", exif=exif)
        d = buf.getvalue()
        r = exporter.export_image(d, analyze_image(d), "natural_pro", 100, None, "jpeg", 90, None, "x")
        self.assertEqual((r.width, r.height), (200, 400))

    def test_icc_source_is_converted_to_srgb(self):
        from PIL import ImageCms
        prof = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        img = Image.fromarray(np.full((100, 100, 3), 130, np.uint8))
        buf = io.BytesIO(); img.save(buf, "JPEG", icc_profile=prof)
        x = engine.load_rgb(buf.getvalue())
        self.assertAlmostEqual(float(x.mean()), 130 / 255, delta=0.02)


if __name__ == "__main__":
    unittest.main()
