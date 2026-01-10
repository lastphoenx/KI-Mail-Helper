/**
 * Semantic Search Frontend (Phase 15)
 * ====================================
 * 
 * Dieses Script erweitert die bestehende Suche um Semantic Search.
 * Füge es in die relevanten Templates ein (z.B. liste.html, base.html).
 */

// =============================================================================
// KONFIGURATION
// =============================================================================

const SemanticSearch = {
    // Standard-Einstellungen
    config: {
        defaultThreshold: 0.25,
        maxResults: 50,
        debounceMs: 300,
        minQueryLength: 2
    },
    
    // State
    isSemanticMode: false,
    lastQuery: '',
    
    // ==========================================================================
    // INITIALIZATION
    // ==========================================================================
    
    init() {
        this.setupToggle();
        this.setupSearchInput();
        this.checkEmbeddingStatus();
    },
    
    setupToggle() {
        // Toggle-Button für Semantic/Text-Suche erstellen
        const searchContainer = document.querySelector('.search-container, #search-box, [data-search]');
        if (!searchContainer) return;
        
        const toggle = document.createElement('label');
        toggle.className = 'semantic-toggle';
        toggle.innerHTML = `
            <input type="checkbox" id="semantic-toggle" />
            <span class="toggle-label">🧠 Semantic</span>
        `;
        toggle.title = 'Semantische Suche: Findet auch ähnliche Begriffe';
        
        searchContainer.appendChild(toggle);
        
        document.getElementById('semantic-toggle')?.addEventListener('change', (e) => {
            this.isSemanticMode = e.target.checked;
            this.updateSearchPlaceholder();
            
            // Re-run search if there's a query
            if (this.lastQuery) {
                this.performSearch(this.lastQuery);
            }
        });
    },
    
    setupSearchInput() {
        const searchInput = document.querySelector('#search-input, input[type="search"], [data-search-input]');
        if (!searchInput) return;
        
        let debounceTimer;
        
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.trim();
            
            clearTimeout(debounceTimer);
            
            if (query.length < this.config.minQueryLength) {
                this.clearResults();
                return;
            }
            
            debounceTimer = setTimeout(() => {
                this.lastQuery = query;
                this.performSearch(query);
            }, this.config.debounceMs);
        });
    },
    
    updateSearchPlaceholder() {
        const searchInput = document.querySelector('#search-input, input[type="search"]');
        if (searchInput) {
            searchInput.placeholder = this.isSemanticMode 
                ? '🧠 Semantische Suche... (findet ähnliche Begriffe)'
                : '🔍 Suche...';
        }
    },
    
    // ==========================================================================
    // SEARCH
    // ==========================================================================
    
    async performSearch(query) {
        if (this.isSemanticMode) {
            await this.semanticSearch(query);
        } else {
            // Fallback zur bestehenden Text-Suche
            this.textSearch(query);
        }
    },
    
    async semanticSearch(query) {
        const resultsContainer = this.getResultsContainer();
        
        // Loading-State
        this.showLoading(resultsContainer);
        
        try {
            const response = await fetch(
                `/api/search/semantic?q=${encodeURIComponent(query)}&limit=${this.config.maxResults}`,
                {
                    headers: {
                        'X-CSRFToken': this.getCsrfToken()
                    }
                }
            );
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            this.displaySemanticResults(data, resultsContainer);
            
        } catch (error) {
            console.error('Semantic Search Fehler:', error);
            this.showError(resultsContainer, 'Suche fehlgeschlagen. Ist Ollama aktiv?');
        }
    },
    
    textSearch(query) {
        // Bestehende Text-Suche aufrufen (falls vorhanden)
        if (typeof window.performTextSearch === 'function') {
            window.performTextSearch(query);
        } else {
            // Fallback: Seite mit Query-Parameter neu laden
            const url = new URL(window.location);
            url.searchParams.set('search', query);
            window.location.href = url.toString();
        }
    },
    
    // ==========================================================================
    // RESULTS DISPLAY
    // ==========================================================================
    
    displaySemanticResults(data, container) {
        if (!data.results || data.results.length === 0) {
            container.innerHTML = `
                <div class="no-results">
                    <p>🔍 Keine Ergebnisse für "<strong>${this.escapeHtml(data.query)}</strong>"</p>
                    <p class="hint">Versuche andere Begriffe oder deaktiviere Semantic Search</p>
                </div>
            `;
            return;
        }
        
        const resultsHtml = data.results.map(r => `
            <div class="search-result semantic-result" data-email-id="${r.email_id}">
                <div class="result-header">
                    <span class="similarity-badge ${this.getSimilarityClass(r.similarity)}">
                        ${r.similarity_percent}% Match
                    </span>
                    <span class="result-date">${this.formatDate(r.received_at)}</span>
                </div>
                <div class="result-subject">
                    <a href="/email/${r.email_id}">${this.escapeHtml(r.subject || '(Kein Betreff)')}</a>
                </div>
                <div class="result-sender">${this.escapeHtml(r.sender)}</div>
                <div class="result-meta">
                    <span class="folder">📁 ${this.escapeHtml(r.folder)}</span>
                    ${r.thread_id ? '<span class="thread">💬 Thread</span>' : ''}
                </div>
            </div>
        `).join('');
        
        container.innerHTML = `
            <div class="search-results-header">
                <span>${data.total_results} Ergebnisse</span>
                <span class="search-mode">🧠 Semantic Search</span>
            </div>
            <div class="search-results-list">
                ${resultsHtml}
            </div>
        `;
        
        // Click-Handler für Ergebnisse
        container.querySelectorAll('.search-result').forEach(el => {
            el.addEventListener('click', (e) => {
                if (e.target.tagName !== 'A') {
                    const emailId = el.dataset.emailId;
                    window.location.href = `/email/${emailId}`;
                }
            });
        });
    },
    
    getSimilarityClass(similarity) {
        if (similarity >= 0.8) return 'similarity-high';
        if (similarity >= 0.5) return 'similarity-medium';
        return 'similarity-low';
    },
    
    // ==========================================================================
    // SIMILAR EMAILS (für Detail-Ansicht)
    // ==========================================================================
    
    async loadSimilarEmails(emailId, containerId) {
        const container = document.getElementById(containerId);
        if (!container) return;
        
        this.showLoading(container);
        
        try {
            const response = await fetch(`/api/emails/${emailId}/similar?limit=5`, {
                headers: { 'X-CSRFToken': this.getCsrfToken() }
            });
            
            if (!response.ok) {
                if (response.status === 400) {
                    // Keine Embeddings
                    container.innerHTML = `
                        <div class="no-embeddings">
                            <p>⚠️ Keine Embeddings vorhanden</p>
                            <button onclick="SemanticSearch.generateEmbeddings()">
                                Embeddings generieren
                            </button>
                        </div>
                    `;
                    return;
                }
                throw new Error(`HTTP ${response.status}`);
            }
            
            const data = await response.json();
            this.displaySimilarEmails(data, container);
            
        } catch (error) {
            console.error('Similar Emails Fehler:', error);
            container.innerHTML = '<p class="error">Fehler beim Laden</p>';
        }
    },
    
    displaySimilarEmails(data, container) {
        if (!data.similar_emails || data.similar_emails.length === 0) {
            container.innerHTML = '<p class="no-similar">Keine ähnlichen Emails gefunden</p>';
            return;
        }
        
        const html = data.similar_emails.map(email => `
            <div class="similar-email">
                <a href="/email/${email.email_id}">
                    <span class="similarity">${email.similarity_percent}%</span>
                    <span class="subject">${this.escapeHtml(email.subject)}</span>
                </a>
                <div class="meta">${this.escapeHtml(email.sender)} • ${this.formatDate(email.received_at)}</div>
            </div>
        `).join('');
        
        container.innerHTML = `
            <h4>📎 Ähnliche Emails</h4>
            ${html}
        `;
    },
    
    // ==========================================================================
    // EMBEDDING MANAGEMENT
    // ==========================================================================
    
    async checkEmbeddingStatus() {
        try {
            const response = await fetch('/api/embeddings/stats');
            const stats = await response.json();
            
            // Badge anzeigen wenn nicht alle Emails Embeddings haben
            if (stats.without_embedding > 0) {
                this.showEmbeddingWarning(stats);
            }
        } catch (error) {
            console.log('Embedding-Stats nicht verfügbar');
        }
    },
    
    showEmbeddingWarning(stats) {
        const toggle = document.getElementById('semantic-toggle');
        if (!toggle) return;
        
        const warning = document.createElement('span');
        warning.className = 'embedding-warning';
        warning.innerHTML = `⚠️ ${stats.without_embedding} Emails ohne Embedding`;
        warning.title = `${stats.coverage_percent}% Coverage. Klicke um Embeddings zu generieren.`;
        warning.style.cursor = 'pointer';
        warning.onclick = () => this.generateEmbeddings();
        
        toggle.parentElement.appendChild(warning);
    },
    
    async generateEmbeddings() {
        const btn = event?.target;
        if (btn) {
            btn.disabled = true;
            btn.textContent = '⏳ Generiere...';
        }
        
        try {
            const response = await fetch('/api/embeddings/generate', {
                method: 'POST',
                headers: { 'X-CSRFToken': this.getCsrfToken() }
            });
            
            const data = await response.json();
            
            if (data.remaining > 0) {
                // Noch mehr zu tun
                alert(`${data.success} Embeddings generiert. Noch ${data.remaining} verbleibend. Bitte erneut ausführen.`);
            } else {
                alert(`✅ ${data.success} Embeddings generiert!`);
                location.reload();
            }
            
        } catch (error) {
            alert('Fehler: ' + error.message);
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Embeddings generieren';
            }
        }
    },
    
    // ==========================================================================
    // HELPERS
    // ==========================================================================
    
    getResultsContainer() {
        let container = document.getElementById('search-results');
        if (!container) {
            container = document.createElement('div');
            container.id = 'search-results';
            container.className = 'search-results-container';
            
            const searchBox = document.querySelector('.search-container, #search-box');
            if (searchBox) {
                searchBox.parentElement.insertBefore(container, searchBox.nextSibling);
            } else {
                document.body.appendChild(container);
            }
        }
        return container;
    },
    
    showLoading(container) {
        container.innerHTML = `
            <div class="loading">
                <span class="spinner">⏳</span> Suche...
            </div>
        `;
    },
    
    showError(container, message) {
        container.innerHTML = `
            <div class="error-message">
                <span>❌</span> ${this.escapeHtml(message)}
            </div>
        `;
    },
    
    clearResults() {
        const container = document.getElementById('search-results');
        if (container) {
            container.innerHTML = '';
        }
    },
    
    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },
    
    formatDate(isoString) {
        if (!isoString) return '';
        try {
            const date = new Date(isoString);
            return date.toLocaleDateString('de-DE', {
                day: '2-digit',
                month: '2-digit',
                year: 'numeric'
            });
        } catch {
            return isoString;
        }
    },
    
    getCsrfToken() {
        return document.querySelector('meta[name="csrf-token"]')?.content 
            || document.querySelector('[name="csrf_token"]')?.value
            || '';
    }
};

// =============================================================================
// AUTO-INIT
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    SemanticSearch.init();
});


// =============================================================================
// CSS (inline oder in separate Datei)
// =============================================================================

const semanticSearchStyles = `
<style>
/* Semantic Toggle */
.semantic-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin-left: 1rem;
    cursor: pointer;
    user-select: none;
}

.semantic-toggle input {
    width: 1.2rem;
    height: 1.2rem;
}

.toggle-label {
    font-size: 0.875rem;
    color: #666;
}

.semantic-toggle input:checked + .toggle-label {
    color: #2563eb;
    font-weight: 600;
}

.embedding-warning {
    font-size: 0.75rem;
    color: #f59e0b;
    margin-left: 0.5rem;
}

/* Search Results */
.search-results-container {
    margin-top: 1rem;
}

.search-results-header {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem;
    background: #f3f4f6;
    border-radius: 0.25rem;
    font-size: 0.875rem;
    margin-bottom: 0.5rem;
}

.search-mode {
    color: #2563eb;
    font-weight: 500;
}

.search-result {
    padding: 1rem;
    border: 1px solid #e5e7eb;
    border-radius: 0.5rem;
    margin-bottom: 0.5rem;
    cursor: pointer;
    transition: all 0.15s;
}

.search-result:hover {
    border-color: #2563eb;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.result-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 0.5rem;
}

.similarity-badge {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.125rem 0.5rem;
    border-radius: 1rem;
}

.similarity-high {
    background: #dcfce7;
    color: #166534;
}

.similarity-medium {
    background: #fef3c7;
    color: #92400e;
}

.similarity-low {
    background: #f3f4f6;
    color: #4b5563;
}

.result-date {
    font-size: 0.75rem;
    color: #9ca3af;
}

.result-subject a {
    color: #111827;
    font-weight: 500;
    text-decoration: none;
}

.result-subject a:hover {
    color: #2563eb;
}

.result-sender {
    font-size: 0.875rem;
    color: #6b7280;
    margin-top: 0.25rem;
}

.result-meta {
    font-size: 0.75rem;
    color: #9ca3af;
    margin-top: 0.5rem;
    display: flex;
    gap: 1rem;
}

/* Similar Emails Widget */
.similar-email {
    padding: 0.5rem;
    border-bottom: 1px solid #e5e7eb;
}

.similar-email:last-child {
    border-bottom: none;
}

.similar-email a {
    display: flex;
    gap: 0.5rem;
    text-decoration: none;
    color: inherit;
}

.similar-email .similarity {
    font-size: 0.75rem;
    color: #2563eb;
    font-weight: 600;
    min-width: 3rem;
}

.similar-email .subject {
    color: #374151;
}

.similar-email .meta {
    font-size: 0.75rem;
    color: #9ca3af;
    margin-top: 0.25rem;
    padding-left: 3.5rem;
}

/* Loading & Error */
.loading {
    padding: 2rem;
    text-align: center;
    color: #6b7280;
}

.spinner {
    animation: spin 1s linear infinite;
    display: inline-block;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.error-message {
    padding: 1rem;
    background: #fef2f2;
    color: #991b1b;
    border-radius: 0.5rem;
}

.no-results {
    padding: 2rem;
    text-align: center;
    color: #6b7280;
}

.no-results .hint {
    font-size: 0.875rem;
    color: #9ca3af;
    margin-top: 0.5rem;
}
</style>
`;

// Inject styles
document.head.insertAdjacentHTML('beforeend', semanticSearchStyles);
