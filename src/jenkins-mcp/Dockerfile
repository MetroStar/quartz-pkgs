# Jenkins MCP server image for Quartz.
#
# A small FastMCP (Streamable HTTP) server that exposes read-mostly Jenkins
# tools (plus build triggering) to kagent agents. Deployed in-cluster via a
# kagent.dev MCPServer resource and consumed by the cicd-agent.
#
# Built from the Iron Bank hardened Python base (matching the other quartz-pkgs
# images, e.g. epyon) rather than Docker Hub. The Iron Bank image already ships
# a non-root user (uid 1000), which satisfies the cluster Kyverno
# require-non-root-user / require-non-root-group policies.
ARG PYTHON_VERSION=v3.11.8

FROM registry1.dso.mil/ironbank/opensource/python:${PYTHON_VERSION}

LABEL org.opencontainers.image.title="quartz-jenkins-mcp" \
      org.opencontainers.image.description="FastMCP server exposing Jenkins tools to kagent agents" \
      org.opencontainers.image.source="https://github.com/MetroStar/quartz-pkgs"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

USER root

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py ./
RUN chown -R 1000:1000 /app

USER 1000

EXPOSE 3000

CMD ["python3", "server.py"]
