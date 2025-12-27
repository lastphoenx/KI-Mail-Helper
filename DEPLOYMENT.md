# Production Deployment Guide

## Prerequisites

- Debian/Ubuntu Server (tested on Debian 12)
- Python 3.11+ with venv
- Nginx (optional, for reverse proxy)
- systemd

## Installation Steps

### 1. Clone Repository

```bash
cd /opt
git clone https://github.com/lastphoenx/KI-Mail-Helper.git
cd KI-Mail-Helper
```

### 2. Setup Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Generate SECRET_KEY

```bash
# Generate secure random key (64 characters)
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# Example output: xK8_zQ9vN2mP5wR7yT3uE6aS1dF4gH0jL9cV8bN5mW2pQ7rT3yU6

# Store in system environment (NOT in .env file!)
sudo nano /etc/environment
# Add line:
FLASK_SECRET_KEY=xK8_zQ9vN2mP5wR7yT3uE6aS1dF4gH0jL9cV8bN5mW2pQ7rT3yU6
```

### 4. Configure Database

```bash
# Initialize database
python3 -m src.00_main --init-db

# Create first user
python3 -m src.00_main --register
# Follow prompts for username/password
```

### 5. Setup Systemd Service

```bash
# Copy service file
sudo cp mail-helper.service /etc/systemd/system/

# Edit service file with your paths and SECRET_KEY
sudo nano /etc/systemd/system/mail-helper.service

# IMPORTANT: Change FLASK_SECRET_KEY to your generated key!
# Change User/Group if not 'thomas'
# Change WorkingDirectory to your install path

# Create log directory
mkdir -p logs

# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable mail-helper

# Start service
sudo systemctl start mail-helper

# Check status
sudo systemctl status mail-helper
```

### 6. Configure Nginx Reverse Proxy (Optional but Recommended)

```nginx
# /etc/nginx/sites-available/mail-helper
server {
    listen 80;
    server_name mail.yourdomain.com;
    
    # Redirect HTTP → HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name mail.yourdomain.com;
    
    # SSL Certificate (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/mail.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/mail.yourdomain.com/privkey.pem;
    
    # SSL Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "DENY" always;
    
    # Proxy to Gunicorn
    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # Rate Limiting (additional to Flask-Limiter)
    limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;
    location /login {
        limit_req zone=login_limit burst=2 nodelay;
        proxy_pass http://127.0.0.1:5001;
        # ... proxy headers ...
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/mail-helper /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 7. Firewall Configuration

```bash
# UFW Firewall
sudo ufw allow 22/tcp     # SSH
sudo ufw allow 80/tcp     # HTTP (redirect)
sudo ufw allow 443/tcp    # HTTPS
sudo ufw enable

# iptables (alternative)
sudo iptables -A INPUT -p tcp --dport 22 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 443 -j ACCEPT
```

### 8. Install Fail2Ban (Network-Level Protection)

Fail2Ban schützt auf Netzwerk-Ebene durch IP-Banning basierend auf Audit-Logs.

#### Installation

```bash
sudo apt install fail2ban
```

#### Filter konfigurieren

```bash
sudo nano /etc/fail2ban/filter.d/mail-helper.conf
```

Inhalt von `fail2ban-filter.conf` kopieren (im Projekt-Root):

```ini
[Definition]
# Fail2Ban Filter für KI-Mail-Helper
# Detektiert: Login-Fehler, 2FA-Fehler, Account-Lockouts

failregex = ^.*SECURITY\[LOGIN_FAILED\]: user=\S+ ip=<HOST>.*$
            ^.*SECURITY\[2FA_FAILED\]: user=\S+ ip=<HOST>.*$
            ^.*SECURITY\[LOCKOUT\]: user=\S+ ip=<HOST>.*$

ignoreregex = ^.*SECURITY\[LOGIN_SUCCESS\]:.*$
              ^.*SECURITY\[LOGOUT\]:.*$

datepattern = {^LN-BEG}%%Y-%%m-%%d %%H:%%M:%%S
```

#### Jail konfigurieren

```bash
sudo nano /etc/fail2ban/jail.d/mail-helper.conf
```

Inhalt von `fail2ban-jail.conf` kopieren:

```ini
[mail-helper]
enabled = true
port = http,https
filter = mail-helper
logpath = /home/thomas/projects/KI-Mail-Helper/logs/gunicorn_error.log
          /home/thomas/projects/KI-Mail-Helper/logs/gunicorn_access.log
maxretry = 5
findtime = 600
bantime = 3600
action = iptables-multiport[name=mail-helper, port="http,https"]
```

#### Aktivieren und testen

```bash
# Fail2Ban starten
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban

# Status prüfen
sudo fail2ban-client status mail-helper

# Filter testen (vor Production Deployment!)
fail2ban-regex logs/gunicorn_error.log /etc/fail2ban/filter.d/mail-helper.conf

# Gebannte IPs anzeigen
sudo fail2ban-client status mail-helper

# IP entbannen (Testing)
sudo fail2ban-client set mail-helper unbanip 192.168.1.100
```

#### Multi-Layer Protection

Die App nutzt 3 Sicherheitsebenen:

1. **Flask-Limiter**: 5 Versuche/Minute pro IP (Application)
2. **Account Lockout**: 5 Fails → 15min User-Sperre (Database)
3. **Fail2Ban**: 5 Fails/10min → 1h IP-Ban (Network)

→ Fail2Ban greift erst, wenn Flask-Limiter umgangen wird (z.B. Tor, VPN, verteilte Angriffe)

## Management Commands

```bash
# Start service
sudo systemctl start mail-helper

# Stop service
sudo systemctl stop mail-helper

# Restart service
sudo systemctl restart mail-helper

# Reload workers (zero-downtime)
sudo systemctl reload mail-helper

# View logs (live)
sudo journalctl -u mail-helper -f

# View application logs
tail -f logs/gunicorn_access.log
tail -f logs/gunicorn_error.log

# Check service status
sudo systemctl status mail-helper
```

## Backup Strategy

### Automated Daily Backups

Das Projekt enthält ein Backup-Script mit automatischer Rotation:

```bash
# Script ausführbar machen
chmod +x scripts/backup_database.sh

# Manuelles Backup testen
./scripts/backup_database.sh

# Backup-Verzeichnis prüfen
ls -lh backups/daily/
```

### Crontab Installation

```bash
# Crontab bearbeiten
crontab -e

# Tägliches Backup um 2:00 Uhr
0 2 * * * /home/thomas/projects/KI-Mail-Helper/scripts/backup_database.sh

# Wöchentliches Backup um 3:00 Uhr (Sonntag)
0 3 * * 0 /home/thomas/projects/KI-Mail-Helper/scripts/backup_database.sh weekly
```

### Backup-Funktionen

✅ **SQLite Hot Backup**: Sicheres Backup während laufendem Betrieb  
✅ **Integrity Check**: Automatische Integritätsprüfung nach Backup  
✅ **Kompression**: gzip-Kompression spart Speicherplatz  
✅ **Rotation**: Automatisches Löschen alter Backups (30 Tage daily, 90 Tage weekly)  
✅ **Logging**: Detaillierte Logs mit Timestamps  
✅ **Error Handling**: Abbbruch bei Fehlern, Exit-Codes für Monitoring  

### Backup Restore

```bash
# Backup wiederherstellen (Application stoppen!)
sudo systemctl stop mail-helper

# Neuestes Backup finden
ls -lt backups/daily/ | head -n 1

# Dekomprimieren und wiederherstellen
gunzip -c backups/daily/emails_20251227_232443.db.gz > emails.db

# Integrität prüfen
sqlite3 emails.db "PRAGMA integrity_check;"

# Application starten
sudo systemctl start mail-helper
```

### Remote Backup (Optional)

Das Script enthält Hooks für Remote-Backups (auskommentiert):

```bash
# rsync zu Remote-Server
rsync -avz "$BACKUP_FILE" user@backup-server:/path/to/backups/

# rclone (Google Drive, S3, etc.)
rclone copy "$BACKUP_FILE" remote:mail-helper-backups/
```

## Security Checklist

### Production Hardening - Phase 1 ✅

- [x] **FLASK_SECRET_KEY** aus System Environment (NOT .env!)
- [x] **Gunicorn** als Production WSGI Server
- [x] **Flask-Limiter** Rate Limiting (5/min Login/2FA)
- [x] **Systemd Service** mit Security Hardening

### Production Hardening - Phase 2 ✅

- [x] **Account Lockout**: 5 Failed → 15min Ban
- [x] **Session Timeout**: 30min Inaktivität → Auto-Logout
- [x] **Audit Logging**: Strukturierte SECURITY[] Logs für Monitoring
- [x] **Database Backups**: Automatische tägliche Backups mit Rotation

### Infrastructure Security

- [ ] **Nginx Reverse Proxy** mit Let's Encrypt SSL
- [ ] **Firewall** aktiviert (UFW/iptables)
- [ ] **Fail2Ban** konfiguriert und getestet
- [ ] **Monitoring** Setup (Logs, Disk Space, Performance)

### Application Security (Phases 1-8)

- [x] **Strong Passwords**: HIBP-Check, min. 24 Zeichen
- [x] **2FA**: TOTP für alle User
- [x] **HTTPS Enforcement**: HSTS, Secure Cookies
- [x] **CSRF Protection**: Flask-WTF Tokens
- [x] **Zero-Knowledge Encryption**: DEK/KEK Pattern
- [x] **XSS Protection**: CSP Nonce (9/10)
- [x] **Code Review**: Automatisch mit Claude (5-10% False Positives)

**Aktueller Security Score: 98/100** 🔒

## Monitoring

```bash
# Server resources
htop

# Disk space
df -h

# Check gunicorn workers
ps aux | grep gunicorn

# Network connections
ss -tulpn | grep 5001
```

## Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u mail-helper -n 50
tail -n 50 logs/gunicorn_error.log

# Check config syntax
/opt/KI-Mail-Helper/venv/bin/gunicorn \
    --config gunicorn.conf.py \
    --check-config \
    src.01_web_app:app
```

### Database locked errors
```bash
# Check file permissions
ls -la emails.db

# Fix ownership
chown thomas:thomas emails.db
chmod 644 emails.db
```

### Workers dying frequently
```bash
# Increase worker timeout in gunicorn.conf.py
timeout = 60  # Instead of 30

# Check memory usage
free -h
```

## Updates

```bash
cd /opt/KI-Mail-Helper
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart mail-helper
```

## Support

- GitHub Issues: https://github.com/lastphoenx/KI-Mail-Helper/issues
- Documentation: See README.md
- Security Issues: See SECURITY.md
