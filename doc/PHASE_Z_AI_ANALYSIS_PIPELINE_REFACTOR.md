# PHASE Z: AI-Analysis Pipeline Refactor & Anonymization Integration

**Status**: Concept (Ready for Implementation)  
**Date**: 2026-01-08  
**Severity**: HIGH (Architecture Clarification)  
**Depends On**: PHASE 18 (Anonymization ready-to-use)

---

## Executive Summary

**Problem**: Current architecture has **mutual exclusivity issues**:
- `enable_ai_analysis_on_fetch` + `urgency_booster_enabled` conflict
- Base-Model from Settings is ignored during Fetch
- No visibility which analysis method was used (provider/model in details is blank)
- Cannot perform 2-step pipeline: Anonymize → CloudAI Analyze

**Solution**: 3-Phase refactor to clarify the mutual-exclusive toggle hierarchy and prepare anonymization pipeline.

---

## Current State (Broken)

```
Settings:
  ├─ Base-Model: "claude-opus"        ← IGNORED on Fetch!
  └─ Optimize-Model: "claude-sonnet"

Whitelist:
  ├─ enable_ai_analysis_on_fetch: True
  └─ urgency_booster_enabled: True    ← Conflict! Both active?

Processing:
  ├─ If urgency_booster_enabled=True → Phase Y (spaCy)
  ├─ Fallback to LLM (NOT the Base-Model!)
  └─ actual_provider/actual_model = NULL (not logged)

Email Details:
  └─ "🤖 Initial Analyse:" [blank]    ← No transparency
```

---

## Desired State (After Phase Z)

```
Whitelist (MUTUALLY EXCLUSIVE):
  
  ├─ [✓] Urgency Booster aktiviert
  │   ├─ [✓] spaCy-Anonymisieren (optional pre-processing)
  │   └─ ❌ AI-Analyse Toggles DISABLED
  │
  └─ [ ] Urgency Booster deaktiviert
      ├─ [✓] spaCy-Anonymisieren (optional pre-processing)
      ├─ [ ] AI-Analyse beim Abruf aktiviert
      │   ├─ Nutzt Base-Model: [claude-opus] ← FROM SETTINGS!
      │   └─ [✓] Mit Anonymisierung
      │       └─ Sends anonymized data to CloudAI
      └─ [ ] AI-Analyse beim Abruf deaktiviert
          └─ Emails nur verschlüsselt gespeichert (kein Fetch-Analysis)

Email Details:
  └─ "🤖 Initial Analyse: [SpaCy-UrgencyBooster] | Confidence: 0.78"
     "🤖 Initial Analyse: [Claude-Opus + spaCy-Anonym] | Model: claude-opus"
```

---

# IMPLEMENTATION PLAN (3 PHASES)

---

## PHASE 1: Fix Current Situation & Transparency

**Goal**: Make current behavior transparent + fix Base-Model during Fetch  
**Effort**: 4-6 hours  
**Files Changed**: 5-7

### 1.1 Add spaCy-Anonymisierung Toggle (Schema)

**File**: `src/02_models.py` (MailAccount table)

Add column:
```python
class MailAccount(Base):
    # ... existing
    enable_spacy_anonymization = Column(Boolean, default=False, nullable=False)
    # "Spacy-Anonymisieren" in Whitelist (pre-processing, independent of AI)
```

Migration: `migrations/versions/phase_z_001_add_anonymization_toggle.py`

### 1.2 Define Analysis Method Enum

**File**: `src/02_models.py` (new)

```python
class AnalysisMethod(str, Enum):
    """Which analysis method was used in initial fetch"""
    SPACY_URGENCY_BOOSTER = "spacy_urgency_booster"
    LLM_BASE_MODEL = "llm_base_model"
    LLM_BASE_ANONYMIZED = "llm_base_anonymized"
    NONE = "none"
```

Add to RawEmail:
```python
class RawEmail(Base):
    # ... existing
    analysis_method = Column(String(50), default="none", nullable=False)
    analysis_provider = Column(String(100), nullable=True)  # "ollama", "claude", etc.
    analysis_model = Column(String(100), nullable=True)      # "de_core_news_sm", "claude-opus"
    analysis_confidence = Column(Float, nullable=True)       # 0.0-1.0
```

### 1.3 Fix Base-Model Usage in Fetch

**File**: `src/14_background_jobs.py` → `_execute_fetch_job()`

Currently: Ignores Base-Model from account settings.

**Change**:
```python
def _execute_fetch_job(self, job: FetchJob, session):
    # ... existing
    
    # 🔄 PHASE Z: Load Base-Model from account settings
    account = session.query(models_mod.MailAccount).get(job.account_id)
    
    # Get Base-Model preference
    ai_provider = account.ai_provider or "ollama"
    ai_model = account.ai_model_base or "all-minilm:22m"
    
    # Pass to processing
    ProcessingEngine.process_raw_email(
        raw_email=raw_email,
        master_key=dek,
        ai_provider=ai_provider,        # ← NEW: From settings
        ai_model=ai_model,              # ← NEW: From settings
        ...
    )
```

### 1.4 Log Analysis Method & Transparency

**File**: `src/12_processing.py` → `process_raw_email()`

**Change** (after line 490-500):
```python
# Phase Z: Track which analysis method was used
if ai_result:
    analysis_method = AnalysisMethod.NONE
    analysis_provider = None
    analysis_model = None
    analysis_confidence = ai_result.get("_confidence", 0.0)
    
    if ai_result.get("_used_booster"):
        analysis_method = AnalysisMethod.SPACY_URGENCY_BOOSTER
        analysis_provider = "spacy"
        analysis_model = "de_core_news_sm"
    elif ai_result.get("_used_anonymized"):  # NEW: flag from anonymization
        analysis_method = AnalysisMethod.LLM_BASE_ANONYMIZED
        analysis_provider = ai_provider
        analysis_model = ai_model
    else:
        analysis_method = AnalysisMethod.LLM_BASE_MODEL
        analysis_provider = ai_provider
        analysis_model = ai_model
    
    # Store in email
    raw_email.analysis_method = analysis_method
    raw_email.analysis_provider = analysis_provider
    raw_email.analysis_model = analysis_model
    raw_email.analysis_confidence = analysis_confidence
```

### 1.5 Display in Email Details

**File**: `templates/email_detail.html`

**Change** (in section "🤖 Initial Analyse"):
```html
{% if email.analysis_method and email.analysis_method != 'none' %}
<div class="alert alert-info">
    <strong>🤖 Initial Analyse:</strong>
    {{ email.analysis_method | replace('_', ' ') | title }}
    {% if email.analysis_provider %}
        <br>
        <small class="text-muted">
            Provider: <code>{{ email.analysis_provider }}</code> | 
            Model: <code>{{ email.analysis_model }}</code>
            {% if email.analysis_confidence %}
                | Confidence: {{ "%.2f" | format(email.analysis_confidence) }}
            {% endif %}
        </small>
    {% endif %}
</div>
{% endif %}
```

### 1.6 Update Processing to Use Base-Model

**File**: `src/03_ai_client.py` → `LocalOllamaClient._analyze_with_chat()`

**Current** (line 1114-1128): Always calls `self.model` (from queue)

**Change**:
```python
def _analyze_with_chat(self, subject, body, sender="", ...):
    # Phase Z: Try spaCy first
    if sender and user_id and db and user_enabled_booster and account_id:
        # ... Phase Y logic (unchanged)
        pass
    
    # Fallback: Use the passed ai_provider & ai_model (from account settings)
    messages = _build_standard_messages(subject, body, language, context)
    
    # Use provided provider/model instead of self.model
    response = requests.post(
        self.chat_url,  # This should point to correct provider
        json={"model": ai_model, ...}  # ← Use parameter, not self.model
    )
```

---

## PHASE 2: Toggle Logic & Mutual Exclusivity

**Goal**: Prepare toggle logic for UI (whitelist) + fetch preparation  
**Effort**: 3-4 hours  
**Files Changed**: 3-4

### 2.1 Add Toggle Logic Helper

**File**: `src/services/account_settings_manager.py` (new)

```python
class AccountSettingsManager:
    """
    Manages mutually exclusive toggles for Account analysis pipeline.
    
    Rules:
    - If urgency_booster_enabled=True → AI toggles DISABLED (spaCy only)
    - If urgency_booster_enabled=False → AI toggles AVAILABLE
    - enable_spacy_anonymization can be True in either case
    """
    
    @staticmethod
    def get_effective_settings(account_id: int, session) -> dict:
        """Returns resolved settings with mutual exclusivity applied"""
        account = session.query(MailAccount).get(account_id)
        
        return {
            "urgency_booster_enabled": account.urgency_booster_enabled,
            "enable_spacy_anonymization": account.enable_spacy_anonymization,
            
            # These only apply if urgency_booster=False
            "enable_ai_analysis_on_fetch": (
                account.enable_ai_analysis_on_fetch 
                if not account.urgency_booster_enabled else False
            ),
            
            # Analysis method (read-only, computed)
            "active_analysis_method": (
                "spacy_urgency_booster" if account.urgency_booster_enabled 
                else "llm_base" if account.enable_ai_analysis_on_fetch
                else "none"
            ),
        }
    
    @staticmethod
    def validate_settings(urgency_booster: bool, ai_analysis: bool):
        """Validates that settings don't conflict"""
        if urgency_booster and ai_analysis:
            logger.warning("Cannot enable both UrgencyBooster and AI-Analysis; disabling AI-Analysis")
            return (True, False)  # (urgency_booster, ai_analysis) resolved
        return (urgency_booster, ai_analysis)
```

### 2.2 Update Whitelist API Endpoint

**File**: `src/01_web_app.py` → `/settings/mail-account/<id>/update-settings`

**Change** (around line 8533):
```python
@app.route("/settings/mail-account/<int:account_id>/update-settings", methods=["POST"])
def update_account_settings(account_id):
    data = request.get_json()
    urgency_booster = bool(data.get("urgency_booster_enabled", True))
    ai_analysis = bool(data.get("enable_ai_analysis_on_fetch", True))
    spacy_anon = bool(data.get("enable_spacy_anonymization", False))
    
    # Phase Z: Apply mutual exclusivity
    from src.services.account_settings_manager import AccountSettingsManager
    urgency_booster, ai_analysis = AccountSettingsManager.validate_settings(
        urgency_booster, ai_analysis
    )
    
    account.urgency_booster_enabled = urgency_booster
    account.enable_ai_analysis_on_fetch = ai_analysis  # Will be False if booster=True
    account.enable_spacy_anonymization = spacy_anon
    
    db.commit()
    
    return {
        "success": True,
        "urgency_booster_enabled": account.urgency_booster_enabled,
        "enable_ai_analysis_on_fetch": account.enable_ai_analysis_on_fetch,
        "enable_spacy_anonymization": account.enable_spacy_anonymization,
    }
```

### 2.3 Update Whitelist UI (Template)

**File**: `templates/whitelist.html` (or `/settings`)

**Change** (new structure):
```html
<!-- Phase Z: Mutually Exclusive Analysis Pipeline -->
<div class="card">
    <div class="card-header">
        <h5>🔄 Email-Analyse Pipeline</h5>
    </div>
    <div class="card-body">
        
        <!-- Shared: Anonymization (works with both) -->
        <div class="form-check mb-3">
            <input class="form-check-input" type="checkbox" 
                   id="spacy_anon" name="enable_spacy_anonymization"
                   value="true" {% if account.enable_spacy_anonymization %}checked{% endif %}>
            <label class="form-check-label" for="spacy_anon">
                <strong>🔐 spaCy-Anonymisierung</strong>
                <br>
                <small class="text-muted">
                    Entfernt/ersetzt Namen, Firmen, Orte, Kontaktdaten 
                    (zusätzliche Vorverarbeitung, immer angewendet wenn aktiviert)
                </small>
            </label>
        </div>

        <hr>
        
        <!-- Phase Z: Mutually Exclusive Selection -->
        <fieldset class="border p-3">
            <legend class="h6">Analyse-Methode (wähle eine):</legend>
            
            <!-- Option 1: Urgency Booster -->
            <div class="form-check mb-3">
                <input class="form-check-input analysis-radio" type="radio"
                       name="analysis_method" value="urgency_booster"
                       id="booster_radio"
                       {% if account.urgency_booster_enabled and not account.enable_ai_analysis_on_fetch %}checked{% endif %}>
                <label class="form-check-label" for="booster_radio">
                    <strong>⚡ UrgencyBooster (spaCy)</strong>
                    <br>
                    <small class="text-muted">
                        Nutzt spaCy NLP + {{ keyword_set_count }} KeywordSets + VIP-Liste
                        (schnell, CPU-only, kein LLM)
                    </small>
                </label>
            </div>
            
            <!-- Option 2: AI-Analyse -->
            <div class="form-check mb-3">
                <input class="form-check-input analysis-radio" type="radio"
                       name="analysis_method" value="ai_analysis"
                       id="ai_radio"
                       {% if account.enable_ai_analysis_on_fetch and not account.urgency_booster_enabled %}checked{% endif %}>
                <label class="form-check-label" for="ai_radio">
                    <strong>🤖 AI-Analyse beim Abruf</strong>
                    <br>
                    <small class="text-muted">
                        Nutzt Base-Model aus Settings: 
                        <code>{{ account.ai_provider }}: {{ account.ai_model_base }}</code>
                    </small>
                </label>
                
                <!-- Sub-option: Anonymize before sending to Cloud AI -->
                <div class="ms-4 mt-2 {% if not (account.enable_ai_analysis_on_fetch and not account.urgency_booster_enabled) %}d-none{% endif %}"
                     id="ai_anon_option">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox"
                               id="ai_with_anon" name="ai_with_anonymization"
                               value="true"
                               {% if account.enable_ai_analysis_on_fetch and account.enable_spacy_anonymization %}checked{% endif %}>
                        <label class="form-check-label" for="ai_with_anon">
                            <small>✓ Anonymisieren vor Cloud-AI</small>
                        </label>
                    </div>
                </div>
            </div>
            
            <!-- Option 3: Disabled -->
            <div class="form-check">
                <input class="form-check-input analysis-radio" type="radio"
                       name="analysis_method" value="none"
                       id="none_radio"
                       {% if not account.urgency_booster_enabled and not account.enable_ai_analysis_on_fetch %}checked{% endif %}>
                <label class="form-check-label" for="none_radio">
                    <strong>⊘ Keine Analyse</strong>
                    <br>
                    <small class="text-muted">Nur Verschlüsselung, keine AI-Analyse beim Abruf</small>
                </label>
            </div>
        </fieldset>

        <button class="btn btn-primary mt-3" onclick="savePipelineSettings()">
            💾 Speichern
        </button>
    </div>
</div>

<script>
function savePipelineSettings() {
    const method = document.querySelector('input[name="analysis_method"]:checked').value;
    const spacy_anon = document.getElementById('spacy_anon').checked;
    
    const payload = {
        enable_spacy_anonymization: spacy_anon,
    };
    
    if (method === 'urgency_booster') {
        payload.urgency_booster_enabled = true;
        payload.enable_ai_analysis_on_fetch = false;
    } else if (method === 'ai_analysis') {
        payload.urgency_booster_enabled = false;
        payload.enable_ai_analysis_on_fetch = true;
    } else {
        payload.urgency_booster_enabled = false;
        payload.enable_ai_analysis_on_fetch = false;
    }
    
    fetch(`/settings/mail-account/{{ account.id }}/update-settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    }).then(r => r.json()).then(d => {
        if (d.success) {
            alert('✅ Einstellungen gespeichert');
            location.reload();
        }
    });
}

// Show/hide AI anonymization option based on radio selection
document.querySelectorAll('input[name="analysis_method"]').forEach(r => {
    r.addEventListener('change', () => {
        document.getElementById('ai_anon_option').classList.toggle(
            'd-none', 
            r.value !== 'ai_analysis'
        );
    });
});
</script>
```

### 2.4 Prepare Fetch Pipeline for Anonymization

**File**: `src/14_background_jobs.py` → `_execute_fetch_job()`

Add pre-processing hook (not calling anonymization yet, just infrastructure):

```python
def _execute_fetch_job(self, job: FetchJob, session):
    # ... existing
    
    # Phase Z: Prepare anonymization pipeline (structure, not yet implemented)
    account = session.query(models_mod.MailAccount).get(job.account_id)
    
    processing_config = {
        "apply_anonymization": account.enable_spacy_anonymization,
        "anonymization_mode": "pseudonymize",  # or "anonymize"
        "analysis_method": self._get_analysis_method(account),
    }
    
    for raw_email in raw_emails:
        ProcessingEngine.process_raw_email(
            raw_email=raw_email,
            master_key=dek,
            processing_config=processing_config,
            ...
        )
```

---

## PHASE 3: Anonymization Integration (Use PHASE_18)

**Goal**: Integrate real anonymization from PHASE_18 into fetch pipeline  
**Effort**: 6-8 hours  
**Files Changed**: 4-5  
**Depends On**: PHASE_18_COMPLETE_V2_FINAL.md

### 3.1 Setup Phase 18 (if not done)

**Reference**: `doc/offen/PHASE_18_COMPLETE_V2_FINAL.md`

Ensure dependencies installed:
```bash
pip install spacy>=3.7.0
python -m spacy download de_core_news_sm
```

### 3.2 Create Anonymization Service Layer

**File**: `src/services/anonymization.py` (new, simplified wrapper around Phase 18)

```python
class EmailAnonymizer:
    """Wraps Phase 18 anonymization for use in fetch pipeline"""
    
    NER_MODE = "spacy"  # From Phase 18 settings
    
    @staticmethod
    def anonymize_email(subject: str, body: str, mode: str = "pseudonymize") -> tuple:
        """
        Anonymizes email using spaCy NER.
        
        Args:
            subject: Email subject
            body: Email body (plain text)
            mode: "pseudonymize" (replace with placeholders) or "anonymize" (remove entirely)
        
        Returns:
            (anonymized_subject, anonymized_body, entities_found: dict)
        """
        from src.services.phase_18_ner import Phase18NEREngine  # Import Phase 18
        
        engine = Phase18NEREngine(mode=EmailAnonymizer.NER_MODE)
        
        # Process subject
        anon_subject, subj_entities = engine.process_text(subject, mode)
        
        # Process body (with batching for performance)
        anon_body, body_entities = engine.process_text(body, mode)
        
        # Merge entity findings
        all_entities = {
            "PER": subj_entities.get("PER", []) + body_entities.get("PER", []),
            "ORG": subj_entities.get("ORG", []) + body_entities.get("ORG", []),
            "GPE": subj_entities.get("GPE", []) + body_entities.get("GPE", []),
            "MISC": subj_entities.get("MISC", []) + body_entities.get("MISC", []),
        }
        
        logger.info(f"✅ Email anonymized: {len(all_entities['PER'])} persons, "
                   f"{len(all_entities['ORG'])} orgs, {len(all_entities['GPE'])} locations")
        
        return (anon_subject, anon_body, all_entities)
```

### 3.2 Update RawEmail Schema for Anonymized Content

**File**: `src/02_models.py`

```python
class RawEmail(Base):
    # ... existing
    
    # Phase Z/18: Anonymized content (stored encrypted)
    encrypted_subject_anonymized = Column(Text, nullable=True)
    encrypted_body_anonymized = Column(Text, nullable=True)
    anonymization_metadata = Column(JSON, nullable=True)  # Which entities were found/replaced
```

Migration: `migrations/versions/phase_z_002_add_anonymized_storage.py`

### 3.3 Update Processing to Store Both Versions

**File**: `src/12_processing.py` → `process_raw_email()`

```python
def process_raw_email(raw_email, master_key, processing_config, ...):
    # ... existing decryption
    decrypted_subject = EmailDataManager.decrypt_email_subject(...)
    decrypted_body = EmailDataManager.decrypt_email_body(...)
    
    # Phase Z: Apply anonymization (optional)
    anon_subject = decrypted_subject
    anon_body = decrypted_body
    anon_metadata = None
    
    if processing_config.get("apply_anonymization"):
        from src.services.anonymization import EmailAnonymizer
        anon_subject, anon_body, anon_metadata = EmailAnonymizer.anonymize_email(
            decrypted_subject, decrypted_body, 
            mode=processing_config.get("anonymization_mode", "pseudonymize")
        )
        
        # Store anonymized versions (encrypted)
        raw_email.encrypted_subject_anonymized = EmailDataManager.encrypt_email_subject(
            anon_subject, master_key
        )
        raw_email.encrypted_body_anonymized = EmailDataManager.encrypt_email_body(
            anon_body, master_key
        )
        raw_email.anonymization_metadata = anon_metadata
    
    # Phase Z: Choose analysis text based on settings
    if processing_config.get("apply_anonymization") and processing_config.get("use_anonymized_for_ai"):
        analysis_subject = anon_subject
        analysis_body = anon_body
        ai_result = active_ai.analyze_email(subject=analysis_subject, body=analysis_body, ...)
        ai_result["_used_anonymized"] = True  # Mark for logging
    else:
        ai_result = active_ai.analyze_email(subject=decrypted_subject, body=decrypted_body, ...)
    
    # ... rest unchanged
```

### 3.4 Add "Anonymized" Tab in Email Details

**File**: `templates/email_detail.html`

Add new tab (alongside HTML, RAW):
```html
<ul class="nav nav-tabs" role="tablist">
    <li class="nav-item">
        <a class="nav-link active" data-bs-toggle="tab" href="#html-tab">HTML</a>
    </li>
    <li class="nav-item">
        <a class="nav-link" data-bs-toggle="tab" href="#raw-tab">RAW</a>
    </li>
    <!-- Phase Z: New Anonymized Tab -->
    {% if email.encrypted_body_anonymized %}
    <li class="nav-item">
        <a class="nav-link" data-bs-toggle="tab" href="#anon-tab">🔐 Anonymisiert</a>
    </li>
    {% endif %}
</ul>

<div class="tab-content">
    <!-- ... existing HTML/RAW tabs ... -->
    
    <!-- Phase Z: Anonymized Tab -->
    {% if email.encrypted_body_anonymized %}
    <div id="anon-tab" class="tab-pane">
        <div class="card">
            <div class="card-header">
                <small class="text-muted">
                    Anonymisierte Version (Personen, Firmen, Orte ersetzt/gelöscht)
                    <br>
                    Entities found: 
                    {{ email.anonymization_metadata.PER | length }} PER |
                    {{ email.anonymization_metadata.ORG | length }} ORG |
                    {{ email.anonymization_metadata.GPE | length }} GPE
                </small>
            </div>
            <div class="card-body">
                <pre style="white-space: pre-wrap; word-wrap: break-word;">{{ decrypted_subject_anonymized }}

---

{{ decrypted_body_anonymized }}</pre>
            </div>
        </div>
    </div>
    {% endif %}
</div>
```

### 3.5 Update Documentation

**File**: `doc/PHASE_Z_AI_ANALYSIS_PIPELINE_REFACTOR.md` (this file)

Add section documenting Phase 18 integration and how anonymization flows through processing.

---

## Summary Table

| Phase | Deliverable | Effort | Priority |
|-------|-------------|--------|----------|
| **Phase 1** | Transparency + Base-Model Fix | 4-6h | 🔴 HIGH |
| **Phase 2** | Toggle Logic + UI | 3-4h | 🟡 MEDIUM |
| **Phase 3** | Anonymization Integration | 6-8h | 🟡 MEDIUM |
| **Total** | Full Pipeline Refactor | ~14-18h | - |

---

## Testing Checklist

### Phase 1 Tests
- [ ] Base-Model from Settings is used in Fetch (not ignored)
- [ ] Email details show analysis_method, provider, model
- [ ] Confidence score is logged and displayed
- [ ] Works with: Ollama, Claude, Mistral

### Phase 2 Tests
- [ ] Radio buttons: only one analysis method active
- [ ] urgency_booster + ai_analysis never both True
- [ ] Settings save and persist correctly
- [ ] Whitelist UI updates correctly after radio selection

### Phase 3 Tests
- [ ] Anonymized text stored correctly (encrypted)
- [ ] "Anonymisiert" tab appears only if content exists
- [ ] AI receives anonymized text when flag is True
- [ ] Original text still available (not lost)
- [ ] Performance: <50ms per email with anonymization

---

## Rollback Plan

If issues found:

**Phase 1**: 
- Keep `analysis_method`, `analysis_provider`, `analysis_model` columns (non-breaking)
- Just don't populate them if issues

**Phase 2**: 
- Toggle logic is UI-only, can disable with CSS (`d-none`)

**Phase 3**: 
- Don't populate `encrypted_subject_anonymized`, hide tabs with `{% if %}` condition

---

## Notes

- **Phase 18 Reference**: Full anonymization engine in `/doc/offen/PHASE_18_COMPLETE_V2_FINAL.md`
- **Backward Compatibility**: Original encrypted_subject/body untouched, only add anonymized versions
- **Performance**: Anonymization adds ~10-15ms per email (spaCy), batching helps
- **Visibility**: Always show which method was used in email details
