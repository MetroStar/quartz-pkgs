FROM registry1.dso.mil/ironbank/opensource/python/python311:v3.11 AS base

USER root

RUN pip install --no-cache-dir fastapi uvicorn aiofiles python-multipart

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
