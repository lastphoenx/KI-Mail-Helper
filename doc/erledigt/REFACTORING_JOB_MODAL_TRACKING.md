# Refactoring: Modal pro Job tracken statt global

**Priorität:** Medium  
**Geschätzter Aufwand:** 30-45 Minuten  
**Betroffene Dateien:** `templates/settings.html`, `templates/email_detail.html`

---

## Problem

### Ist-Zustand

```javascript
// templates/settings.html (Zeile ~485)
let analysisModal = null;  // ← EINE globale Variable für ALLE Jobs

function getAnalysisModal() {
    if (!analysisModal) {
        analysisModal = new bootstrap.Modal(document.getElementById('progressModal'), ...);
    }
    return analysisModal;  // ← Immer dasselbe Modal
}

let pollingActive = false;  // ← Nur Boolean, keine Job-ID
```

### Race Condition Szenario

```
17:34:00 - User startet Job 1 (Batch-Reprocess, 53 Mails)
           → analysisModal zeigt "0/53"
           → pollingActive = true

17:34:30 - Job 1 pollt → Modal zeigt "23/53"

17:36:00 - User startet Job 2 (Fetch, 3 Mails)
           → pollingActive ist true, ABER pollBatchReprocessStatus() 
             hat kein Guard dagegen!
           → Neuer pollJobStatus() startet parallel
           → Modal zeigt plötzlich "0/3" (Job 2 überschreibt)

17:36:15 - Job 1 pollt → Modal zeigt "45/53" 
17:36:17 - Job 2 pollt → Modal zeigt "1/3"
17:36:20 - Job 1 pollt → Modal zeigt "46/53"
           → UI springt wild hin und her!
```

### Betroffene Funktionen

| Funktion | Datei | Nutzt Modal? | Hat Guard? |
|----------|-------|--------------|------------|
| `pollJobStatus()` | settings.html | ✅ Ja | ✅ `pollingActive` |
| `pollBatchReprocessStatus()` | settings.html | ✅ Ja | ❌ **NEIN** |
| `getAnalysisModal()` | email_detail.html | ✅ Ja | ❌ Nein |

---

## Lösung

### Variante A: Einfacher Fix (empfohlen) - 30 Min

**Prinzip:** Aktiven Job-ID tracken, Updates von anderen Jobs ignorieren.

#### Schritt 1: Globale Variable erweitern

```javascript
// templates/settings.html - Ersetze die globalen Variablen

// ALT:
let analysisModal = null;
let pollingActive = false;

// NEU:
let analysisModal = null;
let currentActiveJobId = null;  // Trackt welcher Job das Modal "besitzt"
```

#### Schritt 2: pollJobStatus() anpassen

```javascript
function pollJobStatus(jobId, accountName, btn, originalLabel, attempt = 0, startTime = Date.now(), emailStartTime = null, lastEmailIndex = null) {
    
    // NEU: Bei erstem Aufruf - Job übernimmt das Modal
    if (attempt === 0) {
        // Wenn anderer Job läuft, diesen abbrechen (neuer Job gewinnt)
        if (currentActiveJobId && currentActiveJobId !== jobId) {
            console.log(`⚠️ Neuer Job ${jobId} übernimmt von ${currentActiveJobId}`);
        }
        currentActiveJobId = jobId;
    }
    
    // NEU: Ignoriere Updates wenn ein anderer Job aktiv ist
    if (currentActiveJobId !== jobId) {
        console.log(`🛑 Ignoriere Poll für Job ${jobId}, aktiv ist ${currentActiveJobId}`);
        return;  // Polling für diesen Job stoppen
    }
    
    // ... Rest der Funktion bleibt gleich ...
    
    const modal = getAnalysisModal();
    if (attempt === 0) modal.show();
    
    // Bei ALLEN Exit-Punkten: currentActiveJobId zurücksetzen
    // done:
    if (status.state === 'done') {
        // ... bestehender Code ...
        document.getElementById('closeAnalysisBtn').addEventListener('click', function() {
            modal.hide();
            currentActiveJobId = null;  // ← NEU: Reset
            // ...
        });
    }
    
    // error:
    if (status.state === 'error') {
        // ... bestehender Code ...
        document.getElementById('closeAnalysisBtn').addEventListener('click', function() {
            modal.hide();
            currentActiveJobId = null;  // ← NEU: Reset
            // ...
        });
    }
    
    // timeout:
    if (emailRemaining <= 0) {
        // ... bestehender Code ...
        document.getElementById('closeAnalysisBtn').addEventListener('click', function() {
            modal.hide();
            currentActiveJobId = null;  // ← NEU: Reset
            // ...
        });
    }
    
    // catch-Block:
    .catch(err => {
        modal.hide();
        currentActiveJobId = null;  // ← NEU: Reset
        // ...
    });
}
```

#### Schritt 3: pollBatchReprocessStatus() anpassen

```javascript
function pollBatchReprocessStatus(jobId, btn, originalLabel, attempt = 0, startTime = Date.now(), emailStartTime = null, lastEmailIndex = null) {
    
    // NEU: Gleiche Logik wie pollJobStatus
    if (attempt === 0) {
        if (currentActiveJobId && currentActiveJobId !== jobId) {
            console.log(`⚠️ Batch-Job ${jobId} übernimmt von ${currentActiveJobId}`);
        }
        currentActiveJobId = jobId;
    }
    
    if (currentActiveJobId !== jobId) {
        console.log(`🛑 Ignoriere Batch-Poll für Job ${jobId}, aktiv ist ${currentActiveJobId}`);
        return;
    }
    
    // ... Rest der Funktion ...
    
    // Bei ALLEN Exit-Punkten: currentActiveJobId = null setzen
    // (done, error, timeout, catch)
}
```

#### Schritt 4: pollingActive entfernen (optional)

Da `currentActiveJobId` jetzt die Kontrolle übernimmt, ist `pollingActive` redundant:

```javascript
// ALT:
if (pollingActive) {
    console.warn('Polling bereits aktiv, ignoriere doppelten Start');
    return;
}
pollingActive = true;

// NEU: Nicht mehr nötig, da currentActiveJobId das übernimmt
// Kann entfernt werden ODER als zusätzlicher Guard bleiben
```

---

### Variante B: Robuster Fix mit Event-Cleanup - 45 Min

**Zusätzlich zu Variante A:** Event-Listener Cleanup um Memory Leaks zu vermeiden.

#### Problem: Event-Listener Akkumulation

```javascript
// AKTUELL: Jeder Poll-Zyklus fügt NEUEN Listener hinzu!
document.getElementById('closeAnalysisBtn').addEventListener('click', function() {
    // ...
});
// Nach 50 Polls: 50 Listener auf demselben Button!
```

#### Lösung: Named Function + removeEventListener

```javascript
// Am Anfang der Datei
let closeModalHandler = null;

function pollJobStatus(jobId, ...) {
    // ...
    
    if (status.state === 'done') {
        // Alten Handler entfernen falls vorhanden
        if (closeModalHandler) {
            document.getElementById('closeAnalysisBtn').removeEventListener('click', closeModalHandler);
        }
        
        // Neuen Handler definieren und speichern
        closeModalHandler = function() {
            modal.hide();
            currentActiveJobId = null;
            closeModalHandler = null;  // Selbst-Cleanup
            if (btn) {
                btn.disabled = false;
                btn.textContent = originalLabel || 'Abrufen';
            }
        };
        
        document.getElementById('closeAnalysisBtn').addEventListener('click', closeModalHandler);
    }
}
```

---

## Checkliste für Implementation

### settings.html

- [ ] `let currentActiveJobId = null;` hinzufügen (nach `let analysisModal = null;`)
- [ ] `pollJobStatus()`: Job-ID Check am Anfang (attempt === 0 Block)
- [ ] `pollJobStatus()`: Guard gegen fremde Job-Updates
- [ ] `pollJobStatus()`: Reset `currentActiveJobId = null` bei done
- [ ] `pollJobStatus()`: Reset `currentActiveJobId = null` bei error  
- [ ] `pollJobStatus()`: Reset `currentActiveJobId = null` bei timeout
- [ ] `pollJobStatus()`: Reset `currentActiveJobId = null` im catch-Block
- [ ] `pollBatchReprocessStatus()`: Gleiche 4 Änderungen
- [ ] Optional: `pollingActive` Variable entfernen (redundant)
- [ ] Optional: Event-Listener Cleanup implementieren

### email_detail.html

- [ ] Prüfen ob `getAnalysisModal()` dort auch genutzt wird
- [ ] Falls ja: Gleiche Job-ID-Tracking Logik einbauen

---

## Test-Szenario

1. **Job 1 starten** (Batch-Reprocess mit vielen Mails)
2. **Während Job 1 läuft:** Job 2 starten (Fetch)
3. **Erwartetes Verhalten:**
   - Console zeigt: `⚠️ Neuer Job {job2-id} übernimmt von {job1-id}`
   - Modal zeigt nur noch Job 2 Progress
   - Job 1 Polling stoppt still (keine UI-Updates mehr)
4. **Job 2 beenden** (OK klicken)
5. **Neuen Job starten** - sollte normal funktionieren

---

## Beispiel: Vollständiger Code-Diff

```diff
 // templates/settings.html

 let analysisModal = null;
+let currentActiveJobId = null;

 function getAnalysisModal() {
     // ... unverändert ...
 }

-let pollingActive = false;
-
 function pollJobStatus(jobId, accountName, btn, originalLabel, attempt = 0, startTime = Date.now(), emailStartTime = null, lastEmailIndex = null) {
-    if (attempt === 0) {
-        if (pollingActive) {
-            console.warn('Polling bereits aktiv, ignoriere doppelten Start');
-            return;
-        }
-        pollingActive = true;
+    // Job-Ownership Management
+    if (attempt === 0) {
+        if (currentActiveJobId && currentActiveJobId !== jobId) {
+            console.log(`⚠️ Job ${jobId} übernimmt Modal von ${currentActiveJobId}`);
+        }
+        currentActiveJobId = jobId;
+    }
+    
+    // Ignoriere Updates von nicht-aktiven Jobs
+    if (currentActiveJobId !== jobId) {
+        console.log(`🛑 Poll ignoriert: Job ${jobId} nicht aktiv (aktiv: ${currentActiveJobId})`);
+        return;
     }

     // ... Rest der Funktion ...

                 document.getElementById('closeAnalysisBtn').addEventListener('click', function() {
                     const modal = getAnalysisModal();
                     modal.hide();
-                    pollingActive = false;
+                    currentActiveJobId = null;
                     if (btn) {
                         btn.disabled = false;
                         btn.textContent = originalLabel || 'Abrufen';
                     }
                 });
```

---

## Notizen

- **Warum "neuer Job gewinnt"?** User-Intent: Wenn jemand einen neuen Job startet, will er dessen Progress sehen, nicht den alten.
- **Alternative "alter Job gewinnt":** Button disablen bis Job fertig. Aber schlechtere UX wenn alter Job hängt.
- **Kein zweites Modal nötig:** Ein Modal reicht, solange klar ist welcher Job es kontrolliert.
