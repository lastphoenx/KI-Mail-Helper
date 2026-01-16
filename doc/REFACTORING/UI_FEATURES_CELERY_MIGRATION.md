# UI-Features Celery Migration
## Kritische Buttons in Email-Details

**Datum**: Januar 2026  
**Status**: 🔴 KRITISCH - Diese Features MÜSSEN für Multi-User async werden!  

---

## 📊 ÜBERSICHT: Buttons sind NICHT mit Celery migriert

| Button | Route | Datei + Zeilen | Status | Problem |
|--------|-------|----------------|--------|---------|
| **Basis-Lauf neu machen** | `POST /email/<id>/reprocess` | `email_actions.py:225-338` | ❌ SYNCHRON | Blockiert Request, kein UI-Progress |
| **Optimize-Lauf** | `POST /email/<id>/optimize` | `email_actions.py:344-469` | ❌ SYNCHRON | Blockiert Request, kein UI-Progress |
| **Antwort-Entwurf generieren** | `POST /emails/<id>/generate-reply` | `api.py:672` | ❌ SYNCHRON | Blockiert Request, kein UI-Progress |

---

## 🔍 PROBLEM IM DETAIL

### 1. Base-Lauf neu machen

**Aktuelle Implementierung:**
```python
# src/blueprints/email_actions.py Zeilen 225-338
@email_actions_bp.route("/email/<int:raw_email_id>/reprocess", methods=["POST"])
def reprocess_email(raw_email_id):
    """Reprocess: Base-Lauf neu generieren."""
    
    # 1. Token aus Request holen
    service_token_id = request.json.get("service_token_id")
    token = db.session.query(ServiceToken).get(service_token_id)
    
    # 2. Provider + Model auflösen
    provider = token.provider if token else "openai"
    resolved_model = token.model if token else "gpt-3.5-turbo"
    
    # 3. AI-Client DIREKT aufrufen (SYNCHRON!)
    client = ai_client.build_client(provider, model=resolved_model)
    
    # 4. Email analysieren (BLOCKIERT 5-30 SEKUNDEN!)
    result = client.analyze_email(
        subject=raw_email.subject,
        body=raw_email.body,
        sender=raw_email.sender
    )
    
    # 5. ProcessedEmail updaten
    processed = db.session.query(ProcessedEmail).filter_by(
        raw_email_id=raw_email_id
    ).first()
    
    processed.ai_score = result.get("score")
    processed.ai_reasoning = result.get("reasoning")
    processed.processed_at = datetime.utcnow()
    
    db.session.commit()
    
    # 6. Response zurückgeben (USER HAT GEWARTET!)
    return jsonify({
        "status": "success",
        "score": processed.ai_score,
        "reasoning": processed.ai_reasoning
    })
```

**Probleme:**
1. ⚠️ **Request blockiert**: User-Request wartet auf AI-Call (5-30 Sekunden)
2. ⚠️ **Kein Progress**: UI kann keinen Fortschritt anzeigen
3. ⚠️ **Timeout-Risiko**: Bei langsamen AI-Calls → 504 Gateway Timeout
4. ⚠️ **Multi-User Killer**: 5 Users klicken gleichzeitig → 5 Flask-Worker blockiert
5. ⚠️ **ServiceToken**: Token muss an Task übergeben werden (für User-spezifische AI-Keys)

---

### 2. Optimize-Lauf anstoßen

**Aktuelle Implementierung:**
```python
# src/blueprints/email_actions.py Zeilen 344-469
@email_actions_bp.route("/email/<int:raw_email_id>/optimize", methods=["POST"])
def optimize_email(raw_email_id):
    """Optimize: Mit stärkerem Modell (z.B. GPT-4) neu analysieren."""
    
    # 1. Token für Optimize-Modell
    service_token_id = request.json.get("service_token_id")
    token = db.session.query(ServiceToken).get(service_token_id)
    
    # 2. Stärkeres Modell
    provider_optimize = token.provider if token else "openai"
    resolved_model = token.model if token else "gpt-4"  # ← TEUER!
    
    # 3. AI-Client DIREKT aufrufen (SYNCHRON!)
    client = ai_client.build_client(provider_optimize, model=resolved_model)
    
    # 4. Email analysieren (BLOCKIERT 10-60 SEKUNDEN!)
    result = client.analyze_email(
        subject=raw_email.subject,
        body=raw_email.body,
        sender=raw_email.sender,
        context="optimize"  # Mehr Details
    )
    
    # 5. ProcessedEmail updaten (Optimize-Lauf)
    processed.ai_score_optimize = result.get("score")
    processed.ai_reasoning_optimize = result.get("reasoning")
    processed.optimized_at = datetime.utcnow()
    
    db.session.commit()
    
    # 6. Response (USER HAT LANGE GEWARTET!)
    return jsonify({
        "status": "success",
        "score_base": processed.ai_score,
        "score_optimize": processed.ai_score_optimize,
        "improvement": processed.ai_score_optimize - processed.ai_score
    })
```

**Probleme:**
1. ⚠️ **SEHR lange Laufzeit**: GPT-4 braucht 10-60 Sekunden
2. ⚠️ **SEHR teuer**: GPT-4 kostet 10x mehr als GPT-3.5
3. ⚠️ **Request blockiert**: Noch schlimmer als Base-Lauf
4. ⚠️ **Rate-Limits**: OpenAI limitiert GPT-4 Calls strenger
5. ⚠️ **Cost-Explosion**: Ohne Rate-Limiting → User kann Server teuer machen

---

### 3. Antwort-Entwurf generieren

**Aktuelle Implementierung:**
```python
# src/blueprints/api.py Zeile 672
@api_bp.route("/emails/<int:raw_email_id>/generate-reply", methods=["POST"])
def api_generate_reply(raw_email_id):
    """Generate Reply Draft."""
    
    # 1. Style aus Request
    style = request.json.get("style", "professional")
    
    # 2. Email laden
    raw_email = db.session.query(RawEmail).get(raw_email_id)
    
    # 3. Reply-Generator laden (SYNCHRON!)
    reply_generator_mod = importlib.import_module("src.reply_generator")
    
    # 4. Draft generieren (BLOCKIERT 3-15 SEKUNDEN!)
    draft = reply_generator_mod.generate_reply(
        subject=raw_email.subject,
        body=raw_email.body,
        sender=raw_email.sender,
        style=style,
        user_context={
            "name": current_user.name,
            "email": current_user.email,
            "preferences": current_user.reply_preferences
        }
    )
    
    # 5. Draft speichern (optional)
    draft_obj = DraftReply(
        raw_email_id=raw_email_id,
        user_id=current_user.id,
        draft_text=draft,
        style=style,
        generated_at=datetime.utcnow()
    )
    db.session.add(draft_obj)
    db.session.commit()
    
    # 6. Response
    return jsonify({
        "status": "success",
        "draft": draft
    })
```

**Probleme:**
1. ⚠️ **Häufig genutzt**: Antworten schreiben ist Kern-Feature
2. ⚠️ **3-15 Sekunden**: Blockiert UI
3. ⚠️ **Multi-User**: Viele gleichzeitige Requests
4. ⚠️ **Rate-Limits**: OpenAI Text-Generation hat Limits

---

## ✅ LÖSUNG: Celery-Tasks

### Backend: Neue Tasks erstellen

#### Task 1: Base-Lauf
```python
# src/tasks/email_processing_tasks.py
from src.celery_app import celery_app
from src.helpers.database import get_session
from src.02_models import RawEmail, ProcessedEmail, ServiceToken
import src.ai_client as ai_client

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=120,  # 2 Minuten max
    soft_time_limit=90  # 90 Sekunden warning
)
def reprocess_email_base(self, user_id: int, raw_email_id: int, service_token_id: int):
    """Task: Base-Lauf neu generieren (async)."""
    session = get_session()
    
    try:
        # 1. Ownership-Check
        raw_email = session.query(RawEmail).filter_by(
            id=raw_email_id,
            user_id=user_id
        ).first()
        
        if not raw_email:
            raise ValueError(f"Email {raw_email_id} not found or unauthorized")
        
        # 2. ServiceToken laden
        token = session.query(ServiceToken).filter_by(
            id=service_token_id,
            user_id=user_id  # ← Wichtig: User-spezifischer Token!
        ).first()
        
        if not token:
            raise ValueError(f"ServiceToken {service_token_id} not found")
        
        # 3. AI-Client aufrufen
        provider = token.provider
        model = token.model
        
        client = ai_client.build_client(provider, model=model)
        
        # Progress-Update (optional, für WebSocket)
        self.update_state(
            state='PROGRESS',
            meta={'progress': 30, 'message': 'AI-Analyse läuft...'}
        )
        
        # 4. Analyse
        result = client.analyze_email(
            subject=raw_email.subject,
            body=raw_email.body,
            sender=raw_email.sender
        )
        
        # 5. ProcessedEmail updaten
        processed = session.query(ProcessedEmail).filter_by(
            raw_email_id=raw_email_id
        ).first()
        
        if not processed:
            processed = ProcessedEmail(
                raw_email_id=raw_email_id,
                user_id=user_id
            )
            session.add(processed)
        
        processed.ai_score = result.get("score")
        processed.ai_reasoning = result.get("reasoning")
        processed.processed_at = datetime.utcnow()
        
        session.commit()
        
        # 6. Success
        return {
            "status": "success",
            "email_id": raw_email_id,
            "score": processed.ai_score,
            "reasoning": processed.ai_reasoning,
            "model_used": model
        }
        
    except Exception as exc:
        logger.error(f"Reprocess Base failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    
    finally:
        session.close()
```

#### Task 2: Optimize-Lauf
```python
# src/tasks/email_processing_tasks.py (continued)

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,  # Länger wegen GPT-4 Rate-Limits
    time_limit=180,  # 3 Minuten max (GPT-4 ist langsamer)
    soft_time_limit=150
)
def optimize_email_processing(self, user_id: int, raw_email_id: int, service_token_id: int):
    """Task: Optimize-Lauf mit stärkerem Modell (async)."""
    session = get_session()
    
    try:
        # 1. Ownership-Check
        raw_email = session.query(RawEmail).filter_by(
            id=raw_email_id,
            user_id=user_id
        ).first()
        
        if not raw_email:
            raise ValueError(f"Email {raw_email_id} not found")
        
        # 2. ServiceToken für Optimize-Modell
        token = session.query(ServiceToken).filter_by(
            id=service_token_id,
            user_id=user_id
        ).first()
        
        if not token:
            raise ValueError(f"ServiceToken {service_token_id} not found")
        
        # 3. AI-Client (stärkeres Modell)
        provider = token.provider
        model = token.model  # z.B. "gpt-4"
        
        client = ai_client.build_client(provider, model=model)
        
        # Progress
        self.update_state(
            state='PROGRESS',
            meta={'progress': 40, 'message': f'Optimize mit {model}...'}
        )
        
        # 4. Analyse (mit mehr Kontext)
        result = client.analyze_email(
            subject=raw_email.subject,
            body=raw_email.body,
            sender=raw_email.sender,
            context="optimize",  # Mehr Details
            include_suggestions=True
        )
        
        # 5. ProcessedEmail updaten
        processed = session.query(ProcessedEmail).filter_by(
            raw_email_id=raw_email_id
        ).first()
        
        if not processed:
            raise ValueError("Base-Lauf muss zuerst existieren!")
        
        processed.ai_score_optimize = result.get("score")
        processed.ai_reasoning_optimize = result.get("reasoning")
        processed.ai_suggestions = result.get("suggestions")
        processed.optimized_at = datetime.utcnow()
        
        session.commit()
        
        # 6. Success mit Vergleich
        return {
            "status": "success",
            "email_id": raw_email_id,
            "score_base": processed.ai_score,
            "score_optimize": processed.ai_score_optimize,
            "improvement": processed.ai_score_optimize - processed.ai_score,
            "suggestions": processed.ai_suggestions,
            "model_used": model
        }
        
    except Exception as exc:
        logger.error(f"Optimize failed: {exc}")
        raise self.retry(exc=exc, countdown=120 * (2 ** self.request.retries))
    
    finally:
        session.close()
```

#### Task 3: Antwort-Entwurf
```python
# src/tasks/reply_generation_tasks.py (NEU!)

from src.celery_app import celery_app
from src.helpers.database import get_session
from src.02_models import RawEmail, DraftReply
import importlib

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    time_limit=60,  # 1 Minute max
    soft_time_limit=45
)
def generate_reply_draft(self, user_id: int, raw_email_id: int, style: str = "professional"):
    """Task: Antwort-Entwurf generieren (async)."""
    session = get_session()
    
    try:
        # 1. Ownership-Check
        raw_email = session.query(RawEmail).filter_by(
            id=raw_email_id,
            user_id=user_id
        ).first()
        
        if not raw_email:
            raise ValueError(f"Email {raw_email_id} not found")
        
        # 2. User-Context laden
        from src.02_models import User
        user = session.query(User).get(user_id)
        
        user_context = {
            "name": user.name or user.username,
            "email": user.email,
            "preferences": user.reply_preferences if hasattr(user, 'reply_preferences') else {}
        }
        
        # 3. Reply-Generator laden
        reply_generator_mod = importlib.import_module("src.reply_generator")
        
        # Progress
        self.update_state(
            state='PROGRESS',
            meta={'progress': 50, 'message': 'Entwurf wird generiert...'}
        )
        
        # 4. Draft generieren
        draft = reply_generator_mod.generate_reply(
            subject=raw_email.subject,
            body=raw_email.body,
            sender=raw_email.sender,
            style=style,
            user_context=user_context
        )
        
        # 5. Draft speichern
        draft_obj = DraftReply(
            raw_email_id=raw_email_id,
            user_id=user_id,
            draft_text=draft,
            style=style,
            generated_at=datetime.utcnow()
        )
        session.add(draft_obj)
        session.commit()
        
        # 6. Success
        return {
            "status": "success",
            "email_id": raw_email_id,
            "draft": draft,
            "style": style,
            "draft_id": draft_obj.id
        }
        
    except Exception as exc:
        logger.error(f"Reply generation failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
    
    finally:
        session.close()
```

---

### Blueprint: Routes aktualisieren

```python
# src/blueprints/email_actions.py - AKTUALISIERT

from src.tasks.email_processing_tasks import reprocess_email_base, optimize_email_processing
from src.tasks.reply_generation_tasks import generate_reply_draft

# ---
# ROUTE 1: Base-Lauf (ALT: Zeilen 225-338)
# ---
@email_actions_bp.route("/email/<int:raw_email_id>/reprocess", methods=["POST"])
def reprocess_email(raw_email_id):
    """Reprocess: Base-Lauf neu generieren (ASYNC)."""
    
    # 1. Validate Input
    service_token_id = request.json.get("service_token_id")
    if not service_token_id:
        return jsonify({"error": "service_token_id required"}), 400
    
    # 2. Ownership-Check (schnell)
    raw_email = db.session.query(RawEmail).filter_by(
        id=raw_email_id,
        user_id=current_user.id
    ).first()
    
    if not raw_email:
        return jsonify({"error": "Email not found"}), 404
    
    # 3. Task starten (ASYNC!)
    task = reprocess_email_base.delay(
        user_id=current_user.id,
        raw_email_id=raw_email_id,
        service_token_id=service_token_id
    )
    
    # 4. Sofort Response (UI nicht blockiert!)
    return jsonify({
        "task_id": task.id,
        "status": "queued",
        "message": "Base-Lauf wird neu generiert..."
    })

# ---
# ROUTE 2: Optimize-Lauf (ALT: Zeilen 344-469)
# ---
@email_actions_bp.route("/email/<int:raw_email_id>/optimize", methods=["POST"])
def optimize_email(raw_email_id):
    """Optimize: Mit stärkerem Modell neu analysieren (ASYNC)."""
    
    # 1. Validate Input
    service_token_id = request.json.get("service_token_id")
    if not service_token_id:
        return jsonify({"error": "service_token_id required"}), 400
    
    # 2. Ownership-Check
    raw_email = db.session.query(RawEmail).filter_by(
        id=raw_email_id,
        user_id=current_user.id
    ).first()
    
    if not raw_email:
        return jsonify({"error": "Email not found"}), 404
    
    # 3. Task starten (ASYNC!)
    task = optimize_email_processing.delay(
        user_id=current_user.id,
        raw_email_id=raw_email_id,
        service_token_id=service_token_id
    )
    
    # 4. Sofort Response
    return jsonify({
        "task_id": task.id,
        "status": "queued",
        "message": "Optimize-Lauf wird durchgeführt..."
    })

# ---
# ROUTE 3: Antwort-Entwurf (ALT: api.py:672)
# ---
@email_actions_bp.route("/emails/<int:raw_email_id>/generate-reply", methods=["POST"])
def generate_reply(raw_email_id):
    """Generate Reply Draft (ASYNC)."""
    
    # 1. Validate Input
    style = request.json.get("style", "professional")
    
    # 2. Ownership-Check
    raw_email = db.session.query(RawEmail).filter_by(
        id=raw_email_id,
        user_id=current_user.id
    ).first()
    
    if not raw_email:
        return jsonify({"error": "Email not found"}), 404
    
    # 3. Task starten (ASYNC!)
    task = generate_reply_draft.delay(
        user_id=current_user.id,
        raw_email_id=raw_email_id,
        style=style
    )
    
    # 4. Sofort Response
    return jsonify({
        "task_id": task.id,
        "status": "queued",
        "message": "Antwort-Entwurf wird generiert..."
    })

# ---
# NEU: Task-Status abfragen
# ---
@email_actions_bp.route("/tasks/<task_id>/status", methods=["GET"])
def get_task_status(task_id):
    """Abfrage des Task-Status für UI-Polling."""
    from src.celery_app import celery_app
    
    result = celery_app.AsyncResult(task_id)
    
    response = {
        "task_id": task_id,
        "status": result.state,  # PENDING, STARTED, SUCCESS, FAILURE, RETRY
        "result": None,
        "error": None
    }
    
    if result.ready():
        # Task ist fertig
        if result.successful():
            response["result"] = result.result
        else:
            response["error"] = str(result.info)
    
    elif result.state == "PROGRESS":
        # Task läuft und gibt Progress zurück
        response["progress"] = result.info.get("progress", 0)
        response["message"] = result.info.get("message", "")
    
    return jsonify(response)
```

---

## 🖥️ FRONTEND: Polling implementieren

### JavaScript (email_detail.html oder email_detail.js)

```javascript
/**
 * Task-Poller für asynchrone Backend-Tasks
 */
class TaskPoller {
    constructor(taskId, onSuccess, onError, onProgress) {
        this.taskId = taskId;
        this.onSuccess = onSuccess;
        this.onError = onError;
        this.onProgress = onProgress || (() => {});
        this.pollInterval = 1000;  // 1 Sekunde
        this.maxRetries = 120;     // Max 2 Minuten
        this.retryCount = 0;
    }
    
    async start() {
        const poll = async () => {
            try {
                const response = await fetch(`/tasks/${this.taskId}/status`);
                const data = await response.json();
                
                // Progress-Update
                if (data.progress !== undefined) {
                    this.onProgress(data.progress, data.message);
                }
                
                // Status-Handling
                if (data.status === "SUCCESS") {
                    this.onSuccess(data.result);
                    return;  // Stop polling
                } 
                else if (data.status === "FAILURE") {
                    this.onError(data.error || "Task fehlgeschlagen");
                    return;  // Stop polling
                }
                else if (data.status === "PENDING" || data.status === "STARTED" || data.status === "PROGRESS") {
                    // Task läuft noch - weiter pollen
                    this.retryCount++;
                    if (this.retryCount < this.maxRetries) {
                        setTimeout(poll, this.pollInterval);
                    } else {
                        this.onError("Task timeout nach 2 Minuten");
                    }
                }
            } catch (error) {
                this.onError(`Polling-Fehler: ${error.message}`);
            }
        };
        
        await poll();
    }
}

// ---
// Button 1: Base-Lauf neu machen
// ---
document.getElementById("btn-reprocess-base").addEventListener("click", async () => {
    const emailId = getCurrentEmailId();
    const serviceTokenId = getCurrentServiceTokenId();
    
    // 1. Zeige Spinner
    showSpinner("Base-Lauf wird neu generiert...");
    disableButton("btn-reprocess-base");
    
    try {
        // 2. Starte Task
        const response = await fetch(`/email/${emailId}/reprocess`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({service_token_id: serviceTokenId})
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.error || "Task konnte nicht gestartet werden");
        }
        
        // 3. Polling starten
        const poller = new TaskPoller(
            data.task_id,
            (result) => {
                // Success!
                hideSpinner();
                enableButton("btn-reprocess-base");
                showToast("Base-Lauf erfolgreich abgeschlossen!", "success");
                
                // UI updaten mit neuen Scores
                updateEmailScores({
                    score: result.score,
                    reasoning: result.reasoning,
                    model_used: result.model_used
                });
            },
            (error) => {
                // Error!
                hideSpinner();
                enableButton("btn-reprocess-base");
                showToast(`Fehler: ${error}`, "error");
            },
            (progress, message) => {
                // Progress-Update
                updateProgressBar(progress);
                updateStatusMessage(message);
            }
        );
        
        poller.start();
        
    } catch (error) {
        hideSpinner();
        enableButton("btn-reprocess-base");
        showToast(`Fehler: ${error.message}`, "error");
    }
});

// ---
// Button 2: Optimize-Lauf
// ---
document.getElementById("btn-optimize").addEventListener("click", async () => {
    const emailId = getCurrentEmailId();
    const serviceTokenId = getCurrentOptimizeTokenId();
    
    // Warnung: Optimize ist teuer!
    if (!confirm("Optimize-Lauf nutzt GPT-4 und ist teurer. Fortfahren?")) {
        return;
    }
    
    showSpinner("Optimize-Lauf wird durchgeführt (kann bis zu 1 Minute dauern)...");
    disableButton("btn-optimize");
    
    try {
        const response = await fetch(`/email/${emailId}/optimize`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({service_token_id: serviceTokenId})
        });
        
        const data = await response.json();
        
        const poller = new TaskPoller(
            data.task_id,
            (result) => {
                hideSpinner();
                enableButton("btn-optimize");
                showToast(`Optimize erfolgreich! Verbesserung: ${result.improvement.toFixed(2)}`, "success");
                
                // UI updaten
                updateOptimizeScores({
                    score_base: result.score_base,
                    score_optimize: result.score_optimize,
                    improvement: result.improvement,
                    suggestions: result.suggestions
                });
            },
            (error) => {
                hideSpinner();
                enableButton("btn-optimize");
                showToast(`Fehler: ${error}`, "error");
            }
        );
        
        poller.start();
        
    } catch (error) {
        hideSpinner();
        enableButton("btn-optimize");
        showToast(`Fehler: ${error.message}`, "error");
    }
});

// ---
// Button 3: Antwort-Entwurf generieren
// ---
document.getElementById("btn-generate-reply").addEventListener("click", async () => {
    const emailId = getCurrentEmailId();
    const style = document.getElementById("reply-style-select").value || "professional";
    
    showSpinner("Antwort-Entwurf wird generiert...");
    disableButton("btn-generate-reply");
    
    try {
        const response = await fetch(`/emails/${emailId}/generate-reply`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({style: style})
        });
        
        const data = await response.json();
        
        const poller = new TaskPoller(
            data.task_id,
            (result) => {
                hideSpinner();
                enableButton("btn-generate-reply");
                showToast("Antwort-Entwurf erfolgreich generiert!", "success");
                
                // Draft in Textfeld einfügen
                const replyEditor = document.getElementById("reply-editor");
                if (replyEditor) {
                    replyEditor.value = result.draft;
                    
                    // Optional: Zeige Draft in Modal
                    showDraftModal(result.draft);
                }
            },
            (error) => {
                hideSpinner();
                enableButton("btn-generate-reply");
                showToast(`Fehler: ${error}`, "error");
            }
        );
        
        poller.start();
        
    } catch (error) {
        hideSpinner();
        enableButton("btn-generate-reply");
        showToast(`Fehler: ${error.message}`, "error");
    }
});

// ---
// Helper-Funktionen
// ---
function showSpinner(message) {
    const spinner = document.getElementById("task-spinner");
    const spinnerMessage = document.getElementById("spinner-message");
    
    if (spinner) {
        spinner.style.display = "block";
        if (spinnerMessage) {
            spinnerMessage.textContent = message;
        }
    }
}

function hideSpinner() {
    const spinner = document.getElementById("task-spinner");
    if (spinner) {
        spinner.style.display = "none";
    }
}

function disableButton(buttonId) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = true;
        button.classList.add("disabled");
    }
}

function enableButton(buttonId) {
    const button = document.getElementById(buttonId);
    if (button) {
        button.disabled = false;
        button.classList.remove("disabled");
    }
}

function showToast(message, type = "info") {
    // Implementiere Toast-Notification
    // z.B. mit Bootstrap Toast oder Custom
    console.log(`[${type.toUpperCase()}] ${message}`);
    
    // Beispiel: Bootstrap Toast
    const toastHtml = `
        <div class="toast" role="alert" data-bs-autohide="true" data-bs-delay="3000">
            <div class="toast-header bg-${type === 'success' ? 'success' : 'danger'} text-white">
                <strong class="me-auto">${type === 'success' ? 'Erfolg' : 'Fehler'}</strong>
                <button type="button" class="btn-close" data-bs-dismiss="toast"></button>
            </div>
            <div class="toast-body">
                ${message}
            </div>
        </div>
    `;
    
    const toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
        toastContainer.insertAdjacentHTML("beforeend", toastHtml);
        
        // Bootstrap Toast initialisieren
        const toastElement = toastContainer.lastElementChild;
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
    }
}

function updateEmailScores(data) {
    // UI updaten mit neuen Scores
    document.getElementById("ai-score").textContent = data.score.toFixed(2);
    document.getElementById("ai-reasoning").textContent = data.reasoning;
    document.getElementById("model-used").textContent = data.model_used;
}

function updateOptimizeScores(data) {
    // UI updaten mit Optimize-Scores
    document.getElementById("score-base").textContent = data.score_base.toFixed(2);
    document.getElementById("score-optimize").textContent = data.score_optimize.toFixed(2);
    document.getElementById("improvement").textContent = `+${data.improvement.toFixed(2)}`;
    
    if (data.suggestions) {
        document.getElementById("ai-suggestions").textContent = data.suggestions;
    }
}

function showDraftModal(draft) {
    // Zeige Draft in Modal-Dialog
    const modal = document.getElementById("draft-modal");
    const draftContent = document.getElementById("draft-content");
    
    if (modal && draftContent) {
        draftContent.textContent = draft;
        
        // Bootstrap Modal öffnen
        const bsModal = new bootstrap.Modal(modal);
        bsModal.show();
    }
}
```

---

## 📊 VERGLEICH: Vorher vs. Nachher

### Vorher (SYNCHRON)
```
User klickt "Base-Lauf neu machen"
  ↓
Backend: process_email() [5-30 Sekunden WARTEN]
  ↓
DB-Update
  ↓
Response zurück an User (ENDLICH!)
  ↓
UI aktualisiert

Problem: User kann NICHTS anderes machen!
```

### Nachher (ASYNC mit Celery)
```
User klickt "Base-Lauf neu machen"
  ↓
Backend: Task wird in Redis gequeued [< 100ms]
  ↓
Response SOFORT zurück ("task_id": "abc123")
  ↓
UI zeigt Spinner + "Task läuft..."
  ↓ (Parallel)
Celery Worker: process_email() [5-30 Sekunden]
  ↓
Frontend: Polling alle 1 Sekunde
  ↓
Task fertig: UI aktualisiert mit Result

Vorteil: User kann während Task andere Dinge tun!
```

---

## 🚨 KRITISCHE PUNKTE

### 1. ServiceToken-Integration ⚠️
```python
# WICHTIG: Token muss mit User-ID validiert werden!
token = session.query(ServiceToken).filter_by(
    id=service_token_id,
    user_id=user_id  # ← Multi-User Security!
).first()
```

**Warum:** Sonst könnte User A den Token von User B nutzen → Security-Lücke!

### 2. Ownership-Check ⚠️
```python
# IMMER prüfen: Gehört die Email dem User?
raw_email = session.query(RawEmail).filter_by(
    id=raw_email_id,
    user_id=user_id  # ← Multi-User Security!
).first()
```

**Warum:** User A darf nicht Emails von User B verarbeiten!

### 3. Rate-Limiting ⚠️
```python
# Für Optimize-Lauf (teuer!)
from flask_limiter import Limiter

limiter = Limiter(app, key_func=lambda: current_user.id)

@limiter.limit("5 per hour")  # Max 5 Optimize-Läufe pro Stunde
def optimize_email(raw_email_id):
    ...
```

**Warum:** Sonst kann User Server teuer machen (GPT-4 Kosten!)

### 4. Timeout-Handling ⚠️
```python
# Task-Level Timeouts
@celery_app.task(
    time_limit=120,      # Hard Limit: Task wird nach 2 Min abgebrochen
    soft_time_limit=90   # Soft Limit: Warning nach 90s
)
```

**Warum:** Verhindert stuck tasks!

---

## ✅ CHECKLISTE: Migration abgeschlossen?

### Backend
- [x] `reprocess_email_base` Task erstellt ✅ (src/tasks/email_processing_tasks.py)
- [x] `optimize_email_processing` Task erstellt ✅ (src/tasks/email_processing_tasks.py)
- [x] `generate_reply_draft` Task erstellt ✅ (src/tasks/reply_generation_tasks.py)
- [x] ServiceToken-Integration in allen Tasks ✅ (_get_dek_from_service_token mit user_id check)
- [x] Ownership-Check in allen Tasks ✅ (filter_by(id=token_id, user_id=user_id))
- [x] Timeout-Handling konfiguriert ✅ (reprocess:2min, optimize:3min, reply:90s)
- [x] Retry-Logik implementiert ✅ (autoretry_for + exponential backoff)
- [x] Blueprint-Routes aktualisiert ✅ (email_actions.py + api.py)
- [x] Task-Status-Endpoint ✅ (bestehend: /tasks/<task_id> in accounts.py)

### Frontend
- [x] TaskPoller-Logik implementiert ✅ (inline in event handlers)
- [x] Button 1: Base-Lauf mit Polling ✅ (reprocessEmailBtn handler)
- [x] Button 2: Optimize-Lauf mit Polling ✅ (optimizeBtn handler)
- [x] Button 3: Antwort-Entwurf mit Polling ✅ (generateReply function)
- [x] Spinner/Loading-Indicator ✅ (progress-bar-animated)
- [x] Error-Handling ✅ (FAILURE state detection)
- [x] Progress-Bar ✅ (updates from task.progress)

### Testing
- [ ] Unit-Test: `reprocess_email_base` Task
- [ ] Unit-Test: `optimize_email_processing` Task
- [ ] Unit-Test: `generate_reply_draft` Task
- [ ] Integration-Test: Button → Task → UI-Update
- [ ] Load-Test: 5 concurrent Users klicken Button
- [ ] Security-Test: User A kann nicht Emails von User B verarbeiten
- [ ] Rate-Limit-Test: Optimize-Lauf max 5x pro Stunde

---

## 🎉 IMPLEMENTATION STATUS

**Implementiert am**: Januar 2026  
**Commits**:
1. `feat(tasks): Add UI-triggered Celery tasks for email processing`
2. `feat(blueprints): Add Celery async path for reprocess, optimize, generate-reply`
3. `fix(blueprints): Fix auth import for rule/account Celery paths`
4. `feat(frontend): Add Celery task polling for UI buttons`

**Architektur:**
```
User klickt Button
      │
      ▼
Blueprint (email_actions.py / api.py)
      │
      ├─ USE_CELERY=false → Legacy Sync Path (blockiert)
      │
      └─ USE_CELERY=true → Celery Path:
            │
            ▼
      ServiceToken erstellen (1-day expiry)
            │
            ▼
      task.delay(user_id, email_id, service_token_id)
            │
            ▼
      Return {"task_id": "...", "task_type": "celery"}
            │
            ▼
      Frontend pollt /tasks/<task_id>
            │
            ▼
      Task completed → UI update + page reload
```

---

## 📊 AUFWAND-SCHÄTZUNG (Aktualisiert)

| Aufgabe | Geschätzt | Tatsächlich |
|---------|-----------|-------------|
| Backend: 3 Tasks erstellen | 8h | ✅ ~4h |
| Backend: Blueprint-Routes aktualisieren | 2h | ✅ ~2h |
| Backend: Task-Status-Endpoint | 1h | ✅ Wiederverwendet /tasks/<id> |
| Frontend: TaskPoller + 3 Buttons | 4h | ✅ ~3h |
| Frontend: UI-Feedback (Spinner, Toasts) | 2h | ✅ ~1h |
| Testing: Unit + Integration | 3h | ⏳ TODO |
| **TOTAL** | **20h** | **~10h + Tests** |

---

## 📚 VERWANDTE DOKUMENTE

- **[LEGACY_TO_CELERY_MAPPING.md](LEGACY_TO_CELERY_MAPPING.md)** - Allgemeine Mapping-Tabelle
- **[03_CELERY_TEST_INFRASTRUCTURE.md](03_CELERY_TEST_INFRASTRUCTURE.md)** - Testing-Strategie
- **[00_MASTER_IMPLEMENTIERUNGS_LEITFADEN.md](00_MASTER_IMPLEMENTIERUNGS_LEITFADEN.md)** - Implementations-Timeline

---

**Status**: ✅ IMPLEMENTIERT  
**Priorität**: 🔴 KRITISCH für Multi-User → ✅ GELÖST  
**Nächster Schritt**: Tests schreiben + Celery Worker neustarten

**Viel Erfolg! 🚀**
