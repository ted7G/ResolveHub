# Production image. Coolify builds it straight from the repository; any
# other Docker host works the same way. Configuration comes entirely from
# environment variables at runtime (see .env.example).

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8000

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Static files are baked into the image. Settings insist on real values for
# the database and storage, so placeholders stand in; nothing connects to
# them during collectstatic.
RUN SECRET_KEY=collectstatic-only \
    DATABASE_URL=postgres://build@localhost/build \
    S3_BUCKET_NAME=build S3_ENDPOINT_URL=http://localhost \
    S3_ACCESS_KEY_ID=build S3_SECRET_ACCESS_KEY=build \
    python manage.py collectstatic --no-input

RUN useradd --create-home --uid 10001 app \
    && chmod +x docker-entrypoint.sh
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/healthz', timeout=4)"

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application"]
