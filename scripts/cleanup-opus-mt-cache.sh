#!/usr/bin/env bash
# Speicher freimachen: Hugging-Face-Cache von redundanten Gewichten bereinigen.
#
# Opus-MT lädt standardmäßig pytorch + tensorflow + rust (~1.2 GB/Modell).
# Für transformers/PyTorch reicht pytorch_model.bin (+ Tokenizer) (~300 MB).
#
# Usage (CT 134):
#   sudo bash scripts/cleanup-opus-mt-cache.sh
#   sudo bash scripts/cleanup-opus-mt-cache.sh --dry-run   # nur anzeigen

set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
HF_HOME="${HF_HOME:-$APP_DIR/.cache/huggingface}"
HUB="${HF_HOME}/hub"
DRY_RUN=0

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
    echo "🔍 Dry-run — nichts wird gelöscht"
fi

run_rm() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "  würde löschen: $*"
    else
        rm -rf "$@"
    fi
}

run_find_delete() {
    local desc="$1"
    shift
    local count size
    count=$(find "$HUB" "$@" 2>/dev/null | wc -l)
    if [[ "$count" -eq 0 ]]; then
        echo "   (keine $desc)"
        return
    fi
    size=$(find "$HUB" "$@" -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {printf "%.1f MB", s/1024/1024}')
    echo "   $count × $desc (~$size)"
    if [[ "$DRY_RUN" -eq 0 ]]; then
        find "$HUB" "$@" -delete 2>/dev/null || true
    fi
}

echo "📊 Vorher:"
df -h / | tail -1
if [[ -d "$HUB" ]]; then
    du -sh "$HUB"
else
    echo "   Kein Hub-Cache unter $HUB"
    exit 0
fi

echo ""
echo "🧹 Schritt 1: unvollständige Downloads (.incomplete)"
if [[ "$DRY_RUN" -eq 0 ]]; then
    find "$HF_HOME" -name '*.incomplete' -delete 2>/dev/null || true
fi
echo "   OK"

echo ""
echo "🧹 Schritt 2: kaputtes/teilweises ROMANCE-en (optional, oft unfertig)"
if [[ -d "$HUB/models--Helsinki-NLP--opus-mt-ROMANCE-en" ]]; then
    du -sh "$HUB/models--Helsinki-NLP--opus-mt-ROMANCE-en"
    run_rm "$HUB/models--Helsinki-NLP--opus-mt-ROMANCE-en"
fi

echo ""
echo "🧹 Schritt 3: redundante Gewichte (PyTorch reicht für Opus-MT)"
run_find_delete "rust_model.ot" -type f -name 'rust_model.ot'
run_find_delete "tf_model.h5" -type f -name 'tf_model.h5'
run_find_delete "flax_model.msgpack" -type f -name 'flax_model.msgpack'
run_find_delete "ONNX" -type f -name '*.onnx'

echo ""
echo "🧹 Schritt 4: doppelter root-Cache (falls migriert)"
if [[ -d /root/.cache/huggingface ]]; then
    echo "   /root/.cache/huggingface: $(du -sh /root/.cache/huggingface | cut -f1)"
    echo "   → Kann gelöscht werden wenn $HF_HOME vollständig ist:"
    echo "     rm -rf /root/.cache/huggingface"
fi

echo ""
echo "🧹 Schritt 5: pip/apt Cache (optional, manuell)"
echo "   apt-get clean && rm -rf /root/.cache/pip"

echo ""
echo "📊 Nachher:"
if [[ "$DRY_RUN" -eq 0 ]]; then
    df -h / | tail -1
    du -sh "$HUB" 2>/dev/null || true
    if id mailhelper &>/dev/null; then
        chown -R mailhelper:mailhelper "$HF_HOME"
    fi
    echo "✅ Fertig. Danach: git pull && sudo systemctl restart mail-helper"
else
    echo "   Zum Ausführen ohne --dry-run"
fi
