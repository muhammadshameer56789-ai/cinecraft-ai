from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.routers.edit import Adjustments, valid_preset
from app.routers.images import read_original
from app.security import owner, rate_limit
from app.services.ai.openai_provider import get_provider
from app.state import jobs

router = APIRouter(prefix="/api/images/jobs", tags=["jobs"])

CONSENT = ("AI mode sends a downsized copy of your photo to the configured third-party AI service. "
           "Tick the consent box to continue, or use local editing, which never leaves this server.")


class JobRequest(BaseModel):
    image_id: str
    preset: str
    intensity: float = Field(100, ge=0, le=100)
    adjustments: Adjustments = Adjustments()
    mode: Literal["local", "ai"] = "local"
    fallback_to_local: bool = True
    ai_consent: bool = False


def get_job(job_id: str, who: str):
    job = jobs.get(job_id, who)
    if job is None:
        raise HTTPException(404, "Job not found. It may have expired.")
    return job


@router.post("", status_code=202, dependencies=[rate_limit("job")])
def create(req: JobRequest, who: str = Depends(owner)):
    valid_preset(req.preset)
    read_original(req.image_id, who)
    if req.mode == "ai":
        if get_provider() is None:
            raise HTTPException(503, "AI mode is not available: no AI provider is configured on this server.")
        if not req.ai_consent:
            raise HTTPException(400, CONSENT)
    params = {"preset": req.preset, "intensity": req.intensity, "adjustments": req.adjustments.model_dump()}
    return jobs.submit(who, req.image_id, params, req.mode, req.fallback_to_local).public()


@router.get("/{job_id}")
def status(job_id: str, who: str = Depends(owner)):
    return get_job(job_id, who).public()


@router.get("/{job_id}/result")
def result(job_id: str, who: str = Depends(owner)):
    job = get_job(job_id, who)
    path = jobs.result_path(job)
    if job.status != "succeeded" or path is None or not path.exists():
        raise HTTPException(409 if job.status in ("queued", "running") else 404, "The result is not available.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "no-store",
                        "Content-Disposition": f'inline; filename="cinecraft-{job.mode_used}-{job_id[:8]}.jpg"'})


@router.post("/{job_id}/retry", status_code=202, dependencies=[rate_limit("job")])
def retry(job_id: str, who: str = Depends(owner)):
    job = jobs.retry(job_id, who)
    if job is None:
        raise HTTPException(409, "Only a failed job can be retried.")
    return job.public()
