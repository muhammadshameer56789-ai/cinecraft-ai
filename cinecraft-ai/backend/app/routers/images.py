from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app import config
from app.security import owner, rate_limit
from app.services import analysis, storage
from app.services.validation import ImageRejected, validate_image_bytes
from app.state import jobs

router = APIRouter(prefix="/api/images", tags=["images"])


class AnalyzeRequest(BaseModel):
    image_id: str


def read_original(image_id: str, who: str):
    """404 for missing AND for someone else's image, so ids reveal nothing."""
    path = storage.find_original(image_id)
    if path is None or not storage.owner_ok(image_id, who):
        raise HTTPException(404, "Image not found. It may have expired; upload it again.")
    return path


@router.post("/upload", status_code=201, dependencies=[rate_limit("upload")])
async def upload(file: UploadFile = File(...), who: str = Depends(owner)):
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    try:
        info = validate_image_bytes(data)
    except ImageRejected as e:
        raise HTTPException(e.status, e.message)
    image_id = storage.new_id()
    storage.save_original(image_id, data, config.ALLOWED_FORMATS[info.fmt])
    storage.save_json(image_id, "meta", {"stem": storage.safe_stem(file.filename), "owner": who})
    return {"image_id": image_id, "format": info.fmt, "width": info.width, "height": info.height, "size_bytes": len(data),
            "retention_minutes": config.RETENTION_MINUTES,
            "stored_on": "this server's temporary storage; sent to no third party unless you choose AI mode"}


@router.post("/analyze", dependencies=[rate_limit("edit")])
def analyze(req: AnalyzeRequest, who: str = Depends(owner)):
    path = read_original(req.image_id, who)
    try:
        result = analysis.analyze_image(path.read_bytes())
    except Exception:
        raise HTTPException(500, "Analysis failed for this image.")
    storage.save_json(req.image_id, "analysis", result)
    return result


@router.get("/{image_id}/original")
def original(image_id: str, who: str = Depends(owner)):
    return FileResponse(read_original(image_id, who), headers={"Cache-Control": "private, max-age=300"})


@router.delete("/{image_id}", status_code=204)
def remove(image_id: str, who: str = Depends(owner)):
    read_original(image_id, who)
    jobs.forget_image(image_id)
    storage.delete(image_id)
