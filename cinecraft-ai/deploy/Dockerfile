# UNTESTED sample: build with `docker build -f deploy/Dockerfile -t cinecraft-api .` from the repository root.
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
ENV STORAGE_DIR=/data/storage PROJECT_DIR=/data/projects DB_PATH=/data/projects.db COOKIE_SECURE=true TRUSTED_PROXY=true
VOLUME /data
EXPOSE 8000
# ONE worker on purpose: jobs, rate limits and the render slot are in-process. See README "Scaling".
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
