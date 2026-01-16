# src/blueprints/emails.py
"""Emails Blueprint - Dashboard, Listenansicht, Threads, Email-Detail.

Routes (5 total):
    1. /dashboard (GET) - 3x3-Prioritäten-Matrix
    2. /list (GET) - Listenansicht mit Filtern
    3. /threads (GET) - Thread-basierte Ansicht
    4. /email/<id> (GET) - Email-Detailansicht
    5. /email/<id>/render-html (GET) - HTML-Rendering für iframe

Extracted from 01_web_app.py lines: 978-1759
"""

from flask import Blueprint, render_template, request, redirect, url_for, session, g, make_response
from flask_login import login_required, current_user
from datetime import datetime
import importlib
import json
import logging

from src.helpers import get_db_session, get_current_user_model

emails_bp = Blueprint("emails", __name__)
logger = logging.getLogger(__name__)

# Lazy imports
_models = None
_encryption = None
_scoring = None
_mail_fetcher_mod = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


def _get_encryption():
    global _encryption
    if _encryption is None:
        _encryption = importlib.import_module(".08_encryption", "src")
    return _encryption


def _get_scoring():
    global _scoring
    if _scoring is None:
        _scoring = importlib.import_module(".05_scoring", "src")
    return _scoring


def _get_mail_fetcher_mod():
    global _mail_fetcher_mod
    if _mail_fetcher_mod is None:
        _mail_fetcher_mod = importlib.import_module(".06_mail_fetcher", "src")
    return _mail_fetcher_mod


_tag_manager_mod = None


def _get_tag_manager():
    """Lazy-Import für TagManager (vermeidet zirkuläre Imports)"""
    global _tag_manager_mod
    if _tag_manager_mod is None:
        try:
            _tag_manager_mod = importlib.import_module("src.services.tag_manager")
        except ImportError:
            logger.warning("TagManager nicht verfügbar")
            return None
    return _tag_manager_mod


# =============================================================================
# Route 1: /dashboard (Zeile 978-1098)
# =============================================================================
@emails_bp.route("/dashboard")
@login_required
def dashboard():
    """Hauptseite: 3x3-Prioritäten-Matrix mit Statistiken"""
    models = _get_models()
    encryption = _get_encryption()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))

        # Account-Filter (optional)
        filter_account_id = None
        account_id_str = request.args.get("mail_account")
        if account_id_str:
            try:
                filter_account_id = int(account_id_str)
            except (ValueError, TypeError):
                filter_account_id = None

        # Alle Mail-Accounts des Users (für Dropdown)
        user_accounts = (
            db.query(models.MailAccount)
            .filter(models.MailAccount.user_id == user.id)
            .order_by(models.MailAccount.name)
            .all()
        )

        # Zero-Knowledge: Entschlüssele Email-Adressen für Anzeige
        master_key = session.get("master_key")
        if master_key and user_accounts:
            for account in user_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"Fehler beim Entschlüsseln der Account-Email: {e}"
                        )
                        account.decrypted_imap_username = None

        matrix_data = {}
        total_mails = 0
        high_priority_count = 0

        # Filtere nach Account falls gewählt
        query_filter = [
            models.RawEmail.user_id == user.id,
            models.RawEmail.deleted_at == None,
            models.ProcessedEmail.done == False,
            models.ProcessedEmail.deleted_at == None,
        ]
        if filter_account_id:
            query_filter.append(models.RawEmail.mail_account_id == filter_account_id)

        # Alle unerledigten Mails des Users (optional gefiltert nach Account)
        processed_mails = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(*query_filter)
            .all()
        )

        total_mails = len(processed_mails)

        for mail in processed_mails:
            key = f"{mail.matrix_x}_{mail.matrix_y}"
            if key not in matrix_data:
                matrix_data[key] = {"count": 0, "color": mail.farbe}

            matrix_data[key]["count"] += 1

            if mail.farbe == "rot":
                high_priority_count += 1

        amp_colors = {
            "rot": sum(
                m["count"] for m in matrix_data.values() if m.get("color") == "rot"
            ),
            "gelb": sum(
                m["count"] for m in matrix_data.values() if m.get("color") == "gelb"
            ),
            "grün": sum(
                m["count"] for m in matrix_data.values() if m.get("color") == "grün"
            ),
        }

        matrix = {}
        for x in range(1, 4):
            for y in range(1, 4):
                key = f"{x}_{y}"
                matrix_key = f"{x}{y}"
                matrix[matrix_key] = matrix_data.get(key, {}).get("count", 0)

        # Erledigte Mails (mit Account-Filter)
        done_query_filter = [
            models.RawEmail.user_id == user.id,
            models.RawEmail.deleted_at == None,
            models.ProcessedEmail.done == True,
            models.ProcessedEmail.deleted_at == None,
        ]
        if filter_account_id:
            done_query_filter.append(models.RawEmail.mail_account_id == filter_account_id)

        done_mails = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(*done_query_filter)
            .count()
        )

        stats = {
            "total": total_mails + done_mails,
            "open": total_mails,
            "done": done_mails,
        }

        # Gewählter Account (für Anzeige)
        selected_account = None
        if filter_account_id:
            selected_account = (
                db.query(models.MailAccount)
                .filter(models.MailAccount.id == filter_account_id)
                .first()
            )

        return render_template(
            "dashboard.html",
            matrix=matrix,
            ampel=amp_colors,
            stats=stats,
            top_tags=[],
            user_accounts=user_accounts,
            filter_account_id=filter_account_id,
            selected_account=selected_account,
        )


# =============================================================================
# Route 2: /list (Zeile 1101-1424)
# =============================================================================
@emails_bp.route("/list")
@login_required
def list_view():
    """Listen-Ansicht: alle Mails mit erweiterten Filtern"""
    models = _get_models()
    encryption = _get_encryption()
    mail_fetcher_mod = _get_mail_fetcher_mod()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))

        # Legacy-Filter
        filter_color = request.args.get("farbe") or None
        filter_done = (request.args.get("done") or "").lower()
        search_term = (request.args.get("search", "") or "").strip()

        # Account-Filter
        filter_account_id = None
        account_id_str = request.args.get("mail_account")
        if account_id_str:
            try:
                filter_account_id = int(account_id_str)
            except (ValueError, TypeError):
                filter_account_id = None

        # Phase 10: Tag-Filter
        filter_tag_ids = []
        tag_id_str = request.args.get("tags")
        if tag_id_str:
            try:
                filter_tag_ids = [int(tag_id_str)]
            except (ValueError, TypeError):
                filter_tag_ids = []

        # Phase 13: Neue Filter
        filter_folder = request.args.get("folder") or None
        filter_seen = (request.args.get("seen") or "").lower()
        filter_flagged = (request.args.get("flagged") or "").lower()
        filter_attachments = (request.args.get("attach") or "").lower()

        # Datums-Filter
        filter_date_from = request.args.get("date_from") or None
        filter_date_to = request.args.get("date_to") or None

        # Sortierung
        sort_by = request.args.get("sort", "score")  # date/score/size/sender
        sort_order = request.args.get("order", "desc").lower()  # asc/desc
        if sort_order not in ("asc", "desc"):
            sort_order = "desc"

        query = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
        )

        if filter_done in ("true", "false"):
            query = query.filter(models.ProcessedEmail.done == (filter_done == "true"))

        if filter_color:
            query = query.filter(models.ProcessedEmail.farbe == filter_color)

        if filter_account_id:
            query = query.filter(models.RawEmail.mail_account_id == filter_account_id)

        # Phase 10: Filter nach Tags
        if filter_tag_ids:
            query = query.join(models.EmailTagAssignment).filter(
                models.EmailTagAssignment.tag_id.in_(filter_tag_ids)
            )

        # Phase 13: Ordner-Filter
        if filter_folder:
            query = query.filter(models.RawEmail.imap_folder == filter_folder)

        # Phase 13: Gelesen/Ungelesen-Filter
        if filter_seen == "true":
            query = query.filter(models.RawEmail.imap_is_seen == True)
        elif filter_seen == "false":
            query = query.filter(models.RawEmail.imap_is_seen == False)

        # Phase 13: Geflaggt/Nicht-Filter
        if filter_flagged == "true":
            query = query.filter(models.RawEmail.imap_is_flagged == True)
        elif filter_flagged == "false":
            query = query.filter(models.RawEmail.imap_is_flagged == False)

        # Phase 13: Anhang-Filter
        if filter_attachments == "true":
            query = query.filter(models.RawEmail.has_attachments == True)
        elif filter_attachments == "false":
            query = query.filter(models.RawEmail.has_attachments == False)

        # Phase 13: Datums-Filter
        if filter_date_from:
            try:
                from_date = datetime.fromisoformat(filter_date_from)
                query = query.filter(models.RawEmail.received_at >= from_date)
            except (ValueError, TypeError):
                pass

        if filter_date_to:
            try:
                to_date = datetime.fromisoformat(filter_date_to)
                to_date = to_date.replace(hour=23, minute=59, second=59)
                query = query.filter(models.RawEmail.received_at <= to_date)
            except (ValueError, TypeError):
                pass

        # Phase 13: Sortierung anwenden
        if sort_by == "date":
            sort_col = models.RawEmail.received_at
        elif sort_by == "size":
            sort_col = models.RawEmail.message_size
        elif sort_by == "sender":
            sort_col = models.RawEmail.encrypted_sender
        else:  # "score" (default)
            sort_col = models.ProcessedEmail.score

        # P2-007: Server-Pagination
        page = int(request.args.get('page', 1))
        per_page = 50
        
        # Count total for pagination
        total_count = query.count()
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        
        # Boundary checks
        if page < 1:
            page = 1
        if page > total_pages:
            page = total_pages
        
        # Apply pagination
        if sort_order == "asc":
            mails = query.order_by(sort_col.asc()).limit(per_page).offset((page - 1) * per_page).all()
        else:
            mails = query.order_by(sort_col.desc()).limit(per_page).offset((page - 1) * per_page).all()

        # Lade alle User-Accounts für Filter-Dropdown
        user_accounts = (
            db.query(models.MailAccount)
            .filter(models.MailAccount.user_id == user.id)
            .all()
        )

        # Phase 13C: Lade Server-Ordner via IMAP (für Dropdown-Autocomplete)
        server_folders = []
        if filter_account_id:
            try:
                account = db.query(models.MailAccount).filter_by(
                    id=filter_account_id, user_id=user.id
                ).first()
                if account and account.auth_type == "imap":
                    master_key_temp = session.get("master_key")
                    if master_key_temp:
                        imap_server = encryption.CredentialManager.decrypt_server(
                            account.encrypted_imap_server, master_key_temp
                        )
                        imap_username = encryption.CredentialManager.decrypt_email_address(
                            account.encrypted_imap_username, master_key_temp
                        )
                        imap_password = encryption.CredentialManager.decrypt_imap_password(
                            account.encrypted_imap_password, master_key_temp
                        )
                        fetcher = mail_fetcher_mod.MailFetcher(
                            server=imap_server,
                            username=imap_username,
                            password=imap_password,
                            port=account.imap_port,
                        )
                        fetcher.connect()
                        try:
                            # IMAPClient.list_folders() returns (flags, delimiter, folder_name) tuples
                            folders = fetcher.connection.list_folders()
                            for flags, delimiter, folder_name in folders:
                                # Skip \Noselect folders
                                if b'\\Noselect' in flags or '\\Noselect' in [f.decode() if isinstance(f, bytes) else f for f in flags]:
                                    continue
                                # folder_name is bytes, decode UTF-7 to UTF-8
                                folder_display = mail_fetcher_mod.decode_imap_folder_name(folder_name)
                                server_folders.append(folder_display)
                            server_folders.sort()
                        finally:
                            fetcher.disconnect()
            except Exception as e:
                logger.warning(f"Konnte Server-Ordner nicht laden: {e}")

        # Phase 10: Lade alle User-Tags für Filter-Dropdown
        all_tags = []
        tag_manager_mod = _get_tag_manager()
        if tag_manager_mod:
            try:
                all_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
            except Exception as e:
                logger.warning(f"TagManager konnte Tags nicht laden: {e}")

        # Phase 10 Fix: Eager load alle Tags für alle Emails (verhindert n+1)
        email_ids = [mail.id for mail in mails]
        email_tags_map = {}
        if email_ids and tag_manager_mod:
            try:
                # Single query für alle Email-Tag-Assignments
                tag_assignments = (
                    db.query(models.EmailTagAssignment, models.EmailTag)
                    .join(
                        models.EmailTag,
                        models.EmailTagAssignment.tag_id == models.EmailTag.id,
                    )
                    .filter(
                        models.EmailTagAssignment.email_id.in_(email_ids),
                        models.EmailTag.user_id == user.id,
                    )
                    .all()
                )

                # Group by email_id
                for assignment, tag in tag_assignments:
                    if assignment.email_id not in email_tags_map:
                        email_tags_map[assignment.email_id] = []
                    email_tags_map[assignment.email_id].append(tag)
            except Exception as e:
                logger.warning(f"Tag eager loading fehlgeschlagen: {e}")

        # Zero-Knowledge: Entschlüsselung für Anzeige und Suche
        master_key = session.get("master_key")
        decrypted_mails = []

        # Dekryptiere Mail-Adressen der Accounts für Dropdown
        if master_key and user_accounts:
            for account in user_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(
                            f"Fehler beim Entschlüsseln der Account-Email: {e}"
                        )
                        account.decrypted_imap_username = None

        if master_key:
            for mail in mails:
                try:
                    # RawEmail entschlüsseln
                    decrypted_subject = (
                        encryption.EmailDataManager.decrypt_email_subject(
                            mail.raw_email.encrypted_subject or "", master_key
                        )
                    )
                    decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                        mail.raw_email.encrypted_sender or "", master_key
                    )

                    # ProcessedEmail entschlüsseln
                    decrypted_summary_de = encryption.EmailDataManager.decrypt_summary(
                        mail.encrypted_summary_de or "", master_key
                    )
                    decrypted_tags = encryption.EmailDataManager.decrypt_summary(
                        mail.encrypted_tags or "", master_key
                    )

                    # Suche anwenden (falls nötig)
                    if search_term:
                        if not (
                            search_term.lower() in decrypted_subject.lower()
                            or search_term.lower() in decrypted_sender.lower()
                        ):
                            continue  # Skip diese Mail bei Suche

                    # Mail-Objekt mit entschlüsselten Daten erweitern
                    mail._decrypted_subject = decrypted_subject
                    mail._decrypted_sender = decrypted_sender
                    mail._decrypted_summary_de = decrypted_summary_de
                    mail._decrypted_tags = decrypted_tags

                    # Phase 10 Fix: Tags aus pre-loaded map holen (kein n+1)
                    mail.email_tags = email_tags_map.get(mail.id, [])

                    decrypted_mails.append(mail)

                except (ValueError, KeyError, Exception) as e:
                    logger.error(
                        f"Entschlüsselung fehlgeschlagen für RawEmail {mail.raw_email.id}: {type(e).__name__}"
                    )
                    continue
        else:
            # Ohne master_key können wir nichts anzeigen
            decrypted_mails = []

        # Phase 13: Sammle verfügbare Ordner aus ALLEN RawEmails des Users (nicht nur sichtbare)
        available_folders_query = (
            db.query(models.RawEmail.imap_folder)
            .filter(
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.RawEmail.imap_folder != None,
            )
            .distinct()
        )
        available_folders = sorted([f for (f,) in available_folders_query.all()])

        return render_template(
            "list_view.html",
            user=user,
            mails=decrypted_mails,
            filter_color=filter_color,
            filter_done=filter_done,
            search_term=search_term,
            user_accounts=user_accounts,
            filter_account_id=filter_account_id,
            all_tags=all_tags,
            filter_tag_ids=filter_tag_ids,
            # Phase 13: Neue Filter-Parameter
            filter_folder=filter_folder,
            available_folders=available_folders,
            server_folders=server_folders,
            filter_seen=filter_seen,
            filter_flagged=filter_flagged,
            filter_attachments=filter_attachments,
            filter_date_from=filter_date_from,
            filter_date_to=filter_date_to,
            sort_by=sort_by,
            sort_order=sort_order,
            # P2-007: Pagination
            page=page,
            total_pages=total_pages,
            total_count=total_count,
            per_page=per_page,
        )


# =============================================================================
# Route 3: /threads (Zeile 1427-1483)
# =============================================================================
@emails_bp.route("/threads")
@login_required
def threads_view():
    """Thread-basierte Conversations-Ansicht (Phase 12)"""
    models = _get_models()
    encryption = _get_encryption()
    
    with get_db_session() as db:
        user = get_current_user_model(db)
        if not user:
            return redirect(url_for("auth.login"))

        # Lade User-Accounts für Filter-Dropdown (wie bei /list)
        user_accounts = (
            db.query(models.MailAccount)
            .filter(models.MailAccount.user_id == user.id)
            .all()
        )
        
        # Dekryptiere Account-Email-Adressen für Dropdown
        master_key = session.get("master_key")
        if master_key and user_accounts:
            for account in user_accounts:
                if account.auth_type == "imap" and account.encrypted_imap_username:
                    try:
                        account.decrypted_imap_username = (
                            encryption.EmailDataManager.decrypt_email_sender(
                                account.encrypted_imap_username, master_key
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Fehler beim Entschlüsseln der Account-Email: {e}")
                        account.decrypted_imap_username = None

        # Account-Filter aus Query-Parameter
        filter_account_id = request.args.get("mail_account")

        return render_template(
            "threads_view.html", 
            user=user, 
            user_accounts=user_accounts,
            filter_account_id=filter_account_id
        )


# =============================================================================
# Route 4: /email/<id> (Zeile 1486-1674)
# =============================================================================
@emails_bp.route("/email/<int:raw_email_id>")
@login_required
def email_detail(raw_email_id):
    """Detailansicht einer einzelnen Mail (via raw_email_id)"""
    models = _get_models()
    encryption = _get_encryption()
    scoring = _get_scoring()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

        processed = (
            db.query(models.ProcessedEmail)
            .join(models.RawEmail)
            .filter(
                models.RawEmail.id == raw_email_id,
                models.RawEmail.user_id == user.id,
                models.RawEmail.deleted_at == None,
                models.ProcessedEmail.deleted_at == None,
            )
            .first()
        )

        if not processed:
            return redirect(url_for("emails.list_view"))

        raw = processed.raw_email
        priority_label = scoring.get_priority_label(processed.score)

        # Zero-Knowledge: Entschlüssele E-Mail für Anzeige
        master_key = session.get("master_key")
        decrypted_subject = ""
        decrypted_sender = ""
        decrypted_to = ""
        decrypted_cc = ""
        decrypted_bcc = ""
        decrypted_body = ""
        decrypted_summary_de = ""
        decrypted_text_de = ""
        decrypted_tags = ""
        decrypted_subject_sanitized = ""  # Phase 22
        decrypted_body_sanitized = ""     # Phase 22

        if master_key:
            # RawEmail entschlüsseln (mit individuellen try-except pro Feld!)
            try:
                decrypted_subject = encryption.EmailDataManager.decrypt_email_subject(
                    raw.encrypted_subject or "", master_key
                )
            except Exception as e:
                logger.warning(f"Subject decryption failed for email {raw.id}: {e}")
                decrypted_subject = "(Entschlüsselung fehlgeschlagen)"
            
            try:
                decrypted_sender = encryption.EmailDataManager.decrypt_email_sender(
                    raw.encrypted_sender or "", master_key
                )
            except Exception as e:
                logger.warning(f"Sender decryption failed for email {raw.id}: {e}")
                decrypted_sender = "Unbekannt"
            
            # To/Cc/Bcc sind JSON: [{"name": "...", "email": "..."}]
            try:
                to_encrypted = raw.encrypted_to or ""
                if to_encrypted:
                    to_decrypted = encryption.EmailDataManager.decrypt_email_sender(to_encrypted, master_key)
                    if to_decrypted:
                        to_list = json.loads(to_decrypted)
                        decrypted_to = ", ".join([f"{item.get('name', '')} <{item.get('email', '')}>" if item.get('name') else item.get('email', '') for item in to_list])
            except Exception as e:
                logger.warning(f"To decryption/parsing failed for email {raw.id}: {e}")
            
            try:
                cc_encrypted = raw.encrypted_cc or ""
                if cc_encrypted:
                    cc_decrypted = encryption.EmailDataManager.decrypt_email_sender(cc_encrypted, master_key)
                    if cc_decrypted:
                        cc_list = json.loads(cc_decrypted)
                        decrypted_cc = ", ".join([f"{item.get('name', '')} <{item.get('email', '')}>" if item.get('name') else item.get('email', '') for item in cc_list])
            except Exception as e:
                logger.warning(f"Cc decryption/parsing failed for email {raw.id}: {e}")
            
            try:
                bcc_encrypted = raw.encrypted_bcc or ""
                if bcc_encrypted:
                    bcc_decrypted = encryption.EmailDataManager.decrypt_email_sender(bcc_encrypted, master_key)
                    if bcc_decrypted:
                        bcc_list = json.loads(bcc_decrypted)
                        decrypted_bcc = ", ".join([f"{item.get('name', '')} <{item.get('email', '')}>" if item.get('name') else item.get('email', '') for item in bcc_list])
            except Exception as e:
                logger.warning(f"Bcc decryption/parsing failed for email {raw.id}: {e}")
            
            try:
                decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                    raw.encrypted_body or "", master_key
                )
            except Exception as e:
                logger.warning(f"Body decryption failed for email {raw.id}: {e}")
                decrypted_body = "(Entschlüsselung fehlgeschlagen)"

            # ProcessedEmail entschlüsseln
            try:
                decrypted_summary_de = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_summary_de or "", master_key
                )
            except Exception as e:
                logger.warning(f"Summary decryption failed for email {processed.id}: {e}")
                
            try:
                decrypted_text_de = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_text_de or "", master_key
                )
            except Exception as e:
                logger.warning(f"Text decryption failed for email {processed.id}: {e}")
                
            try:
                decrypted_tags = encryption.EmailDataManager.decrypt_summary(
                    processed.encrypted_tags or "", master_key
                )
            except Exception as e:
                logger.warning(f"Tags decryption failed for email {processed.id}: {e}")
            
            # Phase 22: Anonymisierte Version entschlüsseln (wenn vorhanden)
            try:
                if raw.encrypted_subject_sanitized:
                    decrypted_subject_sanitized = encryption.EmailDataManager.decrypt_email_subject(
                        raw.encrypted_subject_sanitized, master_key
                    )
            except Exception as e:
                logger.warning(f"Sanitized subject decryption failed for email {raw.id}: {e}")
            
            try:
                if raw.encrypted_body_sanitized:
                    decrypted_body_sanitized = encryption.EmailDataManager.decrypt_email_body(
                        raw.encrypted_body_sanitized, master_key
                    )
            except Exception as e:
                logger.warning(f"Sanitized body decryption failed for email {raw.id}: {e}")

        # Phase 10: Lade Email-Tags
        email_tags = []
        all_user_tags = []
        tag_manager_mod = _get_tag_manager()
        if tag_manager_mod:
            try:
                email_tags = tag_manager_mod.TagManager.get_email_tags(
                    db, processed.id, user.id  # processed.id für Tag-Zuordnung
                )
                all_user_tags = tag_manager_mod.TagManager.get_user_tags(db, user.id)
            except Exception as e:
                logger.warning(f"TagManager konnte Tags nicht laden: {e}")

        return render_template(
            "email_detail.html",
            user=user,
            email=processed,
            raw=raw,
            raw_email=raw,  # Phase 22: Alias für Template-Kompatibilität
            decrypted_subject=decrypted_subject,
            decrypted_sender=decrypted_sender,
            decrypted_to=decrypted_to,
            decrypted_cc=decrypted_cc,
            decrypted_bcc=decrypted_bcc,
            decrypted_body=decrypted_body,
            decrypted_summary_de=decrypted_summary_de,
            decrypted_text_de=decrypted_text_de,
            decrypted_tags=decrypted_tags,
            decrypted_subject_sanitized=decrypted_subject_sanitized,  # Phase 22
            decrypted_body_sanitized=decrypted_body_sanitized,        # Phase 22
            priority_label=priority_label,
            email_tags=email_tags,
            all_user_tags=all_user_tags,
        )
    except Exception as e:
        logger.error(f"email_detail: Fehler bei Email {raw_email_id}: {type(e).__name__}: {e}")
        from flask import flash
        flash("Fehler beim Laden der Email-Details.", "danger")
        return redirect(url_for("emails.list_view"))


# =============================================================================
# Route 5: /email/<id>/render-html (Zeile 1677-1759)
# =============================================================================
@emails_bp.route("/email/<int:raw_email_id>/render-html")
@login_required
def render_email_html(raw_email_id: int):
    """Rendert E-Mail-HTML mit lockerer CSP (Fonts/Bilder erlaubt, Scripts blockiert)

    Dieser Endpoint wird von <iframe> in email_detail.html verwendet.
    CSP erlaubt externe Ressourcen für korrektes E-Mail-Rendering,
    blockiert aber alle Scripts (XSS-Schutz).

    Setzt eigene CSP-Header (g.skip_security_headers umgeht globalen Hook).
    """
    import traceback
    models = _get_models()
    encryption = _get_encryption()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                logger.error(f"render_email_html: User not found (raw_email_id={raw_email_id})")
                return "Unauthorized", 403

            processed = (
                db.query(models.ProcessedEmail)
                .join(models.RawEmail)
                .filter(
                    models.RawEmail.id == raw_email_id,
                    models.RawEmail.user_id == user.id,
                    models.RawEmail.deleted_at == None,
                    models.ProcessedEmail.deleted_at == None,
                )
                .first()
            )

            if not processed:
                logger.error(
                    f"render_email_html: Email {raw_email_id} not found for user {user.id}"
                )
                return "Email not found", 404

            # Zero-Knowledge: Entschlüssele E-Mail-Body
            master_key = session.get("master_key")
            if not master_key:
                logger.error(f"render_email_html: master_key missing in session")
                return "Session expired", 401

            try:
                decrypted_body = encryption.EmailDataManager.decrypt_email_body(
                    processed.raw_email.encrypted_body or "", master_key
                )
            except Exception as e:
                logger.error(
                    f"render_email_html: Entschlüsselung fehlgeschlagen für Email {raw_email_id}: {type(e).__name__}: {e}"
                )
                return "Decryption failed", 500

            # Marker für after_request Hook: Überschreibe Headers nicht (MUSS VOR make_response!)
            g.skip_security_headers = True

            # Wrap email body with proper HTML structure to prevent Quirks Mode
            html_content = f"""<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 10px; }}
        img {{ max-width: 100%; height: auto; }}
    </style>
</head>
<body>
{decrypted_body}
</body>
</html>"""

            # Response mit lockerer CSP nur für E-Mail-Content
            response = make_response(html_content)
            response.headers["Content-Type"] = "text/html; charset=utf-8"

            # CSP für E-Mail-Rendering: Erlaube externe Fonts/Bilder (PayPal, etc.)
            # WICHTIG: Scripts IMMER blockiert (XSS-Schutz)
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; "
                "style-src 'unsafe-inline'; "
                "img-src https: data:; "
                "font-src https: data:; "
                "script-src 'none'"
            )

            # Security Headers (ohne X-Frame-Options für iframe embedding)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            return response
    except Exception as e:
        logger.error(
            f"render_email_html: Unerwarteter Fehler für Email {raw_email_id}: "
            f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
        )
        return "Internal Server Error", 500
