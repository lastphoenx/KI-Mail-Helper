#!/usr/bin/env python3
"""
Cache-Invalidierung für Tag-Embeddings nach Bugfix

Nach dem Fix (OllamaEmbeddingClient statt LocalOllamaClient) müssen
alle gecachten Tag-Embeddings gelöscht werden, damit sie neu generiert werden.
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from services.tag_manager import TagEmbeddingCache

def main():
    print("🗑️  Invalidiere Tag-Embedding Cache...")
    
    # Cache komplett leeren
    TagEmbeddingCache._cache = {}
    TagEmbeddingCache._ai_client_cache = {}
    
    print("✅ Cache geleert!")
    print("📝 Beim nächsten Server-Start werden alle Tag-Embeddings neu generiert")
    print("   mit dem korrekten OllamaEmbeddingClient (/api/embeddings Endpoint)")

if __name__ == "__main__":
    main()
