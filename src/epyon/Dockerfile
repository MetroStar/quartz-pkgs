FROM registry1.dso.mil/ironbank/opensource/python:v3.14 AS base

USER root

# System binaries the scan runner shells out to. The in-cluster epyon pod runs
# hardened (no docker/podman), so every scanner script that would normally fall
# back to a container runtime instead skips. To run a FULL scan in-pod, the
# scanners must be present as native binaries. Each run-*-scan.sh prefers a
# local install (`command -v <tool>`) before the container fallback, so simply
# having these on PATH makes the corresponding layer execute natively.
#
# dnf-provided:
#   git   - REQUIRED: web/api/jobs.py clones remote repo/HF targets via
#           `git clone` (asyncio.create_subprocess_exec). Without it the clone
#           raises FileNotFoundError before returncode is set, so the job hangs
#           forever at "Cloning …" (status stays "running"). The old v3.11.8
#           base shipped git implicitly; the v3.14 base does not.
#   jq    - JSON parsing in most scan/enrichment scripts (run-xeol/grype/
#           trivy-scan.sh, enrich-findings.sh); guarded with `command -v jq`.
#   nmap  - Network Discovery layer (run-network-discovery.sh) active scan.
RUN dnf install -y git jq nmap \
    && dnf clean all && rm -rf /var/cache/dnf

# ClamAV (Malware layer, run-clamav-scan.sh): clamscan + freshclam. clamav is
# not in the UBI 10 repos and lives in EPEL. To keep supply-chain hygiene high
# we do NOT install epel-release or drop a persistent EPEL repo file into the
# image; instead EPEL is attached EPHEMERALLY for this single transaction via
# --repofrompath, with GPG verification enabled against the official EPEL 10 key
# and weak deps disabled to pull the minimal closure. Nothing EPEL-related
# survives in the final image: no enabled third-party repo, no epel-release rpm.
# The EPEL package that provides freshclam is clamav-freshclam (the RHEL-style
# `clamav-update` name does not exist on EPEL 10). The virus DB itself is
# populated at runtime via freshclam (kept out of the image so it stays current
# and the layer stays small).
RUN set -eux; \
    rpm --import https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-10; \
    dnf install -y --setopt=install_weak_deps=False \
      --repofrompath "epel,https://dl.fedoraproject.org/pub/epel/10/Everything/$(uname -m)/" \
      --setopt=epel.gpgcheck=1 \
      --setopt=epel.gpgkey=https://dl.fedoraproject.org/pub/epel/RPM-GPG-KEY-EPEL-10 \
      clamav clamav-freshclam; \
    command -v clamscan && command -v freshclam; \
    dnf clean all && rm -rf /var/cache/dnf /etc/yum.repos.d/epel*.repo

# Scanner binaries not packaged in the base image, installed to /usr/local/bin
# via each project's official install script. Versions float to latest stable
# so the nightly image rebuild tracks upstream scanner releases (see
# .github/workflows/epyon.yaml); pin a VERSION here for air-gapped reproducible
# builds if required.
#   syft       - SBOM layer (run-sbom-scan.sh / run-complete-sbom-scan.sh)
#   grype      - Vulnerability + Anchore layers (run-grype-scan.sh, run-anchore-scan.sh)
#   trivy      - Container/filesystem layer (run-trivy-scan.sh)
#   trufflehog - Secret-scanning layer (run-trufflehog-scan.sh)
#   xeol       - End-of-life layer (run-xeol-scan.sh)
#   helm       - Helm Build layer (run-helm-build.sh)
RUN set -eux; \
    curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh        | sh -s -- -b /usr/local/bin; \
    curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh       | sh -s -- -b /usr/local/bin; \
    curl -sSfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b /usr/local/bin; \
    curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh | sh -s -- -b /usr/local/bin; \
    curl -sSfL https://raw.githubusercontent.com/xeol-io/xeol/main/install.sh         | sh -s -- -b /usr/local/bin; \
    curl -sSfL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3    | bash; \
    syft version && grype version && trivy --version && trufflehog --version && xeol version && helm version

# Runtime Python deps for the epyon web API + pip-installed scanners:
#   fastapi/uvicorn       - ASGI app + server
#   aiofiles/python-multipart - async file IO + form uploads
#   httpx                 - REQUIRED: web/api/github_sync.py imports it at module
#                           load (via main.py); missing it crashes startup with
#                           ModuleNotFoundError: No module named 'httpx'
#   openai                - used by web/api/openai_summary.py for the AI summary
#                           endpoints (imported lazily, but must be present for
#                           those features to work). As of MetroStar/epyon#129
#                           these honor a self-hosted OpenAI-compatible base_url
#                           (e.g. in-cluster Ollama) with no real OpenAI key.
#   checkov               - IaC layer (run-checkov-scan.sh); native binary so the
#                           layer runs without a container runtime.
#   picklescan            - Pickle layer (run-picklescan.sh); the script
#                           auto-installs it on demand, but baking it in keeps
#                           the hardened pod (no outbound pip) self-sufficient.
RUN pip install --no-cache-dir fastapi uvicorn aiofiles python-multipart httpx openai checkov picklescan

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
