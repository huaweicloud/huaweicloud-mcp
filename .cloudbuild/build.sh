#!/usr/bin/env bash
# Build all second-party packages with auto-discovery

# Project configuration
export name="huaweicloud-mcp"
export py_version=3

echo "Project: ${name}"
echo "Python version: ${py_version}"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DIST_DIR="${REPO_ROOT}/dist"

# Clean and prepare output directory
rm -rf "$DIST_DIR"
mkdir -p "$DIST_DIR"

# Install build tools
echo "==> Installing build dependencies ..."
pip3 install --quiet build

# Append timestamp to core version for unique CI releases (e.g. 1.0.0 -> 1.0.0.20261012113245)
TIMESTAMP=$(date +%Y%m%d%H%M%S)
CORE_PYPROJECT="${REPO_ROOT}/libs/huaweicloud_mcp_core/pyproject.toml"
if [[ -f "$CORE_PYPROJECT" ]]; then
  ORIGINAL_VERSION=$(sed -n 's/^version = "\(.*\)"/\1/p' "$CORE_PYPROJECT")
  NEW_VERSION="${ORIGINAL_VERSION}.${TIMESTAMP}"
  echo "==> Bumping core version: ${ORIGINAL_VERSION} -> ${NEW_VERSION}"
  sed -i "s/^version = .*/version = \"${NEW_VERSION}\"/" "$CORE_PYPROJECT"
fi

# Auto-discover packages: libs first (core), then server (services)
discover_packages() {
  local dir="$1"
  find "$dir" -maxdepth 2 -name "pyproject.toml" -type f | sort
}

CORE_PACKAGES=()
SERVER_PACKAGES=()

if [[ -d "$REPO_ROOT/libs" ]]; then
  while IFS= read -r pyproject; do
    CORE_PACKAGES+=("$(dirname "$pyproject")")
  done < <(discover_packages "$REPO_ROOT/libs")
fi

if [[ -d "$REPO_ROOT/server" ]]; then
  while IFS= read -r pyproject; do
    SERVER_PACKAGES+=("$(dirname "$pyproject")")
  done < <(discover_packages "$REPO_ROOT/server")
fi

# Build in dependency order: core libraries first, then services
for pkg_dir in "${CORE_PACKAGES[@]}" "${SERVER_PACKAGES[@]}"; do
  pkg_name="$(basename "$pkg_dir")"
  echo "==> Building ${pkg_name} ..."
  python3 -m build --wheel --outdir "$DIST_DIR" "$pkg_dir"
done

echo ""
echo "==> Build complete. Artifacts:"
ls -lh "$DIST_DIR"/
