from fastapi import Depends, HTTPException, Request

from app import config
from app.state import limiter


def client_ip(request: Request) -> str:
    if config.TRUSTED_PROXY:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def owner(request: Request) -> str:
    """The anonymous browser session id set by the session middleware."""
    sid = getattr(request.state, "session", None)
    if not sid:
        raise HTTPException(401, "No session. Reload the page.")
    return sid


def rate_limit(group: str):
    def dep(request: Request):
        limit, window = config.RATE_LIMITS[group]  # read per request so limits can be tuned/tested without a restart
        ok, retry = limiter.check(f"{client_ip(request)}:{group}", limit, window)
        if not ok:
            raise HTTPException(429, "Too many requests. Please slow down and try again shortly.",
                                headers={"Retry-After": str(int(retry) + 1)})
    return Depends(dep)
