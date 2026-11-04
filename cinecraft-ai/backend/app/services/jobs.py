"""Async editing jobs. Stages shown to the user are real states, never fabricated percentages."""
import io
import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from app import config
from app.services import analysis as analysis_svc
from app.services import engine, storage
from app.services.ai.base import USER_MESSAGES, ProviderError
from app.services.ai.canvas import from_canvas, pick_canvas, to_canvas
from app.services.ai.guard import check_composition
from app.services.ai.openai_provider import get_provider
from app.services.ai.prompts import build_prompt
from app.services.limits import Busy, heavy
from app.services.validation import ImageRejected, validate_image_bytes

log = logging.getLogger("cinecraft.jobs")
ACTIVE = {"queued", "running"}
LOCAL_MAX_SIDE = 1600


@dataclass
class Job:
    id: str
    owner: str
    image_id: str
    params: dict
    mode: str                     # requested: local | ai
    fallback: bool
    status: str = "queued"        # queued | running | succeeded | failed
    stage: str = "Waiting in queue"
    error: str | None = None
    error_kind: str | None = None
    mode_used: str | None = None  # local | ai | local-fallback
    warning: str | None = None
    attempts: int = 0
    output_size: tuple[int, int] | None = None
    created: float = field(default_factory=time.time)
    updated: float = field(default_factory=time.time)

    def public(self) -> dict:
        return {"job_id": self.id, "status": self.status, "stage": self.stage, "error": self.error, "error_kind": self.error_kind,
                "mode_requested": self.mode, "mode_used": self.mode_used, "warning": self.warning, "attempts": self.attempts,
                "output_size": self.output_size, "has_result": self.status == "succeeded", "retryable": self.status == "failed"}


class JobManager:
    def __init__(self, provider_factory=get_provider, executor=None, sleep=time.sleep):
        self._provider_factory = provider_factory
        self._pool = executor or ThreadPoolExecutor(max_workers=2, thread_name_prefix="job")
        self._sleep = sleep
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    # ---- public API -------------------------------------------------------------------------------------------
    def submit(self, owner, image_id, params: dict, mode: str, fallback: bool) -> Job:
        key = json.dumps([owner, image_id, params, mode, fallback], sort_keys=True)
        with self._lock:  # prevent duplicate submissions of the same work
            for j in self._jobs.values():
                if j.status in ACTIVE and json.dumps([j.owner, j.image_id, j.params, j.mode, j.fallback], sort_keys=True) == key:
                    return j
            job = Job(uuid.uuid4().hex, owner, image_id, params, mode, fallback)
            self._jobs[job.id] = job
        self._pool.submit(self._run, job)
        return job

    def get(self, job_id: str, owner: str) -> Job | None:
        j = self._jobs.get(job_id)
        return j if j and j.owner == owner else None

    def retry(self, job_id: str, owner: str) -> Job | None:
        j = self.get(job_id, owner)
        if j is None or j.status != "failed":
            return None
        return self.submit(owner, j.image_id, j.params, j.mode, j.fallback)

    def result_path(self, job: Job):
        p = storage.find_original(job.image_id)
        return (p.parent / f"job-{job.id}.jpg") if p else None

    def cleanup(self) -> int:
        cutoff = time.time() - config.JOB_TTL_MINUTES * 60
        with self._lock:
            old = [j for j in self._jobs.values() if j.status not in ACTIVE and j.updated < cutoff]
            for j in old:
                del self._jobs[j.id]
        for j in old:
            p = self.result_path(j)
            if p and p.exists():
                p.unlink(missing_ok=True)
        return len(old)

    def forget_image(self, image_id: str):
        with self._lock:
            for k in [k for k, j in self._jobs.items() if j.image_id == image_id]:
                del self._jobs[k]

    # ---- worker -----------------------------------------------------------------------------------------------
    def _set(self, job: Job, status=None, stage=None):
        if status: job.status = status
        if stage: job.stage = stage
        job.updated = time.time()

    def _fail(self, job: Job, kind: str, detail: str | None = None):
        job.error_kind = kind
        job.error = detail or USER_MESSAGES.get(kind, "The job failed.")
        self._set(job, "failed", "Failed")
        log.info("job %s failed kind=%s", job.id[:8], kind)

    def _run(self, job: Job):
        try:
            self._set(job, "running", "Preparing your photo")
            path = storage.find_original(job.image_id)
            if path is None:
                return self._fail(job, "not_found", "The photo expired or was removed. Upload it again.")
            data = path.read_bytes()
            a = storage.load_json(job.image_id, "analysis")
            if a is None:
                a = analysis_svc.analyze_image(data)
                storage.save_json(job.image_id, "analysis", a)
            p = job.params
            if job.mode == "ai":
                try:
                    arr, info = self._run_ai(job, data, a, p)
                    job.mode_used = "ai"
                except ProviderError as e:
                    if not job.fallback:
                        return self._fail(job, e.kind)
                    job.warning = f"{USER_MESSAGES.get(e.kind, 'The AI step failed.')} Showing the local editing result instead."
                    self._set(job, stage="AI unavailable, using local editing")
                    arr, info = self._run_local(job, data, a, p)
                    job.mode_used = "local-fallback"
            else:
                arr, info = self._run_local(job, data, a, p)
                job.mode_used = "local"
            self._set(job, stage="Saving the result")
            out = self.result_path(job)
            if out is None:
                return self._fail(job, "not_found", "The photo expired or was removed. Upload it again.")
            out.write_bytes(engine.to_jpeg(arr, 92))
            job.output_size = (arr.shape[1], arr.shape[0])
            self._set(job, "succeeded", "Done")
            log.info("job %s done mode=%s", job.id[:8], job.mode_used)
        except Busy:
            self._fail(job, "busy", "The server is busy rendering other photos. Try again shortly.")
        except Exception:
            log.exception("job %s crashed", job.id[:8])
            self._fail(job, "internal", "Editing failed unexpectedly. Try again.")

    def _run_local(self, job, data, a, p):
        self._set(job, stage="Applying local edits")
        with heavy():
            return engine.edit(data, a, p["preset"], p["intensity"], LOCAL_MAX_SIDE, p.get("adjustments"))

    def _run_ai(self, job, data, a, p):
        provider = self._provider_factory()
        if provider is None:
            raise ProviderError("not_configured")
        src = engine.load_rgb(data, config.AI_MAX_SIDE)
        h, w = src.shape[:2]
        canvas = pick_canvas(w, h)
        src_img = Image.fromarray((src * 255 + 0.5).astype(np.uint8))
        canvas_img, box = to_canvas(src_img, canvas)
        buf = io.BytesIO(); canvas_img.save(buf, "PNG")
        prompt = build_prompt(p["preset"], p["intensity"], a, canvas)

        raw = None
        for attempt in range(1, config.AI_MAX_RETRIES + 2):
            job.attempts = attempt
            self._set(job, stage="Sending your photo to the AI service" + (f" (attempt {attempt})" if attempt > 1 else ""))
            try:
                raw = provider.edit(buf.getvalue(), prompt, canvas)
                break
            except ProviderError as e:
                if attempt > config.AI_MAX_RETRIES or e.kind not in ("rate_limit", "timeout", "server"):
                    raise
                wait = min(e.retry_after or (5 if e.kind == "rate_limit" else 2 * attempt), 20)
                self._set(job, stage=f"AI service {'is rate-limiting' if e.kind == 'rate_limit' else 'did not respond'}; retrying in {int(wait)}s")
                self._sleep(wait)

        self._set(job, stage="Checking the AI result")
        try:
            validate_image_bytes(raw)
            out_img = Image.open(io.BytesIO(raw)).convert("RGB")
        except (ImageRejected, OSError):
            raise ProviderError("invalid_output")
        result = from_canvas(out_img, canvas, box, (w, h))
        check_composition(src_img, result)
        return np.asarray(result, dtype=np.float32) / 255.0, {}
