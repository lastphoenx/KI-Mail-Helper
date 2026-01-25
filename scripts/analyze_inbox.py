#!/usr/bin/env python3
"""Analysiert INBOX mit Trash Audit Service für Entwicklungszwecke."""

import sys
sys.path.insert(0, '.')

from importlib import import_module
from collections import defaultdict

# Dynamische Imports
tas = import_module("src.services.trash_audit_service")
models = import_module("src.02_models")
database = import_module("src.helpers.database")
fetcher_mod = import_module("src.06_mail_fetcher")

def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else "INBOX"
    
    with database.get_db_session() as db:
        account = db.query(models.MailAccount).first()
        print(f"Account: {account.email}")
        print(f"Folder: {folder}")
        
        fetcher = fetcher_mod.MailFetcher(account)
        fetcher.connect()
        
        try:
            print(f"\nScanning {folder}...")
            result = tas.TrashAuditService.fetch_and_analyze_trash(
                fetcher, limit=500, db_session=db,
                user_id=account.user_id, account_id=account.id, folder=folder
            )
            
            print(f"\nEmails: {len(result.emails)}")
            print(f"Safe: {result.safe_count}, Review: {result.review_count}, Important: {result.important_count}")
            
            # Cluster analysieren
            clusters = defaultdict(list)
            for email in result.emails:
                clusters[email.cluster_key or "unknown"].append(email)
            
            sorted_clusters = sorted(clusters.items(), key=lambda x: len(x[1]), reverse=True)
            
            print(f"\n{'='*70}")
            print(f"=== Top Cluster (2+ Emails) ===")
            print(f"{'='*70}")
            
            for key, emails in sorted_clusters[:20]:
                if len(emails) >= 2:
                    cats = {"safe": 0, "review": 0, "important": 0}
                    reasons_all = set()
                    for e in emails:
                        cats[e.category.value] += 1
                        reasons_all.update(e.reasons)
                    
                    domain = emails[0].sender.split("@")[-1] if "@" in emails[0].sender else "?"
                    subj = emails[0].subject[:45] if emails[0].subject else "(Kein Betreff)"
                    
                    print(f"\n[{len(emails):3}×] {domain}")
                    print(f"  Pattern: {key[:60]}")
                    print(f"  Sample:  {subj}")
                    print(f"  Cats:    Safe={cats['safe']}, Review={cats['review']}, Important={cats['important']}")
                    print(f"  Reasons: {', '.join(list(reasons_all)[:4])}")
            
            # Domain-Statistik
            print(f"\n{'='*70}")
            print(f"=== Domain-Übersicht ===")
            print(f"{'='*70}")
            
            domain_stats = defaultdict(lambda: {"count": 0, "safe": 0, "review": 0, "important": 0, "clusters": set()})
            for email in result.emails:
                domain = email.sender.split("@")[-1] if "@" in email.sender else "unknown"
                domain_stats[domain]["count"] += 1
                domain_stats[domain][email.category.value] += 1
                domain_stats[domain]["clusters"].add(email.cluster_key)
            
            sorted_domains = sorted(domain_stats.items(), key=lambda x: x[1]["count"], reverse=True)[:15]
            
            for domain, stats in sorted_domains:
                print(f"\n{domain}: {stats['count']} emails, {len(stats['clusters'])} cluster")
                print(f"  Safe={stats['safe']}, Review={stats['review']}, Important={stats['important']}")
                
        finally:
            fetcher.disconnect()

if __name__ == "__main__":
    main()
