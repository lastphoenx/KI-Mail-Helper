# src/blueprints/auth.py
"""Authentication Blueprint - Login, Register, 2FA, Logout.

Routes (7 total):
    1. / (GET) - index → redirect to dashboard or login
    2. /login (GET, POST) - login page
    3. /register (GET, POST) - registration page
    4. /2fa/verify (GET, POST) - 2FA verification
    5. /logout (GET) - logout
    6. /settings/2fa/setup (GET, POST) - 2FA setup
    7. /settings/2fa/recovery-codes/regenerate (POST) - regenerate recovery codes
"""

from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash
from datetime import datetime, UTC
import importlib
import logging

from src.helpers import get_db_session, get_current_user_model

auth_bp = Blueprint("auth", __name__)
logger = logging.getLogger(__name__)

# Rate Limiter Referenz (wird in app_factory.py gesetzt)
_limiter = None


def init_limiter(limiter):
    """Wird von app_factory.py aufgerufen um Limiter zu registrieren"""
    global _limiter
    _limiter = limiter


def get_limiter():
    """Holt den konfigurierten Limiter"""
    global _limiter
    return _limiter

# Lazy imports
_models = None
_auth = None
_password_validator = None


def _get_models():
    global _models
    if _models is None:
        _models = importlib.import_module(".02_models", "src")
    return _models


def _get_auth():
    global _auth
    if _auth is None:
        _auth = importlib.import_module(".07_auth", "src")
    return _auth


def _get_password_validator():
    global _password_validator
    if _password_validator is None:
        _password_validator = importlib.import_module(".09_password_validator", "src")
    return _password_validator


# =============================================================================
# UserWrapper für Flask-Login Kompatibilität
# =============================================================================
class UserWrapper:
    """Wrapper für User-Model für Flask-Login Kompatibilität."""
    
    def __init__(self, user_model):
        self.user_model = user_model
        self.id = user_model.id
    
    @property
    def is_authenticated(self):
        return True
    
    @property
    def is_active(self):
        return True
    
    @property
    def is_anonymous(self):
        return False
    
    def get_id(self):
        return str(self.id)


# =============================================================================
# Route 1: / (Zeile 647-653)
# =============================================================================
@auth_bp.route("/")
def index():
    """Hauptseite: Redirect zu Dashboard oder Login"""
    if current_user.is_authenticated:
        return redirect(url_for("emails.dashboard"))
    return redirect(url_for("auth.login"))


# =============================================================================
# Route 2: /login (Zeile 655-763)
# =============================================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login-Seite mit optional 2FA
    
    Rate Limiting: 5 per minute (konfiguriert in app_factory.py via limiter.limit())
    """
    if current_user.is_authenticated:
        return redirect(url_for("emails.dashboard"))

    models = _get_models()
    auth = _get_auth()
    
    try:
        with get_db_session() as db:
            if request.method == "POST":
                username = request.form.get("username")
                password = request.form.get("password")

                user = db.query(models.User).filter_by(username=username).first()

                # Timing-Attack Protection: Dummy password check für constant-time behavior
                if not user:
                    # Dummy bcrypt check to normalize timing (prevent user enumeration)
                    dummy_hash = "$2b$12$" + "0" * 53  # Valid bcrypt format
                    try:
                        check_password_hash(dummy_hash, password)
                    except:
                        pass
                    logger.warning(
                        f"SECURITY[LOGIN_FAILED]: user={username} ip={request.remote_addr} "
                        f"reason=user_not_found"
                    )
                    return (
                        render_template("login.html", error="Ungültige Anmeldedaten"),
                        401,
                    )

                # Account Lockout Check (Phase 9)
                if user.is_locked():
                    remaining = (user.locked_until - datetime.now(UTC)).total_seconds() / 60
                    # Audit Log für Fail2Ban
                    logger.warning(
                        f"SECURITY[LOCKOUT]: user={username} ip={request.remote_addr} "
                        f"remaining={int(remaining)}min reason=account_locked"
                    )
                    return (
                        render_template(
                            "login.html",
                            error=f"Account gesperrt. Bitte versuche es in {int(remaining)} Minuten erneut.",
                        ),
                        403,
                    )

                if not user.check_password(password):
                    # Phase 9f: Atomic SQL-Update (Race Condition Protection)
                    try:
                        user.record_failed_login(db)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        logger.error(f"login: record_failed_login fehlgeschlagen: {e}")
                    # Audit Log für Fail2Ban
                    logger.warning(
                        f"SECURITY[LOGIN_FAILED]: user={username} ip={request.remote_addr} "
                        f"attempts={user.failed_login_attempts}/5 reason=invalid_credentials"
                    )
                    return (
                        render_template("login.html", error="Ungültige Anmeldedaten"),
                        401,
                    )

                # Erfolgreicher Login - Failed Counter zurücksetzen
                # Phase 9f: Atomic SQL-Update (Race Condition Protection)
                try:
                    user.reset_failed_logins(db)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(f"login: reset_failed_logins fehlgeschlagen: {e}")

                # Phase 8: DEK/KEK Pattern - DEK entschlüsseln
                dek = auth.MasterKeyManager.decrypt_dek_from_password(user, password)
                if not dek:
                    logger.error("❌ DEK-Entschlüsselung fehlgeschlagen")
                    return (
                        render_template(
                            "login.html", error="Entschlüsselung fehlgeschlagen"
                        ),
                        401,
                    )

                if user.totp_enabled:
                    # Security: DEK statt Passwort in Session (2FA-Zwischenschritt)
                    session["pending_user_id"] = user.id
                    session["pending_dek"] = dek
                    session["pending_remember"] = bool(request.form.get("remember"))
                    session["pending_auth_time"] = str(datetime.utcnow())
                    return redirect(url_for("auth.verify_2fa"))

                # DEK in Session speichern
                session["master_key"] = dek  # Session-Key heißt "master_key" aus Kompatibilität
                logger.info("✅ DEK erfolgreich in Session geladen")

                # Zero-Knowledge: Disable remember-me (verhindert DEK-Loss nach Session-Expire)
                login_user(UserWrapper(user), remember=False)
                # Audit Log für erfolgreichen Login
                logger.info(
                    f"SECURITY[LOGIN_SUCCESS]: user={user.username} ip={request.remote_addr} "
                    f"2fa=disabled method=password"
                )
                return redirect(url_for("emails.dashboard"))

            return render_template("login.html")
    except Exception as e:
        logger.error(f"login: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Ein Fehler ist aufgetreten. Bitte versuche es erneut.", "danger")
        return render_template("login.html", error="Systemfehler"), 500


# =============================================================================
# Route 3: /register (Zeile 765-883)
# =============================================================================
@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Registrierungs-Seite"""
    if current_user.is_authenticated:
        return redirect(url_for("emails.dashboard"))

    models = _get_models()
    auth = _get_auth()
    password_validator = _get_password_validator()
    
    try:
        with get_db_session() as db:
            if request.method == "POST":
                username = request.form.get("username")
                email = request.form.get("email")
                password = request.form.get("password")
                password_confirm = request.form.get("password_confirm")

                if not all([username, email, password, password_confirm]):
                    return (
                        render_template(
                            "register.html", error="Alle Felder sind erforderlich"
                        ),
                        400,
                    )

                if password != password_confirm:
                    return (
                        render_template(
                            "register.html",
                            error="Passwörter stimmen nicht überein",
                            username=username,
                            email=email,
                        ),
                        400,
                    )

                # Phase INV: Whitelist-Check (außer für ersten User)
                user_count = db.query(models.User).count()
                if user_count > 0:  # Nicht der erste User
                    invite = db.query(models.InvitedEmail).filter_by(email=email, used=False).first()
                    if not invite:
                        return (
                            render_template(
                                "register.html",
                                error="Registration ist nur mit Einladung möglich. Kontaktiere den Administrator.",
                                username=username,
                            ),
                            403,
                        )

                # Phase 8c: Security Hardening - OWASP Password Policy
                try:
                    is_valid, error_msg = password_validator.PasswordValidator.validate(password)
                    if not is_valid:
                        return (
                            render_template(
                                "register.html", error=error_msg, username=username, email=email
                            ),
                            400,
                        )
                except Exception as e:
                    logger.error(f"register: password_validator fehlgeschlagen: {e}")
                    return (
                        render_template(
                            "register.html", error="Passwort-Validierung fehlgeschlagen", username=username, email=email
                        ),
                        500,
                    )

                if db.query(models.User).filter_by(username=username).first():
                    return (
                        render_template(
                            "register.html",
                            error="Benutzername existiert bereits",
                            email=email,
                        ),
                        400,
                    )

                if db.query(models.User).filter_by(email=email).first():
                    return (
                        render_template(
                            "register.html",
                            error="E-Mail existiert bereits",
                            username=username,
                        ),
                        400,
                    )

                user = models.User()
                user.set_username(username)
                user.set_email(email)
                user.set_password(password)

                try:
                    db.add(user)
                    db.commit()

                    # Phase INV: Markiere Invite als verwendet
                    if user_count > 0:
                        invite.used = True
                        invite.used_at = datetime.now(UTC)
                        db.commit()
                except Exception as e:
                    db.rollback()
                    logger.error(f"register: User-Erstellung fehlgeschlagen: {type(e).__name__}: {e}")
                    flash("Registrierung fehlgeschlagen. Bitte versuche es erneut.", "danger")
                    return (
                        render_template(
                            "register.html", error="Registrierung fehlgeschlagen", username=username, email=email
                        ),
                        500,
                    )

                # Phase 8: DEK/KEK Pattern - DEK erstellen und in Session speichern
                try:
                    salt, encrypted_dek, dek = auth.MasterKeyManager.setup_dek_for_user(
                        user.id, password, db
                    )
                    session["master_key"] = dek  # Session-Key heißt "master_key" aus Kompatibilität
                except Exception as e:
                    db.rollback()
                    logger.error(f"register: DEK-Setup fehlgeschlagen: {type(e).__name__}: {e}")
                    flash("Verschlüsselung fehlgeschlagen. Bitte kontaktiere den Administrator.", "danger")
                    return redirect(url_for("auth.login"))

                logger.info(f"✅ User registriert (ID: {user.id}, DEK/KEK erstellt)")

                # Phase 8c: Security Hardening - Mandatory 2FA Setup
                # User wird automatisch zu 2FA-Setup weitergeleitet
                session["mandatory_2fa_setup"] = True
                session["new_user_id"] = user.id
                flash(
                    "Registrierung erfolgreich! Bitte richte jetzt 2FA ein (Pflichtfeld).",
                    "success",
                )
                return redirect(url_for("auth.setup_2fa"))

            return render_template("register.html")
    except Exception as e:
        logger.error(f"register: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Ein Fehler ist aufgetreten. Bitte versuche es erneut.", "danger")
        return render_template("register.html", error="Systemfehler"), 500


# =============================================================================
# Route 4: /2fa/verify (Zeile 885-955)
# =============================================================================
@auth_bp.route("/2fa/verify", methods=["GET", "POST"])
def verify_2fa():
    """2FA-Verifikation
    
    Rate Limiting: 5 per minute (konfiguriert in app_factory.py via limiter.limit())
    """
    user_id = session.get("pending_user_id")

    if not user_id:
        return redirect(url_for("auth.login"))

    models = _get_models()
    auth = _get_auth()
    
    try:
        with get_db_session() as db:
            user = db.query(models.User).filter_by(id=user_id).first()

            if not user or not user.totp_enabled:
                return redirect(url_for("auth.login"))

            if request.method == "POST":
                token = request.form.get("token", "").strip()
                recovery_code = request.form.get("recovery_code", "").strip()

                verified = False

                if token and len(token) == 6:
                    try:
                        verified = auth.AuthManager.verify_totp(user.totp_secret, token)
                    except Exception as e:
                        logger.error(f"verify_2fa: TOTP-Verifikation fehlgeschlagen: {e}")
                        verified = False

                elif recovery_code:
                    try:
                        verified = auth.RecoveryCodeManager.verify_recovery_code(
                            user.id, recovery_code, db
                        )
                    except Exception as e:
                        db.rollback()
                        logger.error(f"verify_2fa: Recovery-Code-Verifikation fehlgeschlagen: {e}")
                        verified = False

                if verified:
                    # Extract pending data BEFORE session operations
                    dek = session.get("pending_dek")
                    remember = session.get("pending_remember", False)

                    # Clear pending 2FA data
                    session.pop("pending_user_id", None)
                    session.pop("pending_dek", None)
                    session.pop("pending_remember", None)
                    session.pop("pending_auth_time", None)

                    # Phase 8: DEK/KEK Pattern
                    if not dek:
                        logger.error("❌ Kein DEK für 2FA gefunden")
                        flash("Session abgelaufen - bitte erneut einloggen", "danger")
                        return redirect(url_for("auth.login"))

                    session["master_key"] = dek
                    logger.info("✅ DEK nach 2FA in Session geladen")

                    try:
                        login_user(UserWrapper(user), remember=remember)
                    except Exception as e:
                        logger.error(f"verify_2fa: login_user fehlgeschlagen: {e}")
                        flash("Login fehlgeschlagen. Bitte versuche es erneut.", "danger")
                        return redirect(url_for("auth.login"))
                    
                    # Audit Log für erfolgreichen Login mit 2FA
                    logger.info(
                        f"SECURITY[LOGIN_SUCCESS]: user={user.username} ip={request.remote_addr} "
                        f"2fa=verified method=totp"
                    )
                    return redirect(url_for("emails.dashboard"))

                # Fehlgeschlagener 2FA-Versuch
                logger.warning(
                    f"SECURITY[2FA_FAILED]: user={user.username} ip={request.remote_addr} "
                    f"reason=invalid_token"
                )
                return render_template("verify_2fa.html", error="Ungültiger Code"), 401

            return render_template("verify_2fa.html")
    except Exception as e:
        logger.error(f"verify_2fa: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Ein Fehler ist aufgetreten. Bitte versuche es erneut.", "danger")
        return redirect(url_for("auth.login"))


# =============================================================================
# Route 5: /logout (Zeile 957-976)
# =============================================================================
@auth_bp.route("/logout")
@login_required
def logout():
    """Logout mit ServiceToken-Cleanup (Security Fix)"""
    username = (
        current_user.user_model.username
        if hasattr(current_user, "user_model")
        else "User"
    )
    user_id = current_user.user_model.id if hasattr(current_user, "user_model") else None
    ip = request.remote_addr

    # Audit Log für Logout
    logger.info(f"SECURITY[LOGOUT]: user={username} ip={ip}")

    # SECURITY FIX: Lösche ALLE aktiven ServiceTokens des Users
    # Verhindert Token-Leak nach Logout (DEK liegt in Token-DB!)
    if user_id:
        try:
            with get_db_session() as db:
                deleted_count = db.query(models.ServiceToken).filter_by(
                    user_id=user_id
                ).delete()
                db.commit()
                if deleted_count > 0:
                    logger.info(f"SECURITY[LOGOUT]: {deleted_count} ServiceTokens gelöscht für user={username}")
        except Exception as e:
            logger.error(f"SECURITY[LOGOUT]: Fehler beim Löschen von ServiceTokens: {e}")
            # Logout trotzdem fortsetzen

    # Zero-Knowledge: Komplette Session löschen (DEK + pending_* + oauth-state etc.)
    session.clear()

    logout_user()
    return redirect(url_for("auth.login"))


# =============================================================================
# Route 6: /settings/2fa/setup (Zeile 6497-6548)
# =============================================================================
@auth_bp.route("/settings/2fa/setup", methods=["GET", "POST"])
@login_required
def setup_2fa():
    """2FA Setup: QR-Code und Recovery-Codes"""
    auth = _get_auth()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            if user.totp_enabled:
                return redirect(url_for("accounts.settings"))

            if request.method == "POST":
                token = request.form.get("token", "").strip()

                totp_secret = session.get("totp_setup_secret")
                if not totp_secret:
                    return redirect(url_for("auth.setup_2fa"))

                try:
                    if not auth.AuthManager.verify_totp(totp_secret, token):
                        return render_template("setup_2fa.html", error="Ungültiger Code"), 401
                except Exception as e:
                    logger.error(f"setup_2fa: TOTP-Verifikation fehlgeschlagen: {e}")
                    return render_template("setup_2fa.html", error="Verifikation fehlgeschlagen"), 500

                try:
                    user.totp_secret = totp_secret
                    user.totp_enabled = True
                    db.commit()

                    recovery_codes = auth.RecoveryCodeManager.create_recovery_codes(
                        user.id, db, count=10
                    )
                except Exception as e:
                    db.rollback()
                    logger.error(f"setup_2fa: 2FA-Aktivierung fehlgeschlagen: {type(e).__name__}: {e}")
                    flash("2FA-Setup fehlgeschlagen. Bitte versuche es erneut.", "danger")
                    return redirect(url_for("auth.setup_2fa"))

                session.pop("totp_setup_secret", None)

                logger.info(f"✅ 2FA für User {user.username} aktiviert")

                return render_template(
                    "setup_2fa_success.html", recovery_codes=recovery_codes
                )

            totp_secret = auth.AuthManager.generate_totp_secret()
            qr_code = auth.AuthManager.generate_qr_code(user.email, totp_secret)

            session["totp_setup_secret"] = totp_secret

            return render_template(
                "setup_2fa.html", qr_code=qr_code, totp_secret=totp_secret
            )
    except Exception as e:
        logger.error(f"setup_2fa: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Ein Fehler ist aufgetreten. Bitte versuche es erneut.", "danger")
        return redirect(url_for("auth.login"))


# =============================================================================
# Route 7: /settings/2fa/recovery-codes/regenerate (Zeile 6550-6581)
# =============================================================================
@auth_bp.route("/settings/2fa/recovery-codes/regenerate", methods=["POST"])
@login_required
def regenerate_recovery_codes():
    """Generiert neue Recovery-Codes und invalidiert alte (Phase 8c Security Hardening)"""
    auth = _get_auth()
    
    try:
        with get_db_session() as db:
            user = get_current_user_model(db)
            if not user:
                return redirect(url_for("auth.login"))

            if not user.totp_enabled:
                flash("2FA ist nicht aktiviert", "danger")
                return redirect(url_for("accounts.settings"))

            try:
                # Invalidiere alle alten Recovery-Codes
                auth.RecoveryCodeManager.invalidate_all_codes(user.id, db)

                # Generiere neue 10 Recovery-Codes
                recovery_codes = auth.RecoveryCodeManager.create_recovery_codes(
                    user.id, db, count=10
                )
            except Exception as e:
                db.rollback()
                logger.error(f"regenerate_recovery_codes: Regenerierung fehlgeschlagen: {type(e).__name__}: {e}")
                flash("Regenerierung der Recovery-Codes fehlgeschlagen. Alte Codes bleiben gültig.", "danger")
                return redirect(url_for("accounts.settings"))

            logger.info(f"✅ Recovery-Codes regeneriert für User {user.id}")

            return render_template(
                "recovery_codes_regenerated.html", recovery_codes=recovery_codes
            )
    except Exception as e:
        logger.error(f"regenerate_recovery_codes: Unerwarteter Fehler: {type(e).__name__}: {e}")
        flash("Ein Fehler ist aufgetreten. Bitte versuche es erneut.", "danger")
        return redirect(url_for("accounts.settings"))
