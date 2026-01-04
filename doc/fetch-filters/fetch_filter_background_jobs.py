# ============================================================================
# PHASE 13C PART 5: BACKGROUND JOBS ANPASSUNG
# ============================================================================
#
# In src/14_background_jobs.py, in der Funktion _fetch_raw_emails()
# 
# Suche nach dem Kommentar:
#   # Phase 13C Part 4: Delta-Sync wenn aktiviert
#
# Ersetze/erweitere den Abschnitt wie folgt:
# ============================================================================

"""
            # Phase 13C Part 4 + 5: User Fetch-Einstellungen laden
            import json
            from datetime import datetime
            
            user_use_delta = getattr(account.user, 'fetch_use_delta_sync', True)
            user_mails_per_folder = getattr(account.user, 'fetch_mails_per_folder', 100)
            
            # Part 5: Erweiterte Filter
            user_since_date = getattr(account.user, 'fetch_since_date', None)
            user_unseen_only = getattr(account.user, 'fetch_unseen_only', False)
            user_include_folders_json = getattr(account.user, 'fetch_include_folders', None)
            user_exclude_folders_json = getattr(account.user, 'fetch_exclude_folders', None)
            
            # Parse JSON-Listen
            include_folders = []
            exclude_folders = []
            try:
                if user_include_folders_json:
                    include_folders = json.loads(user_include_folders_json)
                if user_exclude_folders_json:
                    exclude_folders = json.loads(user_exclude_folders_json)
            except json.JSONDecodeError:
                logger.warning("Ungültiges JSON in Ordner-Filter, ignoriere")
            
            # Log Fetch-Konfiguration
            filters_active = []
            if user_since_date:
                filters_active.append(f"SINCE {user_since_date}")
            if user_unseen_only:
                filters_active.append("UNSEEN")
            if include_folders:
                filters_active.append(f"Include: {include_folders}")
            if exclude_folders:
                filters_active.append(f"Exclude: {exclude_folders}")
            
            filter_str = f" | Filter: {', '.join(filters_active)}" if filters_active else ""
            
            if user_use_delta and account.initial_sync_done:
                logger.info(f"📁 {len(folders)} Ordner, DELTA SYNC{filter_str}")
            else:
                logger.info(f"📁 {len(folders)} Ordner, FULL SYNC{filter_str}")
"""

# ============================================================================
# ORDNER-FILTERUNG (in der for-Schleife über folders)
# ============================================================================
# 
# Suche nach:
#   for folder_name in folders:
#
# Füge DIREKT DANACH ein:
# ============================================================================

"""
            for folder_name in folders:
                # Part 5: Ordner-Filter anwenden
                if include_folders and folder_name not in include_folders:
                    logger.debug(f"  ⏭️  {folder_name}: Übersprungen (nicht in Include-Liste)")
                    continue
                
                if exclude_folders and folder_name in exclude_folders:
                    logger.debug(f"  ⏭️  {folder_name}: Übersprungen (in Exclude-Liste)")
                    continue
                
                try:
                    # ... rest des bestehenden Codes ...
"""

# ============================================================================
# FETCH MIT SINCE UND UNSEEN FILTERN
# ============================================================================
#
# Suche nach dem fetch_new_emails() Aufruf, etwa:
#   folder_mails = fetcher.fetch_new_emails(
#       folder=folder_name,
#       limit=mails_per_folder,
#       ...
#   )
#
# Ersetze durch:
# ============================================================================

"""
                    # Part 5: SINCE-Datum und UNSEEN-Filter an Fetcher übergeben
                    fetch_since = None
                    if user_since_date and not account.initial_sync_done:
                        # SINCE nur beim Initial-Sync anwenden, nicht bei Delta
                        fetch_since = datetime.combine(user_since_date, datetime.min.time())
                    
                    folder_mails = fetcher.fetch_new_emails(
                        folder=folder_name,
                        limit=mails_per_folder,
                        uid_range=uid_range,
                        # Part 5: Neue Filter
                        since=fetch_since,
                        unseen_only=user_unseen_only if not account.initial_sync_done else False,
                        # Part 4: UIDVALIDITY Support
                        account_id=account.id,
                        session=session,
                    )
"""

# ============================================================================
# VOLLSTÄNDIGER KONTEXT - So sollte der relevante Abschnitt aussehen:
# ============================================================================

"""
            # Phase 13C Part 4 + 5: User Fetch-Einstellungen laden
            import json
            from datetime import datetime
            
            user_use_delta = getattr(account.user, 'fetch_use_delta_sync', True)
            user_mails_per_folder = getattr(account.user, 'fetch_mails_per_folder', 100)
            
            # Part 5: Erweiterte Filter
            user_since_date = getattr(account.user, 'fetch_since_date', None)
            user_unseen_only = getattr(account.user, 'fetch_unseen_only', False)
            user_include_folders_json = getattr(account.user, 'fetch_include_folders', None)
            user_exclude_folders_json = getattr(account.user, 'fetch_exclude_folders', None)
            
            # Parse JSON-Listen
            include_folders = []
            exclude_folders = []
            try:
                if user_include_folders_json:
                    include_folders = json.loads(user_include_folders_json)
                if user_exclude_folders_json:
                    exclude_folders = json.loads(user_exclude_folders_json)
            except json.JSONDecodeError:
                logger.warning("Ungültiges JSON in Ordner-Filter, ignoriere")
            
            # Log Fetch-Konfiguration
            filters_active = []
            if user_since_date:
                filters_active.append(f"SINCE {user_since_date}")
            if user_unseen_only:
                filters_active.append("UNSEEN")
            if include_folders:
                filters_active.append(f"Include: {', '.join(include_folders[:3])}...")
            if exclude_folders:
                filters_active.append(f"Exclude: {', '.join(exclude_folders[:3])}...")
            
            filter_str = f" | {', '.join(filters_active)}" if filters_active else ""
            
            if user_use_delta and account.initial_sync_done:
                logger.info(f"📁 {len(folders)} Ordner, DELTA SYNC{filter_str}")
            else:
                logger.info(f"📁 {len(folders)} Ordner, FULL SYNC{filter_str}")
            
            # ... (rest des bestehenden Codes für mails_per_folder und folder_max_uids) ...
            
            # Gefilterte Ordner-Liste erstellen
            filtered_folders = []
            for folder_name in folders:
                # Part 5: Ordner-Filter anwenden
                if include_folders and folder_name not in include_folders:
                    logger.debug(f"  ⏭️  {folder_name}: Nicht in Include-Liste")
                    continue
                
                if exclude_folders and folder_name in exclude_folders:
                    logger.debug(f"  ⏭️  {folder_name}: In Exclude-Liste")
                    continue
                
                filtered_folders.append(folder_name)
            
            logger.info(f"  📂 {len(filtered_folders)}/{len(folders)} Ordner nach Filter")
            
            for folder_name in filtered_folders:
                try:
                    # Delta-Sync: Fetch nur Mails mit UID > last_known_uid
                    uid_range = None
                    if user_use_delta and folder_name in folder_max_uids:
                        last_uid = folder_max_uids[folder_name]
                        uid_range = f"{last_uid + 1}:*"
                        logger.info(f"  🔄 {folder_name}: Delta ab UID {last_uid + 1}")
                    
                    # Part 5: SINCE-Datum und UNSEEN-Filter
                    fetch_since = None
                    if user_since_date and not account.initial_sync_done:
                        fetch_since = datetime.combine(user_since_date, datetime.min.time())
                    
                    folder_mails = fetcher.fetch_new_emails(
                        folder=folder_name,
                        limit=mails_per_folder,
                        uid_range=uid_range,
                        since=fetch_since,
                        unseen_only=user_unseen_only if not account.initial_sync_done else False,
                        account_id=account.id,
                        session=session,
                    )
                    
                    # ... rest des bestehenden Codes ...
"""
