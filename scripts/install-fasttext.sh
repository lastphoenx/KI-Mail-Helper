#!/usr/bin/env bash
# Install fastText language detection (lid.176.bin) for TranslatorService.
#
# PyPI: fasttext-wheel==0.9.2 is the latest published release (pre-built wheels
# for Linux x86_64 + Python 3.11/3.12). Source builds need GCC 12 on GCC 13+ hosts.
#
# Usage (production CT 134):
#   cd /opt/KI-Mail-Helper
#   sudo -u mailhelper bash scripts/install-fasttext.sh

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

install_fasttext_wheel() {
    pip install --upgrade "fasttext-wheel==${FASTTEXT_VERSION}"
}

echo "📦 Installing fasttext-wheel==${FASTTEXT_VERSION} into $VENV_DIR ..."
if install_fasttext_wheel; then
    echo "✅ fasttext-wheel installed (binary wheel)"
else
    echo "⚠️  Wheel install failed — trying source build with GCC 12 if available ..."
    if command -v gcc-12 >/dev/null 2>&1 && command -v g++-12 >/dev/null 2>&1; then
        CC=gcc-12 CXX=g++-12 pip install --no-cache-dir --no-binary=:all: "fasttext-wheel==${FASTTEXT_VERSION}"
        echo "✅ fasttext-wheel built from source with gcc-12"
    else
        echo "❌ fasttext-wheel install failed." >&2
        echo "   Install build deps: apt install gcc-12 g++-12 python3-dev" >&2
        echo "   Or ensure Python 3.11/3.12 on x86_64 can use the PyPI wheel." >&2
        exit 1
    fi
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

echo "✅ fastText ready."
