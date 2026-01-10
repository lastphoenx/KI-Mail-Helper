# ============================================================================
# PHASE 13C PART 5: ERWEITERTE FETCH-FILTER
# ============================================================================
# 
# Dateien die geändert werden müssen:
# 1. migrations/versions/ph13c_p5_fetch_filters.py (NEUE DATEI - siehe oben)
# 2. src/02_models.py (User-Model erweitern)
# 3. src/01_web_app.py (Route + Template-Daten)
# 4. templates/settings.html (UI erweitern)
# 5. src/14_background_jobs.py (Filter anwenden)
#
# ============================================================================


# ============================================================================
# 1. USER MODEL ERWEITERUNG (src/02_models.py)
# ============================================================================
# Füge diese Zeilen nach fetch_use_delta_sync hinzu (ca. Zeile 168):

"""
    # Phase 13C Part 5: Erweiterte Fetch-Filter
    fetch_since_date = Column(Date, nullable=True)  # Nur Mails ab diesem Datum
    fetch_unseen_only = Column(Boolean, default=False)  # Nur ungelesene
    fetch_include_folders = Column(Text, nullable=True)  # JSON: ["INBOX", "Work"]
    fetch_exclude_folders = Column(Text, nullable=True)  # JSON: ["Spam", "Trash"]
"""


# ============================================================================
# 2. WEB_APP.PY - Settings Route erweitern
# ============================================================================
# In der settings() Funktion, erweitere user_prefs dict:

"""
        # Phase 13C Part 4 + 5: User Fetch Preferences
        user_prefs = {
            'mails_per_folder': getattr(user, 'fetch_mails_per_folder', 100),
            'max_total_mails': getattr(user, 'fetch_max_total', 0),
            'use_delta_sync': getattr(user, 'fetch_use_delta_sync', True),
            # Part 5: Erweiterte Filter
            'since_date': getattr(user, 'fetch_since_date', None),
            'unseen_only': getattr(user, 'fetch_unseen_only', False),
            'include_folders': getattr(user, 'fetch_include_folders', None),
            'exclude_folders': getattr(user, 'fetch_exclude_folders', None),
        }
"""


# ============================================================================
# 3. WEB_APP.PY - save_fetch_config Route erweitern  
# ============================================================================
# Ersetze die komplette save_fetch_config() Funktion:

"""
@app.route("/settings/fetch-config", methods=["POST"])
@login_required
def save_fetch_config():
    \"\"\"Speichert Fetch-Präferenzen des Users
    
    Phase 13C Part 4+5: User kann steuern wie und welche Mails abgerufen werden
    \"\"\"
    import json
    from datetime import datetime
    
    db = get_db_session()

    try:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("login"))

        # Part 4: Basis-Einstellungen
        mails_per_folder = int(request.form.get('mails_per_folder', 100))
        max_total_mails = int(request.form.get('max_total_mails', 0))
        use_delta_sync = request.form.get('use_delta_sync') == 'on'

        # Part 5: Erweiterte Filter
        since_date_str = request.form.get('since_date', '').strip()
        unseen_only = request.form.get('unseen_only') == 'on'
        include_folders = request.form.getlist('include_folders')  # Mehrfachauswahl
        exclude_folders = request.form.getlist('exclude_folders')

        # Validierung Part 4
        if mails_per_folder < 10 or mails_per_folder > 1000:
            flash("❌ Mails pro Ordner muss zwischen 10 und 1000 liegen", "error")
            return redirect(url_for("settings"))
        
        if max_total_mails < 0 or max_total_mails > 10000:
            flash("❌ Max. Gesamt muss zwischen 0 und 10000 liegen", "error")
            return redirect(url_for("settings"))

        # Part 5: Datum parsen
        since_date = None
        if since_date_str:
            try:
                since_date = datetime.strptime(since_date_str, '%Y-%m-%d').date()
            except ValueError:
                flash("❌ Ungültiges Datum-Format (YYYY-MM-DD erwartet)", "error")
                return redirect(url_for("settings"))

        # Speichern
        user.fetch_mails_per_folder = mails_per_folder
        user.fetch_max_total = max_total_mails
        user.fetch_use_delta_sync = use_delta_sync
        
        # Part 5
        user.fetch_since_date = since_date
        user.fetch_unseen_only = unseen_only
        user.fetch_include_folders = json.dumps(include_folders) if include_folders else None
        user.fetch_exclude_folders = json.dumps(exclude_folders) if exclude_folders else None
        
        db.commit()

        # Feedback
        filters = []
        if since_date:
            filters.append(f"ab {since_date}")
        if unseen_only:
            filters.append("nur ungelesene")
        if include_folders:
            filters.append(f"Ordner: {', '.join(include_folders)}")
        
        filter_str = f" | Filter: {', '.join(filters)}" if filters else ""
        flash(f"✅ Fetch-Konfiguration gespeichert: {mails_per_folder}/Ordner{filter_str}", "success")
        return redirect(url_for("settings"))

    except Exception as e:
        logger.error(f"Fehler beim Speichern der Fetch-Config: {e}")
        flash("❌ Fehler beim Speichern", "error")
        return redirect(url_for("settings"))

    finally:
        db.close()
"""
