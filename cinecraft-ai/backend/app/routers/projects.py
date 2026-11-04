from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import config
from app.routers.edit import Adjustments, ExportRequest, export_response, load_source, render_preview
from app.routers.images import read_original
from app.security import owner, rate_limit
from app.services import analysis as analysis_svc
from app.services import storage
from app.services.projects import ProjectError
from app.state import projects

router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[rate_limit("projects")])


class ProjectCreate(BaseModel):
    image_id: str
    name: str = Field(min_length=1, max_length=80)
    preset: str
    intensity: float = Field(100, ge=0, le=100)
    adjustments: Adjustments = Adjustments()


class ProjectUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=80)
    preset: str | None = None
    intensity: float | None = Field(None, ge=0, le=100)
    adjustments: Adjustments | None = None


class ProjectExport(BaseModel):
    format: Literal["jpeg", "png", "webp"] = "jpeg"
    quality: int = Field(92, ge=1, le=100)
    max_side: int | None = Field(None, ge=64, le=20000)


def guarded(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except ProjectError as e:
        raise HTTPException(e.status, e.message)


def _analysis(data: bytes):
    return analysis_svc.analyze_image(data)


@router.post("", status_code=201)
def create(req: ProjectCreate, who: str = Depends(owner)):
    path = read_original(req.image_id, who)
    meta = storage.load_json(req.image_id, "meta") or {}
    from app.services.exporter import source_size
    data = path.read_bytes()
    w, h = source_size(data)
    return guarded(projects.create, who, req.name, data, path.suffix.lstrip("."), meta.get("stem", "photo"), req.preset,
                   req.intensity, req.adjustments.model_dump(), w, h)


@router.get("")
def list_projects(who: str = Depends(owner)):
    return {"projects": projects.list(who), "retention_days": config.PROJECT_RETENTION_DAYS,
            "note": "Projects are saved on this server for this browser only (no account). Clearing cookies or switching browsers loses access."}


@router.get("/{pid}")
def get(pid: str, who: str = Depends(owner)):
    return guarded(projects.get, who, pid)


@router.patch("/{pid}")
def update(pid: str, req: ProjectUpdate, who: str = Depends(owner)):
    return guarded(projects.update, who, pid, req.name, req.preset, req.intensity,
                   req.adjustments.model_dump() if req.adjustments else None)


@router.delete("/{pid}", status_code=204)
def delete(pid: str, who: str = Depends(owner)):
    guarded(projects.delete, who, pid)


@router.get("/{pid}/original")
def original(pid: str, who: str = Depends(owner)):
    data, p = guarded(projects.original, who, pid)
    return Response(data, media_type="image/" + ("jpeg" if p["ext"] == "jpg" else p["ext"]), headers={"Cache-Control": "private, max-age=300"})


@router.get("/{pid}/preview")
def preview(pid: str, size: int = 1400, who: str = Depends(owner)):
    data, p = guarded(projects.original, who, pid)
    return render_preview(data, _analysis(data), p["preset"], p["intensity"], max(64, min(size, 2000)), p["adjustments"])


@router.post("/{pid}/open", status_code=201)
def open_project(pid: str, who: str = Depends(owner)):
    """Copy the saved original back into temporary storage so it can be edited again."""
    data, p = guarded(projects.original, who, pid)
    image_id = storage.register_copy(data, p["ext"], p["stem"], who)
    return {"image_id": image_id, "format": {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[p["ext"]], "width": p["width"],
            "height": p["height"], "size_bytes": len(data), "retention_minutes": config.RETENTION_MINUTES,
            "stored_on": "this server's temporary storage", "project": p}


@router.post("/{pid}/export", dependencies=[rate_limit("export")])
def export(pid: str, req: ProjectExport, who: str = Depends(owner)):
    data, p = guarded(projects.original, who, pid)
    full = ExportRequest(image_id="-", preset=p["preset"], intensity=p["intensity"], adjustments=Adjustments(**p["adjustments"]),
                         format=req.format, quality=req.quality, max_side=req.max_side)
    return export_response(data, _analysis(data), full, storage.safe_stem(p["stem"]))
