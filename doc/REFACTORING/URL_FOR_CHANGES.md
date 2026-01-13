# URL_FOR_CHANGES.md

**Erstellt:** 11. Januar 2026  
**Zweck:** Dokumentation aller url_for() Änderungen

---

## 📊 ÜBERSICHT

| Alt | Neu | Anzahl |
|-----|-----|--------|
| `url_for("login")` | `url_for("auth.login")` | 28 |
| `url_for('login')` | `url_for('auth.login')` | 1 |
| `url_for("settings")` | `url_for("accounts.settings")` | 20 |
| `url_for("dashboard")` | `url_for("emails.dashboard")` | 6 |
| `url_for("list_view")` | `url_for("emails.list_view")` | 5 |
| `url_for("setup_2fa")` | `url_for("auth.setup_2fa")` | 3 |
| `url_for("verify_2fa")` | `url_for("auth.verify_2fa")` | 1 |
| `url_for("index")` | `url_for("auth.index")` | 1 |
| `url_for("google_oauth_callback", ...)` | `url_for("accounts.google_oauth_callback", ...)` | 1 |

**Gesamt: 66 Änderungen**

---

## 🔄 DETAILLIERTE ÄNDERUNGEN

### 1. auth.login (29×)

**Zeilen:** 294, 652, 660, 892, 900, 931, 975, 987, 1132, 1474, 1522, 2408, 2497, 2535, 2586, 2734, 4890, 5394, 6331, 6455, 6506, 6559, 6599, 6648, 6818, 6950, 7199, 8995, 9001

```python
# Alt:
return redirect(url_for("login"))

# Neu:
return redirect(url_for("auth.login"))
```

---

### 2. accounts.settings (20×)

**Zeilen:** 2592, 2601, 2617, 2621, 2630, 2656, 2661, 6350, 6354, 6358, 6377, 6509, 6563, 6792, 6926, 6959, 7105, 7149, 7175, 7179

```python
# Alt:
return redirect(url_for("settings"))
return redirect(url_for("settings") + f"#fetch_config_account_{account_id}")

# Neu:
return redirect(url_for("accounts.settings"))
return redirect(url_for("accounts.settings") + f"#fetch_config_account_{account_id}")
```

---

### 3. emails.dashboard (6×)

**Zeilen:** 651, 757, 769, 942, 7204

```python
# Alt:
return redirect(url_for("dashboard"))

# Neu:
return redirect(url_for("emails.dashboard"))
```

---

### 4. emails.list_view (5×)

**Zeilen:** 1537, 1823, 1830, 1863, 1868

```python
# Alt:
return redirect(url_for("list_view"))
return redirect(request.referrer or url_for("list_view"))

# Neu:
return redirect(url_for("emails.list_view"))
return redirect(request.referrer or url_for("emails.list_view"))
```

---

### 5. auth.setup_2fa (3×)

**Zeilen:** 302, 877, 6516

```python
# Alt:
return redirect(url_for("setup_2fa"))

# Neu:
return redirect(url_for("auth.setup_2fa"))
```

---

### 6. auth.verify_2fa (1×)

**Zeile:** 742

```python
# Alt:
return redirect(url_for("verify_2fa"))

# Neu:
return redirect(url_for("auth.verify_2fa"))
```

---

### 7. auth.index (1×)

**Zeile:** 8494

```python
# Alt:
return redirect(url_for("index"))

# Neu:
return redirect(url_for("auth.index"))
```

---

### 8. accounts.google_oauth_callback (1×)

**Zeile:** 6619, 6700

```python
# Alt:
redirect_uri = url_for("google_oauth_callback", _external=True, _scheme="http")

# Neu:
redirect_uri = url_for("accounts.google_oauth_callback", _external=True, _scheme="http")
```

---

## 🔍 SUCH- UND ERSETZE-BEFEHLE

```bash
# Reihenfolge ist wichtig! Längere zuerst ersetzen.

# 1. google_oauth_callback (mit Parametern - manuell prüfen)
sed -i 's/url_for("google_oauth_callback"/url_for("accounts.google_oauth_callback"/g' src/blueprints/*.py

# 2. setup_2fa
sed -i 's/url_for("setup_2fa")/url_for("auth.setup_2fa")/g' src/blueprints/*.py

# 3. verify_2fa
sed -i 's/url_for("verify_2fa")/url_for("auth.verify_2fa")/g' src/blueprints/*.py

# 4. list_view
sed -i 's/url_for("list_view")/url_for("emails.list_view")/g' src/blueprints/*.py

# 5. dashboard
sed -i 's/url_for("dashboard")/url_for("emails.dashboard")/g' src/blueprints/*.py

# 6. settings
sed -i 's/url_for("settings")/url_for("accounts.settings")/g' src/blueprints/*.py

# 7. login (beide Varianten)
sed -i 's/url_for("login")/url_for("auth.login")/g' src/blueprints/*.py
sed -i "s/url_for('login')/url_for('auth.login')/g" src/blueprints/*.py

# 8. index
sed -i 's/url_for("index")/url_for("auth.index")/g' src/blueprints/*.py
```

---

## ⚠️ TEMPLATES PRÜFEN!

**12 url_for() Aufrufe in 6 Template-Dateien:**

| Template | url_for() Aufrufe | Zu ändern |
|----------|-------------------|-----------|
| `templates/reply_styles.html` | `url_for('settings')` | → `url_for('accounts.settings')` |
| `templates/mail_fetch_config.html` | `url_for('settings')` | → `url_for('accounts.settings')` |
| `templates/whitelist_imap_setup.html` | `url_for('settings')`, `url_for("index")` | → Blueprint-qualified |
| `templates/tag_suggestions.html` | `url_for('settings')` | → `url_for('accounts.settings')` |
| `templates/reply_styles_old.html` | `url_for('settings')` | → `url_for('accounts.settings')` |
| `templates/whitelist.html` | `url_for('settings')`, `url_for('whitelist')`, `url_for('ki_prio')`, `url_for('mail_fetch_config')` | → Blueprint-qualified |

### Template-Änderungen:

```bash
# Templates aktualisieren
sed -i "s/url_for('settings')/url_for('accounts.settings')/g" templates/*.html
sed -i "s/url_for('whitelist')/url_for('accounts.whitelist')/g" templates/*.html
sed -i "s/url_for('ki_prio')/url_for('accounts.ki_prio')/g" templates/*.html
sed -i "s/url_for('mail_fetch_config')/url_for('accounts.mail_fetch_config')/g" templates/*.html
sed -i 's/url_for("index")/url_for("auth.index")/g' templates/*.html
```

---

## 📊 ZUSAMMENFASSUNG ALLER ÄNDERUNGEN

| Bereich | Anzahl |
|---------|--------|
| Python (01_web_app.py → Blueprints) | 66 |
| Templates | 12 |
| **GESAMT** | **78** |

---

## ✅ VALIDIERUNG

Nach Refactoring ausführen:

```bash
# Keine alten url_for() mehr:
grep -rn 'url_for("login")' src/blueprints/
grep -rn 'url_for("settings")' src/blueprints/
grep -rn 'url_for("dashboard")' src/blueprints/

# Erwartete Ergebnisse: 0 Treffer
```

---

## 📋 BLUEPRINT-ZUORDNUNG

| Funktion | Blueprint |
|----------|-----------|
| `login` | auth |
| `register` | auth |
| `logout` | auth |
| `verify_2fa` | auth |
| `setup_2fa` | auth |
| `regenerate_recovery_codes` | auth |
| `index` | auth |
| `dashboard` | emails |
| `list_view` | emails |
| `threads_view` | emails |
| `email_detail` | emails |
| `render_email_html` | emails |
| `settings` | accounts |
| `google_oauth_callback` | accounts |
| `microsoft_oauth_callback` | accounts |
| `rules_management` | rules |
| `training` | training |
| `admin_dashboard` | admin |
