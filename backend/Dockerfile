# syntax=docker/dockerfile:1
# RAKSHA NET AI — backend image.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# No system packages: psycopg[binary] ships its own libpq, and the health check
# below uses Python's standard library instead of curl. Fewer packages, fewer CVEs
# to patch, and no apt mirror needed at build time.

WORKDIR /app

# Dependencies are copied first so a source change does not re-resolve them.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
# The AI boundary is imported by the backend, so it ships in the same image.
COPY ai/ /app/ai/

# Never run as root: a container escape should not start with a free uid 0.
RUN useradd --create-home --uid 10001 raksha \
    && mkdir -p /app/storage/media \
    && chown -R raksha:raksha /app
USER raksha

ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/v1/health/ready', timeout=4)"]

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
