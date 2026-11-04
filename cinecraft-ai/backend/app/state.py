"""Process-wide singletons."""
from app.services.jobs import JobManager
from app.services.projects import ProjectStore
from app.services.ratelimit import RateLimiter

jobs = JobManager()
projects = ProjectStore()
limiter = RateLimiter()
