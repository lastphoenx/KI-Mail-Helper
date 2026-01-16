#!/bin/bash
# Setup Script für Celery Systemd Services
# Installiert Services und startet sie

set -euo pipefail

echo "🚀 KI-Mail-Helper Celery Systemd Setup"
echo "======================================="
echo ""

# Check: Läuft als User thomas?
if [ "$USER" != "thomas" ]; then
    echo "❌ Dieses Script muss als User 'thomas' laufen!"
    echo "   Bitte nicht mit sudo ausführen."
    exit 1
fi

# Check: Sind Service-Dateien vorhanden?
if [ ! -f "config/mail-helper-celery-worker.service" ]; then
    echo "❌ Service-Dateien nicht gefunden!"
    echo "   Stelle sicher, dass du im Projektverzeichnis bist."
    exit 1
fi

echo "📋 Installation der systemd-Services..."
echo ""

# 1. Services nach /etc/systemd/system/ kopieren
echo "1️⃣  Kopiere Service-Dateien..."
sudo cp config/mail-helper-celery-worker.service /etc/systemd/system/
sudo cp config/mail-helper-celery-beat.service /etc/systemd/system/
sudo cp config/mail-helper-celery-flower.service /etc/systemd/system/
echo "   ✅ Service-Dateien kopiert"
echo ""

# 2. systemd reload
echo "2️⃣  Reload systemd daemon..."
sudo systemctl daemon-reload
echo "   ✅ systemd reloaded"
echo ""

# 3. Services enablen (Auto-Start)
echo "3️⃣  Enable Services (Auto-Start)..."
sudo systemctl enable mail-helper-celery-worker.service
sudo systemctl enable mail-helper-celery-beat.service
sudo systemctl enable mail-helper-celery-flower.service
echo "   ✅ Services enabled"
echo ""

# 4. Services starten
echo "4️⃣  Starte Services..."
sudo systemctl start mail-helper-celery-worker.service
sleep 2
sudo systemctl start mail-helper-celery-beat.service
sleep 1
sudo systemctl start mail-helper-celery-flower.service
sleep 1
echo "   ✅ Services gestartet"
echo ""

# 5. Status prüfen
echo "5️⃣  Status-Check..."
echo ""
sudo systemctl status mail-helper-celery-worker.service --no-pager | head -n 5
echo ""
sudo systemctl status mail-helper-celery-beat.service --no-pager | head -n 5
echo ""
sudo systemctl status mail-helper-celery-flower.service --no-pager | head -n 5
echo ""

# 6. Health-Check
echo "======================================="
echo "🏥 Running Health-Check..."
echo ""
bash scripts/celery-health-check.sh

echo ""
echo "======================================="
echo "✅ Setup Complete!"
echo ""
echo "📍 Nützliche Befehle:"
echo "   Status:    systemctl status mail-helper-celery-worker"
echo "   Logs:      sudo journalctl -u mail-helper-celery-worker -f"
echo "   Restart:   sudo systemctl restart mail-helper-celery-worker"
echo "   Stop:      sudo systemctl stop mail-helper-celery-worker"
echo ""
echo "🌸 Flower Web UI:  http://localhost:5555"
echo ""
