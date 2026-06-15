# syntax=docker/dockerfile:1.7
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
#   hostname - scan-manifest generation shells out to `hostname`; without it
#           the scan still finishes, but the metadata/HTML path logs a noisy
#           warning and omits the host field.
#   jq    - JSON parsing in most scan/enrichment scripts (run-xeol/grype/
#           trivy-scan.sh, enrich-findings.sh); guarded with `command -v jq`.
#   nmap  - Network Discovery layer (run-network-discovery.sh) active scan.
#   nodejs/npm/java - SonarQube layer. The upstream runner invokes the
#           sonarqube-scanner npm package via npx, and the scanner needs a JVM.
RUN dnf install -y git hostname jq nmap nodejs npm java-21-openjdk-headless \
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

# SonarQube scanner for the Code Quality layer. Install it during the image
# build so CI scans do not try to download npm packages at runtime.
RUN npm install -g sonarqube-scanner \
    && command -v node \
    && command -v npm \
    && command -v npx \
    && command -v sonar-scanner

COPY epyon/ /app/

# The GitHub Actions checkout used to populate src/epyon/epyon may include a
# CI-only HTTP extraheader in .git/config. If that metadata is copied into the
# runtime image, scanner jobs send a stale credential when cloning any GitHub
# target, causing even public repositories to fail with an auth prompt. Exclude
# .git via .dockerignore so credential-bearing metadata never enters the image.
RUN git config --global --unset-all http.https://github.com/.extraheader || true

# Quartz runs the Epyon scanner in hardened Kubernetes/Jenkins pods where a
# Docker daemon/socket is intentionally unavailable. The upstream scripts are
# workstation-friendly and globally require Docker before dispatching scan
# layers, even for analysis-mode layers that can run from native CLIs. Patch the
# checked-out source at build time until the upstream scanner carries the same
# native-toolchain behavior.
RUN python3 - <<'PY'
import re
from pathlib import Path

def replace(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text()
    if old not in text:
        raise SystemExit(f"expected snippet not found in {path}")
    file_path.write_text(text.replace(old, new))

def regex_replace(path: str, pattern: str, replacement: str, count: int = 1) -> None:
    file_path = Path(path)
    text = file_path.read_text()
    new_text, replaced = re.subn(pattern, replacement, text, count=count, flags=re.S)
    if replaced != count:
        raise SystemExit(f"expected {count} regex replacement(s), got {replaced} in {path}")
    file_path.write_text(new_text)

replace(
    "/app/scripts/shell/run-target-security-scan.sh",
    """# Check if Docker is installed
if ! command -v docker &>/dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    echo -e "${YELLOW}💡 Install options:${NC}"
    echo -e "${YELLOW}   - Docker Engine: https://docs.docker.com/engine/install/${NC}"
    echo -e "${YELLOW}   - Docker Desktop: https://docker.com${NC}"
    echo -e "${YELLOW}   - Colima (macOS): brew install colima docker${NC}"
    echo -e "${YELLOW}   - Rancher Desktop: https://rancherdesktop.io/${NC}"
    exit 1
fi

# Check if Docker daemon is running
if check_docker_running; then
    echo -e "${GREEN}✅ Docker is running${NC}"
else
    echo -e "${YELLOW}⚠️  Docker is not running${NC}"
    start_docker
fi

# Verify Docker is working with a quick test
echo -n "   Verifying Docker connectivity... "
if docker ps &>/dev/null; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${RED}FAILED${NC}"
    echo -e "${RED}❌ Docker is running but not responding properly${NC}"
    exit 1
fi

echo ""
""",
    """if [[ "${EPYON_REQUIRE_DOCKER:-false}" == "true" ]]; then
    # Check if Docker is installed
    if ! command -v docker &>/dev/null; then
        echo -e "${RED}❌ Error: Docker is not installed${NC}"
        echo -e "${YELLOW}💡 Install options:${NC}"
        echo -e "${YELLOW}   - Docker Engine: https://docs.docker.com/engine/install/${NC}"
        echo -e "${YELLOW}   - Docker Desktop: https://docker.com${NC}"
        echo -e "${YELLOW}   - Colima (macOS): brew install colima docker${NC}"
        echo -e "${YELLOW}   - Rancher Desktop: https://rancherdesktop.io/${NC}"
        exit 1
    fi

    # Check if Docker daemon is running
    if check_docker_running; then
        echo -e "${GREEN}✅ Docker is running${NC}"
    else
        echo -e "${YELLOW}⚠️  Docker is not running${NC}"
        start_docker
    fi

    # Verify Docker is working with a quick test
    echo -n "   Verifying Docker connectivity... "
    if docker ps &>/dev/null; then
        echo -e "${GREEN}OK${NC}"
    else
        echo -e "${RED}FAILED${NC}"
        echo -e "${RED}❌ Docker is running but not responding properly${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✅ Native scanner image mode${NC}"
    echo -e "${CYAN}   Docker daemon preflight skipped. Set EPYON_REQUIRE_DOCKER=true for image/socket-backed layers.${NC}"
fi

echo ""
""",
)

replace(
    "/app/scripts/shell/run-target-security-scan.sh",
    """# Create dedicated scan directory
REPORTS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SCAN_DIR="$REPORTS_ROOT/scans/$SCAN_ID"
mkdir -p "$SCAN_DIR"
""",
    """# Create dedicated scan directory. In Kubernetes/Jenkins, EPYON_SCANS_DIR
# points at the mounted persistent scan volume; local workstation runs keep the
# upstream reports-root default.
REPORTS_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
SCAN_ROOT="${EPYON_SCANS_DIR:-$REPORTS_ROOT/scans}"
SCAN_DIR="$SCAN_ROOT/$SCAN_ID"
mkdir -p "$SCAN_DIR"
""",
)

replace(
    "/app/scripts/shell/generate-scan-findings-summary.sh",
    """    # Determine paths
    local SCAN_DIR="$project_root/scans/$scan_id"
    local OUTPUT_FILE="$SCAN_DIR/security-findings-summary.json"
    local OUTPUT_HTML="$SCAN_DIR/security-findings-summary.html"
""",
    """    # Determine paths. Quartz can mount scan output outside the upstream
    # reports root (for example /data/scans in Kubernetes/Jenkins), so use the
    # same scan root selected by run-target-security-scan.sh.
    local SCAN_ROOT="${EPYON_SCANS_DIR:-$project_root/scans}"
    local SCAN_DIR="$SCAN_ROOT/$scan_id"
    local OUTPUT_FILE="$SCAN_DIR/security-findings-summary.json"
    local OUTPUT_HTML="$SCAN_DIR/security-findings-summary.html"
""",
)

replace(
    "/app/scripts/shell/run-anchore-scan.sh",
    """# Ensure Docker is running (auto-starts Docker Desktop / Colima / OrbStack if needed)
ensure_docker_running
log "✅ Docker is available"

# Prefer local grype/syft installations to avoid Docker volume-mount issues on macOS
""",
    """# Prefer local grype/syft installations to avoid Docker volume-mount issues on macOS
if command -v grype &>/dev/null && command -v syft &>/dev/null; then
    log "✅ Native grype/syft available; Docker preflight skipped for filesystem/SBOM analysis"
else
    ensure_docker_running
    log "✅ Docker is available"
fi

""",
)

replace(
    "/app/scripts/shell/run-xeol-scan.sh",
    """# Ensure Docker is running (auto-starts Docker Desktop / Colima / OrbStack if needed)
ensure_docker_running

echo
""",
    """# Filesystem analysis can use the native xeol binary baked into the Quartz
# image. Docker remains required only for Docker image/socket-backed targets.
if command -v xeol &>/dev/null && [[ "${EPYON_REQUIRE_DOCKER:-false}" != "true" ]]; then
    echo -e "${GREEN}✅ Native xeol available; Docker preflight skipped${NC}"
else
    ensure_docker_running
fi

echo
""",
)

replace(
    "/app/scripts/shell/run-xeol-scan.sh",
    """# Create persistent volume for Xeol cache to speed up subsequent scans
XEOL_CACHE_VOL="xeol-cache"
${CONTAINER_CLI} volume create "$XEOL_CACHE_VOL" 2>/dev/null || true

# Update Xeol EOL database before scanning
echo -e "${CYAN}📥 Updating Xeol end-of-life database...${NC}"
echo "This ensures we have the latest EOL data..."

${CONTAINER_CLI} run --rm \\
    -v "$XEOL_CACHE_VOL:/root/.cache" \\
    noqcks/xeol:latest \\
    db update 2>&1 | tee -a "$SCAN_LOG"
""",
    """# Prefer native Xeol when present; Docker is only needed for image/socket
# targets in workstation mode.
LOCAL_XEOL="$(command -v xeol 2>/dev/null || true)"
XEOL_CACHE_VOL="xeol-cache"
if [ -z "$LOCAL_XEOL" ] && [ -n "${CONTAINER_CLI:-}" ]; then
    ${CONTAINER_CLI} volume create "$XEOL_CACHE_VOL" 2>/dev/null || true
fi

# Update Xeol EOL database before scanning
echo -e "${CYAN}📥 Updating Xeol end-of-life database...${NC}"
echo "This ensures we have the latest EOL data..."

if [ -n "$LOCAL_XEOL" ]; then
    "$LOCAL_XEOL" db update 2>&1 | tee -a "$SCAN_LOG" || true
else
    ${CONTAINER_CLI} run --rm \\
        -v "$XEOL_CACHE_VOL:/root/.cache" \\
        noqcks/xeol:latest \\
        db update 2>&1 | tee -a "$SCAN_LOG"
fi
""",
)

replace(
    "/app/scripts/shell/run-xeol-scan.sh",
    """# Show database info
echo -e "${CYAN}📋 Checking Xeol database status...${NC}"
${CONTAINER_CLI} run --rm \\
    -v "$XEOL_CACHE_VOL:/root/.cache" \\
    noqcks/xeol:latest \\
    db status 2>&1 | tee -a "$SCAN_LOG"
echo
""",
    """# Show database info
echo -e "${CYAN}📋 Checking Xeol database status...${NC}"
if [ -n "$LOCAL_XEOL" ]; then
    "$LOCAL_XEOL" db status 2>&1 | tee -a "$SCAN_LOG" || true
else
    ${CONTAINER_CLI} run --rm \\
        -v "$XEOL_CACHE_VOL:/root/.cache" \\
        noqcks/xeol:latest \\
        db status 2>&1 | tee -a "$SCAN_LOG"
fi
echo
""",
)

regex_replace(
    "/app/scripts/shell/run-xeol-scan.sh",
    r"""        # Run xeol scan with Docker using cached/updated database
        if \[ "\$scan_type" = "dir" \]; then
            # For directory scans, mount the target directory
            \$\{CONTAINER_CLI\} run --rm \\
                -v "\$target:/workspace:ro" \\
                -v "\$XEOL_CACHE_VOL:/root/\.cache" \\
                noqcks/xeol:latest \\
                dir:/workspace \\
                -o json 2>>"\$SCAN_LOG" > "\$full_output_path"
        else
            # For image scans, mount Docker socket to access host's Docker daemon
            \$\{CONTAINER_CLI\} run --rm \\
                -v /var/run/docker\.sock:/var/run/docker\.sock \\
                -v "\$XEOL_CACHE_VOL:/root/\.cache" \\
                noqcks/xeol:latest \\
                "docker:\$target" \\
                -o json 2>>"\$SCAN_LOG" > "\$full_output_path"
        fi
""",
    """        # Run xeol scan. Native directory scans work in hardened pods without
        # Docker; image/socket targets still fall back to Docker workstation mode.
        if [ -n "$LOCAL_XEOL" ] && [ "$scan_type" = "dir" ]; then
            "$LOCAL_XEOL" dir:"$target" -o json 2>>"$SCAN_LOG" > "$full_output_path"
        elif [ "$scan_type" = "dir" ]; then
            ${CONTAINER_CLI} run --rm \\
                -v "$target:/workspace:ro" \\
                -v "$XEOL_CACHE_VOL:/root/.cache" \\
                noqcks/xeol:latest \\
                dir:/workspace \\
                -o json 2>>"$SCAN_LOG" > "$full_output_path"
        else
            ${CONTAINER_CLI} run --rm \\
                -v /var/run/docker.sock:/var/run/docker.sock \\
                -v "$XEOL_CACHE_VOL:/root/.cache" \\
                noqcks/xeol:latest \\
                "docker:$target" \\
                -o json 2>>"$SCAN_LOG" > "$full_output_path"
        fi
""",
)

replace(
    "/app/scripts/shell/run-clamav-scan.sh",
    """    # Pull ClamAV Docker image (try primary, then fallback)
    CLAMAV_PULL_OK=false
""",
    """    # Prefer native ClamAV when present. Docker remains a workstation fallback.
    if command -v clamscan >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Using native ClamAV installation: $(clamscan --version 2>/dev/null | head -1)${NC}"
        echo -e "${CYAN}📥 Updating ClamAV virus definitions...${NC}"
        if command -v freshclam >/dev/null 2>&1; then
            freshclam --stdout 2>&1 | tee -a "$SCAN_LOG" || true
        else
            echo -e "${YELLOW}⚠️  freshclam not available; proceeding with existing definitions${NC}"
        fi

        if ! find /var/lib/clamav -type f \\( -name '*.cvd' -o -name '*.cld' \\) -print -quit | grep -q .; then
            echo -e "${RED}❌ No ClamAV virus definitions available after freshclam; refusing to report a no-op scan as clean${NC}" | tee -a "$SCAN_LOG"
            exit 2
        fi

        echo -e "${CYAN}📋 Checking virus definition status...${NC}"
        clamscan --version 2>&1 | tee -a "$SCAN_LOG"

        echo -e "${BLUE}🔍 Scanning directory: $REPO_PATH${NC}"
        clamscan -r \\
            --exclude-dir=node_modules \\
            --exclude-dir=.scannerwork \\
            --scan-mail=yes \\
            --scan-html=yes \\
            --scan-pdf=yes \\
            --scan-ole2=yes \\
            --scan-archive=yes \\
            --alert-encrypted=yes \\
            --alert-encrypted-archive=yes \\
            --alert-encrypted-doc=yes \\
            --max-recursion=30 \\
            --max-filesize=2000M \\
            --max-scansize=2000M \\
            --log="$OUTPUT_DIR/${SCAN_ID}_clamav-detailed.log" \\
            "$REPO_PATH" 2>&1 | tee -a "$SCAN_LOG"
        SCAN_RESULT=${PIPESTATUS[0]}

        SCANNED_FILES=$(awk -F: '/Scanned files:/ {gsub(/ /, "", $2); scanned=$2} END {print scanned+0}' "$OUTPUT_DIR/${SCAN_ID}_clamav-detailed.log" 2>/dev/null || echo 0)
        if [ "${SCANNED_FILES:-0}" -eq 0 ]; then
            echo -e "${RED}❌ ClamAV scanned 0 files; treating this as a failed scan${NC}" | tee -a "$SCAN_LOG"
            exit 2
        fi

        if [ $BASE64_DECODED -gt 0 ]; then
            echo -e "${BLUE}🔍 Scanning decoded base64 content...${NC}"
            clamscan -r "$DECODED_DIR" 2>&1 | tee -a "$SCAN_LOG" >> "$OUTPUT_DIR/${SCAN_ID}_clamav-detailed.log"
            DECODED_SCAN_RESULT=${PIPESTATUS[0]}
            if [ $DECODED_SCAN_RESULT -eq 1 ]; then
                echo -e "${RED}🚨 THREATS FOUND in decoded base64 content!${NC}"
                SCAN_RESULT=1
            fi
        fi
    else
    # Pull ClamAV Docker image (try primary, then fallback)
    CLAMAV_PULL_OK=false
""",
)

replace(
    "/app/scripts/shell/run-clamav-scan.sh",
    """    # Create current symlink for latest results
    if [ -f "$OUTPUT_DIR/${SCAN_ID}_clamav-detailed.log" ]; then
""",
    """    fi

    # Create current symlink for latest results
    if [ -f "$OUTPUT_DIR/${SCAN_ID}_clamav-detailed.log" ]; then
""",
)

replace(
    "/app/scripts/shell/run-checkov-scan.sh",
    """# Check if Docker is available for Checkov
if [ -n "${CONTAINER_CLI:-}" ]; then
    echo "🐳 Using Docker-based Checkov..."
""",
    """# Prefer native Checkov when present. Docker remains a workstation fallback.
if command -v checkov >/dev/null 2>&1; then
    echo "✅ Using native Checkov: $(checkov --version 2>/dev/null | head -1)"
    echo -e "${BLUE}🔍 Running Checkov scan (native, skipping external dependencies)...${NC}"
    set +e
    checkov \\
        --directory "$TARGET_SCAN_DIR" \\
        --skip-path node_modules \\
        --skip-path scans \\
        --skip-path scripts/anchore-results.json \\
        --skip-path scripts/shell/scans \\
        --skip-download \\
        --output json \\
        > "$RESULTS_FILE" 2>>"$SCAN_LOG"
    SCAN_RESULT=$?
    set -e
    echo "✅ Checkov native scan completed (exit: $SCAN_RESULT)"
elif [ -n "${CONTAINER_CLI:-}" ]; then
    echo "🐳 Using Docker-based Checkov..."
""",
)

replace(
    "/app/scripts/shell/run-grype-scan.sh",
    """# Show database info
echo -e "${CYAN}📋 Checking Grype database status...${NC}"
${CONTAINER_CLI} run --rm \\
    -e GRYPE_DB_CACHE_DIR=/cache \\
    -v "$GRYPE_CACHE_VOL:/cache" \\
    anchore/grype:latest \\
    db status 2>&1 | tee -a "$SCAN_LOG"
echo
""",
    """# Show database info
echo -e "${CYAN}📋 Checking Grype database status...${NC}"
if [ -n "$LOCAL_GRYPE" ]; then
    "$LOCAL_GRYPE" db status 2>&1 | tee -a "$SCAN_LOG" || true
else
    ${CONTAINER_CLI} run --rm \\
        -e GRYPE_DB_CACHE_DIR=/cache \\
        -v "$GRYPE_CACHE_VOL:/cache" \\
        anchore/grype:latest \\
        db status 2>&1 | tee -a "$SCAN_LOG"
fi
echo
""",
)

replace(
    "/app/scripts/shell/run-grype-scan.sh",
    """            local sbom_zero
            sbom_zero=$(jq -r '[.matches[] | select(.artifact.version=="0.0.0")] | length' "$output_file" 2>/dev/null || echo "0")
""",
    """            sbom_zero=$(jq -r '[.matches[] | select(.artifact.version=="0.0.0")] | length' "$output_file" 2>/dev/null || echo "0")
""",
)

replace(
    "/app/scripts/shell/run-grype-scan.sh",
    """                local tmp_sbom="${output_file}.tmp"
""",
    """                tmp_sbom="${output_file}.tmp"
""",
)

replace(
    "/app/scripts/shell/run-sonar-analysis.sh",
    """if [[ "$SONAR_HOST_URL" != https://* ]]; then
  echo "[ERROR] SONAR_HOST_URL must use HTTPS to protect transmitted credentials and source code." >&2
  echo "[ERROR] Current value: $SONAR_HOST_URL" >&2
  exit 1
fi
""",
    """if [[ "$SONAR_HOST_URL" != https://* ]]; then
  case "$SONAR_HOST_URL" in
    http://sonarqube.sonarqube:9000|http://sonarqube.sonarqube.svc:9000|http://sonarqube.sonarqube.svc.cluster.local:9000)
      echo "[INFO] Allowing in-cluster SonarQube HTTP URL: $SONAR_HOST_URL" >&2
      ;;
    *)
      echo "[ERROR] SONAR_HOST_URL must use HTTPS unless it is the in-cluster SonarQube service." >&2
      echo "[ERROR] Current value: $SONAR_HOST_URL" >&2
      exit 1
      ;;
  esac
fi
""",
)

replace(
    "/app/scripts/shell/run-sonar-analysis.sh",
    """if [ -n "$PROPS_FILE" ]; then
  # Properties file found — cd to its directory so relative paths inside it resolve
  cd "$(dirname "$PROPS_FILE")"
  npx sonarqube-scanner \\
    -Dsonar.projectKey="$SONAR_PROJECT_KEY" \\
    -Dsonar.host.url="$SONAR_HOST_URL" \\
    -Dsonar.token="$SONAR_TOKEN" \\
    $ORG_ARG \\
    $EXTRA_ARGS \\
    2>&1 | tee "$SCANNER_LOG"
else
  # No properties file — pass sources explicitly
  cd "$REPO_PATH"
  npx sonarqube-scanner \\
    -Dsonar.projectKey="$SONAR_PROJECT_KEY" \\
    -Dsonar.sources="$REPO_PATH" \\
    -Dsonar.projectBaseDir="$REPO_PATH" \\
    -Dsonar.host.url="$SONAR_HOST_URL" \\
    -Dsonar.token="$SONAR_TOKEN" \\
    $ORG_ARG \\
    $EXTRA_ARGS \\
    2>&1 | tee "$SCANNER_LOG"
fi
""",
    """if command -v sonar-scanner >/dev/null 2>&1; then
  SONAR_SCANNER=(sonar-scanner)
elif command -v sonarqube-scanner >/dev/null 2>&1; then
  SONAR_SCANNER=(sonarqube-scanner)
elif command -v npx >/dev/null 2>&1; then
  SONAR_SCANNER=(npx --yes sonarqube-scanner)
else
  echo "[ERROR] Neither sonarqube-scanner, sonar-scanner, nor npx is available in this image." >&2
  exit 1
fi

if [ -n "$PROPS_FILE" ]; then
  # Properties file found — cd to its directory so relative paths inside it resolve
  cd "$(dirname "$PROPS_FILE")"
  "${SONAR_SCANNER[@]}" \\
    -Dsonar.projectKey="$SONAR_PROJECT_KEY" \\
    -Dsonar.host.url="$SONAR_HOST_URL" \\
    -Dsonar.token="$SONAR_TOKEN" \\
    $ORG_ARG \\
    $EXTRA_ARGS \\
    2>&1 | tee "$SCANNER_LOG"
else
  # No properties file — pass sources explicitly
  cd "$REPO_PATH"
  "${SONAR_SCANNER[@]}" \\
    -Dsonar.projectKey="$SONAR_PROJECT_KEY" \\
    -Dsonar.sources="$REPO_PATH" \\
    -Dsonar.projectBaseDir="$REPO_PATH" \\
    -Dsonar.host.url="$SONAR_HOST_URL" \\
    -Dsonar.token="$SONAR_TOKEN" \\
    $ORG_ARG \\
    $EXTRA_ARGS \\
    2>&1 | tee "$SCANNER_LOG"
fi
""",
)

replace(
    "/app/scripts/shell/run-sonar-analysis.sh",
    """echo ""
echo "✅ SonarCloud scanner completed successfully"

# ---------------------------------------------------------------------------
# Fetch metrics from API and save results JSON
# ---------------------------------------------------------------------------
""",
    """echo ""
echo "✅ SonarCloud scanner completed successfully"

# ---------------------------------------------------------------------------
# Wait for SonarQube background processing
# ---------------------------------------------------------------------------
_REPORT_TASK_FILE=""
for _candidate in \\
  "$REPO_PATH/.scannerwork/report-task.txt" \\
  "${PROPS_FILE:+$(dirname "$PROPS_FILE")/.scannerwork/report-task.txt}"; do
  if [ -n "$_candidate" ] && [ -f "$_candidate" ]; then
    _REPORT_TASK_FILE="$_candidate"
    break
  fi
done

if [ -n "$_REPORT_TASK_FILE" ]; then
  _ce_task_id=$(grep -E '^ceTaskId=' "$_REPORT_TASK_FILE" | cut -d= -f2- || true)
  if [ -n "$_ce_task_id" ] && command -v curl &>/dev/null; then
    echo "[INFO] Waiting for SonarQube background task: $_ce_task_id"
    _ce_auth_header="Authorization: Bearer ${SONAR_TOKEN}"
    _ce_status="PENDING"
    for _attempt in $(seq 1 "${SONAR_CE_WAIT_ATTEMPTS:-60}"); do
      _ce_response=$(curl -s -H "$_ce_auth_header" "${SONAR_HOST_URL}/api/ce/task?id=${_ce_task_id}" 2>/dev/null) || _ce_response=""
      if command -v jq >/dev/null 2>&1; then
        _ce_status=$(echo "$_ce_response" | jq -r '.task.status // "UNKNOWN"' 2>/dev/null || echo "UNKNOWN")
      else
        _ce_status=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("task",{}).get("status","UNKNOWN"))' <<< "$_ce_response" 2>/dev/null || echo "UNKNOWN")
      fi
      case "$_ce_status" in
        SUCCESS)
          echo "[OK] SonarQube background task completed"
          break
          ;;
        FAILED|CANCELED)
          echo "[WARNING] SonarQube background task ended with status: $_ce_status"
          break
          ;;
      esac
      sleep "${SONAR_CE_WAIT_SECONDS:-2}"
    done
    if [ "$_ce_status" != "SUCCESS" ]; then
      echo "[WARNING] Continuing with metrics fetch after SonarQube task status: $_ce_status"
    fi
  else
    echo "[WARNING] Could not find a SonarQube CE task id in $_REPORT_TASK_FILE"
  fi
else
  echo "[WARNING] SonarQube report-task.txt not found; metrics may not be ready yet"
fi

# ---------------------------------------------------------------------------
# Fetch metrics from API and save results JSON
# ---------------------------------------------------------------------------
""",
)

replace(
    "/app/scripts/shell/run-sonar-analysis.sh",
    """_coverage="n/a"
_bugs="n/a"
_vulns="n/a"
_smells="n/a"
_hotspots="n/a"

if [ -n "$_api_response" ] && echo "$_api_response" | grep -q '"component"'; then
  _extract() { echo "$_api_response" | grep -o "\\"metric\\":\\"$1\\"[^}]*\\"value\\":\\"[^\\"]*\\"" | grep -o '"value":"[^"]*"' | cut -d'"' -f4 | head -1; }
  _coverage=$(_extract coverage || echo "n/a")
  _bugs=$(_extract bugs || echo "n/a")
  _vulns=$(_extract vulnerabilities || echo "n/a")
  _smells=$(_extract code_smells || echo "n/a")
  _hotspots=$(_extract security_hotspots || echo "n/a")
  echo "[OK] Metrics fetched:"
  echo "  • Bugs              : $_bugs"
  echo "  • Vulnerabilities   : $_vulns"
  echo "  • Code Smells       : $_smells"
  echo "  • Security Hotspots : $_hotspots"
  echo "  • Coverage          : ${_coverage}%"
else
  echo "[INFO] Could not fetch metrics (API unavailable or project not yet processed)"
fi
""",
    """_coverage="n/a"
_bugs="n/a"
_vulns="n/a"
_smells="n/a"
_hotspots="n/a"
_quality_gate_status="n/a"

if [ -n "$_api_response" ] && echo "$_api_response" | grep -q '"component"'; then
  if command -v jq >/dev/null 2>&1; then
    _extract() { echo "$_api_response" | jq -r --arg metric "$1" '.component.measures[]? | select(.metric == $metric) | .value' | head -1; }
    _coverage=$(_extract coverage); _coverage=${_coverage:-n/a}
    _bugs=$(_extract bugs); _bugs=${_bugs:-n/a}
    _vulns=$(_extract vulnerabilities); _vulns=${_vulns:-n/a}
    _smells=$(_extract code_smells); _smells=${_smells:-n/a}
    _hotspots=$(_extract security_hotspots); _hotspots=${_hotspots:-n/a}
  else
    _extract() { python3 -c 'import json,sys; data=json.load(sys.stdin); metric=sys.argv[1]; print(next((m.get("value","n/a") for m in data.get("component",{}).get("measures",[]) if m.get("metric")==metric), "n/a"))' "$1" <<< "$_api_response"; }
    _coverage=$(_extract coverage)
    _bugs=$(_extract bugs)
    _vulns=$(_extract vulnerabilities)
    _smells=$(_extract code_smells)
    _hotspots=$(_extract security_hotspots)
  fi
  echo "[OK] Metrics fetched:"
  echo "  - Bugs              : $_bugs"
  echo "  - Vulnerabilities   : $_vulns"
  echo "  - Code Smells       : $_smells"
  echo "  - Security Hotspots : $_hotspots"
  echo "  - Coverage          : ${_coverage}%"
else
  echo "[INFO] Could not fetch metrics (API unavailable or project not yet processed)"
fi

_qg_url="${SONAR_HOST_URL}/api/qualitygates/project_status?projectKey=${SONAR_PROJECT_KEY}"
if command -v curl &>/dev/null; then
  _qg_response=$(curl -s -H "$_auth_header" "$_qg_url" 2>/dev/null) || _qg_response=""
  if [ -n "$_qg_response" ] && echo "$_qg_response" | grep -q '"projectStatus"'; then
    if command -v jq >/dev/null 2>&1; then
      _quality_gate_status=$(echo "$_qg_response" | jq -r '.projectStatus.status // "n/a"')
    else
      _quality_gate_status=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("projectStatus",{}).get("status","n/a"))' <<< "$_qg_response")
    fi
  fi
fi
""",
)

replace(
    "/app/scripts/shell/run-sonar-analysis.sh",
    '''  "metrics": {
    "bugs": "$_bugs",
    "vulnerabilities": "$_vulns",
    "code_smells": "$_smells",
    "security_hotspots": "$_hotspots",
    "coverage": "$_coverage"
  },
  "status": "ANALYSIS_COMPLETE"
''',
    '''  "metrics": {
    "bugs": "$_bugs",
    "vulnerabilities": "$_vulns",
    "code_smells": "$_smells",
    "security_hotspots": "$_hotspots",
    "coverage": "$_coverage"
  },
  "quality_gate_status": "$_quality_gate_status",
  "status": "ANALYSIS_COMPLETE"
''',
)
PY

RUN chown -R 1000:1000 /app && \
    (getent group 1000 >/dev/null || echo 'epyon:x:1000:' >> /etc/group) && \
    (getent passwd 1000 >/dev/null || echo 'epyon:x:1000:1000:Epyon:/tmp:/sbin/nologin' >> /etc/passwd) && \
    mkdir -p /data/scans && \
    chown -R 1000:1000 /data && \
    mkdir -p /var/lib/clamav /var/log/clamav && \
    sed -i 's/^DatabaseOwner /# DatabaseOwner /' /etc/freshclam.conf && \
    sed -i 's|^UpdateLogFile .*|UpdateLogFile /var/log/clamav/freshclam.log|' /etc/freshclam.conf && \
    chmod 0644 /etc/freshclam.conf && \
    chown -R 1000:1000 /var/lib/clamav /var/log/clamav

USER 1000
WORKDIR /app

ENV HOST=0.0.0.0
ENV PORT=8056
ENV EPYON_SCANS_DIR=/data/scans

EXPOSE 8056

CMD ["python3", "-m", "uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8056"]
