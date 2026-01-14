# Copy-Paste-Ready Snippets - Hybrid Progress
## Alle Code-Änderungen zum direkten Einfügen

---

## 📄 DATEI 1: src/services/mail_sync_v2.py

### SNIPPET 1.1 - Zeile 120 (Methoden-Signatur)

**SUCHE**:
```python
    def sync_state_with_server(self, include_folders: Optional[List[str]] = None) -> SyncStats:
```

**ERSETZE MIT**:
```python
    def sync_state_with_server(
        self, 
        include_folders: Optional[List[str]] = None,
        progress_callback: Optional[callable] = None
    ) -> SyncStats:
```

---

### SNIPPET 1.2 - Zeile 134 (Docstring erweitern)

**SUCHE**:
```python
            include_folders: Ordner die gescannt werden sollen (aus Filter).
                           Wenn None, werden bekannte Ordner aus State verwendet.
        
        Returns:
```

**ERSETZE MIT**:
```python
            include_folders: Ordner die gescannt werden sollen (aus Filter).
                           Wenn None, werden bekannte Ordner aus State verwendet.
            progress_callback: Optional callback(phase, message, **kwargs) für Progress-Updates.
        
        Returns:
```

---

### SNIPPET 1.3 - Zeile 155-157 (Folder-Loop)

**SUCHE**:
```python
            # 2. Pro Ordner: DELETE + INSERT (simpel und robust!)
            for folder in folders_to_scan:
                self._sync_folder_state(folder, stats)
```

**ERSETZE MIT**:
```python
            # 2. Pro Ordner: DELETE + INSERT (simpel und robust!)
            total_folders = len(folders_to_scan)
            
            for idx, folder in enumerate(folders_to_scan, 1):
                # Progress: Ordner startet
                if progress_callback:
                    progress_callback(
                        phase="state_sync_folder_start",
                        message=f"📁 Ordner {idx}/{total_folders}: {folder}",
                        current_folder=idx,
                        total_folders=total_folders,
                        folder_name=folder
                    )
                
                # Sync Ordner (mit Batch-Updates)
                folder_mail_count = self._sync_folder_state(folder, stats, progress_callback)
                
                # Progress: Ordner fertig
                if progress_callback:
                    progress_callback(
                        phase="state_sync_folder_complete",
                        message=f"✅ Ordner {idx}/{total_folders} fertig: {folder}",
                        folder_name=folder,
                        mails_in_folder=folder_mail_count
                    )
```

---

### SNIPPET 1.4 - Zeile 174 (Methoden-Signatur)

**SUCHE**:
```python
    def _sync_folder_state(self, folder: str, stats: SyncStats):
```

**ERSETZE MIT**:
```python
    def _sync_folder_state(
        self, 
        folder: str, 
        stats: SyncStats,
        progress_callback: Optional[callable] = None
    ):
```

---

### SNIPPET 1.5 - Zeile 178 (Docstring erweitern)

**SUCHE**:
```python
        """
        Synchronisiert mail_server_state für EINEN Ordner.
        
        Simpel: DELETE alle für diesen Ordner, dann INSERT alle vom Server.
        """
```

**ERSETZE MIT**:
```python
        """
        Synchronisiert mail_server_state für EINEN Ordner.
        
        Simpel: DELETE alle für diesen Ordner, dann INSERT alle vom Server.
        
        Args:
            folder: Ordner-Name (z.B. "INBOX")
            stats: SyncStats-Objekt zum Aktualisieren
            progress_callback: Optional callback für Batch-Progress
        """
```

---

### SNIPPET 1.6 - Zeile 193-197 (Batch-Loop)

**SUCHE**:
```python
            if uids:
                # Batch-Fetch ENVELOPEs
                for i in range(0, len(uids), 500):
                    batch_uids = uids[i:i+500]
                    envelopes = self.conn.fetch(batch_uids, ['ENVELOPE', 'FLAGS'])
```

**ERSETZE MIT**:
```python
            if uids:
                # Batch-Fetch ENVELOPEs
                total_uids = len(uids)
                
                for i in range(0, total_uids, 500):
                    # Progress: Batch-Update (nur wenn >500 Mails im Ordner)
                    if total_uids > 500 and progress_callback:
                        processed = min(i + 500, total_uids)
                        progress_callback(
                            phase="state_sync_batch",
                            message=f"  → {processed}/{total_uids} Mails",
                            current=processed,
                            total=total_uids,
                            folder=folder
                        )
                    
                    batch_uids = uids[i:i+500]
                    envelopes = self.conn.fetch(batch_uids, ['ENVELOPE', 'FLAGS'])
```

---

### SNIPPET 1.7 - Zeile 256-257 (Return hinzufügen)

**SUCHE**:
```python
            stats.folders_scanned += 1
            logger.debug(f"  ✓ {folder}: {len(server_mails)} Mails (deleted {deleted}, inserted {len(server_mails)})")
        
        except Exception as e:
```

**ERSETZE MIT**:
```python
            stats.folders_scanned += 1
            logger.debug(f"  ✓ {folder}: {len(server_mails)} Mails (deleted {deleted}, inserted {len(server_mails)})")
            
            # Return mail count für Progress-Callback
            return len(server_mails)
        
        except Exception as e:
```

---

### SNIPPET 1.8 - Zeile ~261 (Return bei Fehler)

**SUCHE**:
```python
        except Exception as e:
            stats.errors.append(f"{folder}: {str(e)}")
            logger.error(f"❌ Ordner {folder} fehlgeschlagen: {e}")
```

**ERSETZE MIT**:
```python
        except Exception as e:
            stats.errors.append(f"{folder}: {str(e)}")
            logger.error(f"❌ Ordner {folder} fehlgeschlagen: {e}")
            return 0  # Return 0 bei Fehler
```

---

## 📄 DATEI 2: src/14_background_jobs.py

### SNIPPET 2.1 - Zeile ~427 (Callback-Funktion)

**SUCHE**:
```python
            fetcher.connect()
            
            try:
```

**ERSETZE MIT**:
```python
            fetcher.connect()
            
            # Progress-Callback für State-Sync
            def state_sync_progress(phase, message, **kwargs):
                """Callback für kontinuierliche Progress-Updates während State-Sync."""
                self._update_status(
                    job.job_id,
                    {
                        "phase": phase,
                        "message": message,
                        **kwargs
                    }
                )
            
            try:
```

---

### SNIPPET 2.2 - Zeile 436 (Callback übergeben)

**SUCHE**:
```python
                stats1 = sync_service.sync_state_with_server(include_folders)
```

**ERSETZE MIT**:
```python
                stats1 = sync_service.sync_state_with_server(
                    include_folders, 
                    progress_callback=state_sync_progress
                )
```

---

## ✅ ALLE SNIPPETS KOPIERT?

Checkliste:
- [ ] `mail_sync_v2.py` - Snippet 1.1 (Zeile 120)
- [ ] `mail_sync_v2.py` - Snippet 1.2 (Zeile 134)
- [ ] `mail_sync_v2.py` - Snippet 1.3 (Zeile 155-157)
- [ ] `mail_sync_v2.py` - Snippet 1.4 (Zeile 174)
- [ ] `mail_sync_v2.py` - Snippet 1.5 (Zeile 178)
- [ ] `mail_sync_v2.py` - Snippet 1.6 (Zeile 193-197)
- [ ] `mail_sync_v2.py` - Snippet 1.7 (Zeile 256-257)
- [ ] `mail_sync_v2.py` - Snippet 1.8 (Zeile ~261)
- [ ] `14_background_jobs.py` - Snippet 2.1 (Zeile ~427)
- [ ] `14_background_jobs.py` - Snippet 2.2 (Zeile 436)

**Fertig? Flask neu starten und testen!** 🚀

---

## 🧪 Quick Test

Nach allen Änderungen:

```bash
# 1. Backup
cp src/services/mail_sync_v2.py src/services/mail_sync_v2.py.backup
cp src/14_background_jobs.py src/14_background_jobs.py.backup

# 2. Änderungen einfügen (siehe Snippets oben)

# 3. Flask neu starten
# (Dein üblicher Start-Befehl)

# 4. Mail-Fetch triggern
# → Frontend sollte jetzt kontinuierliche Updates anzeigen:
#    "📁 Ordner 1/5: INBOX"
#    "  → 500/5772 Mails"
#    "  → 1000/5772 Mails"
#    ...
```

**Wenn Updates sichtbar sind**: ✅ SUCCESS!  
**Wenn keine Updates**: 🐛 Siehe Troubleshooting in HYBRID_PROGRESS_IMPLEMENTATION.md
