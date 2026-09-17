# Backend image: Django API (gunicorn) and the Celery worker both build
# from this image — see docker-compose.yml, which points the worker
# service's `command` at `celery -A deid_backend worker` instead of
# gunicorn. One image, two run modes, so they can never drift apart.
FROM python:3.13-slim AS base

# tesseract-ocr: the OCR fallback (documents/extraction.py) shells out to
# the `tesseract` binary, not just the pytesseract Python package.
# poppler-utils/libgl1: transitive rendering deps for pymupdf/pdfplumber
# page rasterization. build-essential: compiles any source wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libgl1 \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt gunicorn

COPY . .

# No DB access needed for static assets (DRF's browsable-API CSS/JS, admin
# static files) — safe and correct to do at build time. STORAGE_PROVIDER is
# intentionally left unset here so this always uses local FileSystemStorage
# regardless of the deployment's runtime storage backend.
RUN python manage.py collectstatic --noinput

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/media /app/staticfiles \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8000/api/auth/me/ -o /dev/null -w '%{http_code}' | grep -qE '^(200|401)$' || exit 1

# Migrations run as their own one-shot service in docker-compose.yml
# (`migrate`), not here — running `migrate` from both the api and worker
# services on every start would race the same database. This image's
# default command just serves; the worker service overrides `command`.
CMD ["gunicorn", "deid_backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]
