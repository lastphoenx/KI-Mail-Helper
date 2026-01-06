# KI-Modell-Empfehlungen für KI-Mail-Helper

> **Zielgruppe:** Anwender und Administratoren  
> **Stand:** Januar 2026  
> **Getestet mit:** Ollama, OpenAI, Anthropic, Mistral

---

## Übersicht: Die 3-Stufen-Architektur

KI-Mail-Helper verwendet drei separate KI-Modelle für unterschiedliche Aufgaben:

| Stufe | Zweck | Wann ausgeführt |
|-------|-------|-----------------|
| **Embedding** | Semantische Vektoren für Suche & Tag-Matching | Bei jedem Email-Fetch |
| **Base** | Schnelle Klassifikation (Score, Farbe, Tags) | Bei jedem Email-Fetch |
| **Optimize** | Tiefe Analyse (bessere Tags, Kontext) | Manuell pro Email |

---

## 1. Embedding-Modell

### Aufgabe
Wandelt Email-Text in einen numerischen Vektor (z.B. 384 Dimensionen) um. Dieser Vektor ermöglicht:
- **Semantische Suche:** "Finde Emails über Vertragskündigungen"
- **Tag-Suggestions:** Ähnlichkeit zwischen Email und Tag-Beschreibung
- **Learned Tags:** Durchschnitt aller Email-Vektoren eines Tags

### Modell-Vergleich

| Modell | Provider | Dimensionen | Geschwindigkeit | Qualität | Größe |
|--------|----------|-------------|-----------------|----------|-------|
| `all-minilm:22m` | Ollama | 384 | ⚡⚡⚡ Sehr schnell | ⭐⭐⭐ Gut | 46 MB |
| `nomic-embed-text` | Ollama | 768 | ⚡⚡ Schnell | ⭐⭐⭐⭐ Sehr gut | 274 MB |
| `mxbai-embed-large` | Ollama | 1024 | ⚡ Mittel | ⭐⭐⭐⭐⭐ Exzellent | 669 MB |
| `bge-m3` | Ollama | 1024 | ⚡⚡ Schnell | ⭐⭐⭐⭐⭐ Exzellent | 567 MB |
| `text-embedding-3-small` | OpenAI | 1536 | ⚡⚡⚡ Sehr schnell | ⭐⭐⭐⭐ Sehr gut | Cloud |
| `text-embedding-3-large` | OpenAI | 3072 | ⚡⚡ Schnell | ⭐⭐⭐⭐⭐ Exzellent | Cloud |

### Empfehlung: `all-minilm:22m` ✅

**Begründung:**

Die Wahl des Embedding-Modells hat **weniger Einfluss auf die Qualität** als ursprünglich angenommen. Unsere Tests zeigten:

| Szenario | all-minilm:22m | mxbai-embed-large |
|----------|----------------|-------------------|
| Description-basierte Tags | 15-25% Similarity | 20-30% Similarity |
| **Learned Tags** (3+ Emails) | **85-95% Similarity** | **87-96% Similarity** |

**Der Qualitätssprung kommt vom Learning, nicht vom Modell.**

Wenn ein Tag aus 3+ manuell zugewiesenen Emails lernt, erreichen beide Modelle exzellente Ergebnisse. Das größere Modell bringt nur ~2-5% mehr Similarity – bei 10x längerer Verarbeitungszeit.

**Fazit:** `all-minilm:22m` bietet das beste Verhältnis aus Geschwindigkeit und Qualität. Die investierte Zeit ist bei größeren Modellen besser in manuelles Tagging investiert.

---

## 2. Base-Modell

### Aufgabe
Analysiert jede Email beim Fetch und bestimmt:
- **Score** (1-10): Priorität der Email
- **Farbe** (Rot/Gelb/Grün): Visuelle Dringlichkeit
- **Dringlichkeit** (1-3): Zeitliche Komponente
- **Wichtigkeit** (1-3): Inhaltliche Relevanz
- **Kategorie:** "aktion_erforderlich" / "dringend" / "nur_information"
- **Tag-Vorschläge:** 1-5 semantische Tags

### Modell-Vergleich

| Modell | Provider | Parameter | Geschwindigkeit | Qualität | VRAM |
|--------|----------|-----------|-----------------|----------|------|
| `llama3.2:1b` | Ollama | 1B | ⚡⚡⚡ Sehr schnell | ⭐⭐⭐ Gut | 2-3 GB |
| `llama3.2:3b` | Ollama | 3B | ⚡⚡ Schnell | ⭐⭐⭐⭐ Sehr gut | 4-5 GB |
| `gemma2:2b` | Ollama | 2B | ⚡⚡⚡ Sehr schnell | ⭐⭐⭐ Gut | 3 GB |
| `phi3:3.8b` | Ollama | 3.8B | ⚡⚡ Schnell | ⭐⭐⭐⭐ Sehr gut | 4 GB |
| `gpt-4o-mini` | OpenAI | - | ⚡⚡⚡ Sehr schnell | ⭐⭐⭐⭐⭐ Exzellent | Cloud |
| `claude-3-5-haiku` | Anthropic | - | ⚡⚡⚡ Sehr schnell | ⭐⭐⭐⭐⭐ Exzellent | Cloud |

### Empfehlung: `llama3.2:1b` (lokal) oder `gpt-4o-mini` (Cloud) ✅

**Begründung:**

Das Base-Modell wird bei **jedem Email-Fetch** ausgeführt. Bei 50 neuen Emails bedeutet das 50 Analysen. Geschwindigkeit ist hier kritisch.

| Aspekt | llama3.2:1b | llama3.2:3b |
|--------|-------------|-------------|
| Zeit pro Email (CPU) | ~5-8 Min | ~15+ Min |
| Zeit pro Email (GPU) | <1 Sek | ~2 Sek |
| Score-Genauigkeit | 85% | 90% |
| Tag-Qualität | Gut | Sehr gut |

**Der Unterschied in der Analyse-Qualität ist marginal**, da:
1. Die KI nur eine Ersteinschätzung liefert
2. User die Bewertung korrigieren können (Learning)
3. Tags über Embeddings gematcht werden, nicht über das Base-Modell

**Für Cloud-User:** `gpt-4o-mini` bietet exzellente Qualität bei sehr niedrigen Kosten (~$0.15 pro 1M Tokens).

---

## 3. Optimize-Modell

### Aufgabe
Führt eine tiefere Analyse durch, wenn der User auf "Optimieren" klickt:
- Bessere Tag-Vorschläge durch längere Analyse
- Kontext aus Email-Thread berücksichtigen
- Feinere Unterscheidung bei ambivalenten Emails

### Modell-Vergleich

| Modell | Provider | Parameter | Geschwindigkeit | Qualität | Kosten |
|--------|----------|-----------|-----------------|----------|--------|
| `llama3.2:3b` | Ollama | 3B | ⚡⚡ Schnell | ⭐⭐⭐⭐ Sehr gut | Kostenlos |
| `llama3.1:8b` | Ollama | 8B | ⚡ Langsam | ⭐⭐⭐⭐⭐ Exzellent | Kostenlos |
| `gpt-4o` | OpenAI | - | ⚡⚡ Schnell | ⭐⭐⭐⭐⭐ Exzellent | ~$5/1M |
| `claude-3-5-sonnet` | Anthropic | - | ⚡⚡ Schnell | ⭐⭐⭐⭐⭐ Exzellent | ~$3/1M |
| `mistral-large` | Mistral | - | ⚡⚡ Schnell | ⭐⭐⭐⭐⭐ Exzellent | ~$2/1M |

### Empfehlung: `llama3.2:3b` (lokal) oder `claude-3-5-sonnet` (Cloud) ✅

**Begründung:**

Optimize wird nur **manuell und selten** ausgeführt. Hier lohnt sich ein größeres Modell, da:
1. Geschwindigkeit weniger kritisch ist
2. Komplexe Emails von besserer Analyse profitieren
3. Der User aktiv auf das Ergebnis wartet

**Für rein lokalen Betrieb:** `llama3.2:3b` bietet gute Qualität ohne Cloud-Abhängigkeit.

**Für beste Ergebnisse:** Cloud-Modelle wie `claude-3-5-sonnet` oder `gpt-4o` liefern die präzisesten Analysen.

---

## Finale Empfehlung

### Lokaler Betrieb (Privacy-First)

| Stufe | Modell | Begründung |
|-------|--------|------------|
| **Embedding** | `all-minilm:22m` | Schnell, Qualität kommt vom Learning |
| **Base** | `llama3.2:1b` | Beste Balance Geschwindigkeit/Qualität |
| **Optimize** | `llama3.2:3b` | Tiefere Analyse bei manueller Nutzung |

**Ollama-Installation:**
```bash
ollama pull all-minilm:22m
ollama pull llama3.2:1b
ollama pull llama3.2:3b
```

**Ressourcen-Bedarf:**
- RAM: 8 GB minimum, 16 GB empfohlen
- Speicher: ~3.5 GB für alle Modelle
- GPU: Optional, aber 10-50x schneller

---

### Hybrid-Betrieb (Lokal + Cloud)

| Stufe | Modell | Begründung |
|-------|--------|------------|
| **Embedding** | `all-minilm:22m` | Lokal, keine Daten in Cloud |
| **Base** | `gpt-4o-mini` | Schnell, günstig, exzellent |
| **Optimize** | `claude-3-5-sonnet` | Beste Qualität für wichtige Emails |

**Vorteile:**
- Embeddings bleiben lokal (Privacy)
- Cloud-Modelle für Analyse (Qualität)
- Keine GPU erforderlich

---

### Cloud-Only (Einfachste Einrichtung)

| Stufe | Modell | Begründung |
|-------|--------|------------|
| **Embedding** | `text-embedding-3-small` | Schnell, günstig |
| **Base** | `gpt-4o-mini` | Beste Balance |
| **Optimize** | `gpt-4o` | Maximale Qualität |

**Hinweis:** Bei Cloud-Only werden Email-Inhalte an externe Server gesendet.

---

## Der entscheidende Faktor: Learning

> **Wichtig:** Die Wahl des Modells ist weniger entscheidend als das **Tag-Learning-System**.

### Wie Learning funktioniert

1. User weist Tag manuell zu einer Email zu
2. System speichert Email-Embedding als "positives Beispiel"
3. Nach 3+ Beispielen: Tag bekommt "Learned Embedding" (Durchschnitt)
4. Neue Emails werden gegen Learned Embedding gematcht
5. Similarity steigt von ~20% (Description) auf ~90% (Learned)

### Warum Learning wichtiger ist als Modellgröße

| Ansatz | Similarity | Zeitaufwand |
|--------|------------|-------------|
| Größeres Embedding-Modell | +5% | +500% Rechenzeit |
| 3 Emails manuell taggen | +60% | 30 Sekunden |

**Fazit:** Investiere Zeit ins Tagging, nicht in größere Modelle.

---

## Performance-Richtwerte

### Mit GPU (RTX 3060 oder besser)

| Operation | Zeit |
|-----------|------|
| Email-Embedding | ~50 ms |
| Base-Analyse | <1 Sekunde |
| Optimize-Analyse | ~2-3 Sekunden |
| **50 Emails verarbeiten** | **~2-3 Minuten** |

### Ohne GPU (nur CPU)

| Operation | Zeit |
|-----------|------|
| Email-Embedding | ~2-5 Sekunden |
| Base-Analyse | ~5-10 Minuten |
| Optimize-Analyse | ~15-20 Minuten |
| **50 Emails verarbeiten** | **~8+ Stunden** |

**Empfehlung für CPU-Only:** Cloud-Provider für Base/Optimize nutzen, Embedding lokal.

---

## Zusammenfassung

1. **Embedding:** `all-minilm:22m` – Klein, schnell, ausreichend (Learning macht den Unterschied)
2. **Base:** `llama3.2:1b` – Schnell genug für Batch-Processing
3. **Optimize:** `llama3.2:3b` oder Cloud – Qualität bei manueller Nutzung

**Die wichtigste Erkenntnis:** Ein kleines Modell mit gutem Learning schlägt ein großes Modell ohne Learning.
