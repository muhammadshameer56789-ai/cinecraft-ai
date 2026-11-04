import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config
from app.routers import edit, images, jobs as jobs_router, projects as projects_router
from app.services import storage
from app.services.ai.openai_provider import get_provider
from app.services.sessions import new_session_id, valid_session
from app.state import jobs, projects

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("cinecraft")
SESSION_COOKIE = "cc_session"


async def _janitor():
    while True:
        try:
            storage.cleanup_expired(); jobs.cleanup(); projects.purge_expired()
        except Exception:
            log.exception("cleanup failed")
        await asyncio.sleep(300)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_janitor())
    yield
    task.cancel()


app = FastAPI(title="CINECRAFT AI", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition", "X-Export-Width", "X-Export-Height", "X-Export-Notes", "X-Auto-Note"])


@app.middleware("http")
async def session_and_safety(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > config.MAX_BODY_BYTES:
        return JSONResponse({"detail": f"Request too large (limit {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB)."}, status_code=413)
    sid = request.cookies.get(SESSION_COOKIE)
    fresh = not valid_session(sid)
    if fresh:
        sid = new_session_id()
    request.state.session = sid
    response = await call_next(request)
    if fresh:
        response.set_cookie(SESSION_COOKIE, sid, httponly=True, samesite="lax", secure=config.COOKIE_SECURE, max_age=60 * 60 * 24 * 365)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("X-Frame-Options", "DENY")
    return response


@app.exception_handler(Exception)
async def unexpected(request: Request, exc: Exception):
    ref = secrets.token_hex(4)
    log.error("unhandled error ref=%s path=%s", ref, request.url.path, exc_info=exc)  # logged without request bodies or file paths
    return JSONResponse({"detail": f"Something went wrong on the server (ref {ref})."}, status_code=500)


# jobs router first so /api/images/jobs/... is never read as an image id
app.include_router(jobs_router.router)
app.include_router(images.router)
app.include_router(edit.router)
app.include_router(projects_router.router)


@app.get("/api/health")
def health():
    p = get_provider()
    return {"status": "ok", "editing_mode": "local", "ai_provider": {"configured": p is not None, "name": p.name if p else None},
            "limits": {"max_upload_mb": config.MAX_UPLOAD_BYTES // (1024 * 1024), "max_megapixels": config.MAX_PIXELS // 1_000_000,
                       "export_max_megapixels": config.EXPORT_MAX_PIXELS // 1_000_000}}


@app.get("/api/privacy")
def privacy():
    p = get_provider()
    return {
        "uploads": f"Photos you upload are kept in temporary storage on this server for {config.RETENTION_MINUTES} minutes after last use, then deleted. You can remove a photo at any time.",
        "projects": f"Saved projects (including the original photo) are kept for {config.PROJECT_RETENTION_DAYS} days after their last change, tied to this browser's anonymous session (no account). You can delete them at any time.",
        "ai": (f"AI mode is available using '{p.name}'. It sends a downsized copy of the photo to that third-party service, only when you tick the consent box. Their terms apply."
               if p else "AI mode is not configured, so photos are never sent to any third party."),
        "training": "This app does not use your photos to train models.",
        "cookies": "One essential cookie identifies your browser session so only you can see your photos and projects.",
    }
