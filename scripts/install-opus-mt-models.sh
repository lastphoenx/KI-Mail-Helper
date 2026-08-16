#!/usr/bin/env bash
# Pre-download Helsinki-NLP Opus-MT models into the Hugging Face cache.
# Required for offline/local translation after torch is installed.
#
# Usage on CT 134:
#   cd /opt/KI-Mail-Helper
#   source venv/bin/activate
#   bash scripts/install-opus-mt-models.sh
#   sudo systemctl restart mail-helper mail-helper-celery-worker
#
# Needs outbound HTTPS to huggingface.co (or set HF_ENDPOINT mirror).

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"

# Common pairs for mail translation + translator UI (DACH context)
MODELS=(
    Helsinki-NLP/opus-mt-de-en
    Helsinki-NLP/opus-mt-en-de
    Helsinki-NLP/opus-mt-de-it
    Helsinki-NLP/opus-mt-it-de
    Helsinki-NLP/opus-mt-de-fr
    Helsinki-NLP/opus-mt-fr-de
    Helsinki-NLP/opus-mt-en-it
    Helsinki-NLP/opus-mt-it-en
    Helsinki-NLP/opus-mt-en-fr
    Helsinki-NLP/opus-mt-fr-en
)

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "❌ venv not found: $VENV_DIR/bin/python" >&2
    exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$APP_DIR"

echo "🐍 Python: $($VENV_DIR/bin/python --version)"
echo "🔥 Checking torch..."
python -c "import torch; print(f'   torch {torch.__version__}')" || {
    echo "❌ torch missing. Install first:" >&2
    echo "   pip install torch --index-url https://download.pytorch.org/whl/cpu" >&2
    exit 1
}

pip install -q "huggingface_hub>=0.26.0"

echo "📥 Downloading ${#MODELS[@]} Opus-MT models into ~/.cache/huggingface/hub ..."
for model in "${MODELS[@]}"; do
    echo ""
    echo "➡️  $model"
    python - <<PY
from huggingface_hub import snapshot_download
snapshot_download(repo_id="${model}")
print("   ✅ cached")
PY
done

echo ""
echo "✅ Done. Test:"
echo "   python -c \"from transformers import MarianTokenizer; MarianTokenizer.from_pretrained('Helsinki-NLP/opus-mt-de-en', local_files_only=True); print('OK')\""
