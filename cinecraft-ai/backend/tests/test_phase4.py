import base64
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageEnhance

from app import config
from app.services import engine, storage
from app.services.ai import canvas, guard, prompts
from app.services.ai.base import ProviderError
from app.services.ai.openai_provider import OpenAIImageProvider, get_provider
from app.services.jobs import JobManager
from app.services.projects import ProjectError, ProjectStore
from app.services.ratelimit import RateLimiter
from tests.test_phase2 import scene

PARAMS = {"preset": "golden_hour", "intensity": 80, "adjustments": {}}


def png(arr_or_img) -> bytes:
    img = arr_or_img if isinstance(arr_or_img, Image.Image) else Image.fromarray(arr_or_img)
    b = io.BytesIO(); img.save(b, "PNG"); return b.getvalue()


class SyncExecutor:
    def submit(self, fn, *a): fn(*a)


class DeferredExecutor:
    def __init__(self): self.q = []
    def submit(self, fn, *a): self.q.append((fn, a))
    def run_all(self):
        for fn, a in self.q: fn(*a)
        self.q.clear()


class FakeAI:
    """Simulates an AI editor by grading the image it receives."""
    def __init__(self, script=None):
        self.script, self.calls, self.prompts = list(script or []), 0, []
    def edit(self, image_png, prompt, size):
        self.calls += 1; self.prompts.append(prompt)
        step = self.script.pop(0) if self.script else "ok"
        if isinstance(step, ProviderError): raise step
        img = Image.open(io.BytesIO(image_png)).convert("RGB")
        if step == "garbage": return b"not an image"
        if step == "other_scene":
            return png(np.random.default_rng(3).integers(0, 255, (size[1], size[0], 3), dtype=np.uint8))
        img = ImageEnhance.Color(ImageEnhance.Contrast(img).enhance(1.15)).enhance(1.2)
        return png(img)


class TempStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(config, "STORAGE_DIR", Path(self.tmp.name) / "s")
        self.patch.start()
        self.data = scene(size=(480, 360))
        self.image_id = storage.register_copy(self.data, "png", "holiday", "ownerA")
    def tearDown(self):
        self.patch.stop(); self.tmp.cleanup()


class JobTests(TempStorage):
    def mgr(self, provider, ex=None, sleeps=None):
        return JobManager(provider_factory=lambda: provider, executor=ex or SyncExecutor(),
                          sleep=(sleeps.append if sleeps is not None else (lambda s: None)))

    def test_local_job(self):
        m = self.mgr(None)
        j = m.submit("ownerA", self.image_id, PARAMS, "local", True)
        self.assertEqual((j.status, j.mode_used), ("succeeded", "local"))
        self.assertTrue(Image.open(m.result_path(j)).size[0] > 0)

    def test_ai_job_success_keeps_framing(self):
        ai = FakeAI(); m = self.mgr(ai)
        j = m.submit("ownerA", self.image_id, PARAMS, "ai", False)
        self.assertEqual((j.status, j.mode_used), ("succeeded", "ai"))
        self.assertEqual(Image.open(m.result_path(j)).size, (480, 360))
        self.assertIn("Preserve the original person's identity", ai.prompts[0])

    def test_rate_limit_is_retried_with_wait(self):
        sleeps = []
        ai = FakeAI([ProviderError("rate_limit", retry_after=3), "ok"])
        j = self.mgr(ai, sleeps=sleeps).submit("ownerA", self.image_id, PARAMS, "ai", False)
        self.assertEqual((j.status, j.attempts, sleeps), ("succeeded", 2, [3]))

    def test_exhausted_retries_fail_then_user_can_retry(self):
        ai = FakeAI([ProviderError("rate_limit")] * 3)
        m = self.mgr(ai)
        j = m.submit("ownerA", self.image_id, PARAMS, "ai", False)
        self.assertEqual((j.status, j.error_kind), ("failed", "rate_limit"))
        self.assertIn("busy", j.error)
        j2 = m.retry(j.id, "ownerA")
        self.assertEqual(j2.status, "succeeded")
        self.assertIsNone(m.retry(j2.id, "ownerA"))  # only failed jobs can be retried

    def test_non_retryable_error_fails_immediately(self):
        ai = FakeAI([ProviderError("auth")])
        j = self.mgr(ai).submit("ownerA", self.image_id, PARAMS, "ai", False)
        self.assertEqual((j.status, j.error_kind, ai.calls), ("failed", "auth", 1))

    def test_fallback_to_local_is_labelled(self):
        ai = FakeAI([ProviderError("timeout")] * 3)
        j = self.mgr(ai).submit("ownerA", self.image_id, PARAMS, "ai", True)
        self.assertEqual((j.status, j.mode_used), ("succeeded", "local-fallback"))
        self.assertIn("local", j.warning)

    def test_unusable_outputs_are_rejected(self):
        for bad in ("garbage", "other_scene"):
            j = self.mgr(FakeAI([bad])).submit("ownerA", self.image_id, {**PARAMS, "intensity": 71 + len(bad)}, "ai", False)
            self.assertEqual((j.status, j.error_kind), ("failed", "invalid_output"), bad)

    def test_not_configured_ai(self):
        j = self.mgr(None).submit("ownerA", self.image_id, PARAMS, "ai", False)
        self.assertEqual(j.error_kind, "not_configured")
        j = self.mgr(None).submit("ownerA", self.image_id, {**PARAMS, "intensity": 5}, "ai", True)
        self.assertEqual(j.mode_used, "local-fallback")

    def test_duplicate_submission_returns_same_job(self):
        ex = DeferredExecutor(); m = self.mgr(None, ex)
        a = m.submit("ownerA", self.image_id, PARAMS, "local", True)
        b = m.submit("ownerA", self.image_id, PARAMS, "local", True)
        self.assertEqual(a.id, b.id); self.assertEqual(len(ex.q), 1)
        ex.run_all()
        self.assertNotEqual(m.submit("ownerA", self.image_id, PARAMS, "local", True).id, a.id)  # finished: new job allowed

    def test_jobs_are_private_to_their_owner(self):
        m = self.mgr(None); j = m.submit("ownerA", self.image_id, PARAMS, "local", True)
        self.assertIsNone(m.get(j.id, "ownerB")); self.assertIsNotNone(m.get(j.id, "ownerA"))

    def test_missing_image_fails_cleanly(self):
        j = self.mgr(None).submit("ownerA", "0" * 32, PARAMS, "local", True)
        self.assertEqual(j.status, "failed")

    def test_cleanup_expires_old_jobs_and_files(self):
        m = self.mgr(None); j = m.submit("ownerA", self.image_id, PARAMS, "local", True)
        path = m.result_path(j); self.assertTrue(path.exists())
        j.updated -= config.JOB_TTL_MINUTES * 60 + 5
        self.assertEqual(m.cleanup(), 1); self.assertFalse(path.exists())


class StorageAuthTests(TempStorage):
    def test_owner_check(self):
        self.assertTrue(storage.owner_ok(self.image_id, "ownerA"))
        self.assertFalse(storage.owner_ok(self.image_id, "ownerB"))
        self.assertFalse(storage.owner_ok(self.image_id, ""))
        self.assertFalse(storage.owner_ok("../../etc", "ownerA"))

    def test_cleanup_removes_expired_but_access_refreshes(self):
        import os
        old = time.time() - config.RETENTION_MINUTES * 60 - 100
        os.utime(config.STORAGE_DIR / self.image_id, (old, old))
        storage.find_original(self.image_id)  # use refreshes the clock
        self.assertEqual(storage.cleanup_expired(), 0)
        os.utime(config.STORAGE_DIR / self.image_id, (old, old))
        self.assertEqual(storage.cleanup_expired(), 1)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = ProjectStore(Path(self.tmp.name) / "db.sqlite", Path(self.tmp.name) / "files")
        self.data = scene()
    def tearDown(self): self.tmp.cleanup()
    def make(self, owner="A", name="Trip", **kw):
        return self.s.create(owner, name, self.data, "png", "trip", kw.get("preset", "golden_hour"), kw.get("intensity", 70),
                             kw.get("adjustments", {"exposure": 10, "bogus": 3}), 480, 360)

    def test_create_get_list_and_settings_cleaned(self):
        p = self.make()
        self.assertEqual(p["adjustments"], {"exposure": 10.0}); self.assertNotIn("owner", p)
        self.assertEqual([x["id"] for x in self.s.list("A")], [p["id"]])
        self.assertEqual(self.s.original("A", p["id"])[0], self.data)

    def test_other_sessions_cannot_see_modify_or_delete(self):
        p = self.make()
        self.assertEqual(self.s.list("B"), [])
        for fn in (lambda: self.s.get("B", p["id"]), lambda: self.s.update("B", p["id"], name="x"),
                   lambda: self.s.delete("B", p["id"]), lambda: self.s.original("B", p["id"])):
            with self.assertRaises(ProjectError) as c: fn()
            self.assertEqual(c.exception.status, 404)
        self.assertEqual(self.s.get("A", p["id"])["name"], "Trip")

    def test_rename_update_and_validation(self):
        p = self.make()
        u = self.s.update("A", p["id"], name="  Sunset\x00 walk ", preset="sunset_glow", intensity=40, adjustments={"contrast": 20})
        self.assertEqual((u["name"], u["preset"], u["intensity"], u["adjustments"]), ("Sunset walk", "sunset_glow", 40.0, {"contrast": 20.0}))
        for kw in ({"preset": "nope"}, {"intensity": 150}, {"intensity": "x"}, {"name": "   "}):
            with self.assertRaises(ProjectError): self.s.update("A", p["id"], **kw)

    def test_delete_removes_files(self):
        p = self.make(); folder = Path(self.tmp.name) / "files" / p["id"]
        self.assertTrue(folder.exists()); self.s.delete("A", p["id"]); self.assertFalse(folder.exists())
        with self.assertRaises(ProjectError): self.s.get("A", p["id"])

    def test_per_session_limit(self):
        with mock.patch.object(config, "MAX_PROJECTS_PER_SESSION", 2):
            self.make(name="1"); self.make(name="2")
            with self.assertRaises(ProjectError) as c: self.make(name="3")
            self.assertEqual(c.exception.status, 409)
            self.make(owner="B", name="other")  # limit is per session

    def test_retention_purge(self):
        p = self.make(); old = self.make(name="old")
        with self.s._lock, self.s._db:
            self.s._db.execute("UPDATE projects SET updated=? WHERE id=?", (time.time() - (config.PROJECT_RETENTION_DAYS + 1) * 86400, old["id"]))
        self.assertEqual(self.s.purge_expired(), 1)
        self.assertEqual([x["id"] for x in self.s.list("A")], [p["id"]])

    def test_persists_across_restart(self):
        p = self.make(); s2 = ProjectStore(Path(self.tmp.name) / "db.sqlite", Path(self.tmp.name) / "files")
        self.assertEqual(s2.get("A", p["id"])["name"], "Trip")


class RateLimitTests(unittest.TestCase):
    def test_window_and_keys(self):
        t = [0.0]; r = RateLimiter(clock=lambda: t[0])
        self.assertTrue(all(r.check("ip:x", 3, 10)[0] for _ in range(3)))
        ok, retry = r.check("ip:x", 3, 10); self.assertFalse(ok); self.assertAlmostEqual(retry, 10)
        self.assertTrue(r.check("ip:y", 3, 10)[0])        # other client unaffected
        t[0] = 10.1; self.assertTrue(r.check("ip:x", 3, 10)[0])  # window slid


class AICoreTests(unittest.TestCase):
    def test_canvas_round_trip_preserves_framing(self):
        img = Image.fromarray(np.asarray(Image.open(io.BytesIO(scene(size=(500, 300)))).convert("RGB")))
        c = canvas.pick_canvas(*img.size); self.assertEqual(c, (1536, 1024))
        big, box = canvas.to_canvas(img, c)
        back = canvas.from_canvas(big, c, box, img.size)
        err = np.abs(np.asarray(back, np.float32) - np.asarray(img, np.float32)).mean() / 255
        self.assertLess(err, 0.03)
        self.assertEqual(canvas.pick_canvas(300, 500), (1024, 1536)); self.assertEqual(canvas.pick_canvas(400, 400), (1024, 1024))

    def test_guard(self):
        base = Image.open(io.BytesIO(scene())).convert("RGB")
        graded = ImageEnhance.Contrast(base).enhance(1.3)
        self.assertGreater(guard.composition_similarity(base, graded), 0.9)
        noise = Image.fromarray(np.random.default_rng(1).integers(0, 255, (360, 480, 3), dtype=np.uint8))
        with self.assertRaises(ProviderError): guard.check_composition(base, noise)

    def test_prompts_adapt(self):
        a = {"flags": {"already_warm": True, "indoor_likely": False, "harsh_light": False, "outdoor_greenery": True, "low_resolution": True},
             "exposure": {"label": "underexposed"}}
        p1, p2 = (prompts.build_prompt(x, 100, a, (1536, 1024)) for x in ("golden_forest", "moody_cinema"))
        self.assertNotEqual(p1, p2); self.assertIn("golden-green", p1); self.assertIn("deeper shadows", p2)
        for needle in ("already has warm lighting", "underexposed", "foliage", "Do not invent", "identity", "1536x1024"):
            self.assertIn(needle, p1)
        self.assertIn("subtle", prompts.build_prompt("natural_pro", 10, None, (1024, 1024)))
        self.assertIn("full cinematic", prompts.build_prompt("natural_pro", 100, None, (1024, 1024)))
        with self.assertRaises(ValueError): prompts.build_prompt("nope", 50, None, (1, 1))

    def test_provider_not_configured_by_default(self):
        self.assertIsNone(get_provider())
        with mock.patch.object(config, "AI_PROVIDER", "openai"), mock.patch.object(config, "AI_API_KEY", ""):
            self.assertIsNone(get_provider())
        with mock.patch.object(config, "AI_PROVIDER", "openai"), mock.patch.object(config, "AI_API_KEY", "k"):
            self.assertEqual(get_provider().name, "openai")


class FakeServer(BaseHTTPRequestHandler):
    seen = {}
    mode = "ok"
    def log_message(self, *a): pass
    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        FakeServer.seen = {"path": self.path, "auth": self.headers.get("Authorization"), "body": body, "ctype": self.headers["Content-Type"]}
        m = FakeServer.mode
        if m == "slow": time.sleep(2)
        code, hdr, out = 200, {}, json.dumps({"data": [{"b64_json": base64.b64encode(png(np.full((8, 8, 3), 90, np.uint8))).decode()}]}).encode()
        if m == "429": code, hdr, out = 429, {"Retry-After": "7"}, b"{}"
        if m in ("401", "400", "500", "504"): code, out = int(m), b"{}"
        if m == "text": out = b"<html>"
        if m == "url": out = json.dumps({"data": [{"url": "http://169.254.169.254/x"}]}).encode()
        self.send_response(code)
        for k, v in hdr.items(): self.send_header(k, v)
        self.end_headers()
        try: self.wfile.write(out)
        except BrokenPipeError: pass  # client timed out on purpose


class ProviderAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), FakeServer)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"
    @classmethod
    def tearDownClass(cls): cls.srv.shutdown()

    def call(self, mode, timeout=5):
        FakeServer.mode = mode
        return OpenAIImageProvider("sk-test", "gpt-image-1", self.url, timeout).edit(png(np.zeros((8, 8, 3), np.uint8)), "make it golden", (1536, 1024))

    def test_request_format(self):
        out = self.call("ok")
        self.assertEqual(Image.open(io.BytesIO(out)).size, (8, 8))
        s = FakeServer.seen
        self.assertEqual((s["path"], s["auth"]), ("/v1/images/edits", "Bearer sk-test"))
        self.assertTrue(s["ctype"].startswith("multipart/form-data; boundary="))
        for needle in (b'name="prompt"', b"make it golden", b'name="size"', b"1536x1024", b'name="model"', b'filename="photo.png"'):
            self.assertIn(needle, s["body"])

    def test_error_mapping(self):
        for mode, kind in (("429", "rate_limit"), ("401", "auth"), ("400", "bad_request"), ("500", "server"), ("504", "timeout"),
                           ("text", "invalid_output"), ("url", "invalid_output")):
            with self.assertRaises(ProviderError) as c: self.call(mode)
            self.assertEqual(c.exception.kind, kind, mode)
        with self.assertRaises(ProviderError) as c: self.call("429")
        self.assertEqual(c.exception.retry_after, 7.0)

    def test_timeout(self):
        with self.assertRaises(ProviderError) as c: self.call("slow", timeout=1)
        self.assertEqual(c.exception.kind, "timeout")

    def test_unreachable(self):
        with self.assertRaises(ProviderError) as c:
            OpenAIImageProvider("k", "m", "http://127.0.0.1:1", 2).edit(b"x", "p", (1024, 1024))
        self.assertEqual(c.exception.kind, "server")

    def test_key_never_in_error_text(self):
        with self.assertRaises(ProviderError) as c: self.call("401")
        self.assertNotIn("sk-test", str(c.exception))


if __name__ == "__main__":
    unittest.main()
