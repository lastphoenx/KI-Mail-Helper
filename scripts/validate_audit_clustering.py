"""
Manuelle Cluster-Statistik (lokal). Nutzt nur synthetische Testdaten — keine Mailbox-Exports im Repo.
"""
import sys
import random
import collections
from datetime import datetime

sys.path.insert(0, ".")
from src.services.folder_audit_service import (
    FolderAuditService as S,
    TrashEmailInfo,
    TrashCategory as C,
)

random.seed(1)


def word():
    return "".join(random.choice("abcdefghklmnoprstuvwz") for _ in range(7))


def mkmail(uid, sender, name, fl, subj):
    reasons = []
    if "M" in fl:
        reasons.append("Newsletter (50%)")
    if "S" in fl:
        reasons.append("🚫 Server-Spam (Score: 6.0)")
    if "W" in fl:
        reasons.append("War als wichtig markiert")
    cat = C.REVIEW if "W" in fl else (C.SCAM if "X" in fl else C.SAFE)
    return TrashEmailInfo(
        uid=uid,
        subject=subj,
        sender=sender,
        sender_name=name,
        date=datetime(2026, 9, 1),
        has_attachments=False,
        flags=[],
        size=1000,
        has_list_unsubscribe="N" in fl,
        server_spam_flag="S" in fl,
        provider_junk_score=10 if "S" in fl else None,
        auth_results="spf=pass dkim=pass" if "A" in fl else None,
        category=cat,
        reasons=reasons,
    )


def synthetic_load(target_mails: int = 800):
    """Generiert U/T-ähnliche Verteilung ohne echte Absender oder Betreffzeilen."""
    out = []
    uid = 0
    senders = [
        ("news@shop-a.example", "Shop A", "NM", 40),
        ("noreply@shop-b.example", "Shop B", "NM", 35),
        ("alerts@service-c.example", "Service C", "N", 28),
        ("promo@retailer-d.example", "Retailer D", "M", 22),
        ("news@newsletter-e.example", "Newsletter E", "NM", 18),
    ]
    for sender, name, fl, weight in senders:
        n_unique = max(3, weight // 4)
        for _ in range(n_unique):
            if uid >= target_mails:
                return out
            uid += 1
            out.append(mkmail(uid, sender, name, fl, f"{word()} {word()} {word()} jetzt"))
    recurring = [
        ("noreply@shop-b.example", "Shop B", "M", "Deine Lieferung vom 01.01.2026", 12),
        ("alerts@service-c.example", "Service C", "NM", "Wöchentlicher Überblick", 8),
    ]
    for sender, name, fl, subj, count in recurring:
        for _ in range(count):
            if uid >= target_mails:
                return out
            uid += 1
            out.append(mkmail(uid, sender, name, fl, subj))
    while uid < target_mails:
        s, n, fl = random.choice(senders)[:3]
        uid += 1
        out.append(mkmail(uid, s, n, fl, f"{word()} angebot"))
    return out


if __name__ == "__main__":
    for mode in ("maintenance", "cleanup"):
        em = synthetic_load()
        cl = S.build_clusters(em, mode=mode)
        byk = {c.cluster_key: c for c in cl}
        multi = [c for c in cl if c.count >= 2]
        inm = sum(c.count for c in multi)
        print(
            f"\n=== {mode}: {len(em)} Mails | {len(cl)} Karten insgesamt | "
            f"{len(multi)} Cluster | {inm} Mails in Clustern ({100 * inm // len(em)}%) | "
            f"{len(cl) - len(multi)} Einzelkarten"
        )
        sizes = collections.Counter(
            "2-4" if c.count < 5 else "5-19" if c.count < 20 else "20+" for c in multi
        )
        print("  Clustergrössen:", dict(sizes))
        for c in sorted(multi, key=lambda c: -c.count)[
            : int(sys.argv[1]) if len(sys.argv) > 1 else 15
        ]:
            print(f"  {c.count:4d} [{c.category.value:6s}] {c.cluster_key[:58]}")
        bad = [
            e
            for e in em
            if "wichtig" in " ".join(e.reasons).lower()
            and byk[e.cluster_key].count >= 2
            and "*" in e.cluster_key
        ]
        print("  ⚠️ wichtig-Mails in Sammelclustern:", len(bad))
        mixed = [c for c in multi if c.safe_count and c.review_count]
        print(
            "  ⚠️ Cluster mit SAFE+REVIEW gemischt:",
            len(mixed),
            [m.cluster_key[:40] for m in mixed][:5],
        )
        kamp = [c for c in multi if "kampagne" in c.cluster_key]
        print(f"  Kampagnen-Cluster: {len(kamp)} mit {sum(c.count for c in kamp)} Mails")
        flagged = [e for e in em if e.server_spam_flag and (byk[e.cluster_key].count == 1)]
        print(
            "  Spam-geflaggte Einzelmails:",
            len(flagged),
            sorted({e.sender_name for e in flagged})[:12],
        )
