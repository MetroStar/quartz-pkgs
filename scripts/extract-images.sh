#!/usr/bin/env bash
set -euo pipefail

# extract-images.sh — Statically discover all container images required by a Quartz deployment
# without needing a running cluster. Outputs an updated image-manifest.json.
#
# Usage:
#   ./scripts/extract-images.sh [--quartz-values <path>] [--bigbang-version <tag>] [--output <path>]
#
# Environment:
#   QUARTZ_VALUES_PATH  - path to quartz chart/values.yaml (default: ../quartz/chart/values.yaml)
#   BIGBANG_VERSION     - BigBang chart version tag (auto-detected from values if not set)
#   OUTPUT_PATH         - output manifest path (default: src/ironbank/image-manifest.json)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Defaults
QUARTZ_VALUES_PATH="${QUARTZ_VALUES_PATH:-${SCRIPT_DIR}/../../quartz/chart/values.yaml}"
BIGBANG_VERSION="${BIGBANG_VERSION:-}"
OUTPUT_PATH="${OUTPUT_PATH:-${REPO_ROOT}/src/ironbank/image-manifest.json}"
BB_OCI_REGISTRY="oci://registry1.dso.mil/bigbang"
BB_GIT_REPO="https://repo1.dso.mil/big-bang/bigbang.git"

# Parse CLI args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --quartz-values) QUARTZ_VALUES_PATH="$2"; shift 2 ;;
    --bigbang-version) BIGBANG_VERSION="$2"; shift 2 ;;
    --output) OUTPUT_PATH="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

# Validate dependencies
for cmd in helm jq yq git; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: $cmd is required but not found" >&2; exit 1; }
done

if [[ ! -f "$QUARTZ_VALUES_PATH" ]]; then
  echo "ERROR: Quartz values file not found: $QUARTZ_VALUES_PATH" >&2
  exit 1
fi

# Auto-detect BigBang version from quartz values if not specified
if [[ -z "$BIGBANG_VERSION" ]]; then
  BIGBANG_VERSION=$(yq -r '.bigbang.git.tag // .bigbang.helmRepo.tag // ""' "$QUARTZ_VALUES_PATH" 2>/dev/null)
  if [[ -z "$BIGBANG_VERSION" ]]; then
    echo "ERROR: Could not detect BigBang version from values. Use --bigbang-version." >&2
    exit 1
  fi
fi

echo "=== Quartz Image Manifest Extraction ===" >&2
echo "  BigBang version: ${BIGBANG_VERSION}" >&2
echo "  Quartz values:   ${QUARTZ_VALUES_PATH}" >&2
echo "  Output:          ${OUTPUT_PATH}" >&2
echo "" >&2

# Load existing manifest for clobber preservation
EXISTING_MANIFEST="[]"
if [[ -f "$OUTPUT_PATH" ]]; then
  EXISTING_MANIFEST=$(jq -rc '.' "$OUTPUT_PATH" 2>/dev/null || echo "[]")
fi

# Collect all discovered images into a temp file
IMAGES_FILE=$(mktemp)
trap 'rm -f "$IMAGES_FILE" 2>/dev/null' EXIT

###############################################################################
# 1. BigBang Flux images (from base/flux/kustomization.yaml)
###############################################################################
echo "[1/5] Extracting Flux images from BigBang ${BIGBANG_VERSION}..." >&2
BB_TMPDIR=$(mktemp -d)
trap 'rm -rf "$BB_TMPDIR" "$IMAGES_FILE" 2>/dev/null' EXIT

git clone --depth 1 --branch "$BIGBANG_VERSION" --quiet "$BB_GIT_REPO" "$BB_TMPDIR" 2>/dev/null || {
  echo "  WARN: Could not clone BigBang repo, skipping Flux images" >&2
}

if [[ -f "$BB_TMPDIR/base/flux/kustomization.yaml" ]]; then
  # Extract newName:newTag pairs from the Flux kustomization
  yq -r '.images[] | .newName + ":" + .newTag' "$BB_TMPDIR/base/flux/kustomization.yaml" 2>/dev/null >> "$IMAGES_FILE"
  echo "  Found $(yq -r '.images | length' "$BB_TMPDIR/base/flux/kustomization.yaml" 2>/dev/null) Flux images" >&2
fi

###############################################################################
# 2. BigBang package images (from OCI chart defaults)
###############################################################################
echo "[2/5] Extracting BigBang package images via helm show values..." >&2

# Get list of enabled packages and their chart versions from BigBang defaults
BB_VALUES="$BB_TMPDIR/chart/values.yaml"
if [[ -f "$BB_VALUES" ]]; then
  # Extract all helmRepo entries: chartName + tag
  # Format: chartName tag
  PACKAGES=$(yq -r '
    .. | select(has("helmRepo")) | .helmRepo |
    select(.chartName != null and .tag != null) |
    .chartName + " " + .tag
  ' "$BB_VALUES" 2>/dev/null | sort -u)

  TOTAL=$(echo "$PACKAGES" | grep -c "." || echo 0)
  COUNT=0

  while IFS=' ' read -r chart_name chart_version; do
    [[ -z "$chart_name" ]] && continue
    COUNT=$((COUNT + 1))
    echo -ne "  [$COUNT/$TOTAL] ${chart_name}:${chart_version}...\r" >&2

    # Pull chart values and extract image repository+tag pairs
    VALUES_OUTPUT=$(helm show values "${BB_OCI_REGISTRY}/${chart_name}" --version "$chart_version" 2>/dev/null || echo "")
    if [[ -z "$VALUES_OUTPUT" ]]; then
      echo "  WARN: Could not pull values for ${chart_name}:${chart_version}" >&2
      continue
    fi

    # Strategy: find all "repository:" lines and pair with nearby "tag:" lines
    # BigBang charts use the pattern:
    #   repository: ironbank/path/to/image  (or registry1.dso.mil/ironbank/...)
    #   [pullPolicy: ...]
    #   tag: vX.Y.Z
    echo "$VALUES_OUTPUT" | awk '
      /^\s*repository:/ {
        repo = $2
        gsub(/["'"'"']/, "", repo)
        # Skip empty, placeholder, or comment-only repos
        if (repo == "" || repo ~ /^#/) next
        pending_repo = repo
      }
      /^\s*tag:/ && pending_repo != "" {
        tag = $2
        gsub(/["'"'"']/, "", tag)
        if (tag == "" || tag == "null" || tag == "~" || tag ~ /^#/) { next }
        # Normalize: add registry1.dso.mil prefix if not already a full reference
        if (pending_repo !~ /^[a-z]+\.(dso|io|com|aws|dev|k8s)/ && pending_repo !~ /^registry/) {
          pending_repo = "registry1.dso.mil/" pending_repo
        }
        print pending_repo ":" tag
        pending_repo = ""
      }
      # Reset pending_repo if we hit another section (non-image key at same/lower indent)
      /^\s*[a-z]/ && !/^\s*(repository|tag|pullPolicy|digest|registry):/ && pending_repo != "" {
        pending_repo = ""
      }
    ' >> "$IMAGES_FILE"
  done <<< "$PACKAGES"
  echo "" >&2
  echo "  Processed $COUNT BigBang packages" >&2
fi

###############################################################################
# 3. Non-BigBang Helm chart images (Keda, External-Secrets, Cilium, etc.)
###############################################################################
echo "[3/5] Extracting images from non-BigBang Helm charts..." >&2

# Map of quartz values key → helm repo alias, chart name
# Format: "repoAlias repoURL chartName version"
HELM_CHARTS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && HELM_CHARTS+=("$line")
done < <(yq -r '
  to_entries[] |
  select(.value | type == "!!map") |
  select((.value.enabled // true) == true) |
  select(.value | has("helm")) |
  select(.value.helm | has("repo")) |
  select(.value.helm | has("version")) |
  select(.value.helm.repo | test("repo1\\.dso\\.mil|^$") | not) |
  [.key, .value.helm.repo, .value.helm.version] | @tsv
' "$QUARTZ_VALUES_PATH" 2>/dev/null || true)

# Also check nested helm specs (e.g. kafka.operator.helm) - handled by explicit additions below

# Chart name mapping (quartz values key → actual chart name in repo)
declare -A CHART_NAME_MAP=(
  [certManager]="cert-manager"
  [externalDns]="external-dns"
  [externalSecrets]="external-secrets"
  [k8sgpt]="k8sgpt-operator"
  [nvidiaDevicePlugin]="nvidia-device-plugin"
  [agentgatewayCrds]="agentgateway-crds"
  [kagentCrds]="kagent-crds"
  [openWebui]="open-webui"
  [argoWorkflows]="argo-workflows"
  [argoRollouts]="argo-rollouts"
  [argoEvents]="argo-events"
)

# Manually add Argo sub-charts (repo is at parent level, version at child)
ARGO_REPO=$(yq -r '.argo.helm.repo // ""' "$QUARTZ_VALUES_PATH" 2>/dev/null)
if [[ -n "$ARGO_REPO" ]]; then
  for sub in workflows events rollouts; do
    enabled=$(yq -r ".argo.${sub}.enabled // false" "$QUARTZ_VALUES_PATH" 2>/dev/null)
    ver=$(yq -r ".argo.${sub}.helm.version // \"\"" "$QUARTZ_VALUES_PATH" 2>/dev/null)
    if [[ "$enabled" == "true" && -n "$ver" ]]; then
      HELM_CHARTS+=("argo${sub^}"$'\t'"${ARGO_REPO}"$'\t'"${ver}")
    fi
  done
fi

# Manually add Strimzi (nested under kafka.operator)
STRIMZI_REPO=$(yq -r '.kafka.operator.helm.repo // ""' "$QUARTZ_VALUES_PATH" 2>/dev/null)
STRIMZI_VER=$(yq -r '.kafka.operator.helm.version // ""' "$QUARTZ_VALUES_PATH" 2>/dev/null)
if [[ -n "$STRIMZI_REPO" && -n "$STRIMZI_VER" ]]; then
  HELM_CHARTS+=("strimzi-kafka-operator"$'\t'"${STRIMZI_REPO}"$'\t'"${STRIMZI_VER}")
fi

HELM_CHART_COUNT=0
HTTP_REPO_COUNT=0
declare -A SEEN_HTTP_REPOS=()

# Add/update traditional Helm repositories before we start pulling from them.
for entry in "${HELM_CHARTS[@]}"; do
  IFS=$'\t' read -r key repo_url version <<< "$entry"
  [[ -z "$repo_url" || -z "$version" ]] && continue
  [[ "$repo_url" == oci://* ]] && continue

  repo_alias=$(echo "$key" | tr '[:upper:]' '[:lower:]' | tr -d '-')
  if [[ -z "${SEEN_HTTP_REPOS[$repo_alias]:-}" ]]; then
    helm repo add "$repo_alias" "$repo_url" >/dev/null 2>&1 || true
    SEEN_HTTP_REPOS["$repo_alias"]=1
    HTTP_REPO_COUNT=$((HTTP_REPO_COUNT + 1))
  fi
done

if [[ $HTTP_REPO_COUNT -gt 0 ]]; then
  helm repo update >/dev/null 2>&1 || true
fi

for entry in "${HELM_CHARTS[@]}"; do
  IFS=$'\t' read -r key repo_url version <<< "$entry"
  [[ -z "$repo_url" || -z "$version" ]] && continue

  # Resolve chart name
  chart_name="${CHART_NAME_MAP[$key]:-$key}"
  chart_ref=""

  if [[ "$repo_url" == oci://* ]]; then
    chart_ref="${repo_url}/${chart_name}"
  else
    repo_alias=$(echo "$key" | tr '[:upper:]' '[:lower:]' | tr -d '-')
    chart_ref="${repo_alias}/${chart_name}"
  fi

  # Fetch chart metadata first. Some CRD/helper charts ship no values at all,
  # which should not be treated as a hard extraction failure.
  CHART_METADATA=$(helm show chart "$chart_ref" --version "$version" 2>/dev/null || echo "")
  APP_VERSION=$(printf '%s' "$CHART_METADATA" | yq -r '.appVersion // ""' 2>/dev/null || echo "")
  if [[ -z "$CHART_METADATA" ]]; then
    echo "  WARN: Could not pull values for $chart_name:$version from $repo_url" >&2
    continue
  fi

  CHART_VALUES=$(helm show values "$chart_ref" --version "$version" 2>/dev/null || true)
  if [[ -z "$CHART_VALUES" ]]; then
    HELM_CHART_COUNT=$((HELM_CHART_COUNT + 1))
    continue
  fi

  # Extract images using multiple patterns:
  # Pattern A: registry + repository + tag (e.g. Keda)
  # Pattern B: repository + tag (full path like docker.io/org/image)
  # Pattern C: image: "full-reference:tag"
  echo "$CHART_VALUES" | awk -v appver="$APP_VERSION" '
    /^\s*registry:/ {
      registry = $2; gsub(/["'"'"']/, "", registry)
    }
    /^\s*repository:/ {
      repo = $2; gsub(/["'"'"']/, "", repo)
      if (repo == "" || repo ~ /^#/) { repo = ""; next }
    }
    /^\s*tag:/ {
      tag = $2; gsub(/["'"'"']/, "", tag)
      if (tag == "" || tag == "null" || tag == "~" || tag ~ /^#/) tag = appver
      if (tag == "" || tag ~ /^#/) next
      if (repo == "") next
      # Build full image reference
      if (repo ~ /^[a-z]+\.(io|com|aws|dev|k8s\.io)\//) {
        # repo already has full registry prefix (e.g. registry.k8s.io/foo)
        print repo ":" tag
      } else if (registry != "") {
        print registry "/" repo ":" tag
      } else if (repo ~ /^[a-z][a-z0-9-]*\/[a-z]/) {
        # Docker Hub short name (org/image) - prefix with docker.io
        print "docker.io/" repo ":" tag
      }
      registry = ""; repo = ""
    }
    /^\s*image:/ {
      img = $2; gsub(/["'"'"']/, "", img)
      if (img ~ /\// && img ~ /:/) print img
    }
  ' >> "$IMAGES_FILE"

  HELM_CHART_COUNT=$((HELM_CHART_COUNT + 1))
done
echo "  Processed $HELM_CHART_COUNT upstream Helm charts" >&2

###############################################################################
# 4. Quartz-specific images (from chart/values.yaml)
###############################################################################
echo "[4/5] Extracting Quartz-specific images from values.yaml..." >&2

# Pattern 1: Full image references (registry/path:tag format in _image keys)
grep -oP '(?:buildah_image|build_tools_image|maven_image|nodejs_image|cypress_image|playwright_image):\s*\K\S+' \
  "$QUARTZ_VALUES_PATH" 2>/dev/null | tr -d '"'"'" | grep "/" >> "$IMAGES_FILE" || true

# Pattern 2: Any string value that looks like a full image reference
AUX_IMAGES_FROM_VALUES=$(yq -r '
  .. | select(type == "!!str") | select(test("^(docker\\.io|quay\\.io|ghcr\\.io|gcr\\.io|public\\.ecr\\.aws|registry\\.k8s\\.io|registry1\\.dso\\.mil)/.*:"))
' "$QUARTZ_VALUES_PATH" 2>/dev/null || true)
if [[ -n "$AUX_IMAGES_FROM_VALUES" ]]; then
  echo "$AUX_IMAGES_FROM_VALUES" >> "$IMAGES_FILE"
fi

echo "  Extracted quartz images from values" >&2

###############################################################################
# 5. Additional known images (operator-managed, not in chart defaults)
###############################################################################
echo "[5/5] Adding known auxiliary images..." >&2

# Images deployed by operators/CRDs that aren't in Helm chart values
# These are discovered once from a running cluster and maintained here
KNOWN_OPERATOR_IMAGES=(
  # Kaniko (used by Jenkins pipelines, not in any chart values)
  "gcr.io/kaniko-project/executor:v1.24.0-debug"
)

for img in "${KNOWN_OPERATOR_IMAGES[@]}"; do
  echo "$img" >> "$IMAGES_FILE"
done

###############################################################################
# Build the manifest
###############################################################################
echo "" >&2
echo "=== Building manifest ===" >&2

# Deduplicate and sort, filter out empty lines and localhost refs
FINAL_IMAGES=$(sort -u "$IMAGES_FILE" | grep -v "^$\|^localhost" | grep ":" || true)
IMAGE_COUNT=$(echo "$FINAL_IMAGES" | grep -c "." || echo 0)

# Build JSON array preserving clobber flags from existing manifest
JSON=$(echo "$FINAL_IMAGES" | jq -R -s -c --argjson existing "$EXISTING_MANIFEST" '
  split("\n") | map(select(length > 0)) | unique |
  map(. as $img |
    ($img | split(":")[0:-1] | join(":")) as $base |
    ($existing | map(select(.source | startswith($base))) | sort_by(.source) | reverse | .[0].clobber // false) as $clobber |
    { source: $img, clobber: $clobber }
  )
')

# Write formatted output
echo "$JSON" | jq '.' > "$OUTPUT_PATH"

FINAL_COUNT=$(jq '. | length' "$OUTPUT_PATH")
echo "Updated ${OUTPUT_PATH} with ${FINAL_COUNT} images" >&2
echo "" >&2

# Show diff summary if existing manifest was present
if [[ "$EXISTING_MANIFEST" != "[]" ]]; then
  EXISTING_SOURCES=$(echo "$EXISTING_MANIFEST" | jq -r '.[].source' | sort)
  NEW_SOURCES=$(jq -r '.[].source' "$OUTPUT_PATH" | sort)

  ADDED=$(comm -13 <(echo "$EXISTING_SOURCES") <(echo "$NEW_SOURCES") | wc -l)
  REMOVED=$(comm -23 <(echo "$EXISTING_SOURCES") <(echo "$NEW_SOURCES") | wc -l)

  if [[ $ADDED -gt 0 || $REMOVED -gt 0 ]]; then
    echo "Changes: +${ADDED} added, -${REMOVED} removed" >&2
    if [[ $ADDED -gt 0 ]]; then
      echo "  Added:" >&2
      comm -13 <(echo "$EXISTING_SOURCES") <(echo "$NEW_SOURCES") | head -10 | sed 's/^/    /' >&2
      [[ $ADDED -gt 10 ]] && echo "    ... and $((ADDED - 10)) more" >&2
    fi
    if [[ $REMOVED -gt 0 ]]; then
      echo "  Removed:" >&2
      comm -23 <(echo "$EXISTING_SOURCES") <(echo "$NEW_SOURCES") | head -10 | sed 's/^/    /' >&2
      [[ $REMOVED -gt 10 ]] && echo "    ... and $((REMOVED - 10)) more" >&2
    fi
  else
    echo "No changes detected." >&2
  fi
fi
