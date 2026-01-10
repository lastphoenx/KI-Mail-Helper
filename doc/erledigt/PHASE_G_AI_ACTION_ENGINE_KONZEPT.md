# 🤖 Phase G: AI Action Engine - Vollständiges Konzept

**Estimated Duration:** 10-14 Stunden  
**Status:** 📋 KONZEPT BEREIT  
**Abhängigkeiten:** Phase E (Thread-Context) ✅, Phase F (Semantic Intelligence) ✅  
**Erstellt:** 02. Januar 2026

---

## 📋 Executive Summary

Phase G erweitert KI-Mail-Helper um zwei leistungsstarke Features:

| Feature | Aufwand | User-Value |
|---------|---------|------------|
| **G.1 Reply Draft Generator** | 4-6h | ⭐⭐⭐⭐⭐ KI schreibt Antwort-Entwürfe |
| **G.2 Auto-Action Rules Engine** | 6-8h | ⭐⭐⭐⭐⭐ Automatische Email-Aktionen |

**Warum jetzt?**
- Thread-Context (Phase E) ist bereits implementiert → KI versteht Konversationen
- Semantic Intelligence (Phase F) funktioniert → Ähnlichkeitserkennung möglich
- Infrastruktur steht bereit → Nur neue Endpoints + Services nötig

---

## 🎯 G.1: Reply Draft Generator (4-6h)

### Was wird gebaut?

Ein Service der:
1. Thread-Kontext analysiert
2. Passenden Antwort-Entwurf generiert
3. Ton-Optionen bietet (Formell/Freundlich/Kurz)
4. Copy-to-Clipboard oder direkt in Mail-Client öffnet

### Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND                                │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  Email-Detail-View                                   │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │  [📝 Antwort-Entwurf generieren]            │    │    │
│  │  │                                              │    │    │
│  │  │  Ton: ◉ Formell  ○ Freundlich  ○ Kurz      │    │    │
│  │  │                                              │    │    │
│  │  │  [Generieren]                               │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  │                                                      │    │
│  │  ┌─────────────────────────────────────────────┐    │    │
│  │  │  Generierter Entwurf:                       │    │    │
│  │  │  ─────────────────────────────────────────  │    │    │
│  │  │  Sehr geehrter Herr Müller,                 │    │    │
│  │  │                                              │    │    │
│  │  │  vielen Dank für Ihre Nachricht...          │    │    │
│  │  │                                              │    │    │
│  │  │  [📋 Kopieren] [✉️ In Mail-Client öffnen]   │    │    │
│  │  └─────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                      BACKEND                                 │
│                                                              │
│  POST /api/email/<id>/generate-reply                        │
│       Body: { "tone": "formal|friendly|brief" }             │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  ReplyDraftService                                    │   │
│  │  ├── build_reply_context()     # Thread + Original   │   │
│  │  ├── select_tone_prompt()      # Ton-spezifisch      │   │
│  │  └── generate_draft()          # KI-Aufruf           │   │
│  └──────────────────────────────────────────────────────┘   │
│                              │                               │
│                              ▼                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  AIClient.generate_reply()     # Neuer AI-Endpoint   │   │
│  │  ├── LocalOllamaClient                               │   │
│  │  ├── OpenAIClient                                    │   │
│  │  └── AnthropicClient                                 │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

### Datei-Struktur

```
src/
├── 03_ai_client.py          # ERWEITERN: generate_reply() Methode
├── 17_reply_service.py      # NEU: ReplyDraftService
├── 01_web_app.py            # ERWEITERN: /api/email/<id>/generate-reply
└── templates/
    └── email_detail.html    # ERWEITERN: Reply-Draft UI
```

---

### Code-Beispiele

#### 1. Neuer Service: `src/17_reply_service.py`

```python
"""
Reply Draft Service - Phase G.1
Generiert KI-basierte Antwort-Entwürfe mit Ton-Auswahl
"""

from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
import logging

from src.02_models import RawEmail, ProcessedEmail, db
from src.03_ai_client import get_active_ai_client
from src.12_processing import build_thread_context
from src.04_encryption import decrypt_value

logger = logging.getLogger(__name__)


class ReplyTone(Enum):
    """Verfügbare Antwort-Töne"""
    FORMAL = "formal"
    FRIENDLY = "friendly"
    BRIEF = "brief"


@dataclass
class ReplyDraft:
    """Generierter Antwort-Entwurf"""
    draft_text: str
    tone: ReplyTone
    subject: str  # "Re: ..." 
    recipient: str
    generation_time_ms: int
    model_used: str


# Ton-spezifische Prompts
TONE_PROMPTS = {
    ReplyTone.FORMAL: """
Du schreibst eine FORMELLE Geschäftsantwort.
- Verwende "Sehr geehrte/r..." als Anrede
- Sachlicher, professioneller Ton
- Korrekte Grammatik und Rechtschreibung
- Höfliche Grußformel am Ende
- Keine Emojis oder umgangssprachliche Ausdrücke
""",
    
    ReplyTone.FRIENDLY: """
Du schreibst eine FREUNDLICHE Antwort.
- Verwende "Hallo..." oder "Liebe/r..." als Anrede
- Warmer, persönlicher Ton
- Darf lockerer formuliert sein
- Freundliche Grußformel (z.B. "Viele Grüße")
- Gelegentliche Emojis sind OK
""",
    
    ReplyTone.BRIEF: """
Du schreibst eine KURZE, prägnante Antwort.
- Maximal 3-4 Sätze
- Direkt auf den Punkt kommen
- Keine überflüssigen Floskeln
- Kurze Anrede, kurze Grußformel
- Nur das Wesentliche
"""
}


REPLY_SYSTEM_PROMPT = """
Du bist ein E-Mail-Assistent der professionelle Antwort-Entwürfe erstellt.

AUFGABE:
Basierend auf der Original-Mail und dem Konversationsverlauf, 
erstelle einen passenden Antwort-Entwurf.

REGELN:
1. Antworte in der Sprache der Original-Mail
2. Beziehe dich auf den Inhalt der Original-Mail
3. Berücksichtige den Konversationsverlauf falls vorhanden
4. Füge KEINE Betreffzeile hinzu (nur den Body-Text)
5. Beginne direkt mit der Anrede
6. Beende mit einer passenden Grußformel
7. Verwende [PLATZHALTER] für Informationen die du nicht weißt

{tone_instructions}

WICHTIG: Generiere NUR den Antwort-Text, keine Meta-Kommentare.
"""


class ReplyDraftService:
    """Service für KI-generierte Antwort-Entwürfe"""
    
    def __init__(self, master_key: str):
        self.master_key = master_key
        self.ai_client = get_active_ai_client()
    
    def generate_draft(
        self,
        email_id: int,
        tone: ReplyTone = ReplyTone.FORMAL,
        custom_instructions: Optional[str] = None
    ) -> Optional[ReplyDraft]:
        """
        Generiert einen Antwort-Entwurf für eine Email.
        
        Args:
            email_id: ID der zu beantwortenden Email
            tone: Gewünschter Ton (formal/friendly/brief)
            custom_instructions: Optionale zusätzliche Anweisungen
            
        Returns:
            ReplyDraft mit generiertem Text oder None bei Fehler
        """
        import time
        start_time = time.time()
        
        # 1. Email laden
        raw_email = db.session.query(RawEmail).get(email_id)
        if not raw_email:
            logger.error(f"Email {email_id} nicht gefunden")
            return None
        
        # 2. Email-Inhalte entschlüsseln
        try:
            original_subject = decrypt_value(
                raw_email.encrypted_subject, 
                self.master_key
            )
            original_body = decrypt_value(
                raw_email.encrypted_body, 
                self.master_key
            )
            original_sender = decrypt_value(
                raw_email.encrypted_sender, 
                self.master_key
            )
        except Exception as e:
            logger.error(f"Entschlüsselung fehlgeschlagen: {e}")
            return None
        
        # 3. Thread-Kontext sammeln (nutzt Phase E!)
        thread_context = build_thread_context(
            db.session, 
            raw_email, 
            self.master_key
        )
        
        # 4. Reply-Kontext aufbauen
        reply_context = self._build_reply_context(
            original_subject=original_subject,
            original_body=original_body,
            original_sender=original_sender,
            thread_context=thread_context,
            custom_instructions=custom_instructions
        )
        
        # 5. System-Prompt mit Ton-Anweisungen
        system_prompt = REPLY_SYSTEM_PROMPT.format(
            tone_instructions=TONE_PROMPTS[tone]
        )
        
        # 6. KI-Aufruf
        try:
            draft_text = self.ai_client.generate_text(
                system_prompt=system_prompt,
                user_prompt=reply_context,
                max_tokens=1000
            )
        except Exception as e:
            logger.error(f"KI-Generierung fehlgeschlagen: {e}")
            return None
        
        # 7. Ergebnis zusammenstellen
        generation_time = int((time.time() - start_time) * 1000)
        
        # Re: Betreff generieren
        reply_subject = original_subject or ""
        if not reply_subject.lower().startswith("re:"):
            reply_subject = f"Re: {reply_subject}"
        
        return ReplyDraft(
            draft_text=draft_text.strip(),
            tone=tone,
            subject=reply_subject,
            recipient=original_sender or "",
            generation_time_ms=generation_time,
            model_used=self.ai_client.model_name
        )
    
    def _build_reply_context(
        self,
        original_subject: str,
        original_body: str,
        original_sender: str,
        thread_context: Optional[str],
        custom_instructions: Optional[str]
    ) -> str:
        """Baut den Kontext für die KI-Anfrage auf"""
        
        parts = []
        
        # Thread-Kontext (falls vorhanden)
        if thread_context:
            parts.append(f"=== KONVERSATIONSVERLAUF ===\n{thread_context}")
        
        # Original-Email
        parts.append(f"""
=== ZU BEANTWORTENDE EMAIL ===
Von: {original_sender}
Betreff: {original_subject}

{original_body[:3000]}  # Limitiert auf 3000 Zeichen
""")
        
        # Custom Instructions
        if custom_instructions:
            parts.append(f"""
=== ZUSÄTZLICHE ANWEISUNGEN ===
{custom_instructions}
""")
        
        parts.append("""
=== AUFGABE ===
Erstelle einen passenden Antwort-Entwurf für diese Email.
""")
        
        return "\n\n".join(parts)


# Convenience-Funktion für einfache Nutzung
def generate_reply_draft(
    email_id: int,
    master_key: str,
    tone: str = "formal",
    custom_instructions: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Convenience-Funktion zum Generieren eines Antwort-Entwurfs.
    
    Returns:
        Dict mit draft_text, subject, recipient, etc. oder None
    """
    try:
        tone_enum = ReplyTone(tone.lower())
    except ValueError:
        tone_enum = ReplyTone.FORMAL
    
    service = ReplyDraftService(master_key)
    draft = service.generate_draft(
        email_id=email_id,
        tone=tone_enum,
        custom_instructions=custom_instructions
    )
    
    if draft:
        return {
            "draft_text": draft.draft_text,
            "subject": draft.subject,
            "recipient": draft.recipient,
            "tone": draft.tone.value,
            "generation_time_ms": draft.generation_time_ms,
            "model_used": draft.model_used
        }
    return None
```

---

#### 2. AI Client erweitern: `src/03_ai_client.py`

```python
# === ERGÄNZUNG in src/03_ai_client.py ===

# In der abstrakten Basisklasse AIClient hinzufügen:

class AIClient(ABC):
    # ... bestehende Methoden ...
    
    @abstractmethod
    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """
        Generiert Text basierend auf System- und User-Prompt.
        Wird für Reply-Drafts und andere Text-Generierung verwendet.
        
        Args:
            system_prompt: Anweisungen für die KI
            user_prompt: Der eigentliche Inhalt/Kontext
            max_tokens: Maximale Antwortlänge
            temperature: Kreativität (0.0-1.0)
            
        Returns:
            Generierter Text
        """
        pass


# In LocalOllamaClient implementieren:

class LocalOllamaClient(AIClient):
    # ... bestehender Code ...
    
    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Generiert Text via Ollama Chat-API"""
        
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.chat_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "num_predict": max_tokens,
                "temperature": temperature
            }
        }
        
        response = requests.post(url, json=payload, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        return result.get("message", {}).get("content", "")


# In OpenAIClient implementieren:

class OpenAIClient(AIClient):
    # ... bestehender Code ...
    
    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Generiert Text via OpenAI Chat-API"""
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=max_tokens,
            temperature=temperature
        )
        
        return response.choices[0].message.content


# In AnthropicClient implementieren:

class AnthropicClient(AIClient):
    # ... bestehender Code ...
    
    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0.7
    ) -> str:
        """Generiert Text via Anthropic Messages-API"""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature
        )
        
        return response.content[0].text
```

---

#### 3. Web-Route hinzufügen: `src/01_web_app.py`

```python
# === ERGÄNZUNG in src/01_web_app.py ===

from src.17_reply_service import generate_reply_draft


@app.route('/api/email/<int:email_id>/generate-reply', methods=['POST'])
@login_required
def api_generate_reply(email_id):
    """
    Generiert einen KI-basierten Antwort-Entwurf.
    
    POST Body:
    {
        "tone": "formal" | "friendly" | "brief",
        "custom_instructions": "Optional: Zusätzliche Anweisungen"
    }
    
    Response:
    {
        "success": true,
        "draft": {
            "draft_text": "Sehr geehrter Herr...",
            "subject": "Re: Ihre Anfrage",
            "recipient": "sender@example.com",
            "tone": "formal",
            "generation_time_ms": 1234,
            "model_used": "mistral:7b"
        }
    }
    """
    # Master-Key aus Session
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({
            "success": False,
            "error": "Nicht authentifiziert - Master-Key fehlt"
        }), 401
    
    # Request-Body parsen
    data = request.get_json() or {}
    tone = data.get('tone', 'formal')
    custom_instructions = data.get('custom_instructions')
    
    # Validierung
    if tone not in ['formal', 'friendly', 'brief']:
        return jsonify({
            "success": False,
            "error": f"Ungültiger Ton: {tone}. Erlaubt: formal, friendly, brief"
        }), 400
    
    # Email-Zugriff prüfen
    raw_email = RawEmail.query.get(email_id)
    if not raw_email:
        return jsonify({
            "success": False,
            "error": "Email nicht gefunden"
        }), 404
    
    # Benutzer-Berechtigung prüfen
    if raw_email.user_id != current_user.id:
        return jsonify({
            "success": False,
            "error": "Keine Berechtigung für diese Email"
        }), 403
    
    # Draft generieren
    try:
        draft = generate_reply_draft(
            email_id=email_id,
            master_key=master_key,
            tone=tone,
            custom_instructions=custom_instructions
        )
        
        if draft:
            return jsonify({
                "success": True,
                "draft": draft
            })
        else:
            return jsonify({
                "success": False,
                "error": "Generierung fehlgeschlagen"
            }), 500
            
    except Exception as e:
        logger.error(f"Reply-Draft Fehler: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
```

---

#### 4. Frontend-Integration: JavaScript

```javascript
// === In templates/email_detail.html oder separates JS-File ===

/**
 * Reply Draft Generator - Frontend Integration
 */
class ReplyDraftGenerator {
    constructor(emailId) {
        this.emailId = emailId;
        this.container = null;
        this.init();
    }
    
    init() {
        this.createUI();
        this.bindEvents();
    }
    
    createUI() {
        // UI-Container erstellen
        const html = `
        <div class="card mt-3" id="reply-draft-card">
            <div class="card-header">
                <h6 class="mb-0">
                    <i class="bi bi-pencil-square"></i> Antwort-Entwurf generieren
                </h6>
            </div>
            <div class="card-body">
                <!-- Ton-Auswahl -->
                <div class="mb-3">
                    <label class="form-label">Ton der Antwort:</label>
                    <div class="btn-group w-100" role="group">
                        <input type="radio" class="btn-check" name="tone" 
                               id="tone-formal" value="formal" checked>
                        <label class="btn btn-outline-primary" for="tone-formal">
                            🎩 Formell
                        </label>
                        
                        <input type="radio" class="btn-check" name="tone" 
                               id="tone-friendly" value="friendly">
                        <label class="btn btn-outline-primary" for="tone-friendly">
                            😊 Freundlich
                        </label>
                        
                        <input type="radio" class="btn-check" name="tone" 
                               id="tone-brief" value="brief">
                        <label class="btn btn-outline-primary" for="tone-brief">
                            ⚡ Kurz
                        </label>
                    </div>
                </div>
                
                <!-- Optionale Anweisungen -->
                <div class="mb-3">
                    <label class="form-label">Zusätzliche Anweisungen (optional):</label>
                    <textarea class="form-control" id="custom-instructions" 
                              rows="2" placeholder="z.B. 'Termine vorschlagen' oder 'Absage formulieren'"></textarea>
                </div>
                
                <!-- Generieren-Button -->
                <button class="btn btn-primary w-100" id="generate-draft-btn">
                    <i class="bi bi-magic"></i> Entwurf generieren
                </button>
                
                <!-- Loading-Indicator -->
                <div class="text-center mt-3 d-none" id="draft-loading">
                    <div class="spinner-border text-primary" role="status">
                        <span class="visually-hidden">Generiere...</span>
                    </div>
                    <p class="mt-2 text-muted">KI generiert Antwort-Entwurf...</p>
                </div>
                
                <!-- Ergebnis-Container -->
                <div class="mt-3 d-none" id="draft-result">
                    <hr>
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong>Generierter Entwurf:</strong>
                        <span class="badge bg-secondary" id="draft-meta"></span>
                    </div>
                    <div class="border rounded p-3 bg-light" id="draft-text"
                         style="white-space: pre-wrap; font-family: inherit;"></div>
                    
                    <!-- Action-Buttons -->
                    <div class="mt-3 d-flex gap-2">
                        <button class="btn btn-success" id="copy-draft-btn">
                            <i class="bi bi-clipboard"></i> Kopieren
                        </button>
                        <button class="btn btn-outline-primary" id="open-mailclient-btn">
                            <i class="bi bi-envelope"></i> In Mail-Client öffnen
                        </button>
                        <button class="btn btn-outline-secondary" id="regenerate-btn">
                            <i class="bi bi-arrow-clockwise"></i> Neu generieren
                        </button>
                    </div>
                </div>
                
                <!-- Fehler-Anzeige -->
                <div class="alert alert-danger mt-3 d-none" id="draft-error"></div>
            </div>
        </div>
        `;
        
        // In die Seite einfügen (nach Email-Details)
        const emailDetails = document.querySelector('.email-content');
        if (emailDetails) {
            emailDetails.insertAdjacentHTML('afterend', html);
        }
        
        this.container = document.getElementById('reply-draft-card');
    }
    
    bindEvents() {
        // Generieren-Button
        document.getElementById('generate-draft-btn')
            .addEventListener('click', () => this.generateDraft());
        
        // Kopieren-Button
        document.getElementById('copy-draft-btn')
            .addEventListener('click', () => this.copyToClipboard());
        
        // Mail-Client öffnen
        document.getElementById('open-mailclient-btn')
            .addEventListener('click', () => this.openMailClient());
        
        // Neu generieren
        document.getElementById('regenerate-btn')
            .addEventListener('click', () => this.generateDraft());
    }
    
    async generateDraft() {
        const tone = document.querySelector('input[name="tone"]:checked').value;
        const customInstructions = document.getElementById('custom-instructions').value;
        
        // UI-Status: Loading
        this.showLoading(true);
        this.hideError();
        this.hideResult();
        
        try {
            const response = await fetch(`/api/email/${this.emailId}/generate-reply`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.getCSRFToken()
                },
                body: JSON.stringify({
                    tone: tone,
                    custom_instructions: customInstructions || null
                })
            });
            
            const data = await response.json();
            
            if (data.success) {
                this.showResult(data.draft);
            } else {
                this.showError(data.error || 'Generierung fehlgeschlagen');
            }
        } catch (error) {
            this.showError(`Netzwerkfehler: ${error.message}`);
        } finally {
            this.showLoading(false);
        }
    }
    
    showResult(draft) {
        const resultDiv = document.getElementById('draft-result');
        const textDiv = document.getElementById('draft-text');
        const metaSpan = document.getElementById('draft-meta');
        
        textDiv.textContent = draft.draft_text;
        metaSpan.textContent = `${draft.model_used} • ${draft.generation_time_ms}ms`;
        
        // Speichere für Copy/MailClient
        this.currentDraft = draft;
        
        resultDiv.classList.remove('d-none');
    }
    
    hideResult() {
        document.getElementById('draft-result').classList.add('d-none');
    }
    
    showLoading(show) {
        const loadingDiv = document.getElementById('draft-loading');
        const generateBtn = document.getElementById('generate-draft-btn');
        
        if (show) {
            loadingDiv.classList.remove('d-none');
            generateBtn.disabled = true;
        } else {
            loadingDiv.classList.add('d-none');
            generateBtn.disabled = false;
        }
    }
    
    showError(message) {
        const errorDiv = document.getElementById('draft-error');
        errorDiv.textContent = message;
        errorDiv.classList.remove('d-none');
    }
    
    hideError() {
        document.getElementById('draft-error').classList.add('d-none');
    }
    
    async copyToClipboard() {
        if (!this.currentDraft) return;
        
        try {
            await navigator.clipboard.writeText(this.currentDraft.draft_text);
            
            // Feedback
            const btn = document.getElementById('copy-draft-btn');
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i class="bi bi-check"></i> Kopiert!';
            btn.classList.replace('btn-success', 'btn-outline-success');
            
            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.classList.replace('btn-outline-success', 'btn-success');
            }, 2000);
        } catch (err) {
            this.showError('Kopieren fehlgeschlagen');
        }
    }
    
    openMailClient() {
        if (!this.currentDraft) return;
        
        const subject = encodeURIComponent(this.currentDraft.subject);
        const body = encodeURIComponent(this.currentDraft.draft_text);
        const to = encodeURIComponent(this.currentDraft.recipient);
        
        // mailto: Link öffnen
        window.location.href = `mailto:${to}?subject=${subject}&body=${body}`;
    }
    
    getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }
}

// Initialisierung auf Email-Detail-Seite
document.addEventListener('DOMContentLoaded', () => {
    const emailIdMatch = window.location.pathname.match(/\/email\/(\d+)/);
    if (emailIdMatch) {
        new ReplyDraftGenerator(parseInt(emailIdMatch[1]));
    }
});
```

---

## 🎯 G.2: Auto-Action Rules Engine (6-8h)

### Was wird gebaut?

Eine regelbasierte Engine die:
1. Benutzerdefinierte Regeln speichert
2. Eingehende Emails automatisch verarbeitet
3. Aktionen ausführt (Move, Flag, Mark as Read)
4. Newsletter-Problem löst!

### Architektur-Übersicht

```
┌─────────────────────────────────────────────────────────────┐
│                 AUTO-ACTION RULES ENGINE                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌─────────────────────┐    ┌─────────────────────────────┐ │
│  │   Rules UI          │    │   Rules Engine              │ │
│  │   /settings/rules   │───▶│   process_rules()           │ │
│  └─────────────────────┘    └─────────────────────────────┘ │
│                                       │                      │
│  ┌─────────────────────┐              ▼                      │
│  │   DB: AutoRule      │    ┌─────────────────────────────┐ │
│  │   - conditions      │◀──▶│   Rule Matcher              │ │
│  │   - actions         │    │   - sender_matches()        │ │
│  │   - priority        │    │   - subject_contains()      │ │
│  └─────────────────────┘    │   - has_attachment()        │ │
│                              └─────────────────────────────┘ │
│                                       │                      │
│                                       ▼                      │
│                              ┌─────────────────────────────┐ │
│                              │   Action Executor           │ │
│                              │   - move_to_folder()        │ │
│                              │   - mark_as_read()          │ │
│                              │   - add_flag()              │ │
│                              │   - apply_tag()             │ │
│                              └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

### Datenbank-Schema

```python
# === ERGÄNZUNG in src/02_models.py ===

class AutoRule(db.Model):
    """
    Automatische Aktionsregeln für Emails.
    
    Beispiel-Regel:
    - Name: "Newsletter archivieren"
    - Conditions: {"sender_contains": "newsletter@", "subject_contains": "Newsletter"}
    - Actions: {"move_to": "Archive", "mark_as_read": true}
    """
    __tablename__ = 'auto_rules'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    
    # Regel-Metadaten
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    priority = db.Column(db.Integer, default=100)  # Niedrigere = höhere Priorität
    
    # Bedingungen (JSON)
    # Mögliche Keys:
    # - sender_equals: "exact@match.com"
    # - sender_contains: "newsletter"
    # - sender_domain: "marketing.com"
    # - subject_contains: "Newsletter"
    # - subject_regex: "\\[SPAM\\].*"
    # - has_attachment: true/false
    # - body_contains: "unsubscribe"
    # - match_mode: "all" (AND) oder "any" (OR)
    conditions_json = db.Column(db.Text, nullable=False, default='{}')
    
    # Aktionen (JSON)
    # Mögliche Keys:
    # - move_to_folder: "Spam"
    # - mark_as_read: true
    # - mark_as_flagged: true
    # - apply_tag: "Newsletter"
    # - set_priority: "low"
    # - delete: true (VORSICHT!)
    actions_json = db.Column(db.Text, nullable=False, default='{}')
    
    # Statistiken
    times_triggered = db.Column(db.Integer, default=0)
    last_triggered_at = db.Column(db.DateTime, nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('auto_rules', lazy='dynamic'))
    
    @property
    def conditions(self) -> dict:
        return json.loads(self.conditions_json) if self.conditions_json else {}
    
    @conditions.setter
    def conditions(self, value: dict):
        self.conditions_json = json.dumps(value)
    
    @property
    def actions(self) -> dict:
        return json.loads(self.actions_json) if self.actions_json else {}
    
    @actions.setter
    def actions(self, value: dict):
        self.actions_json = json.dumps(value)
    
    def __repr__(self):
        return f'<AutoRule {self.id}: {self.name}>'
```

---

### Code-Beispiele

#### 1. Rules Engine Service: `src/18_auto_rules.py`

```python
"""
Auto-Action Rules Engine - Phase G.2
Automatische Email-Verarbeitung basierend auf benutzerdefinierten Regeln
"""

import re
import json
import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, UTC

from src.02_models import db, AutoRule, RawEmail, ProcessedEmail, User
from src.04_encryption import decrypt_value
from src.16_mail_sync import MailSynchronizer

logger = logging.getLogger(__name__)


@dataclass
class RuleMatch:
    """Ergebnis eines Regel-Matchings"""
    rule: AutoRule
    matched: bool
    matched_conditions: List[str]  # Welche Bedingungen gematcht haben


@dataclass
class RuleExecutionResult:
    """Ergebnis einer Regel-Ausführung"""
    rule_id: int
    rule_name: str
    email_id: int
    success: bool
    actions_executed: List[str]
    error: Optional[str] = None


class AutoRulesEngine:
    """
    Engine für automatische Email-Aktionen basierend auf Regeln.
    
    Wird aufgerufen:
    1. Nach dem Fetch neuer Emails (Background-Job)
    2. Manuell vom User für bestehende Emails
    """
    
    def __init__(self, user_id: int, master_key: str):
        self.user_id = user_id
        self.master_key = master_key
        self._mail_sync: Optional[MailSynchronizer] = None
    
    @property
    def mail_sync(self) -> MailSynchronizer:
        """Lazy-Init für MailSynchronizer"""
        if self._mail_sync is None:
            self._mail_sync = MailSynchronizer(self.user_id, self.master_key)
        return self._mail_sync
    
    def get_active_rules(self) -> List[AutoRule]:
        """Lädt alle aktiven Regeln für den User, sortiert nach Priorität"""
        return AutoRule.query.filter_by(
            user_id=self.user_id,
            is_active=True
        ).order_by(AutoRule.priority.asc()).all()
    
    def process_email(
        self, 
        email_id: int,
        dry_run: bool = False
    ) -> List[RuleExecutionResult]:
        """
        Wendet alle aktiven Regeln auf eine Email an.
        
        Args:
            email_id: ID der zu verarbeitenden Email
            dry_run: Wenn True, nur prüfen ohne Aktionen auszuführen
            
        Returns:
            Liste der Ausführungsergebnisse
        """
        results = []
        
        # Email laden
        raw_email = RawEmail.query.get(email_id)
        if not raw_email or raw_email.user_id != self.user_id:
            return results
        
        # Email-Inhalte entschlüsseln
        email_data = self._decrypt_email_for_matching(raw_email)
        if not email_data:
            return results
        
        # Regeln laden und anwenden
        rules = self.get_active_rules()
        
        for rule in rules:
            match = self._match_rule(rule, email_data)
            
            if match.matched:
                if dry_run:
                    results.append(RuleExecutionResult(
                        rule_id=rule.id,
                        rule_name=rule.name,
                        email_id=email_id,
                        success=True,
                        actions_executed=[f"[DRY-RUN] Would execute: {rule.actions}"]
                    ))
                else:
                    result = self._execute_rule(rule, raw_email)
                    results.append(result)
                
                # Stop-After-Match? (Optional: Kann pro Regel konfiguriert werden)
                if rule.actions.get('stop_processing', False):
                    break
        
        return results
    
    def process_new_emails(
        self,
        since_minutes: int = 60,
        limit: int = 100
    ) -> Dict[str, Any]:
        """
        Verarbeitet alle neuen Emails der letzten X Minuten.
        Wird typischerweise vom Background-Job aufgerufen.
        """
        from datetime import timedelta
        
        cutoff = datetime.now(UTC) - timedelta(minutes=since_minutes)
        
        # Neue Emails finden (noch nicht von Regeln verarbeitet)
        new_emails = RawEmail.query.filter(
            RawEmail.user_id == self.user_id,
            RawEmail.created_at >= cutoff,
            RawEmail.auto_rules_processed == False  # Neues Flag!
        ).limit(limit).all()
        
        stats = {
            "emails_checked": len(new_emails),
            "rules_triggered": 0,
            "actions_executed": 0,
            "errors": 0
        }
        
        for email in new_emails:
            try:
                results = self.process_email(email.id)
                
                for result in results:
                    if result.success:
                        stats["rules_triggered"] += 1
                        stats["actions_executed"] += len(result.actions_executed)
                    else:
                        stats["errors"] += 1
                
                # Markiere als verarbeitet
                email.auto_rules_processed = True
                
            except Exception as e:
                logger.error(f"Auto-Rule Error für Email {email.id}: {e}")
                stats["errors"] += 1
        
        db.session.commit()
        return stats
    
    def _decrypt_email_for_matching(self, raw_email: RawEmail) -> Optional[Dict]:
        """Entschlüsselt Email-Felder für Regel-Matching"""
        try:
            return {
                'sender': decrypt_value(raw_email.encrypted_sender, self.master_key) or '',
                'subject': decrypt_value(raw_email.encrypted_subject, self.master_key) or '',
                'body': decrypt_value(raw_email.encrypted_body, self.master_key) or '',
                'has_attachment': raw_email.imap_has_attachments or False,
                'folder': raw_email.imap_folder or '',
                'flags': raw_email.imap_flags or ''
            }
        except Exception as e:
            logger.error(f"Entschlüsselung für Regel-Matching fehlgeschlagen: {e}")
            return None
    
    def _match_rule(self, rule: AutoRule, email_data: Dict) -> RuleMatch:
        """
        Prüft ob eine Regel auf die Email-Daten matcht.
        """
        conditions = rule.conditions
        match_mode = conditions.get('match_mode', 'all')  # 'all' (AND) oder 'any' (OR)
        
        matched_conditions = []
        
        # Sender-Bedingungen
        if 'sender_equals' in conditions:
            if email_data['sender'].lower() == conditions['sender_equals'].lower():
                matched_conditions.append('sender_equals')
        
        if 'sender_contains' in conditions:
            if conditions['sender_contains'].lower() in email_data['sender'].lower():
                matched_conditions.append('sender_contains')
        
        if 'sender_domain' in conditions:
            sender_domain = email_data['sender'].split('@')[-1].lower() if '@' in email_data['sender'] else ''
            if sender_domain == conditions['sender_domain'].lower():
                matched_conditions.append('sender_domain')
        
        # Subject-Bedingungen
        if 'subject_contains' in conditions:
            if conditions['subject_contains'].lower() in email_data['subject'].lower():
                matched_conditions.append('subject_contains')
        
        if 'subject_regex' in conditions:
            try:
                if re.search(conditions['subject_regex'], email_data['subject'], re.IGNORECASE):
                    matched_conditions.append('subject_regex')
            except re.error:
                logger.warning(f"Ungültiger Regex in Regel {rule.id}: {conditions['subject_regex']}")
        
        # Body-Bedingungen
        if 'body_contains' in conditions:
            if conditions['body_contains'].lower() in email_data['body'].lower():
                matched_conditions.append('body_contains')
        
        # Attachment-Bedingung
        if 'has_attachment' in conditions:
            if email_data['has_attachment'] == conditions['has_attachment']:
                matched_conditions.append('has_attachment')
        
        # Match-Logik auswerten
        total_conditions = len([k for k in conditions.keys() if k != 'match_mode'])
        
        if match_mode == 'any':
            matched = len(matched_conditions) > 0
        else:  # 'all'
            matched = len(matched_conditions) == total_conditions and total_conditions > 0
        
        return RuleMatch(
            rule=rule,
            matched=matched,
            matched_conditions=matched_conditions
        )
    
    def _execute_rule(
        self, 
        rule: AutoRule, 
        raw_email: RawEmail
    ) -> RuleExecutionResult:
        """
        Führt die Aktionen einer gematchten Regel aus.
        """
        actions = rule.actions
        executed = []
        error = None
        
        try:
            # Move to Folder
            if 'move_to_folder' in actions:
                target_folder = actions['move_to_folder']
                result = self.mail_sync.move_email(
                    uid=raw_email.imap_uid,
                    source_folder=raw_email.imap_folder,
                    target_folder=target_folder
                )
                if result.success:
                    # DB aktualisieren
                    raw_email.imap_folder = result.target_folder
                    raw_email.imap_uid = result.target_uid
                    raw_email.imap_uidvalidity = result.target_uidvalidity
                    executed.append(f"move_to:{target_folder}")
            
            # Mark as Read
            if actions.get('mark_as_read'):
                success = self.mail_sync.mark_as_read(
                    uid=raw_email.imap_uid,
                    folder=raw_email.imap_folder
                )
                if success:
                    raw_email.imap_is_seen = True
                    executed.append("mark_as_read")
            
            # Mark as Flagged
            if actions.get('mark_as_flagged'):
                success = self.mail_sync.add_flag(
                    uid=raw_email.imap_uid,
                    folder=raw_email.imap_folder,
                    flag='\\Flagged'
                )
                if success:
                    raw_email.imap_is_flagged = True
                    executed.append("mark_as_flagged")
            
            # Apply Tag (lokal in DB)
            if 'apply_tag' in actions:
                tag_name = actions['apply_tag']
                # Tag-Logik hier (abhängig von deinem Tag-System)
                executed.append(f"apply_tag:{tag_name}")
            
            # Set Priority (in ProcessedEmail)
            if 'set_priority' in actions:
                priority = actions['set_priority']
                processed = ProcessedEmail.query.filter_by(raw_email_id=raw_email.id).first()
                if processed:
                    if priority == 'low':
                        processed.dringlichkeit = 1
                        processed.wichtigkeit = 1
                    elif priority == 'high':
                        processed.dringlichkeit = 3
                        processed.wichtigkeit = 3
                    executed.append(f"set_priority:{priority}")
            
            # Statistik aktualisieren
            rule.times_triggered += 1
            rule.last_triggered_at = datetime.now(UTC)
            
            db.session.commit()
            
            logger.info(f"✅ Regel '{rule.name}' ausgeführt für Email {raw_email.id}: {executed}")
            
            return RuleExecutionResult(
                rule_id=rule.id,
                rule_name=rule.name,
                email_id=raw_email.id,
                success=True,
                actions_executed=executed
            )
            
        except Exception as e:
            db.session.rollback()
            error = str(e)
            logger.error(f"❌ Regel '{rule.name}' fehlgeschlagen: {e}")
            
            return RuleExecutionResult(
                rule_id=rule.id,
                rule_name=rule.name,
                email_id=raw_email.id,
                success=False,
                actions_executed=executed,
                error=error
            )


# === VORDEFINIERTE REGEL-TEMPLATES ===

RULE_TEMPLATES = {
    "newsletter_archive": {
        "name": "Newsletter automatisch archivieren",
        "description": "Verschiebt Newsletter in den Archiv-Ordner und markiert als gelesen",
        "conditions": {
            "match_mode": "any",
            "sender_contains": "newsletter",
            "body_contains": "unsubscribe"
        },
        "actions": {
            "move_to_folder": "Archive",
            "mark_as_read": True,
            "apply_tag": "Newsletter"
        }
    },
    "spam_delete": {
        "name": "Spam-Keywords → Papierkorb",
        "description": "Emails mit Spam-Keywords direkt in den Papierkorb",
        "conditions": {
            "match_mode": "any",
            "subject_contains": "[SPAM]",
            "subject_regex": "(?i)(viagra|lottery|winner|prize)"
        },
        "actions": {
            "move_to_folder": "Trash",
            "mark_as_read": True
        }
    },
    "important_sender": {
        "name": "Wichtiger Absender",
        "description": "Emails von bestimmten Absendern als wichtig markieren",
        "conditions": {
            "sender_domain": "example.com"
        },
        "actions": {
            "mark_as_flagged": True,
            "set_priority": "high"
        }
    }
}


def create_rule_from_template(
    user_id: int,
    template_name: str,
    overrides: Optional[Dict] = None
) -> Optional[AutoRule]:
    """
    Erstellt eine neue Regel aus einem Template.
    
    Args:
        user_id: User-ID
        template_name: Name des Templates (newsletter_archive, spam_delete, etc.)
        overrides: Optionale Überschreibungen für conditions/actions
        
    Returns:
        Erstellte AutoRule oder None
    """
    if template_name not in RULE_TEMPLATES:
        return None
    
    template = RULE_TEMPLATES[template_name].copy()
    
    if overrides:
        if 'conditions' in overrides:
            template['conditions'].update(overrides['conditions'])
        if 'actions' in overrides:
            template['actions'].update(overrides['actions'])
    
    rule = AutoRule(
        user_id=user_id,
        name=template['name'],
        description=template.get('description'),
        conditions=template['conditions'],
        actions=template['actions']
    )
    
    db.session.add(rule)
    db.session.commit()
    
    return rule
```

---

#### 2. Web-Routes für Rules Management: `src/01_web_app.py`

```python
# === ERGÄNZUNG in src/01_web_app.py ===

from src.18_auto_rules import AutoRulesEngine, RULE_TEMPLATES, create_rule_from_template


# === RULES CRUD ===

@app.route('/api/rules', methods=['GET'])
@login_required
def api_list_rules():
    """Listet alle Regeln des Users"""
    rules = AutoRule.query.filter_by(user_id=current_user.id)\
        .order_by(AutoRule.priority.asc()).all()
    
    return jsonify({
        "success": True,
        "rules": [{
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "is_active": r.is_active,
            "priority": r.priority,
            "conditions": r.conditions,
            "actions": r.actions,
            "times_triggered": r.times_triggered,
            "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None
        } for r in rules]
    })


@app.route('/api/rules', methods=['POST'])
@login_required
def api_create_rule():
    """Erstellt eine neue Regel"""
    data = request.get_json()
    
    # Validierung
    if not data.get('name'):
        return jsonify({"success": False, "error": "Name ist erforderlich"}), 400
    
    if not data.get('conditions'):
        return jsonify({"success": False, "error": "Mindestens eine Bedingung erforderlich"}), 400
    
    if not data.get('actions'):
        return jsonify({"success": False, "error": "Mindestens eine Aktion erforderlich"}), 400
    
    rule = AutoRule(
        user_id=current_user.id,
        name=data['name'],
        description=data.get('description'),
        priority=data.get('priority', 100),
        conditions=data['conditions'],
        actions=data['actions']
    )
    
    db.session.add(rule)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "rule_id": rule.id,
        "message": f"Regel '{rule.name}' erstellt"
    })


@app.route('/api/rules/<int:rule_id>', methods=['PUT'])
@login_required
def api_update_rule(rule_id):
    """Aktualisiert eine Regel"""
    rule = AutoRule.query.get(rule_id)
    
    if not rule or rule.user_id != current_user.id:
        return jsonify({"success": False, "error": "Regel nicht gefunden"}), 404
    
    data = request.get_json()
    
    if 'name' in data:
        rule.name = data['name']
    if 'description' in data:
        rule.description = data['description']
    if 'is_active' in data:
        rule.is_active = data['is_active']
    if 'priority' in data:
        rule.priority = data['priority']
    if 'conditions' in data:
        rule.conditions = data['conditions']
    if 'actions' in data:
        rule.actions = data['actions']
    
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Regel '{rule.name}' aktualisiert"
    })


@app.route('/api/rules/<int:rule_id>', methods=['DELETE'])
@login_required
def api_delete_rule(rule_id):
    """Löscht eine Regel"""
    rule = AutoRule.query.get(rule_id)
    
    if not rule or rule.user_id != current_user.id:
        return jsonify({"success": False, "error": "Regel nicht gefunden"}), 404
    
    rule_name = rule.name
    db.session.delete(rule)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "message": f"Regel '{rule_name}' gelöscht"
    })


# === RULE TEMPLATES ===

@app.route('/api/rules/templates', methods=['GET'])
@login_required
def api_list_rule_templates():
    """Listet verfügbare Regel-Templates"""
    return jsonify({
        "success": True,
        "templates": {
            name: {
                "name": t["name"],
                "description": t.get("description"),
                "conditions": t["conditions"],
                "actions": t["actions"]
            }
            for name, t in RULE_TEMPLATES.items()
        }
    })


@app.route('/api/rules/from-template', methods=['POST'])
@login_required
def api_create_from_template():
    """Erstellt Regel aus Template"""
    data = request.get_json()
    template_name = data.get('template')
    
    if not template_name:
        return jsonify({"success": False, "error": "Template-Name erforderlich"}), 400
    
    rule = create_rule_from_template(
        user_id=current_user.id,
        template_name=template_name,
        overrides=data.get('overrides')
    )
    
    if rule:
        return jsonify({
            "success": True,
            "rule_id": rule.id,
            "message": f"Regel '{rule.name}' aus Template erstellt"
        })
    else:
        return jsonify({
            "success": False,
            "error": f"Template '{template_name}' nicht gefunden"
        }), 404


# === RULE TESTING ===

@app.route('/api/rules/test/<int:rule_id>', methods=['POST'])
@login_required
def api_test_rule(rule_id):
    """
    Testet eine Regel gegen ausgewählte Emails (Dry-Run).
    
    POST Body:
    {
        "email_ids": [1, 2, 3]  // Optional, sonst letzte 20 Emails
    }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({"success": False, "error": "Nicht authentifiziert"}), 401
    
    rule = AutoRule.query.get(rule_id)
    if not rule or rule.user_id != current_user.id:
        return jsonify({"success": False, "error": "Regel nicht gefunden"}), 404
    
    data = request.get_json() or {}
    email_ids = data.get('email_ids')
    
    # Falls keine IDs angegeben, letzte 20 Emails nehmen
    if not email_ids:
        recent_emails = RawEmail.query.filter_by(user_id=current_user.id)\
            .order_by(RawEmail.received_at.desc())\
            .limit(20).all()
        email_ids = [e.id for e in recent_emails]
    
    engine = AutoRulesEngine(current_user.id, master_key)
    
    matches = []
    for email_id in email_ids:
        raw_email = RawEmail.query.get(email_id)
        if not raw_email or raw_email.user_id != current_user.id:
            continue
        
        email_data = engine._decrypt_email_for_matching(raw_email)
        if email_data:
            match = engine._match_rule(rule, email_data)
            if match.matched:
                matches.append({
                    "email_id": email_id,
                    "subject": email_data['subject'][:50] + "..." if len(email_data['subject']) > 50 else email_data['subject'],
                    "sender": email_data['sender'],
                    "matched_conditions": match.matched_conditions
                })
    
    return jsonify({
        "success": True,
        "rule_name": rule.name,
        "emails_tested": len(email_ids),
        "matches_found": len(matches),
        "matches": matches
    })


# === MANUAL RULE EXECUTION ===

@app.route('/api/rules/run', methods=['POST'])
@login_required
def api_run_rules():
    """
    Führt alle aktiven Regeln auf neue/ausgewählte Emails aus.
    
    POST Body:
    {
        "email_ids": [1, 2, 3],  // Optional, sonst neue Emails der letzten Stunde
        "dry_run": false
    }
    """
    master_key = session.get('master_key')
    if not master_key:
        return jsonify({"success": False, "error": "Nicht authentifiziert"}), 401
    
    data = request.get_json() or {}
    email_ids = data.get('email_ids')
    dry_run = data.get('dry_run', False)
    
    engine = AutoRulesEngine(current_user.id, master_key)
    
    if email_ids:
        # Spezifische Emails verarbeiten
        all_results = []
        for email_id in email_ids:
            results = engine.process_email(email_id, dry_run=dry_run)
            all_results.extend(results)
        
        return jsonify({
            "success": True,
            "dry_run": dry_run,
            "emails_processed": len(email_ids),
            "rules_triggered": len([r for r in all_results if r.success]),
            "results": [{
                "email_id": r.email_id,
                "rule_name": r.rule_name,
                "success": r.success,
                "actions": r.actions_executed,
                "error": r.error
            } for r in all_results]
        })
    else:
        # Neue Emails verarbeiten
        stats = engine.process_new_emails()
        return jsonify({
            "success": True,
            "dry_run": dry_run,
            "stats": stats
        })
```

---

#### 3. Background-Job Integration: `src/14_background_jobs.py`

```python
# === ERGÄNZUNG in src/14_background_jobs.py ===

from src.18_auto_rules import AutoRulesEngine


def run_auto_rules_job(user_id: int, master_key: str) -> Dict[str, Any]:
    """
    Background-Job: Führt Auto-Rules für neue Emails aus.
    Wird nach jedem Email-Fetch aufgerufen.
    """
    try:
        engine = AutoRulesEngine(user_id, master_key)
        stats = engine.process_new_emails(since_minutes=60, limit=100)
        
        logger.info(
            f"🤖 Auto-Rules Job: {stats['emails_checked']} Emails geprüft, "
            f"{stats['rules_triggered']} Regeln ausgelöst, "
            f"{stats['actions_executed']} Aktionen ausgeführt"
        )
        
        return {
            "success": True,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Auto-Rules Job fehlgeschlagen: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# In der bestehenden fetch_and_process_emails() Funktion ergänzen:

def fetch_and_process_emails(user_id: int, master_key: str):
    """Bestehende Funktion erweitern"""
    
    # ... bestehender Fetch-Code ...
    
    # NEU: Auto-Rules nach Fetch ausführen
    if new_emails_count > 0:
        auto_rules_result = run_auto_rules_job(user_id, master_key)
        logger.info(f"Auto-Rules: {auto_rules_result}")
    
    # ... rest ...
```

---

## 📊 Zusammenfassung & Implementierungsplan

### Zeitplan

| Phase | Task | Aufwand | Abhängigkeit |
|-------|------|---------|--------------|
| **G.1a** | ReplyDraftService erstellen | 2h | - |
| **G.1b** | AI Client `generate_text()` | 1h | G.1a |
| **G.1c** | API-Endpoint | 1h | G.1b |
| **G.1d** | Frontend-Integration | 1-2h | G.1c |
| | **Subtotal G.1** | **5-6h** | |
| **G.2a** | DB-Schema (AutoRule) | 0.5h | - |
| **G.2b** | AutoRulesEngine | 3h | G.2a |
| **G.2c** | CRUD-Endpoints | 1.5h | G.2b |
| **G.2d** | Background-Job Integration | 1h | G.2c |
| **G.2e** | Rules-UI (Settings-Seite) | 2h | G.2c |
| | **Subtotal G.2** | **8h** | |
| | **TOTAL Phase G** | **13-14h** | |

### Dateien zu erstellen/ändern

```
NEU:
├── src/17_reply_service.py       # G.1: Reply Draft Service
├── src/18_auto_rules.py          # G.2: Auto-Rules Engine
└── templates/settings_rules.html # G.2: Rules Management UI

ÄNDERN:
├── src/02_models.py              # G.2: AutoRule Model
├── src/03_ai_client.py           # G.1: generate_text() Methode
├── src/01_web_app.py             # G.1+G.2: Neue Endpoints
├── src/14_background_jobs.py     # G.2: Auto-Rules Integration
└── templates/email_detail.html   # G.1: Reply-Draft UI
```

### Empfohlene Reihenfolge

1. **Woche 1:** G.1 (Reply Draft Generator)
   - Sofort sichtbarer User-Value
   - Weniger Komplexität
   - Baut auf bestehender Infrastructure auf

2. **Woche 2:** G.2 (Auto-Action Rules)
   - Löst Newsletter-Problem
   - Mehr Moving Parts (DB, Engine, Jobs)
   - Braucht gründlicheres Testing

---

## ✅ Nächste Schritte

1. **Heute:** Dieses Dokument reviewen
2. **Morgen:** Mit G.1a starten (ReplyDraftService)
3. **Diese Woche:** G.1 komplett
4. **Nächste Woche:** G.2

Soll ich mit einem bestimmten Teil beginnen?
