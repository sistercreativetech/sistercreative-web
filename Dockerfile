# syntax=docker/dockerfile:1

# --- Tahap 1: build CSS (Tailwind) dan aset vendor -------------------------------
FROM node:22-alpine AS assets
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY assets ./assets
COPY templates ./templates
COPY apps ./apps
COPY static ./static
RUN npm run build && npm run vendor

# --- Tahap 2: aplikasi Django -------------------------------------------------------
FROM python:3.12-slim AS app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod

WORKDIR /app

RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --home /app app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY --chown=app:app . .
COPY --from=assets --chown=app:app /build/static/css/app.css ./static/css/app.css
COPY --from=assets --chown=app:app /build/static/vendor ./static/vendor

# collectstatic butuh settings lengkap; nilai di bawah hanya untuk tahap build.
RUN DJANGO_SECRET_KEY=build-only POSTGRES_DB=x POSTGRES_USER=x POSTGRES_PASSWORD=x \
    python manage.py collectstatic --noinput \
    && mkdir -p /app/media \
    && chown app:app /app \
    && chown -R app:app /app/staticfiles /app/media \
    && chmod +x /app/docker/entrypoint.sh

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz/', timeout=4).status == 200 else 1)"

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "docker/gunicorn.conf.py"]
