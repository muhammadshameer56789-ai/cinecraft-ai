"""End-to-end HTTP tests. Requires fastapi + httpx (pip install -r requirements.txt httpx); skipped otherwise.
NOTE: written without being able to run FastAPI in the authoring environment: run it once and report any failure."""
import io
import os
import tempfile
import unittest
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ.update(STORAGE_DIR=f"{_tmp}/s", PROJECT_DIR=f"{_tmp}/p", DB_PATH=f"{_tmp}/db.sqlite", AI_PROVIDER="", AI_API_KEY="")

try:
    from fastapi.testclient import TestClient
    from app.main import app
    HAVE = True
except Exception:  # fastapi/httpx not installed
    HAVE = False

from tests.test_phase2 import scene


@unittest.skipUnless(HAVE, "fastapi/httpx not installed")
class ApiTests(unittest.TestCase):
    def setUp(self):
        self.a, self.b = TestClient(app), TestClient(app)   # two separate browser sessions
        self.png = scene(size=(600, 400))

    def upload(self, c, data=None, name="trip.png"):
        return c.post("/api/images/upload", files={"file": (name, data or self.png, "image/png")})

    def test_session_cookie_is_httponly_and_upload_works(self):
        r = self.upload(self.a)
        self.assertEqual(r.status_code, 201)
        self.assertIn("httponly", r.headers.get("set-cookie", "").lower())
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertNotIn("path", r.text.lower().replace("stored_on", ""))   # no filesystem paths leak

    def test_full_flow_and_isolation_between_sessions(self):
        iid = self.upload(self.a).json()["image_id"]
        self.assertEqual(self.a.post("/api/images/analyze", json={"image_id": iid}).status_code, 200)
        body = {"image_id": iid, "preset": "golden_hour", "intensity": 70, "adjustments": {"exposure": 10}}
        self.assertEqual(self.a.post("/api/images/edit", json=body).headers["content-type"], "image/jpeg")
        ex = self.a.post("/api/images/export", json={**body, "format": "webp", "quality": 80})
        self.assertIn("trip-cinecraft-golden-hour-70pct.webp", ex.headers["content-disposition"])
        for call in (lambda: self.b.get(f"/api/images/{iid}/original"), lambda: self.b.post("/api/images/edit", json=body),
                     lambda: self.b.post("/api/images/export", json=body), lambda: self.b.delete(f"/api/images/{iid}")):
            self.assertEqual(call().status_code, 404)

    def test_rejects_bad_input_cleanly(self):
        self.assertEqual(self.upload(self.a, b"not an image").status_code, 422)
        self.assertEqual(self.a.post("/api/images/edit", json={"image_id": "x", "preset": "golden_hour", "intensity": 500}).status_code, 422)
        self.assertEqual(self.a.post("/api/images/edit", json={"image_id": "../../etc/passwd", "preset": "golden_hour"}).status_code, 404)

    def test_oversized_body_rejected_early(self):
        with mock.patch("app.config.MAX_BODY_BYTES", 1000):
            self.assertEqual(self.upload(self.a).status_code, 413)

    def test_jobs_local_and_ai_gating(self):
        iid = self.upload(self.a).json()["image_id"]
        j = self.a.post("/api/images/jobs", json={"image_id": iid, "preset": "natural_pro", "intensity": 60}).json()
        import time
        for _ in range(60):
            s = self.a.get(f"/api/images/jobs/{j['job_id']}").json()
            if s["status"] in ("succeeded", "failed"): break
            time.sleep(0.5)
        self.assertEqual(s["status"], "succeeded")
        self.assertEqual(self.a.get(f"/api/images/jobs/{j['job_id']}/result").headers["content-type"], "image/jpeg")
        self.assertEqual(self.b.get(f"/api/images/jobs/{j['job_id']}").status_code, 404)
        r = self.a.post("/api/images/jobs", json={"image_id": iid, "preset": "natural_pro", "mode": "ai", "ai_consent": True})
        self.assertEqual(r.status_code, 503)   # no provider configured: honest refusal, never a fake AI result
        self.assertFalse(self.a.get("/api/health").json()["ai_provider"]["configured"])

    def test_projects_lifecycle_and_privacy_between_sessions(self):
        iid = self.upload(self.a).json()["image_id"]
        p = self.a.post("/api/projects", json={"image_id": iid, "name": "Holiday", "preset": "golden_hour", "intensity": 80}).json()
        self.assertEqual(self.b.get("/api/projects").json()["projects"], [])
        self.assertEqual(self.b.get(f"/api/projects/{p['id']}").status_code, 404)
        self.assertEqual(self.b.delete(f"/api/projects/{p['id']}").status_code, 404)
        self.assertEqual(self.a.patch(f"/api/projects/{p['id']}", json={"name": "Renamed"}).json()["name"], "Renamed")
        self.assertEqual(self.a.get(f"/api/projects/{p['id']}/preview").status_code, 200)
        opened = self.a.post(f"/api/projects/{p['id']}/open").json()
        self.assertNotEqual(opened["image_id"], iid)
        self.assertEqual(self.a.post(f"/api/projects/{p['id']}/export", json={"format": "png"}).status_code, 200)
        self.assertEqual(self.a.delete(f"/api/projects/{p['id']}").status_code, 204)

    def test_rate_limit(self):
        from app.services.ratelimit import RateLimiter
        with mock.patch.dict("app.config.RATE_LIMITS", {"upload": (2, 60)}), mock.patch("app.security.limiter", RateLimiter()):
            codes = [self.upload(TestClient(app)).status_code for _ in range(4)]
        self.assertEqual(codes[:2], [201, 201]); self.assertEqual(codes[-1], 429)

    def test_privacy_endpoint_is_honest_about_ai(self):
        t = self.a.get("/api/privacy").json()
        self.assertIn("not configured", t["ai"]); self.assertIn("training", t)


if __name__ == "__main__":
    unittest.main()
