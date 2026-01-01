#!/bin/bash
# Quick DB checks for Phase 14

echo "=== Phase 14: DB Status Check ==="
echo

echo "1️⃣ Anzahl Mails mit UIDVALIDITY:"
sqlite3 emails.db "SELECT COUNT(*) FROM raw_emails WHERE imap_uidvalidity IS NOT NULL;"

echo
echo "2️⃣ Anzahl Mails OHNE UIDVALIDITY (sollte 0 sein):"
sqlite3 emails.db "SELECT COUNT(*) FROM raw_emails WHERE imap_uidvalidity IS NULL;"

echo
echo "3️⃣ Breakdown nach Ordner:"
sqlite3 emails.db "SELECT imap_folder, COUNT(*) as count FROM raw_emails GROUP BY imap_folder ORDER BY count DESC;"

echo
echo "4️⃣ Beispiel-Mails (erste 5):"
sqlite3 emails.db -header -column "SELECT id, imap_folder, imap_uid, imap_uidvalidity, message_id FROM raw_emails LIMIT 5;"

echo
echo "5️⃣ Check unique constraint (Duplikate sollten 0 sein):"
sqlite3 emails.db "SELECT user_id, mail_account_id, imap_folder, imap_uidvalidity, imap_uid, COUNT(*) as count 
FROM raw_emails 
GROUP BY user_id, mail_account_id, imap_folder, imap_uidvalidity, imap_uid 
HAVING count > 1;"

echo
echo "6️⃣ Neueste Mails (letzte 3):"
sqlite3 emails.db -header -column "SELECT id, imap_folder, imap_uid, received_at, message_id 
FROM raw_emails 
ORDER BY received_at DESC 
LIMIT 3;"

echo
echo "7️⃣ UIDVALIDITY Tracking in mail_accounts:"
sqlite3 emails.db -header "SELECT id, name, folder_uidvalidity FROM mail_accounts WHERE id = 1;"
