#!/usr/bin/env bash
set -e

CUR_DIR=$(pwd)
mkdir -p dist

build_pkg() {
  cd "${CUR_DIR}"
  echo "Start to build packages in ${1}"
  for pkg_name in ${1}/*/; do
    echo "==> Building ${pkg_name} ..."
    cd "${CUR_DIR}/${pkg_name}"
    if [ -f "pyproject.toml" ]; then
      echo "==> Build ${pkg_name} ..."
      python -m build --wheel --outdir "${CUR_DIR}/dist"
    else
      echo "::warning::pyproject.toml not found for ${pkg_name}, skip build"
    fi
    echo ""
  done
}

build_pkg libs
build_pkg server
