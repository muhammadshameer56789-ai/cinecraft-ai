import os
from pathlib import Path

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "20")) * 1024 * 1024
MAX_PIXELS = int(os.getenv("MAX_PIXELS", "60000000"))
STORAGE_DIR = Path(os.getenv("STORAGE_DIR", "./storage")).resolve()
RETENTION_MINUTES = int(os.getenv("RETENTION_MINUTES", "60"))
CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o]
ALLOWED_FORMATS = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}
ANALYSIS_MAX_SIDE = 1024
LOW_RES_PIXELS = 640 * 480
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip()  # empty = not configured
EXPORT_MAX_PIXELS = int(os.getenv("EXPORT_MAX_PIXELS", "12000000"))  # ~150 MB RAM per megapixel

HEAVY_CONCURRENCY = int(os.getenv("HEAVY_CONCURRENCY", "1"))      # simultaneous full-size renders
MAX_BODY_BYTES = MAX_UPLOAD_BYTES + 1024 * 1024
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
TRUSTED_PROXY = os.getenv("TRUSTED_PROXY", "false").lower() == "true"
DB_PATH = Path(os.getenv("DB_PATH", "./data/projects.db")).resolve()
PROJECT_DIR = Path(os.getenv("PROJECT_DIR", "./data/projects")).resolve()
PROJECT_RETENTION_DAYS = int(os.getenv("PROJECT_RETENTION_DAYS", "14"))
MAX_PROJECTS_PER_SESSION = int(os.getenv("MAX_PROJECTS_PER_SESSION", "50"))
JOB_TTL_MINUTES = int(os.getenv("JOB_TTL_MINUTES", "30"))
RATE_LIMITS = {"upload": (20, 60), "edit": (240, 60), "job": (12, 60), "export": (20, 60), "projects": (60, 60)}
# AI provider (all optional). Empty AI_PROVIDER = local editing only.
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-image-1").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://api.openai.com").strip().rstrip("/")
AI_TIMEOUT_S = int(os.getenv("AI_TIMEOUT_S", "120"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "2"))
AI_MAX_SIDE = 1536
AI_MIN_SIMILARITY = float(os.getenv("AI_MIN_SIMILARITY", "0.55"))
