# Hito - single container, no build step at image-build time.
#
# The frontend (web/) is compiled to app/static and committed, so this image
# needs Python only. That is deliberate: judges and reviewers get the same
# artifact whether they run `docker build`, deploy to Render, or just run
# uvicorn on their laptop.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HITO_DB=/data/hito.db

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY scripts ./scripts

# SQLite lives on a writable volume so a redeploy does not wipe the ledger.
RUN mkdir -p /data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/status', timeout=4).status == 200 else 1)"

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
