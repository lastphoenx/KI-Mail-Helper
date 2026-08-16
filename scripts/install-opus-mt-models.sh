#!/usr/bin/env bash
# Pre-download Helsinki-NLP Opus-MT models into the Hugging Face cache.
# Lädt NUR fehlende Modelle nach – bereits gecachte werden übersprungen.
#
# Usage on CT 134:
#   sudo -u mailhelper bash scripts/install-opus-mt-models.sh
#
# Einzelnes Modell nachladen:
#   MODELS="Helsinki-NLP/opus-mt-tc-big-en-pt" sudo -u mailhelper bash scripts/install-opus-mt-models.sh

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
VENV_DIR="${VENV_DIR:-$APP_DIR/venv}"
HF_HOME="${HF_HOME:-$APP_DIR/.cache/huggingface}"
export HF_HOME APP_DIR

DEFAULT_MODELS=(
    Helsinki-NLP/opus-mt-de-en
    Helsinki-NLP/opus-mt-en-de
    Helsinki-NLP/opus-mt-de-it
    Helsinki-NLP/opus-mt-it-de
    Helsinki-NLP/opus-mt-de-fr
    Helsinki-NLP/opus-mt-fr-de
    Helsinki-NLP/opus-mt-de-es
    Helsinki-NLP/opus-mt-es-de
    Helsinki-NLP/opus-mt-de-nl
    Helsinki-NLP/opus-mt-nl-en
    Helsinki-NLP/opus-mt-de-pl
    Helsinki-NLP/opus-mt-pl-en
    Helsinki-NLP/opus-mt-en-it
    Helsinki-NLP/opus-mt-it-en
    Helsinki-NLP/opus-mt-en-fr
    Helsinki-NLP/opus-mt-fr-en
    Helsinki-NLP/opus-mt-tc-big-en-pt
)

# Optional: nur für PT→DE (selten gebraucht); Fehler blockiert nicht
OPTIONAL_MODELS=(
    Helsinki-NLP/opus-mt-ROMANCE-en
)

copy_tree() {
    local src="$1"
    local dst="$2"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a "$src" "$dst"
    else
        mkdir -p "$dst"
        cp -a "${src%/}/." "$dst/"
    fi
}

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "❌ venv not found: $VENV_DIR/bin/python" >&2
    exit 1
fi

if [[ "$(id -un)" == "root" ]]; then
    echo "⚠️  Besser: sudo -u mailhelper bash scripts/install-opus-mt-models.sh"
    if [[ -d /root/.cache/huggingface && ! -d "$HF_HOME/hub" ]]; then
        echo "📦 Migriere root-Cache → $HF_HOME"
        mkdir -p "$HF_HOME"
        copy_tree /root/.cache/huggingface/ "$HF_HOME/"
    fi
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$APP_DIR"
mkdir -p "$HF_HOME"

# Override via env: MODELS="Helsinki-NLP/opus-mt-de-en ..."
if [[ -n "${MODELS:-}" ]]; then
    # shellcheck disable=SC2206
    TARGET_MODELS=($MODELS)
else
    TARGET_MODELS=("${DEFAULT_MODELS[@]}" "${OPTIONAL_MODELS[@]}")
fi

echo "🐍 $($VENV_DIR/bin/python --version) | HF_HOME=$HF_HOME"
python -c "import torch; print(f'torch {torch.__version__}')" || {
    echo "❌ torch fehlt: pip install torch --index-url https://download.pytorch.org/whl/cpu" >&2
    exit 1
}

pip install -q "huggingface_hub>=0.26.0"

python - "${TARGET_MODELS[@]}" <<'PY'
import os, sys
from pathlib import Path

HF_HOME = os.environ["HF_HOME"]
OPTIONAL = {
    "Helsinki-NLP/opus-mt-ROMANCE-en",
}
models = sys.argv[1:]

def is_cached(repo_id: str) -> bool:
    slug = "models--" + repo_id.replace("/", "--")
    snaps = Path(HF_HOME) / "hub" / slug / "snapshots"
    if not snaps.is_dir():
        return False
    return any((p / "config.json").exists() for p in snaps.iterdir() if p.is_dir())

from huggingface_hub import snapshot_download

skipped = downloaded = failed = 0
for repo_id in models:
    print(f"\n➡️  {repo_id}")
    if is_cached(repo_id):
        print("   ⏭️  bereits im Cache")
        skipped += 1
        continue
    try:
        snapshot_download(repo_id=repo_id)
        print("   ✅ heruntergeladen")
        downloaded += 1
    except Exception as exc:
        tag = "optional, übersprungen" if repo_id in OPTIONAL else "fehlgeschlagen"
        print(f"   ⚠️  {tag}: {exc}")
        failed += 1

print(f"\n📊 {skipped} im Cache, {downloaded} neu, {failed} fehlgeschlagen")
if failed and failed == len(models):
    sys.exit(1)
PY

if id mailhelper &>/dev/null; then
    chown -R mailhelper:mailhelper "$HF_HOME"
fi

echo "✅ Fertig."
