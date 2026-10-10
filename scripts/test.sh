#!/usr/bin/env bash
# test.sh — Run lint, type-check, and tests for all MCP packages in the monorepo.
#
# Usage:
#   ./scripts/test.sh                 # Run all packages (lint + mypy + pytest)
#   ./scripts/test.sh vpc             # Run only the vpc service package
#   ./scripts/test.sh core            # Run only the core library
#   ./scripts/test.sh --no-lint       # Skip ruff
#   ./scripts/test.sh --no-mypy       # Skip mypy
#   ./scripts/test.sh --no-tests      # Skip pytest
#   ./scripts/test.sh --quick         # Only run pytest (skip lint + mypy)
#
# Exit code: 0 if all pass, 1 if any fail.

set -euo pipefail

# ─── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Detect WSL: uv is a Windows binary; WSL paths must be converted.
IS_WSL=false
if grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null; then
  IS_WSL=true
fi

# Pick the correct uv binary name.
if $IS_WSL; then
  UV_BIN="uv.exe"
else
  UV_BIN="uv"
fi

# Convert a WSL path to a Windows path (forward-slash style) if in WSL.
to_native_path() {
  local p="$1"
  if $IS_WSL; then
    wslpath -w "$p" | tr '\\\\' '/'
  else
    echo "$p"
  fi
}

# ─── Auto-scan packages ────────────────────────────────────────────────────────
# Format per entry: "short_name:relative_dir_from_repo_root:has_dev_tools"
#
# short_name:
#   server/mcp_server_<svc>  -> <svc>
#   libs/<name>              -> <name>
#
# has_dev_tools: "yes" if pyproject.toml mentions both ruff and mypy (i.e. they
# are declared as dev dependencies); otherwise "no".

declare -a PACKAGES=()

check_dev_tools() {
  local pyproject="$1/pyproject.toml"
  if [[ ! -f "$pyproject" ]]; then
    echo "no"; return
  fi
  if grep -q 'ruff' "$pyproject" && grep -q 'mypy' "$pyproject"; then
    echo "yes"
  else
    echo "no"
  fi
}

# Scan libs/*
for dir in "$REPO_ROOT"/libs/*/; do
  [[ -d "$dir" ]] || continue
  name="$(basename "$dir")"
  has_tools="$(check_dev_tools "$dir")"
  PACKAGES+=("$name:libs/$name:$has_tools")
done

# Scan server/mcp_server_*
for dir in "$REPO_ROOT"/server/mcp_server_*/; do
  [[ -d "$dir" ]] || continue
  full="$(basename "$dir")"
  short="${full#mcp_server_}"
  has_tools="$(check_dev_tools "$dir")"
  PACKAGES+=("$short:server/$full:$has_tools")
done

RUN_LINT=true
RUN_MYPY=true
RUN_TESTS=true

# ─── Parse args ────────────────────────────────────────────────────────────────

TARGET_FILTER=""
for arg in "$@"; do
  case "$arg" in
    --no-lint)   RUN_LINT=false ;;
    --no-mypy)   RUN_MYPY=false ;;
    --no-tests)  RUN_TESTS=false ;;
    --quick)     RUN_LINT=false; RUN_MYPY=false ;;
    -h|--help)
      echo "Usage: ./scripts/test.sh [package-filter] [--no-lint] [--no-mypy] [--no-tests] [--quick]"
      echo ""
      echo "Auto-detected packages:"
      for entry in "${PACKAGES[@]}"; do
        IFS=':' read -r n _ _ <<< "$entry"
        echo "  - $n"
      done
      exit 0
      ;;
    *)
      TARGET_FILTER="$arg"
      ;;
  esac
done

if [[ ${#PACKAGES[@]} -eq 0 ]]; then
  echo "[ERROR] No packages found under libs/ or server/mcp_server_*/"
  exit 1
fi

# ─── Helpers ───────────────────────────────────────────────────────────────────

declare -a FAILED_PACKAGES=()

step() {
  echo ""
  echo "=== $1 ==="
}

ok() {
  echo "  [OK] $1"
}

fail() {
  echo "  [FAIL] $1"
}

warn() {
  echo "  [WARN] $1"
}

# Run a uv subcommand inside a package directory.
run_in_pkg() {
  local dir="$1"; shift
  local native_dir
  native_dir="$(to_native_path "$dir")"
  "$UV_BIN" run --directory "$native_dir" "$@"
}

# ─── Main loop ─────────────────────────────────────────────────────────────────

step "MCP Monorepo Test Runner"
echo "  Repo:     $REPO_ROOT"
echo "  WSL:      $IS_WSL"
echo "  uv:       $UV_BIN"
echo "  Lint:     $RUN_LINT"
echo "  Mypy:     $RUN_MYPY"
echo "  Tests:    $RUN_TESTS"
echo "  Filter:   ${TARGET_FILTER:-all}"
echo "  Packages: ${#PACKAGES[@]}"

for entry in "${PACKAGES[@]}"; do
  IFS=':' read -r name reldir has_dev_tools <<< "$entry"

  # Apply filter: substring match against short name or dir name.
  if [[ -n "$TARGET_FILTER" && "$name" != *"$TARGET_FILTER"* && "$reldir" != *"$TARGET_FILTER"* ]]; then
    continue
  fi

  pkg_dir="$REPO_ROOT/$reldir"
  native_pkg_dir="$(to_native_path "$pkg_dir")"
  pkg_fail=false

  step "Package: $name  ($reldir)"

  if [[ ! -d "$pkg_dir" ]]; then
    fail "Directory not found: $pkg_dir"
    FAILED_PACKAGES+=("$name (missing dir)")
    continue
  fi

  # ── uv sync ──────────────────────────────────────────────────────────────────
  echo "  Syncing dependencies..."
  if ! "$UV_BIN" sync --directory "$native_pkg_dir" --quiet; then
    fail "uv sync failed"
    FAILED_PACKAGES+=("$name (uv sync)")
    continue
  fi
  ok "uv sync"

  # ── Ruff ─────────────────────────────────────────────────────────────────────
  if $RUN_LINT && [[ "$has_dev_tools" == "yes" ]]; then
    echo "  Running ruff check..."
    if run_in_pkg "$pkg_dir" ruff check; then
      ok "ruff check"
    else
      fail "ruff check"
      pkg_fail=true
    fi

    echo "  Running ruff format --check..."
    if run_in_pkg "$pkg_dir" ruff format --check; then
      ok "ruff format --check"
    else
      fail "ruff format --check"
      pkg_fail=true
    fi
  elif $RUN_LINT; then
    warn "ruff skipped (not in dev deps for $name)"
  fi

  # ── Mypy ─────────────────────────────────────────────────────────────────────
  if $RUN_MYPY && [[ "$has_dev_tools" == "yes" ]]; then
    echo "  Running mypy..."
    if run_in_pkg "$pkg_dir" mypy src tests; then
      ok "mypy"
    else
      fail "mypy"
      pkg_fail=true
    fi
  elif $RUN_MYPY; then
    warn "mypy skipped (not in dev deps for $name)"
  fi

  # ── Pytest ───────────────────────────────────────────────────────────────────
  if $RUN_TESTS; then
    echo "  Running pytest..."
    if run_in_pkg "$pkg_dir" pytest --cov; then
      ok "pytest"
    else
      fail "pytest"
      pkg_fail=true
    fi
  fi

  if $pkg_fail; then
    FAILED_PACKAGES+=("$name")
  fi
done

# ─── Summary ───────────────────────────────────────────────────────────────────

step "Summary"

if [[ ${#FAILED_PACKAGES[@]} -eq 0 ]]; then
  echo "  All packages passed!"
  exit 0
else
  echo "  Failed packages (${#FAILED_PACKAGES[@]}):"
  for p in "${FAILED_PACKAGES[@]}"; do
    echo "    - $p"
  done
  exit 1
fi
