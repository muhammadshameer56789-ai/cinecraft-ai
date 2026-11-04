import io
import unittest

import numpy as np
from PIL import Image

from app.services.analysis import analyze_image
from app.services.validation import ImageRejected, validate_image_bytes


def to_bytes(img, fmt="JPEG"):
    buf = io.BytesIO()
    img.save(buf, fmt)
    return buf.getvalue()


def solid(rgb, size=(400, 300)):
    return Image.new("RGB", size, rgb)


class ValidationTests(unittest.TestCase):
    def test_accepts_jpeg_png_webp(self):
        for fmt in ("JPEG", "PNG", "WEBP"):
            self.assertEqual(validate_image_bytes(to_bytes(solid((90, 120, 60)), fmt)).fmt, fmt)

    def test_rejects_corrupted(self):
        with self.assertRaises(ImageRejected) as c:
            validate_image_bytes(b"not an image at all")
        self.assertEqual(c.exception.status, 422)

    def test_rejects_truncated(self):
        data = to_bytes(Image.fromarray(np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)))
        with self.assertRaises(ImageRejected):
            validate_image_bytes(data[: len(data) // 2])

    def test_rejects_unsupported_gif(self):
        with self.assertRaises(ImageRejected) as c:
            validate_image_bytes(to_bytes(solid((1, 2, 3)), "GIF"))
        self.assertEqual(c.exception.status, 415)

    def test_rejects_empty(self):
        with self.assertRaises(ImageRejected):
            validate_image_bytes(b"")


class AnalysisTests(unittest.TestCase):
    def test_dark_image_is_underexposed_and_gets_positive_ev(self):
        a = analyze_image(to_bytes(solid((20, 20, 24))))
        self.assertEqual(a["exposure"]["label"], "underexposed")
        self.assertGreater(a["suggested_adjustments"]["exposure_ev"], 0.3)
        self.assertTrue(a["suggested_adjustments"]["noise_caution"])

    def test_bright_image_is_overexposed_and_gets_negative_ev(self):
        a = analyze_image(to_bytes(solid((240, 240, 238))))
        self.assertEqual(a["exposure"]["label"], "overexposed")
        self.assertLess(a["suggested_adjustments"]["exposure_ev"], 0)

    def test_green_scene_detected_and_boost_applied(self):
        a = analyze_image(to_bytes(solid((50, 140, 50))))
        self.assertTrue(a["flags"]["outdoor_greenery"])
        self.assertGreater(a["suggested_adjustments"]["green_boost"], 0)

    def test_warm_scene_blocks_extra_warmth(self):
        a = analyze_image(to_bytes(solid((230, 170, 80))))
        self.assertTrue(a["flags"]["already_warm"])
        self.assertEqual(a["suggested_adjustments"]["warmth_allowed"], 0.0)

    def test_cool_scene_labelled_cool(self):
        a = analyze_image(to_bytes(solid((80, 110, 190))))
        self.assertEqual(a["color"]["temperature"], "cool")

    def test_low_resolution_flag(self):
        a = analyze_image(to_bytes(solid((120, 120, 120), (200, 150))))
        self.assertTrue(a["flags"]["low_resolution"])

    def test_exif_orientation_is_applied(self):
        img = solid((100, 100, 100), (400, 200))
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90 CW -> portrait
        buf = io.BytesIO()
        img.save(buf, "JPEG", exif=exif)
        a = analyze_image(buf.getvalue())
        self.assertEqual(a["dimensions"]["orientation"], "portrait")
        self.assertEqual((a["dimensions"]["width"], a["dimensions"]["height"]), (200, 400))

    def test_large_image_downscaled_for_analysis(self):
        a = analyze_image(to_bytes(solid((90, 90, 90), (3000, 2000))))
        self.assertLessEqual(max(a["dimensions"]["analysed_at"].values()), 1024)
        self.assertEqual(a["dimensions"]["width"], 3000)


if __name__ == "__main__":
    unittest.main()
