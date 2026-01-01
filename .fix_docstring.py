with open('src/06_mail_fetcher.py', 'r') as f:
    lines = f.readlines()

# Finde Zeile 581 (index 580)
for i, line in enumerate(lines):
    if 'def _fetch_email_by_id(self, mail_id: int' in line:
        # Zeile ist durcheinander - teile sie auf
        # Ersetze die ganze Zeile + die nächsten 6 Zeilen (Docstring)
        lines[i] = '    def _fetch_email_by_id(self, mail_id: int, folder: str = "INBOX") -> Optional[Dict]:\n'
        lines[i+1] = '        """Holt eine einzelne E-Mail mit erweiterten Metadaten (Phase 12)\n'
        lines[i+2] = '        \n'
        lines[i+3] = '        Phase 14c: Nutzt IMAPClient für robustes Response-Handling\n'
        lines[i+4] = '        - mail_id: Integer (IMAPClient gibt UIDs als int zurück)\n'
        lines[i+5] = '        - Response: Dict statt (status, data) Tuple\n'
        lines[i+6] = '        """\n'
        break

with open('src/06_mail_fetcher.py', 'w') as f:
    f.writelines(lines)

print("✅ Docstring fixiert!")
