#!/bin/bash
# IMAP Server Discovery für verschiedene Domains
# Hilft zu finden, welcher IMAP-Server für eine E-Mail-Domain genutzt wird

echo "🔍 IMAP Server Discovery Tool"
echo "=============================="
echo ""

# Check if domain provided
if [ -z "$1" ]; then
    echo "Usage: $0 <domain>"
    echo "Example: $0 example.com"
    echo ""
    exit 1
fi

DOMAIN=$1
echo "📧 Analysiere Domain: $DOMAIN"
echo ""

# 1. MX Records (Mail Exchange - zeigt Mail-Server)
echo "1️⃣  MX Records (Mail-Server):"
echo "   (Zeigt, welcher Server E-Mails empfängt)"
echo ""
MX_RECORDS=$(nslookup -type=mx $DOMAIN 2>/dev/null | grep "mail exchanger" || echo "Keine MX Records gefunden")
echo "$MX_RECORDS"
echo ""

# 2. Häufige IMAP-Server testen
echo "2️⃣  Teste häufige IMAP-Server:"
echo ""

IMAP_SERVERS=(
    "imap.$DOMAIN"
    "mail.$DOMAIN"
    "smtp.$DOMAIN"
    "outlook.office365.com"
    "imap.gmail.com"
)

for SERVER in "${IMAP_SERVERS[@]}"; do
    echo -n "   Teste $SERVER:993 ... "
    
    # Test mit timeout (5 Sekunden)
    timeout 5 bash -c "cat < /dev/null > /dev/tcp/$SERVER/993" 2>/dev/null
    
    if [ $? -eq 0 ]; then
        echo "✅ ERREICHBAR (möglicher IMAP-Server!)"
    else
        echo "❌ nicht erreichbar"
    fi
done

echo ""
echo "3️⃣  DNS Lookup für Standard-Server:"
echo ""

# Check standard IMAP domains
for PREFIX in "imap" "mail" "smtp"; do
    echo -n "   $PREFIX.$DOMAIN: "
    RESULT=$(nslookup $PREFIX.$DOMAIN 2>/dev/null | grep "Address:" | tail -1)
    if [ -z "$RESULT" ]; then
        echo "❌ nicht gefunden"
    else
        IP=$(echo $RESULT | awk '{print $2}')
        echo "✅ $IP"
    fi
done

echo ""
echo "4️⃣  Autoconfig-Server (Thunderbird-Style):"
echo ""

# Thunderbird autoconfig
AUTOCONFIG_URL="https://autoconfig.$DOMAIN/mail/config-v1.1.xml"
echo "   Teste: $AUTOCONFIG_URL"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 $AUTOCONFIG_URL 2>/dev/null)
if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✅ Autoconfig gefunden! Lade Konfiguration..."
    curl -s --max-time 5 $AUTOCONFIG_URL | grep -E "(hostname|port|socketType|username)" | sed 's/^/   /'
else
    echo "   ❌ Kein Autoconfig verfügbar"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📋 ZUSAMMENFASSUNG"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Mögliche IMAP-Server für $DOMAIN:"
echo ""

# Extrahiere wahrscheinliche Server aus MX Records
if echo "$MX_RECORDS" | grep -q "outlook"; then
    echo "🔹 Microsoft Office365 erkannt!"
    echo "   IMAP: outlook.office365.com:993 (SSL)"
    echo "   SMTP: smtp.office365.com:587 (STARTTLS)"
    echo "   Username: vollständige E-Mail-Adresse"
    echo ""
elif echo "$MX_RECORDS" | grep -q "google"; then
    echo "🔹 Google Workspace erkannt!"
    echo "   IMAP: imap.gmail.com:993 (SSL)"
    echo "   SMTP: smtp.gmail.com:587 (STARTTLS)"
    echo "   Username: vollständige E-Mail-Adresse"
    echo ""
else
    echo "🔹 Eigener Mail-Server (wahrscheinlich)"
    echo "   Teste die ✅ ERREICHBAR Server oben!"
    echo ""
fi

echo "💡 Tipp: Nutze diese Einstellungen in deiner App!"
echo ""
