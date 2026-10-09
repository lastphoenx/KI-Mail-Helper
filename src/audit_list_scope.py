"""Geltungsbereich der Audit-Listen, die ein optionales Konto haben."""


def apply_account_scope(query, account_column, account_id):
    """Ohne Konto nur Zeilen mit leerem account_id. Mit Konto diese plus die leeren."""
    if account_id:
        return query.filter((account_column == account_id) | (account_column == None))
    return query.filter(account_column == None)
