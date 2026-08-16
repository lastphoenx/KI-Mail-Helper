#!/usr/bin/env bash
# Pre-download Helsinki-NLP Opus-MT models into the Hugging Face cache.
# Required for offline/local translation after torch is installed.
#
# WICHTIG: Der Dienst läuft als User mailhelper (ProtectHome=true).
# Cache MUSS unter /opt/KI-Mail-Helper/.cache/huggingface liegen, nicht in /root/.cache!
#
# Usage on CT 134:
#   cd /opt/KI-Mail-Helper
#   sudo -u mailhelper bash scripts/install-opus-mt-models.sh
#   sudo systemctl restart mail-helper mail-helper-celery-worker
#
# Falls du vorher als root installiert hast:
#   rsync -a /root/.cache/huggingface/ /opt/KI-Mail-Helper/.cache/huggingface/
#   chown -R mailhelper:mailhelper /opt/KI-Mail-Helper/.cache

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
HF_HOME="${HF_HOME:-$APP_DIR/.cache/huggingface}"
export HF_HOME APP_DIR

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
    Helsinki-NLP/opus-mt-de-es
    Helsinki-NLP/opus-mt-es-de
    Helsinki-NLP/opus-mt-de-nl
    Helsinki-NLP/opus-mt-nl-de
    Helsinki-NLP/opus-mt-de-pl
    Helsinki-NLP/opus-mt-pl-de
    Helsinki-NLP/opus-mt-tc-big-en-pt
    Helsinki-NLP/opus-mt-ROMANCE-en
)

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "❌ venv not found: $VENV_DIR/bin/python" >&2
    exit 1
fi

if [[ "$(id -un)" == "root" ]]; then
    echo "⚠️  Du bist root. Besser: sudo -u mailhelper bash scripts/install-opus-mt-models.sh"
    if [[ -d /root/.cache/huggingface && ! -d "$HF_HOME/hub" ]]; then
        echo "📦 Migriere vorhandenen root-Cache nach $HF_HOME ..."
        mkdir -p "$HF_HOME"
        rsync -a /root/.cache/huggingface/ "$HF_HOME/"
    fi
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$APP_DIR"
mkdir -p "$HF_HOME"

echo "🐍 Python: $($VENV_DIR/bin/python --version)"
echo "📁 HF_HOME=$HF_HOME"
echo "🔥 Checking torch..."
python -c "import torch; print(f'   torch {torch.__version__}')" || {
    echo "❌ torch missing. Install first:" >&2
    echo "   pip install torch --index-url https://download.pytorch.org/whl/cpu" >&2
    exit 1
}

pip install -q "huggingface_hub>=0.26.0"

echo "📥 Downloading ${#MODELS[@]} Opus-MT models ..."
for model in "${MODELS[@]}"; do
    echo ""
    echo "➡️  $model"
    python - <<PY
import os
os.environ["HF_HOME"] = "${HF_HOME}"
from huggingface_hub import snapshot_download
snapshot_download(repo_id="${model}")
print("   ✅ cached")
PY
done

if id mailhelper &>/dev/null; then
    chown -R mailhelper:mailhelper "$HF_HOME"
fi

echo ""
echo "✅ Done. Test (als mailhelper):"
echo "   sudo -u mailhelper env HF_HOME=$HF_HOME $VENV_DIR/bin/python -c \\"
echo "     \"from transformers import AutoTokenizer; AutoTokenizer.from_pretrained('Helsinki-NLP/opus-mt-de-en', local_files_only=True); print('OK')\""
