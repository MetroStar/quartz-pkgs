FROM registry1.dso.mil/ironbank/opensource/python:v3.11.8 AS base

USER root

# Runtime Python deps for the epyon web API:
#   fastapi/uvicorn       - ASGI app + server
#   aiofiles/python-multipart - async file IO + form uploads
#   httpx                 - REQUIRED: web/api/github_sync.py imports it at module
#                           load (via main.py); missing it crashes startup with
#                           ModuleNotFoundError: No module named 'httpx'
#   openai                - used by web/api/openai_summary.py for the AI summary
#                           endpoints (imported lazily, but must be present for
#                           those features to work)
RUN pip install --no-cache-dir fastapi uvicorn aiofiles python-multipart httpx openai

COPY epyon/ /app/

RUN chown -R 1000:1000 /app && \
    mkdir -p /data/scans && \
    chown -R 1000:1000 /data

USER 1000
WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=8056
ENV EPYON_SCANS_DIR=/data/scans

EXPOSE 8056

CMD ["python3", "-m", "uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8056"]
