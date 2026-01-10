# Provider/Modell-Auswahl für Reply-Generierung - Machbarkeits-Analyse

## Status: ✅ MACHBAR

---

## Problem

Aktuell nutzt Reply-Generator automatisch:
```python
provider = (user.preferred_ai_provider_optimize or user.preferred_ai_provider or "ollama").lower()
optimize_model = user.preferred_ai_model_optimize or user.preferred_ai_model
```

**Wunsch:** Vor Reply-Generierung Provider + Modell im UI auswählen können.

---

## Lösung - 2 Varianten

### ✅ **Variante A: Dropdown im Modal (EMPFOHLEN)**

**UI-Flow:**
1. User klickt "Antwort-Entwurf generieren"
2. Modal öffnet sich MIT:
   - Provider-Dropdown (Ollama, OpenAI, Anthropic, etc.)
   - Modell-Dropdown (dynamisch basierend auf Provider)
   - Ton-Buttons (wie bisher)
3. User wählt Provider + Modell + Ton
4. Generierung startet

**Vorteile:**
- ✅ Keine neue Seite nötig
- ✅ Schneller Workflow
- ✅ Nutzt vorhandene Modal-Struktur

**Aufwand:** ~30-45 Min

---

### Variante B: Settings-Override (ALTERNATIV)

**UI-Flow:**
1. User setzt in Settings "Reply-Generator bevorzugter Provider/Modell"
2. Bei Reply-Generierung: Nutze diese Settings
3. Fallback auf `preferred_ai_provider_optimize`

**Vorteile:**
- ✅ Sehr einfach zu implementieren
- ✅ Nur Backend-Änderung

**Nachteil:**
- ❌ Nicht flexibel pro E-Mail

**Aufwand:** ~15-20 Min

---

## Implementierung Variante A (Empfohlen)

### 1. Backend-Änderung

**Datei:** `src/01_web_app.py`

```python
@app.route("/api/emails/<int:email_id>/generate-reply", methods=["POST"])
@login_required
def api_generate_reply(email_id):
    # ...
    
    # Parse request body
    data = request.get_json() or {}
    tone = data.get("tone", "formal")
    
    # 🆕 NEU: Provider/Modell aus Request (optional)
    requested_provider = data.get("provider")  # Optional vom Frontend
    requested_model = data.get("model")        # Optional vom Frontend
    
    # Provider/Modell Selection
    if requested_provider and requested_model:
        # User hat explizit gewählt
        provider = requested_provider.lower()
        resolved_model = ai_client.resolve_model(provider, requested_model, kind="optimize")
        logger.info(f"🎯 User-selected Reply-Generator: {provider}/{resolved_model}")
    else:
        # Fallback: Settings
        provider = (user.preferred_ai_provider_optimize or user.preferred_ai_provider or "ollama").lower()
        optimize_model = user.preferred_ai_model_optimize or user.preferred_ai_model
        resolved_model = ai_client.resolve_model(provider, optimize_model, kind="optimize")
        logger.info(f"🤖 Default Reply-Generator: {provider}/{resolved_model}")
    
    client = ai_client.build_client(provider, model=resolved_model)
    # ... rest bleibt gleich
```

### 2. Frontend-Änderung

**Datei:** `templates/email_detail.html`

```html
<!-- Reply Draft Modal - ADD Provider/Model Selection -->
<div class="modal-body">
    
    <!-- 🆕 NEU: Provider/Model Selection -->
    <div class="mb-4 border-bottom pb-3">
        <h6 class="mb-3">🤖 KI-Modell</h6>
        <div class="row">
            <div class="col-md-6">
                <label class="form-label small text-muted">Provider</label>
                <select class="form-select form-select-sm" id="replyProvider">
                    <!-- Dynamisch gefüllt via JS -->
                </select>
            </div>
            <div class="col-md-6">
                <label class="form-label small text-muted">Modell</label>
                <select class="form-select form-select-sm" id="replyModel">
                    <!-- Dynamisch gefüllt via JS -->
                </select>
            </div>
        </div>
        <small class="text-muted">
            💡 Leer lassen = Standard aus Settings verwenden
        </small>
    </div>
    
    <!-- Bestehende Ton-Auswahl -->
    <h6 class="mb-3">🎭 Ton</h6>
    <!-- ... Ton-Buttons wie bisher ... -->
</div>
```

**JavaScript:**

```javascript
// Load available providers & models
async function loadProviderModels() {
    try {
        const response = await fetch('/api/ai-providers', {
            credentials: 'include'
        });
        const data = await response.json();
        
        if (data.success) {
            populateProviderDropdown(data.providers);
        }
    } catch (err) {
        console.error('Failed to load providers:', err);
    }
}

function populateProviderDropdown(providers) {
    const select = document.getElementById('replyProvider');
    select.innerHTML = '<option value="">🔧 Standard (aus Settings)</option>';
    
    providers.forEach(p => {
        const option = document.createElement('option');
        option.value = p.name.toLowerCase();
        option.textContent = `${p.icon} ${p.name}`;
        select.appendChild(option);
    });
}

// Update model dropdown when provider changes
document.getElementById('replyProvider').addEventListener('change', async function() {
    const provider = this.value;
    if (!provider) {
        document.getElementById('replyModel').innerHTML = 
            '<option value="">Standard</option>';
        return;
    }
    
    // Load models for selected provider
    try {
        const response = await fetch(`/api/ai-providers/${provider}/models`, {
            credentials: 'include'
        });
        const data = await response.json();
        
        const modelSelect = document.getElementById('replyModel');
        modelSelect.innerHTML = '<option value="">Bitte wählen</option>';
        
        data.models.forEach(m => {
            const option = document.createElement('option');
            option.value = m.name;
            option.textContent = m.display_name || m.name;
            modelSelect.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load models:', err);
    }
});

// Modified generateReply function
async function generateReply(tone) {
    // ...
    
    const provider = document.getElementById('replyProvider').value;
    const model = document.getElementById('replyModel').value;
    
    const requestBody = { tone: tone };
    
    // Add provider/model if selected
    if (provider && model) {
        requestBody.provider = provider;
        requestBody.model = model;
    }
    
    const response = await fetch(`/api/emails/${emailId}/generate-reply`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken()
        },
        credentials: 'include',
        body: JSON.stringify(requestBody)  // 🆕 Mit provider/model
    });
    
    // ... rest bleibt gleich
}

// Load providers when modal opens
document.getElementById('replyDraftModal').addEventListener('shown.bs.modal', function() {
    loadProviderModels();
    // ... rest bleibt gleich
});
```

---

## API-Endpoint für Provider/Models

**Brauchen wir:** `/api/ai-providers` und `/api/ai-providers/<provider>/models`

**Prüfe ob schon vorhanden:**

```bash
grep -r "api/ai-providers" src/
```

Falls nicht vorhanden → Nutze bestehende Settings-API oder erstelle minimal:

```python
@app.route("/api/ai-providers", methods=["GET"])
@login_required
def api_get_ai_providers():
    """Liste verfügbare AI-Provider"""
    providers = [
        {"name": "ollama", "icon": "🦙", "enabled": True},
        {"name": "openai", "icon": "🤖", "enabled": True},
        {"name": "anthropic", "icon": "🧠", "enabled": True},
    ]
    return jsonify({"success": True, "providers": providers})

@app.route("/api/ai-providers/<provider>/models", methods=["GET"])
@login_required
def api_get_provider_models(provider):
    """Liste Modelle für Provider"""
    # Nutze ai_client.list_models()
    try:
        models = ai_client.list_models(provider)
        return jsonify({"success": True, "models": models})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

---

## Zeitaufwand

| Task | Aufwand |
|------|---------|
| Backend: Request-Parameter erweitern | 5 Min |
| Frontend: Dropdowns hinzufügen | 15 Min |
| JavaScript: Provider/Model Loading | 15 Min |
| API-Endpoints (falls nicht vorhanden) | 10 Min |
| Testing | 10 Min |
| **TOTAL** | **~45 Min** |

---

## Soll ich implementieren?

**JA → Ich mache Variante A komplett**  
**NEIN → Dokumentation reicht als Anleitung**

Was möchtest du?
