#!/bin/bash
# Test Alembic Migrations gegen PostgreSQL
# FÜHRE DIES AUS BEVOR DU MIT DER MIGRATION BEGINNST!

set -e

echo "🧪 ALEMBIC POSTGRESQL COMPATIBILITY TEST"
echo "========================================"

# 1. PostgreSQL Test-Container starten
echo "📦 Starte PostgreSQL Test-Container..."
docker run -d --name alembic-test-pg \
  -e POSTGRES_PASSWORD=test123 \
  -e POSTGRES_DB=mail_helper_test \
  -p 5433:5432 \
  postgres:15-alpine

sleep 5

# 2. Test-Verbindung
echo "🔌 Teste Verbindung..."
psql postgresql://postgres:test123@localhost:5433/mail_helper_test -c "SELECT 1" || {
  echo "❌ PostgreSQL Verbindung fehlgeschlagen!"
  docker stop alembic-test-pg
  docker rm alembic-test-pg
  exit 1
}

# 3. Alembic Migrations generieren (dry-run)
echo "📝 Generiere Migrations SQL (dry-run)..."
DATABASE_URL=postgresql://postgres:test123@localhost:5433/mail_helper_test \
  alembic upgrade head --sql > /tmp/migration_sql.sql

echo "✅ SQL generiert: /tmp/migration_sql.sql"

# 4. Prüfe auf SQLite-spezifische Syntax
echo "🔍 Prüfe auf SQLite-spezifische DDL..."
SQLITE_ISSUES=0

if grep -i "autoincrement\|pragma\|without rowid" /tmp/migration_sql.sql; then
  echo "⚠️  WARNUNG: SQLite-spezifische Syntax gefunden!"
  echo "   Diese Statements müssen für PostgreSQL angepasst werden."
  SQLITE_ISSUES=1
fi

# Prüfe auf String() ohne Länge (kann PostgreSQL-Probleme verursachen)
if grep -E "String\(\)" /tmp/migration_sql.sql; then
  echo "⚠️  WARNUNG: String() ohne Länge gefunden!"
  echo "   PostgreSQL empfiehlt explizite Längen: String(255)"
  SQLITE_ISSUES=1
fi

if [ $SQLITE_ISSUES -eq 0 ]; then
  echo "✅ Keine SQLite-spezifische Syntax gefunden"
fi

# 5. Führe Migrations tatsächlich aus
echo "🚀 Führe Migrations aus..."
DATABASE_URL=postgresql://postgres:test123@localhost:5433/mail_helper_test \
  alembic upgrade head || {
  echo "❌ Migration fehlgeschlagen!"
  docker stop alembic-test-pg
  docker rm alembic-test-pg
  exit 1
}

echo "✅ Migrations erfolgreich!"

# 6. Validiere Schema
echo "📊 Validiere Schema..."
psql postgresql://postgres:test123@localhost:5433/mail_helper_test << 'EOF'
-- Prüfe kritische Tabellen
SELECT 'users' as table_name, count(*) as exists FROM information_schema.tables WHERE table_name = 'users'
UNION ALL
SELECT 'mail_accounts', count(*) FROM information_schema.tables WHERE table_name = 'mail_accounts'
UNION ALL
SELECT 'raw_emails', count(*) FROM information_schema.tables WHERE table_name = 'raw_emails'
UNION ALL
SELECT 'processed_emails', count(*) FROM information_schema.tables WHERE table_name = 'processed_emails';

-- Prüfe Indizes
\di
EOF

# 7. Cleanup
echo "🧹 Cleanup..."
docker stop alembic-test-pg
docker rm alembic-test-pg

echo ""
echo "✅ ALEMBIC POSTGRESQL COMPATIBILITY TEST ERFOLGREICH!"
echo ""
echo "Nächste Schritte:"
echo "1. Prüfe /tmp/migration_sql.sql auf Probleme"
echo "2. Wenn alles OK: Starte mit echter Migration"
