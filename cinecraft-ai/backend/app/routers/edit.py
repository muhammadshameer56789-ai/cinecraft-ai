import logging
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.routers.images import read_original
from app.security import owner, rate_limit
from app.services import analysis as analysis_svc
from app.services import engine, exporter, storage
from app.services.limits import Busy
from app.services.presets import AUTO_ID, PRESETS, catalog

log = logging.getLogger("cinecraft.edit")
router = APIRouter(prefix="/api", tags=["editing"])
BUSY = "The server is busy rendering other photos. Try again shortly."


class Adjustments(BaseModel):
    exposure: float = Field(0, ge=-100, le=100)
    brightness: float = Field(0, ge=-100, le=100)
    contrast: float = Field(0, ge=-100, le=100)
    highlights: float = Field(0, ge=-100, le=100)
    shadows: float = Field(0, ge=-100, le=100)
    temperature: float = Field(0, ge=-100, le=100)
    tint: float = Field(0, ge=-100, le=100)
    saturation: float = Field(0, ge=-100, le=100)
    vibrance: float = Field(0, ge=-100, le=100)
    sharpness: float = Field(0, ge=0, le=100)
    fade: float = Field(0, ge=0, le=100)
    vignette: float = Field(0, ge=0, le=100)
    grain: float = Field(0, ge=0, le=100)
    green_intensity: float = Field(0, ge=-100, le=100)
    golden_intensity: float = Field(0, ge=-100, le=100)


class EditRequest(BaseModel):
    image_id: str
    preset: str
    intensity: float = Field(100, ge=0, le=100)
    max_side: int = Field(1400, ge=64, le=4096)
    adjustments: Adjustments = Adjustments()


class ExportRequest(BaseModel):
    image_id: str
    preset: str
    intensity: float = Field(100, ge=0, le=100)
    adjustments: Adjustments = Adjustments()
    format: Literal["jpeg", "png", "webp"] = "jpeg"
    quality: int = Field(92, ge=1, le=100)
    max_side: int | None = Field(None, ge=64, le=20000)


def valid_preset(pid: str):
    if pid != AUTO_ID and pid not in PRESETS:
        raise HTTPException(422, f"Unknown preset '{pid}'.")


def load_source(image_id: str, who: str):
    path = read_original(image_id, who)
    data = path.read_bytes()
    a = storage.load_json(image_id, "analysis")
    if a is None:
        a = analysis_svc.analyze_image(data)
        storage.save_json(image_id, "analysis", a)
    return data, a


def render_preview(data, a, preset, intensity, max_side, adjustments=None) -> Response:
    valid_preset(preset)
    try:
        x, info = engine.edit(data, a, preset, intensity, max_side, adjustments)
        return Response(engine.to_jpeg(x, 88 if max_side > 400 else 80), media_type="image/jpeg", headers={
            "X-Edit-Mode": info["mode"], "X-Auto-Note": info["auto_note"] or "", "Cache-Control": "no-store"})
    except Exception:
        log.exception("preview failed")
        raise HTTPException(500, "Editing failed for this image.")


def export_response(data, a, req, stem) -> Response:
    try:
        r = exporter.export_image(data, a, req.preset, req.intensity, req.adjustments.model_dump(), req.format,
                                  req.quality, req.max_side, stem)
    except Busy:
        raise HTTPException(503, BUSY, headers={"Retry-After": "15"})
    except MemoryError:
        raise HTTPException(507, "The server ran out of memory for this export. Try a smaller size.")
    except Exception:
        log.exception("export failed")
        raise HTTPException(500, "Export failed for this image.")
    return Response(r.data, media_type=r.mime, headers={
        "Content-Disposition": f"attachment; filename=\"{r.filename}\"; filename*=UTF-8''{quote(r.filename)}",
        "X-Export-Width": str(r.width), "X-Export-Height": str(r.height), "X-Export-Notes": " ".join(r.notes),
        "Cache-Control": "no-store"})


@router.get("/presets")
def presets():
    return {"presets": catalog(), "editing_mode": "local"}


@router.post("/images/edit", dependencies=[rate_limit("edit")])
def edit(req: EditRequest, who: str = Depends(owner)):
    data, a = load_source(req.image_id, who)
    return render_preview(data, a, req.preset, req.intensity, req.max_side, req.adjustments.model_dump())


@router.get("/images/{image_id}/thumbnail/{preset}", dependencies=[rate_limit("edit")])
def thumbnail(image_id: str, preset: str, size: int = Query(180, ge=64, le=400), who: str = Depends(owner)):
    data, a = load_source(image_id, who)
    return render_preview(data, a, preset, 100, size)


@router.post("/images/export", dependencies=[rate_limit("export")])
def export(req: ExportRequest, who: str = Depends(owner)):
    valid_preset(req.preset)
    data, a = load_source(req.image_id, who)
    stem = (storage.load_json(req.image_id, "meta") or {}).get("stem", "photo")
    return export_response(data, a, req, stem)
