/**
 * SMTP Sender Frontend Integration
 * 
 * Diese Datei zeigt die JavaScript-Integration für:
 * - Reply Draft generieren + senden
 * - Neue Emails senden
 * - SMTP-Status prüfen
 * 
 * Integration in templates/email_detail.html
 */

// ============================================================================
// SMTP SENDER CLASS
// ============================================================================

class EmailSender {
    constructor(emailId, accountId) {
        this.emailId = emailId;
        this.accountId = accountId;
        this.smtpConfigured = null;
    }
    
    /**
     * Prüft ob SMTP für den Account konfiguriert ist
     */
    async checkSMTPStatus() {
        try {
            const response = await fetch(`/api/account/${this.accountId}/smtp-status`, {
                headers: { 'X-CSRFToken': this.getCSRFToken() }
            });
            const data = await response.json();
            this.smtpConfigured = data.configured;
            return data;
        } catch (error) {
            console.error('SMTP Status Check fehlgeschlagen:', error);
            return { configured: false, error: error.message };
        }
    }
    
    /**
     * Testet die SMTP-Verbindung
     */
    async testConnection() {
        const response = await fetch(`/api/account/${this.accountId}/test-smtp`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            }
        });
        return await response.json();
    }
    
    /**
     * Sendet eine Antwort auf die aktuelle Email
     */
    async sendReply(replyText, options = {}) {
        const payload = {
            reply_text: replyText,
            reply_html: options.replyHtml || null,
            include_quote: options.includeQuote !== false,
            cc: options.cc || [],
            attachments: options.attachments || []
        };
        
        const response = await fetch(`/api/email/${this.emailId}/send-reply`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(payload)
        });
        
        return await response.json();
    }
    
    /**
     * Generiert einen KI-Entwurf und sendet optional direkt
     */
    async generateAndSend(tone, options = {}) {
        const payload = {
            tone: tone,
            custom_instructions: options.customInstructions || null,
            include_quote: options.includeQuote !== false,
            send_immediately: options.sendImmediately || false
        };
        
        const response = await fetch(`/api/email/${this.emailId}/generate-and-send`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCSRFToken()
            },
            body: JSON.stringify(payload)
        });
        
        return await response.json();
    }
    
    getCSRFToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content || '';
    }
}


// ============================================================================
// ENHANCED REPLY DRAFT GENERATOR (mit Send-Funktion)
// ============================================================================

class EnhancedReplyDraftGenerator {
    constructor(emailId, accountId) {
        this.emailId = emailId;
        this.accountId = accountId;
        this.sender = new EmailSender(emailId, accountId);
        this.currentDraft = null;
        this.smtpReady = false;
        
        this.init();
    }
    
    async init() {
        // SMTP-Status prüfen
        const status = await this.sender.checkSMTPStatus();
        this.smtpReady = status.configured;
        
        this.createUI();
        this.bindEvents();
        this.updateSendButtonState();
    }
    
    createUI() {
        const html = `
        <div class="card mt-3" id="reply-draft-card">
            <div class="card-header d-flex justify-content-between align-items-center">
                <h6 class="mb-0">
                    <i class="bi bi-pencil-square"></i> Antwort-Entwurf generieren
                </h6>
                <span class="badge ${this.smtpReady ? 'bg-success' : 'bg-warning'}" 
                      id="smtp-status-badge">
                    ${this.smtpReady ? '✓ SMTP bereit' : '⚠ SMTP nicht konfiguriert'}
                </span>
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
                
                <!-- Zusätzliche Anweisungen -->
                <div class="mb-3">
                    <label class="form-label">Zusätzliche Anweisungen (optional):</label>
                    <textarea class="form-control" id="custom-instructions" rows="2" 
                              placeholder="z.B. 'Termine vorschlagen' oder 'Höflich ablehnen'"></textarea>
                </div>
                
                <!-- Optionen -->
                <div class="mb-3">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="include-quote" checked>
                        <label class="form-check-label" for="include-quote">
                            Original-Nachricht zitieren
                        </label>
                    </div>
                </div>
                
                <!-- Generieren-Button -->
                <button class="btn btn-primary w-100" id="generate-draft-btn">
                    <i class="bi bi-magic"></i> Entwurf generieren
                </button>
                
                <!-- Loading -->
                <div class="text-center mt-3 d-none" id="draft-loading">
                    <div class="spinner-border text-primary" role="status"></div>
                    <p class="mt-2 text-muted">KI generiert Antwort...</p>
                </div>
                
                <!-- Ergebnis -->
                <div class="mt-3 d-none" id="draft-result">
                    <hr>
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <strong>Generierter Entwurf:</strong>
                        <div>
                            <span class="badge bg-secondary" id="draft-meta"></span>
                            <button class="btn btn-sm btn-link" id="edit-draft-btn" title="Bearbeiten">
                                <i class="bi bi-pencil"></i>
                            </button>
                        </div>
                    </div>
                    
                    <!-- Draft Text (editierbar) -->
                    <div id="draft-view-mode">
                        <div class="border rounded p-3 bg-light" id="draft-text"
                             style="white-space: pre-wrap;"></div>
                    </div>
                    <div id="draft-edit-mode" class="d-none">
                        <textarea class="form-control" id="draft-textarea" rows="10"></textarea>
                        <div class="mt-2">
                            <button class="btn btn-sm btn-success" id="save-edit-btn">
                                <i class="bi bi-check"></i> Übernehmen
                            </button>
                            <button class="btn btn-sm btn-secondary" id="cancel-edit-btn">
                                Abbrechen
                            </button>
                        </div>
                    </div>
                    
                    <!-- Action-Buttons -->
                    <div class="mt-3 d-flex gap-2 flex-wrap">
                        <button class="btn btn-success" id="send-reply-btn" 
                                ${!this.smtpReady ? 'disabled' : ''}>
                            <i class="bi bi-send"></i> Absenden
                        </button>
                        <button class="btn btn-outline-success" id="copy-draft-btn">
                            <i class="bi bi-clipboard"></i> Kopieren
                        </button>
                        <button class="btn btn-outline-primary" id="open-mailclient-btn">
                            <i class="bi bi-envelope"></i> In Mail-Client
                        </button>
                        <button class="btn btn-outline-secondary" id="regenerate-btn">
                            <i class="bi bi-arrow-clockwise"></i> Neu generieren
                        </button>
                    </div>
                    
                    <!-- Send Status -->
                    <div class="mt-3 d-none" id="send-status"></div>
                </div>
                
                <!-- Fehler -->
                <div class="alert alert-danger mt-3 d-none" id="draft-error"></div>
            </div>
        </div>
        `;
        
        const emailContent = document.querySelector('.email-content');
        if (emailContent) {
            emailContent.insertAdjacentHTML('afterend', html);
        }
    }
    
    bindEvents() {
        // Generieren
        document.getElementById('generate-draft-btn')
            .addEventListener('click', () => this.generateDraft());
        
        // Regenerieren
        document.getElementById('regenerate-btn')
            .addEventListener('click', () => this.generateDraft());
        
        // Kopieren
        document.getElementById('copy-draft-btn')
            .addEventListener('click', () => this.copyToClipboard());
        
        // Mail-Client öffnen
        document.getElementById('open-mailclient-btn')
            .addEventListener('click', () => this.openMailClient());
        
        // Senden
        document.getElementById('send-reply-btn')
            .addEventListener('click', () => this.sendReply());
        
        // Bearbeiten Toggle
        document.getElementById('edit-draft-btn')
            .addEventListener('click', () => this.toggleEditMode(true));
        document.getElementById('save-edit-btn')
            .addEventListener('click', () => this.saveEdit());
        document.getElementById('cancel-edit-btn')
            .addEventListener('click', () => this.toggleEditMode(false));
    }
    
    async generateDraft() {
        const tone = document.querySelector('input[name="tone"]:checked').value;
        const customInstructions = document.getElementById('custom-instructions').value;
        
        this.showLoading(true);
        this.hideError();
        this.hideResult();
        
        try {
            const response = await fetch(`/api/email/${this.emailId}/generate-reply`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': this.sender.getCSRFToken()
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
                this.showError(data.error);
            }
        } catch (error) {
            this.showError(`Fehler: ${error.message}`);
        } finally {
            this.showLoading(false);
        }
    }
    
    showResult(draft) {
        this.currentDraft = draft;
        
        document.getElementById('draft-text').textContent = draft.draft_text;
        document.getElementById('draft-textarea').value = draft.draft_text;
        document.getElementById('draft-meta').textContent = 
            `${draft.model_used} • ${draft.generation_time_ms}ms`;
        
        document.getElementById('draft-result').classList.remove('d-none');
    }
    
    hideResult() {
        document.getElementById('draft-result').classList.add('d-none');
    }
    
    showLoading(show) {
        document.getElementById('draft-loading').classList.toggle('d-none', !show);
        document.getElementById('generate-draft-btn').disabled = show;
    }
    
    showError(message) {
        const el = document.getElementById('draft-error');
        el.textContent = message;
        el.classList.remove('d-none');
    }
    
    hideError() {
        document.getElementById('draft-error').classList.add('d-none');
    }
    
    toggleEditMode(edit) {
        document.getElementById('draft-view-mode').classList.toggle('d-none', edit);
        document.getElementById('draft-edit-mode').classList.toggle('d-none', !edit);
    }
    
    saveEdit() {
        const newText = document.getElementById('draft-textarea').value;
        this.currentDraft.draft_text = newText;
        document.getElementById('draft-text').textContent = newText;
        this.toggleEditMode(false);
    }
    
    async copyToClipboard() {
        if (!this.currentDraft) return;
        
        try {
            await navigator.clipboard.writeText(this.currentDraft.draft_text);
            this.showButtonFeedback('copy-draft-btn', '✓ Kopiert!', 'btn-outline-success', 'btn-success');
        } catch (err) {
            this.showError('Kopieren fehlgeschlagen');
        }
    }
    
    openMailClient() {
        if (!this.currentDraft) return;
        
        const subject = encodeURIComponent(this.currentDraft.subject);
        const body = encodeURIComponent(this.currentDraft.draft_text);
        const to = encodeURIComponent(this.currentDraft.recipient);
        
        window.location.href = `mailto:${to}?subject=${subject}&body=${body}`;
    }
    
    async sendReply() {
        if (!this.currentDraft || !this.smtpReady) return;
        
        const sendBtn = document.getElementById('send-reply-btn');
        const statusDiv = document.getElementById('send-status');
        
        sendBtn.disabled = true;
        sendBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Sende...';
        
        try {
            const includeQuote = document.getElementById('include-quote').checked;
            
            const result = await this.sender.sendReply(this.currentDraft.draft_text, {
                includeQuote: includeQuote
            });
            
            if (result.success) {
                statusDiv.className = 'mt-3 alert alert-success';
                statusDiv.innerHTML = `
                    <i class="bi bi-check-circle"></i> <strong>Email gesendet!</strong><br>
                    <small>
                        Message-ID: ${result.message_id}<br>
                        ${result.saved_to_sent ? `✓ Im Ordner "${result.sent_folder}" gespeichert` : ''}<br>
                        ${result.saved_to_db ? '✓ In Datenbank gespeichert' : ''}
                    </small>
                `;
                statusDiv.classList.remove('d-none');
                
                sendBtn.innerHTML = '<i class="bi bi-check"></i> Gesendet!';
                sendBtn.classList.replace('btn-success', 'btn-outline-success');
            } else {
                statusDiv.className = 'mt-3 alert alert-danger';
                statusDiv.innerHTML = `<i class="bi bi-x-circle"></i> Fehler: ${result.error}`;
                statusDiv.classList.remove('d-none');
                
                sendBtn.disabled = false;
                sendBtn.innerHTML = '<i class="bi bi-send"></i> Absenden';
            }
        } catch (error) {
            statusDiv.className = 'mt-3 alert alert-danger';
            statusDiv.innerHTML = `<i class="bi bi-x-circle"></i> Fehler: ${error.message}`;
            statusDiv.classList.remove('d-none');
            
            sendBtn.disabled = false;
            sendBtn.innerHTML = '<i class="bi bi-send"></i> Absenden';
        }
    }
    
    updateSendButtonState() {
        const sendBtn = document.getElementById('send-reply-btn');
        if (sendBtn) {
            sendBtn.disabled = !this.smtpReady;
            if (!this.smtpReady) {
                sendBtn.title = 'SMTP nicht konfiguriert - bitte in Einstellungen aktivieren';
            }
        }
    }
    
    showButtonFeedback(btnId, text, oldClass, newClass) {
        const btn = document.getElementById(btnId);
        const original = btn.innerHTML;
        btn.innerHTML = text;
        btn.classList.replace(oldClass, newClass);
        setTimeout(() => {
            btn.innerHTML = original;
            btn.classList.replace(newClass, oldClass);
        }, 2000);
    }
}


// ============================================================================
// INITIALISIERUNG
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
    // Email-Detail-Seite erkennen
    const emailIdMatch = window.location.pathname.match(/\/email\/(\d+)/);
    
    if (emailIdMatch) {
        const emailId = parseInt(emailIdMatch[1]);
        
        // Account-ID aus der Seite extrahieren (muss im HTML vorhanden sein)
        const accountIdEl = document.querySelector('[data-account-id]');
        const accountId = accountIdEl ? parseInt(accountIdEl.dataset.accountId) : null;
        
        if (accountId) {
            // Enhanced Generator mit Send-Funktion initialisieren
            window.replyGenerator = new EnhancedReplyDraftGenerator(emailId, accountId);
        } else {
            // Fallback: Nur Draft-Generator ohne Send
            console.warn('Account-ID nicht gefunden, SMTP-Versand deaktiviert');
        }
    }
});
