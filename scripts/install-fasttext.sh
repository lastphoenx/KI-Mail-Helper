#!/usr/bin/env bash
# Install fastText language detection (lid.176.bin) for TranslatorService.
#
# PyPI fasttext-wheel==0.9.2 ships pre-built wheels for Python 3.11/3.12 on Linux x86_64.
# Python 3.13+ has no wheel → patched source build (adds #include <cstdint> for GCC 13+).
#
# Usage on CT 134 (as root in pct enter):
#   cd /opt/KI-Mail-Helper
#   source venv/bin/activate
#   bash scripts/install-fasttext.sh
#   chown -R mailhelper:mailhelper venv models

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
FASTTEXT_VERSION="${FASTTEXT_VERSION:-0.9.2}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "❌ venv not found: $VENV_DIR/bin/python" >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$APP_DIR"

PY_MM="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "🐍 Python ${PY_MM} in ${VENV_DIR}"

patch_fasttext_sources() {
    local srcdir="$1"
    local patched=0
    for rel in src/args.h src/args.cc; do
        local target="${srcdir}/${rel}"
        if [[ ! -f "$target" ]]; then
            continue
        fi
        if grep -q '#include <cstdint>' "$target"; then
            continue
        fi
        if grep -q '#include <unordered_map>' "$target"; then
            sed -i '/#include <unordered_map>/a #include <cstdint>' "$target"
            echo "🩹 Patched ${rel} (#include <cstdint> for GCC 13+)"
            patched=1
        fi
    done
    if [[ "$patched" -eq 0 ]]; then
        echo "❌ Could not patch fastText sources (args.h/args.cc)" >&2
        exit 1
    fi
}

install_from_patched_source() {
    local build_dir cc cxx
    build_dir="$(mktemp -d)"
    trap 'rm -rf "$build_dir"' RETURN

    if command -v gcc-12 >/dev/null 2>&1 && command -v g++-12 >/dev/null 2>&1; then
        cc=gcc-12
        cxx=g++-12
        echo "🔧 Building with ${cc}/${cxx}"
    else
        cc=gcc
        cxx=g++
        echo "🔧 Building with default ${cc}/${cxx} (patched sources)"
    fi

    pip install --upgrade pip setuptools wheel pybind11
    pip download --no-deps --no-binary fasttext-wheel \
        "fasttext-wheel==${FASTTEXT_VERSION}" -d "$build_dir"

    local archive
    archive="$(find "$build_dir" -maxdepth 1 -name 'fasttext*.tar.gz' | head -1)"
    if [[ -z "$archive" ]]; then
        echo "❌ Could not download fasttext-wheel source archive" >&2
        exit 1
    fi

    tar -xzf "$archive" -C "$build_dir"
    local srcdir
    srcdir="$(find "$build_dir" -maxdepth 1 -type d -name 'fasttext*' ! -path "$build_dir" | head -1)"
    if [[ -z "$srcdir" ]]; then
        echo "❌ Could not extract fasttext-wheel sources" >&2
        exit 1
    fi

    patch_fasttext_sources "$srcdir"
    CC="$cc" CXX="$cxx" pip install --no-build-isolation --no-cache-dir "$srcdir"
    echo "✅ fasttext-wheel built from patched source"
}

install_fasttext_wheel() {
    pip install --upgrade "fasttext-wheel==${FASTTEXT_VERSION}"
}

echo "📦 Installing fasttext-wheel==${FASTTEXT_VERSION} ..."

if python -c 'import sys; raise SystemExit(0 if sys.version_info < (3, 13) else 1)'; then
    if install_fasttext_wheel; then
        echo "✅ fasttext-wheel installed (binary wheel)"
    else
        echo "⚠️  Wheel install failed — trying patched source build ..."
        install_from_patched_source
    fi
else
    echo "ℹ️  Python 3.13+: no PyPI wheel — using patched source build"
    install_from_patched_source
fi

echo "🔍 Verifying import ..."
python -c "import fasttext; print('fasttext import OK')"

echo "📥 Ensuring lid.176.bin language model (~126 MB) ..."
python <<'PY'
from src.services.translator_service import get_translator

translator = get_translator()
result = translator.detect_language("Guten Tag, dies ist ein kurzer Test.")
print(f"✅ Language detection: {result.language} ({result.confidence:.2f}) — {result.language_name}")
PY

if [[ "$(id -u)" -eq 0 ]]; then
    if id mailhelper &>/dev/null; then
        chown -R mailhelper:mailhelper "$VENV_DIR" "${APP_DIR}/models" 2>/dev/null || true
        echo "🔐 Ownership: mailhelper on venv/ and models/"
    fi
fi

echo "✅ fastText ready."
