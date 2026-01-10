# 🎯 Phase Y: Analysis Modes - Implementierungskonzept

**Ziel:** Klarheit & Kontrolle über Analyse-Modi beim Email-Fetch  
**Status:** 🔴 Konzept (noch nicht implementiert)  
**Datum:** 2026-01-08  
**Aufwand:** Phase 1: 3-4h | Phase 2: 4-6h | Phase 3: siehe PHASE_18

---

## 📋 Problemstellung (Aktuell)

### ❌ Was ist kaputt:

1. **Settings-UI irreführend:**
   - User wählt Base-Modell (Llama 3.2 1B)
   - Denkt: "Das wird beim Fetch genutzt"
   - **Realität:** Wird ignoriert wenn Urgency Booster aktiv ist

2. **Undokumentierte Konflikt-Logik:**
   ```python
   if urgency_booster_enabled:
       # Phase Y Spacy läuft → Base-Modell wird NICHT genutzt
       return spacy_result
   else:
       # Jetzt erst wird Base-Modell verwendet
       return llm_result
   ```

3. **"Initial Analyse: N/A":**
   - User sieht nicht, welche Analyse lief
   - Keine Transparenz über verwendete Methode

4. **Fehlende Anonymisierungs-Option:**
   - Keine Möglichkeit, Spacy-Anonymisierung vor LLM-Call zu nutzen
   - Cloud-LLM ohne Datenschutz-Layer

---

## 🎯 Ziel-Architektur (Vision)

### ✅ Was wir erreichen wollen:

```
┌────────────────────────────────────────────────────┐
│  ACCOUNT-LEVEL TOGGLES (hierarchisch)              │
├────────────────────────────────────────────────────┤
│                                                     │
│  1️⃣ [ ] Mit Spacy anonymisieren                     │
│      └─ Immer verfügbar, unabhängig von anderen   │
│         Erstellt: subject_anon + body_anon         │
│                                                     │
│  ╔════════════════════════════════════════╗        │
│  ║ ENTWEDER: Urgency Booster              ║        │
│  ╠════════════════════════════════════════╣        │
│  ║  2️⃣ [✓] Urgency Booster (Spacy)         ║        │
│  ║     → Nur Spacy-Analyse                ║        │
│  ║     → Blockiert AI-Toggles (3️⃣ & 4️⃣)   ║        │
│  ╚════════════════════════════════════════╝        │
│                                                     │
│  ╔════════════════════════════════════════╗        │
│  ║ ODER: AI-Analyse (gegenseitig exkl.)  ║        │
│  ╠════════════════════════════════════════╣        │
│  ║  3️⃣ [ ] AI-Analyse - Anonyme Daten      ║        │
│  ║     → Base-Model auf anonyme Version   ║        │
│  ║     → Benötigt Toggle 1️⃣ aktiviert      ║        │
│  ║                                        ║        │
│  ║  4️⃣ [✓] AI-Analyse - Original Daten     ║        │
│  ║     → Base-Model auf Original-Email    ║        │
│  ║     → Unabhängig von Toggle 1️⃣          ║        │
│  ╚════════════════════════════════════════╝        │
│                                                     │
│  ⚠️ Konflikt-Regel:                                │
│  Toggle 2️⃣ AN → Toggles 3️⃣ & 4️⃣ disabled           │
│  Toggle 3️⃣ & 4️⃣: Maximal EINER aktiv               │
└────────────────────────────────────────────────────┘
```

### 📊 Erlaubte Kombinationen:

| 1️⃣ Anon | 2️⃣ Urgency | 3️⃣ AI-Anon | 4️⃣ AI-Orig | Resultat |
|---------|-----------|-----------|-----------|----------|
| ❌ | ❌ | ❌ | ❌ | Nur Embeddings |
| ❌ | ❌ | ❌ | ✅ | **Base-Model auf Original** |
| ❌ | ✅ | - | - | **Spacy Booster only** |
| ✅ | ❌ | ❌ | ❌ | **Nur Anonymisierung** (für Archiv) |
| ✅ | ❌ | ✅ | ❌ | **Base-Model auf Anon** ⭐ Datenschutz |
| ✅ | ❌ | ❌ | ✅ | **Base-Model auf Orig** + Anon gespeichert |
| ✅ | ✅ | - | - | **Spacy Booster** + Anon gespeichert |

**Verboten:**
- ✅ ✅ ✅ ❌ → **NICHT erlaubt** (beide AI-Toggles gleichzeitig)
- Urgency Booster blockiert AI-Toggles komplett

---

## 🚀 Implementierung: 3 Phasen

---

## Phase 1: Status Quo fixen (3-4h)

**Ziel:** Aktuelle Situation transparenter machen, ohne neue Features

### 1.1 Initial Analyse korrekt anzeigen

**Problem:** "Initial Analyse: N/A" ist undurchsichtig

**Lösung:** Zeige verwendete Methode in Email-Details

**Änderungen:**

#### A) Backend: Analysis-Methode tracken

**Datei:** `src/12_processing.py` (ab Line 490)

```python
# Provider/Model Tracking: Prüfe ob UrgencyBooster oder LLM verwendet wurde
actual_provider = None
actual_model = None
analysis_method = None  # NEU

if ai_result:
    if ai_result.get("_used_booster"):
        # UrgencyBooster (spaCy) hat die Email verarbeitet
        actual_provider = "urgency_booster"
        actual_model = "spacy:de_core_news_sm"
        analysis_method = "spacy_booster"  # NEU
    elif ai_result.get("_used_phase_y"):  # NEU
        # Phase Y Hybrid Pipeline
        actual_provider = "phase_y"
        actual_model = "hybrid:spacy+sgd"
        analysis_method = "phase_y_hybrid"  # NEU
    else:
        # Normales LLM hat die Email verarbeitet
        actual_provider = ai_provider
        actual_model = ai_model
        analysis_method = f"llm:{ai_provider}"  # NEU
else:
    analysis_method = "none"  # NEU: Keine Analyse
```

**Datei:** `src/03_ai_client.py` (Line 1085)

```python
# In _convert_phase_y_to_llm_format():
result = {
    "dringlichkeit": pipeline_result["dringlichkeit"],
    "wichtigkeit": pipeline_result["wichtigkeit"],
    # ... rest ...
    "_used_booster": True,
    "_used_phase_y": True,  # NEU: Markiere Phase Y
}
```

#### B) Email Model erweitern

**Datei:** `src/02_models.py`

```python
class Email(Base):
    # ... bestehende Felder ...
    
    # ===== PHASE Y: ANALYSIS METHOD TRACKING =====
    analysis_method = Column(String(50), nullable=True)
    # Werte: "none" | "spacy_booster" | "phase_y_hybrid" | "llm:ollama" | "llm:openai" | etc.
```

**Migration:**

```bash
alembic revision -m "add_analysis_method"
```

```python
def upgrade():
    op.add_column('emails', 
        sa.Column('analysis_method', sa.String(50), nullable=True)
    )
    
    # Setze Default für bestehende Emails
    op.execute("""
        UPDATE emails 
        SET analysis_method = CASE 
            WHEN ai_provider = 'urgency_booster' THEN 'spacy_booster'
            WHEN ai_provider IS NOT NULL THEN 'llm:' || ai_provider
            ELSE 'none'
        END
        WHERE analysis_method IS NULL
    """)
```

#### C) UI: Initial Analyse aussagekräftig machen

**Datei:** `templates/email_details.html`

```html
<!-- Statt: -->
<div class="detail-row">
    <span class="detail-label">🤖 Initial Analyse:</span>
    <span class="detail-value">{{ email.ai_provider or 'N/A' }}</span>
</div>

<!-- NEU: -->
<div class="detail-row">
    <span class="detail-label">🤖 Initial Analyse:</span>
    <span class="detail-value">
        {% if email.analysis_method == 'none' %}
            <span class="badge bg-secondary">Keine Analyse</span>
            <small class="text-muted">(AI-Analyse beim Abruf deaktiviert)</small>
        {% elif email.analysis_method == 'spacy_booster' %}
            <span class="badge bg-info">⚡ Spacy Booster</span>
            <small class="text-muted">(Regel-basiert, keine LLM-Kosten)</small>
        {% elif email.analysis_method == 'phase_y_hybrid' %}
            <span class="badge bg-success">🔬 Phase Y Hybrid</span>
            <small class="text-muted">(Spacy + SGD Ensemble Learning)</small>
        {% elif email.analysis_method and email.analysis_method.startswith('llm:') %}
            <span class="badge bg-primary">🤖 {{ email.analysis_method.replace('llm:', '').upper() }}</span>
            <small class="text-muted">({{ email.ai_model or 'unbekannt' }})</small>
        {% else %}
            <span class="badge bg-warning">{{ email.ai_provider or 'N/A' }}</span>
        {% endif %}
    </span>
</div>
```

### 1.2 Settings-Page: Klarheit schaffen

**Datei:** `templates/settings.html` (KI-Priorisierung Tab)

Füge Warnung nach Base-Model Dropdown hinzu:

```html
<!-- Nach Base-Model Auswahl: -->
<div class="alert alert-info mt-2">
    ℹ️ <strong>Wichtig:</strong> Das Base-Modell wird verwendet für:
    <ul class="mb-0 mt-2">
        <li>✅ Manuelle "Pass neu" Analysen (Email-Details)</li>
        <li>✅ Fetch-Analysen (wenn Urgency Booster AUS)</li>
        <li>❌ <strong>NICHT</strong> bei aktivem Urgency Booster (nutzt Spacy statt LLM)</li>
    </ul>
</div>
```

**Im Account-Settings Bereich:**

```html
<div class="settings-section">
    <h4>🔬 Analyse beim Email-Abruf</h4>
    
    <div class="form-check mb-3">
        <input type="checkbox" class="form-check-input" 
               id="enable_ai_analysis" name="enable_ai_analysis"
               {{ 'checked' if account.enable_ai_analysis_on_fetch }}>
        <label class="form-check-label" for="enable_ai_analysis">
            <strong>AI-Analyse beim Abruf aktivieren</strong>
            <br>
            <small class="text-muted">
                Nutzt Base-Modell ({{ current_base_model or 'nicht konfiguriert' }})
            </small>
        </label>
    </div>
    
    <div class="form-check mb-3">
        <input type="checkbox" class="form-check-input" 
               id="urgency_booster_enabled" name="urgency_booster_enabled"
               {{ 'checked' if account.urgency_booster_enabled }}>
        <label class="form-check-label" for="urgency_booster_enabled">
            <strong>⚡ Urgency Booster (Spacy)</strong>
            <br>
            <small class="text-muted">
                Regel-basierte Analyse (schnell, kostenlos, offline)
            </small>
        </label>
    </div>
    
    <!-- NEU: Konflikt-Warnung -->
    <div class="alert alert-warning" id="conflict-warning" style="display:none;">
        ⚠️ <strong>Konflikt:</strong> Urgency Booster überschreibt AI-Analyse!
        <br>
        Wenn Urgency Booster aktiv ist, wird das Base-Modell NICHT verwendet.
        <br>
        → Nur Spacy-Regeln werden angewandt (keine LLM-Analyse)
    </div>
</div>

<script>
// Zeige Warnung wenn beide aktiv
function checkConflict() {
    const aiEnabled = $('#enable_ai_analysis').is(':checked');
    const boosterEnabled = $('#urgency_booster_enabled').is(':checked');
    
    if (aiEnabled && boosterEnabled) {
        $('#conflict-warning').show();
    } else {
        $('#conflict-warning').hide();
    }
}

$('#enable_ai_analysis, #urgency_booster_enabled').change(checkConflict);
checkConflict(); // Initial check
</script>
```

### 1.3 Whitelist-Page: use_urgency_booster erklären

**Datei:** `templates/whitelist.html`

```html
<!-- Bei jedem Trusted Sender: -->
<div class="form-check">
    <input type="checkbox" class="form-check-input" 
           id="use_booster_{{ sender.id }}" 
           {{ 'checked' if sender.use_urgency_booster }}>
    <label class="form-check-label" for="use_booster_{{ sender.id }}">
        ⚡ Urgency Booster aktivieren
    </label>
    
    <!-- NEU: Tooltip/Erklärung -->
    <div class="small text-muted mt-1">
        ℹ️ <strong>Was bedeutet das?</strong>
        <ul class="mb-0 ps-3">
            <li><strong>AN:</strong> Emails von diesem Absender werden mit Spacy-Regeln analysiert (schnell, offline)</li>
            <li><strong>AUS:</strong> Emails nutzen das Base-Modell aus Settings (LLM-basiert)</li>
        </ul>
        
        <div class="alert alert-sm alert-info mt-2">
            💡 <strong>Empfehlung:</strong>
            <br>• AN für regelmäßige Business-Absender (Newsletter, HR-System, etc.)
            <br>• AUS für komplexe/wichtige Emails (Chef, Kunden, unbekannte Absender)
        </div>
    </div>
</div>
```

### 1.4 Testing & Validation

**Testfälle:**

```python
# test_analysis_method_tracking.py

def test_phase_y_tracked_correctly():
    """Phase Y Analysis soll als 'phase_y_hybrid' getrackt werden"""
    # Account mit urgency_booster_enabled=True
    # Fetch Email
    assert email.analysis_method == "phase_y_hybrid"
    assert email.ai_provider == "phase_y"

def test_llm_tracked_correctly():
    """LLM Analysis soll als 'llm:provider' getrackt werden"""
    # Account mit urgency_booster_enabled=False
    # Fetch Email
    assert email.analysis_method.startswith("llm:")
    assert email.ai_provider in ["ollama", "openai", "anthropic"]

def test_no_analysis_tracked():
    """Keine Analyse soll als 'none' getrackt werden"""
    # Account mit enable_ai_analysis_on_fetch=False
    # Fetch Email
    assert email.analysis_method == "none"
    assert email.ai_provider is None
```

**Checklist Phase 1:**

- [ ] Migration für `analysis_method` Spalte
- [ ] Backend trackt Analyse-Methode korrekt
- [ ] Email-Details zeigt aussagekräftige Badges
- [ ] Settings-Page hat Warnung für Base-Model
- [ ] Settings-Page zeigt Konflikt-Warnung
- [ ] Whitelist-Page erklärt `use_urgency_booster`
- [ ] Tests für alle 3 Szenarien (Phase Y, LLM, none)
- [ ] Dokumentation aktualisiert

**Geschätzter Aufwand Phase 1:** 3-4 Stunden

---

## Phase 2: Toggle-Logik vorbereiten (4-6h)

**Ziel:** Hierarchische Toggle-Struktur einbauen, noch OHNE Anonymisierung

### 2.1 Datenbank-Schema erweitern

**Migration:** `alembic revision -m "analysis_modes_toggle_structure"`

```python
def upgrade():
    # ===== NEUE TOGGLES =====
    
    # 1️⃣ Anonymisierung (noch nicht funktional, nur Struktur)
    op.add_column('mail_accounts',
        sa.Column('anonymize_with_spacy', sa.Boolean, nullable=False, server_default='0')
    )
    
    # 2️⃣ Urgency Booster (umbenennen für Klarheit)
    # Bestehend: urgency_booster_enabled (behalten)
    
    # 3️⃣ AI-Analyse auf anonyme Daten (vorbereitet)
    op.add_column('mail_accounts',
        sa.Column('ai_analysis_anon_enabled', sa.Boolean, nullable=False, server_default='0')
    )
    
    # 4️⃣ AI-Analyse auf Original-Daten (ersetzt enable_ai_analysis_on_fetch)
    op.add_column('mail_accounts',
        sa.Column('ai_analysis_original_enabled', sa.Boolean, nullable=False, server_default='0')
    )
    
    # Migriere alte enable_ai_analysis_on_fetch → ai_analysis_original_enabled
    op.execute("""
        UPDATE mail_accounts
        SET ai_analysis_original_enabled = enable_ai_analysis_on_fetch
        WHERE ai_analysis_original_enabled = 0
    """)
    
    # enable_ai_analysis_on_fetch behalten für Kompatibilität (deprecated)

def downgrade():
    op.drop_column('mail_accounts', 'ai_analysis_original_enabled')
    op.drop_column('mail_accounts', 'ai_analysis_anon_enabled')
    op.drop_column('mail_accounts', 'anonymize_with_spacy')
```

### 2.2 Models aktualisieren

**Datei:** `src/02_models.py`

```python
class MailAccount(Base):
    __tablename__ = "mail_accounts"
    
    # ... bestehende Felder ...
    
    # ===== PHASE Y: ANALYSIS MODES =====
    
    # 1️⃣ Anonymisierung (vorbereitet für Phase 3)
    anonymize_with_spacy = Column(Boolean, nullable=False, default=False)
    
    # 2️⃣ Urgency Booster (bestehend)
    urgency_booster_enabled = Column(Boolean, nullable=False, default=False)
    
    # 3️⃣ AI-Analyse auf anonyme Daten (vorbereitet für Phase 3)
    ai_analysis_anon_enabled = Column(Boolean, nullable=False, default=False)
    
    # 4️⃣ AI-Analyse auf Original-Daten (neu, ersetzt enable_ai_analysis_on_fetch)
    ai_analysis_original_enabled = Column(Boolean, nullable=False, default=False)
    
    # Legacy (deprecated, wird durch ai_analysis_original_enabled ersetzt)
    enable_ai_analysis_on_fetch = Column(Boolean, nullable=False, default=False)
    
    @property
    def effective_ai_mode(self) -> str:
        """
        Berechnet effektiven Analyse-Modus unter Berücksichtigung aller Toggles.
        
        Returns:
            "none" | "spacy_booster" | "llm_original" | "llm_anon" (Phase 3)
        """
        # Priorität 1: Urgency Booster (überschreibt alles)
        if self.urgency_booster_enabled:
            return "spacy_booster"
        
        # Priorität 2: AI auf anonyme Daten (Phase 3)
        if self.ai_analysis_anon_enabled and self.anonymize_with_spacy:
            return "llm_anon"
        
        # Priorität 3: AI auf Original
        if self.ai_analysis_original_enabled:
            return "llm_original"
        
        # Fallback: Keine Analyse
        return "none"
```

### 2.3 Backend: Fetch-Logik anpassen

**Datei:** `src/12_processing.py`

```python
# Ersetze bisherige Logik (Line 434-450):

def process_email(raw_email, session, active_ai, ...):
    # ... 
    
    # ===== PHASE Y: ANALYSIS MODE DETECTION =====
    
    # Account-Settings laden
    account = session.query(models_mod.MailAccount).filter_by(
        id=raw_email.mail_account_id
    ).first()
    
    if not account:
        logger.warning(f"Account {raw_email.mail_account_id} nicht gefunden")
        ai_result = None
        analysis_method = "none"
    else:
        # Effektiven Modus berechnen
        effective_mode = account.effective_ai_mode
        
        logger.info(f"📧 Account '{account.name}': effective_mode={effective_mode}")
        
        if effective_mode == "none":
            logger.info("⏭️  Keine Analyse (alle Toggles aus)")
            ai_result = None
            analysis_method = "none"
            
        elif effective_mode == "spacy_booster":
            logger.info("⚡ Urgency Booster Modus")
            ai_result = active_ai.analyze_email(
                subject=decrypted_subject or "",
                body=clean_body,
                sender=decrypted_sender or "",
                language="de",
                user_id=raw_email.user_id,
                account_id=raw_email.mail_account_id,
                db=session,
                user_enabled_booster=True  # Force Phase Y
            )
            analysis_method = "phase_y_hybrid" if ai_result else "none"
            
        elif effective_mode == "llm_original":
            logger.info("🤖 LLM auf Original-Daten")
            ai_result = active_ai.analyze_email(
                subject=decrypted_subject or "",
                body=clean_body,
                sender=decrypted_sender or "",
                language="de",
                user_id=raw_email.user_id,
                account_id=raw_email.mail_account_id,
                db=session,
                user_enabled_booster=False  # Force LLM
            )
            analysis_method = f"llm:{ai_result.get('_provider', 'unknown')}" if ai_result else "none"
            
        elif effective_mode == "llm_anon":
            # Phase 3: Anonymisierte Daten nutzen
            logger.info("🛡️ LLM auf anonymisierte Daten (Phase 3)")
            # Noch nicht implementiert, Fallback:
            logger.warning("⚠️ llm_anon noch nicht implementiert, Fallback auf llm_original")
            effective_mode = "llm_original"
            # ... (wie llm_original)
    
    # ... Rest der Funktion ...
```

### 2.4 UI: Neue Toggle-Struktur

**Datei:** `templates/settings.html`

```html
<div class="settings-section">
    <h4>🔬 Analyse beim Email-Abruf</h4>
    
    <div class="alert alert-info">
        ℹ️ <strong>Hierarchische Modi:</strong> Toggles folgen einer Priorität.
        Nur ein Modus ist gleichzeitig aktiv.
    </div>
    
    <!-- 1️⃣ Anonymisierung (vorbereitet) -->
    <div class="form-check mb-3">
        <input type="checkbox" class="form-check-input" 
               id="anonymize_with_spacy" name="anonymize_with_spacy"
               {{ 'checked' if account.anonymize_with_spacy }}>
        <label class="form-check-label" for="anonymize_with_spacy">
            <strong>🛡️ Mit Spacy anonymisieren</strong>
            <span class="badge bg-secondary">Phase 3</span>
            <br>
            <small class="text-muted">
                Entfernt Namen, Firmen, Orte aus Emails (PII-Schutz).
                Erstellt separaten "Anonym"-Tab in Email-Details.
            </small>
        </label>
    </div>
    
    <hr>
    
    <!-- Modus-Auswahl (gegenseitig exklusiv) -->
    <div class="card">
        <div class="card-header bg-light">
            <strong>Analyse-Modus wählen (nur einer aktiv):</strong>
        </div>
        <div class="card-body">
            
            <!-- 2️⃣ Urgency Booster -->
            <div class="form-check mb-3">
                <input type="radio" class="form-check-input" 
                       name="analysis_mode" value="spacy_booster"
                       id="mode_spacy_booster"
                       {{ 'checked' if account.urgency_booster_enabled }}>
                <label class="form-check-label" for="mode_spacy_booster">
                    <strong>⚡ Urgency Booster (Spacy)</strong>
                    <br>
                    <small class="text-muted">
                        ✅ Schnell, kostenlos, offline
                        <br>✅ Nutzt deine Keyword-Sets + VIP-Liste
                        <br>❌ Nur regel-basiert (kein LLM)
                        <br>❌ Funktioniert besser bei Business-Mails
                    </small>
                </label>
            </div>
            
            <!-- 3️⃣ AI auf anonyme Daten -->
            <div class="form-check mb-3">
                <input type="radio" class="form-check-input" 
                       name="analysis_mode" value="llm_anon"
                       id="mode_llm_anon"
                       {{ 'checked' if account.ai_analysis_anon_enabled }}
                       {{ 'disabled' if not account.anonymize_with_spacy }}>
                <label class="form-check-label" for="mode_llm_anon">
                    <strong>🛡️ AI-Analyse - Anonyme Daten</strong>
                    <span class="badge bg-secondary">Phase 3</span>
                    <br>
                    <small class="text-muted">
                        ✅ Datenschutz: PII entfernt vor Cloud-LLM
                        <br>✅ Base-Modell aus Settings (Cloud möglich)
                        <br>❌ Benötigt "Mit Spacy anonymisieren"
                        <br>❌ Leicht reduzierte Qualität (weniger Context)
                    </small>
                </label>
            </div>
            
            <!-- 4️⃣ AI auf Original -->
            <div class="form-check mb-3">
                <input type="radio" class="form-check-input" 
                       name="analysis_mode" value="llm_original"
                       id="mode_llm_original"
                       {{ 'checked' if account.ai_analysis_original_enabled }}>
                <label class="form-check-label" for="mode_llm_original">
                    <strong>🤖 AI-Analyse - Original Daten</strong>
                    <br>
                    <small class="text-muted">
                        ✅ Base-Modell aus Settings ({{ current_base_model or 'nicht konfiguriert' }})
                        <br>✅ Beste Qualität (voller Context)
                        <br>⚠️ KEIN Datenschutz-Layer (sendet Original an LLM)
                        <br>💰 LLM-Kosten (falls Cloud-Modell)
                    </small>
                </label>
            </div>
            
            <!-- Keine Analyse -->
            <div class="form-check">
                <input type="radio" class="form-check-input" 
                       name="analysis_mode" value="none"
                       id="mode_none"
                       {{ 'checked' if account.effective_ai_mode == 'none' }}>
                <label class="form-check-label" for="mode_none">
                    <strong>❌ Keine Analyse</strong>
                    <br>
                    <small class="text-muted">
                        Nur Embeddings + Tag-Suggestions werden erstellt.
                        Scores bleiben bei Default (D:1, W:1).
                    </small>
                </label>
            </div>
            
        </div>
    </div>
    
    <!-- Anonymisierungs-Abhängigkeit -->
    <div class="alert alert-warning mt-3" id="anon-required" style="display:none;">
        ⚠️ "AI-Analyse - Anonyme Daten" benötigt aktivierte Anonymisierung!
    </div>
</div>

<script>
// Toggle-Logik
$(document).ready(function() {
    function updateToggleStates() {
        const anonEnabled = $('#anonymize_with_spacy').is(':checked');
        const mode = $('input[name="analysis_mode"]:checked').val();
        
        // AI-Anon nur verfügbar wenn Anonymisierung an
        if (!anonEnabled && mode === 'llm_anon') {
            $('#mode_llm_anon').prop('disabled', true);
            $('#mode_none').prop('checked', true);
            $('#anon-required').show();
        } else {
            $('#mode_llm_anon').prop('disabled', !anonEnabled);
            $('#anon-required').hide();
        }
    }
    
    $('#anonymize_with_spacy').change(updateToggleStates);
    $('input[name="analysis_mode"]').change(updateToggleStates);
    updateToggleStates();
});
</script>
```

### 2.5 Backend: Settings speichern

**Datei:** `src/01_web_app.py`

```python
@app.route("/account/<int:account_id>/settings", methods=["POST"])
@login_required
def update_account_settings(account_id):
    # ...
    
    # ===== PHASE Y: ANALYSIS MODES =====
    
    # 1️⃣ Anonymisierung
    account.anonymize_with_spacy = request.form.get('anonymize_with_spacy') == 'on'
    
    # 2️⃣-4️⃣ Modus-Auswahl (Radio-Buttons)
    analysis_mode = request.form.get('analysis_mode', 'none')
    
    # Reset alle Modi
    account.urgency_booster_enabled = False
    account.ai_analysis_anon_enabled = False
    account.ai_analysis_original_enabled = False
    
    # Aktiviere gewählten Modus
    if analysis_mode == 'spacy_booster':
        account.urgency_booster_enabled = True
    elif analysis_mode == 'llm_anon':
        if not account.anonymize_with_spacy:
            flash("⚠️ AI-Analyse auf anonyme Daten benötigt aktivierte Anonymisierung!", "warning")
            analysis_mode = 'none'
        else:
            account.ai_analysis_anon_enabled = True
    elif analysis_mode == 'llm_original':
        account.ai_analysis_original_enabled = True
    # else: none (alle bleiben False)
    
    # Legacy-Support
    account.enable_ai_analysis_on_fetch = (
        account.ai_analysis_original_enabled or account.ai_analysis_anon_enabled
    )
    
    db.session.commit()
    
    flash(f"✅ Analyse-Modus: {analysis_mode}", "success")
    # ...
```

### 2.6 Testing Phase 2

```python
# test_analysis_modes.py

def test_effective_mode_none():
    """Alle Toggles aus → none"""
    account = create_account(
        anonymize_with_spacy=False,
        urgency_booster_enabled=False,
        ai_analysis_anon_enabled=False,
        ai_analysis_original_enabled=False
    )
    assert account.effective_ai_mode == "none"

def test_effective_mode_spacy_booster():
    """Urgency Booster überschreibt alles"""
    account = create_account(
        urgency_booster_enabled=True,
        ai_analysis_original_enabled=True  # Wird ignoriert!
    )
    assert account.effective_ai_mode == "spacy_booster"

def test_effective_mode_llm_original():
    """LLM Original wenn kein Urgency"""
    account = create_account(
        urgency_booster_enabled=False,
        ai_analysis_original_enabled=True
    )
    assert account.effective_ai_mode == "llm_original"

def test_effective_mode_llm_anon_requires_anonymization():
    """LLM Anon benötigt Anonymisierung"""
    account = create_account(
        anonymize_with_spacy=False,
        ai_analysis_anon_enabled=True  # Alleine nicht genug!
    )
    assert account.effective_ai_mode != "llm_anon"  # Fällt zurück
    
    account.anonymize_with_spacy = True
    assert account.effective_ai_mode == "llm_anon"  # Jetzt OK
```

**Checklist Phase 2:**

- [ ] Migration für neue Toggle-Spalten
- [ ] `effective_ai_mode` Property in MailAccount
- [ ] Fetch-Logik nutzt `effective_ai_mode`
- [ ] UI mit Radio-Buttons (gegenseitig exklusiv)
- [ ] Settings-POST speichert Modi korrekt
- [ ] Anonymisierungs-Abhängigkeit erzwungen
- [ ] Tests für alle Modi-Kombinationen
- [ ] Legacy `enable_ai_analysis_on_fetch` kompatibel

**Geschätzter Aufwand Phase 2:** 4-6 Stunden

---

## Phase 3: Anonymisierung implementieren

**Verweis:** Siehe `/doc/offen/PHASE_18_COMPLETE_V2_FINAL.md`

### 3.1 Was muss angepasst werden?

Phase 18 ist bereits gut dokumentiert, aber muss an neue Toggle-Struktur angepasst werden:

#### Änderungen in PHASE_18:

1. **Conditional Anonymization:**
   ```python
   # Nur anonymisieren wenn Toggle 1️⃣ AN
   if account.anonymize_with_spacy:
       sanitized = sanitizer.sanitize(subject, body, ner_mode=account.ner_mode)
       raw_email.encrypted_subject_sanitized = encrypt(sanitized['subject'])
       raw_email.encrypted_body_sanitized = encrypt(sanitized['body'])
   ```

2. **Content Router erweitern:**
   ```python
   def get_content_for_analysis(account, raw_email):
       """
       Entscheidet welche Content-Version an LLM gesendet wird.
       """
       mode = account.effective_ai_mode
       
       if mode == "llm_anon":
           # Anonymisierte Version (falls vorhanden)
           if raw_email.encrypted_subject_sanitized:
               return {
                   'subject': decrypt(raw_email.encrypted_subject_sanitized),
                   'body': decrypt(raw_email.encrypted_body_sanitized),
                   'source': 'anonymized'
               }
           else:
               # Fallback auf Original (on-the-fly anonymisierung)
               logger.warning("Anon requested but not available, using on-the-fly")
               orig = get_original_content(raw_email)
               sanitized = sanitizer.sanitize(orig['subject'], orig['body'])
               return {**sanitized, 'source': 'on-the-fly-anon'}
       
       elif mode in ["llm_original", "spacy_booster"]:
           # Original-Version
           return {
               'subject': decrypt(raw_email.encrypted_subject),
               'body': decrypt(raw_email.encrypted_body),
               'source': 'original'
           }
   ```

3. **UI: "Anonym"-Tab nur zeigen wenn aktiviert:**
   ```html
   {% if email.encrypted_subject_sanitized and account.anonymize_with_spacy %}
   <li class="nav-item">
       <a class="nav-link" data-bs-toggle="tab" href="#tab-anon">
           🛡️ Anonym
       </a>
   </li>
   {% endif %}
   ```

### 3.2 Anpassungen an PHASE_18 Dokument

**Neue Sektion einfügen nach "Phase 5: Fetch-Pipeline":**

```markdown
### 5.5 Integration mit Analysis Modes (Phase Y)

**Conditional Anonymization basierend auf Toggle:**

```python
# In fetch_emails() oder process_email():

# 1. Prüfe ob Anonymisierung aktiviert
if account.anonymize_with_spacy:
    logger.info("🛡️ Anonymisierung aktiv, erstelle pseudonymisierte Version")
    
    # Sanitizer laden
    sanitizer = ContentSanitizer(
        ner_mode=user.ner_mode,
        db_session=session
    )
    
    # Anonymisieren
    result = sanitizer.sanitize(
        subject=decrypted_subject,
        body=decrypted_body
    )
    
    # Speichern
    raw_email.encrypted_subject_sanitized = encrypt(result['subject_sanitized'])
    raw_email.encrypted_body_sanitized = encrypt(result['body_sanitized'])
    raw_email.sanitization_level = result['level']
    raw_email.sanitization_ner_mode = result['ner_mode']
    raw_email.sanitization_time_ms = result['processing_time_ms']
else:
    logger.debug("⏭️  Anonymisierung deaktiviert, überspringe")

# 2. Wähle Content für AI-Analyse
if account.effective_ai_mode == "llm_anon":
    # Nutze anonymisierte Version
    analysis_subject = decrypt(raw_email.encrypted_subject_sanitized)
    analysis_body = decrypt(raw_email.encrypted_body_sanitized)
    analysis_source = "anonymized"
elif account.effective_ai_mode in ["llm_original", "spacy_booster"]:
    # Nutze Original
    analysis_subject = decrypted_subject
    analysis_body = decrypted_body
    analysis_source = "original"
else:
    # Keine Analyse
    analysis_subject = None
    analysis_body = None
```
```

**Checklist Phase 3:**

- [ ] PHASE_18 Konzept vollständig durchgearbeitet
- [ ] Conditional Anonymization eingebaut
- [ ] Content Router nutzt `effective_ai_mode`
- [ ] UI zeigt "Anonym"-Tab nur wenn relevant
- [ ] Performance-Tests (Batch-Processing)
- [ ] End-to-End Test: Fetch → Anon → LLM-Analysis
- [ ] Dokumentation: PHASE_18 + PHASE_Y vereint

**Geschätzter Aufwand Phase 3:** Siehe PHASE_18 (~3-4 Stunden)

---

## 📊 Gesamt-Übersicht

| Phase | Features | Aufwand | Abhängigkeiten |
|-------|----------|---------|----------------|
| **Phase 1** | Status quo fixen<br>• Transparenz (Initial Analyse)<br>• UI-Warnungen<br>• Dokumentation | 3-4h | Keine |
| **Phase 2** | Toggle-Logik<br>• 4 Toggles strukturiert<br>• Hierarchie erzwungen<br>• Radio-Button UI | 4-6h | Phase 1 ✓ |
| **Phase 3** | Anonymisierung<br>• Spacy NER<br>• Doppelte Speicherung<br>• Content Router | 3-4h | Phase 2 ✓<br>PHASE_18 Konzept |

**Gesamt:** ~10-14 Stunden

---

## 🎯 Prioritäten-Empfehlung

### Option A: Inkrementell (empfohlen)
```
Woche 1: Phase 1 (Fix Status Quo)
  → Nutzer verstehen System
  → Keine neuen Bugs

Woche 2: Phase 2 (Toggle-Struktur)
  → Vorbereitung für Zukunft
  → Klarere Modi-Auswahl

Woche 3: Phase 3 (Anonymisierung)
  → Datenschutz-Feature
  → Cloud-LLM sicher nutzbar
```

### Option B: Minimal (nur Phase 1)
```
Phase 1 implementieren
  → Problem ist gelöst (Transparenz)
  → Phase 2 & 3 optional für später
```

### Option C: All-in (alle 3 Phasen)
```
1 Sprint (2-3 Wochen)
  → Komplettes Feature-Set
  → Höheres Risiko
```

---

## 🚧 Offene Fragen

1. **Whitelist vs. Account-Settings:**
   - Aktuell: `use_urgency_booster` pro Trusted Sender
   - Neu: `urgency_booster_enabled` global im Account
   - Frage: Soll Whitelist global override bekommen?

2. **Legacy-Felder:**
   - `enable_ai_analysis_on_fetch` deprecaten oder entfernen?
   - Migration für bestehende Setups nötig?

3. **Base-Model Auswahl:**
   - Aktuell: Ein Base-Model für alle Modi
   - Zukunft: Separates Model für Anon-Analyse?

---

## 📝 Nächste Schritte

1. **Entscheidung:** Welche Phasen umsetzen? (A, B, oder C)
2. **Review:** Dieses Konzept durchgehen, Feedback geben
3. **Implementierung:** Mit gewählter Phase starten
4. **Testing:** Jede Phase einzeln testen vor nächster
5. **Dokumentation:** User-Guide aktualisieren

---

**Autor:** GitHub Copilot  
**Review:** [Offen]  
**Approval:** [Pending]
