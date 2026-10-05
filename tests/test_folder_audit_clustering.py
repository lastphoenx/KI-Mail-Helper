from datetime import datetime
from src.services.folder_audit_service import (
    FolderAuditService as S, TrashEmailInfo, TrashCategory,
    DEFAULT_BULK_MERGE_BLOCK_DOMAINS,
)


def mk(uid, subj, sender="news@shop.ch", cat=TrashCategory.SAFE, **kw):
    kw.setdefault("has_list_unsubscribe", True)
    ha = kw.pop("has_attachments", False)
    kw.setdefault("attachment_state", "yes" if ha else "no")
    return TrashEmailInfo(uid=uid, subject=subj, sender=sender, sender_name="x",
                          date=datetime(2026, 1, 1), has_attachments=ha,
                          flags=[], size=100, category=cat, **kw)


def test_normalization_streak_and_decimals():
    n = S.normalize_subject_for_clustering
    assert n("Du hast einen 5-tägigen Streak") == n("Du hast einen 3-tägigen Streak")
    assert n("Im Jackpot: 26.7 Millionen") == n("Im Jackpot: 9.6 Millionen")
    assert n("⏰ Nur heute") == n("Nur heute")


def test_normalization_reply_and_currency():
    n = S.normalize_subject_for_clustering
    assert n("Re: AW: Angebot") == n("Angebot")
    assert n("Gelesen: Newsletter") == n("Newsletter")
    assert n("CHF4.72 für Sie") == n("CHF9.99 für Sie")


def test_noreply_sender_normalization():
    k1 = S.create_cluster_key("noreply0@shop.example", "News")
    k2 = S.create_cluster_key("noreply7@shop.example", "News")
    assert k1 == k2


def test_sender_cluster_groups_safe_leftovers():
    emails = [mk(i, f"Unique {chr(97+i)}xyz angebot") for i in range(4)]
    cl = S.build_clusters(emails)
    assert len(cl) == 1 and cl[0].count == 4


def test_sender_cluster_needs_three():
    cl = S.build_clusters([mk(1, "aaa"), mk(2, "bbb")])
    assert all(c.count == 1 for c in cl)


def test_sender_cluster_never_mixes_non_safe_or_important():
    emails = [mk(1, "aaa"), mk(2, "bbb"), mk(3, "ccc", cat=TrashCategory.REVIEW),
              mk(4, "ddd", has_attachments=True), mk(5, "eee", reasons=["Wichtiger Betreff"])]
    cl = S.build_clusters(emails)
    assert all(c.count == 1 for c in cl)


def test_freemail_and_non_bulk_excluded():
    freemail_dom = sorted(DEFAULT_BULK_MERGE_BLOCK_DOMAINS)[0]
    sender = f"promo@{freemail_dom}"
    bulk = [mk(i, f"news {i}", sender=sender, has_list_unsubscribe=True) for i in range(4)]
    assert all(c.count == 1 for c in S.build_clusters(bulk, mode="cleanup"))
    non_bulk = [mk(10 + i, f"t{i}x", sender=sender, has_list_unsubscribe=False) for i in range(4)]
    assert all(c.count == 1 for c in S.build_clusters(non_bulk, mode="cleanup"))


def _spam(uid, domain, subj="Nur noch heute: Ihre exklusive Prämie wartet", name="ADAC"):
    e = mk(uid, subj, sender=f"x@{domain}", has_list_unsubscribe=False)
    e.sender_name, e.server_spam_flag, e.provider_junk_score = name, True, 10
    return e


def test_campaign_cluster_needs_multiple_domains():
    same = [_spam(i, "evil.com") for i in range(4)]
    assert all(c.count == 1 or "kampagne" not in c.cluster_key for c in S.build_clusters(same))
    multi = [_spam(i, f"d{i}.com") for i in range(3)]
    cl = [c for c in S.build_clusters(multi) if "kampagne" in c.cluster_key]
    assert len(cl) == 1 and cl[0].count == 3


def test_campaign_excludes_replies_attachments():
    em = [_spam(i, f"d{i}.com") for i in range(3)]
    em[0].is_reply = True
    em[1].has_attachments = True
    em[1].attachment_state = "yes"
    assert not [c for c in S.build_clusters(em) if "kampagne" in c.cluster_key]


def test_domain_stage_needs_whitelist_auth_and_not_transactional():
    def apple(uid, subj, auth="spf=pass"):
        return mk(uid, subj, sender=f"a{uid}@apple.com", auth_results=auth)
    ok = [apple(1, "Neuheiten"), apple(2, "Angebote"), apple(3, "Tipps")]
    assert any("*domain" in c.cluster_key for c in S.build_clusters(ok, mode="cleanup"))
    assert not any("*domain" in c.cluster_key for c in S.build_clusters(ok, mode="maintenance"))
    forged = [apple(i, f"s{i}", auth="spf=fail") for i in range(3)]
    assert not any("*domain" in c.cluster_key for c in S.build_clusters(forged))
    inv = [apple(1, "Neuheiten"), apple(2, "Angebote"), apple(3, "Ihre Rechnung")]
    cl = S.build_clusters(inv)
    assert not any(c.count == 3 and "*domain" in c.cluster_key for c in cl)


def test_rebuild_clusters_multi_folder_same_uid():
    """IMAP-UIDs sind pro Ordner — gleiche UID in zwei Ordnern darf einen Cluster nicht zerstören."""
    from src.services.folder_audit_service import TrashCategory as C

    def em(uid, folder, subj="Newsletter Angebot"):
        return mk(uid, subj, sender="news@shop.example", cat=C.SAFE, folder=folder)

    emails = [em(42, "INBOX"), em(42, "Archiv")]
    for e in emails:
        e.cluster_key = S.create_cluster_key(e.sender, e.subject)
    cmap = {}
    rebuilt = S._rebuild_clusters_from_emails(emails, cmap)
    assert len(rebuilt) == 1 and rebuilt[0].count == 2
    assert len(rebuilt[0].members) == 2


def test_merged_clusters_never_mix_categories():
    em = [mk(1, "a1x"), mk(2, "b2x"), mk(3, "c3x"),
          mk(4, "d4x", cat=TrashCategory.REVIEW), mk(5, "e5x", cat=TrashCategory.REVIEW),
          mk(6, "f6x", cat=TrashCategory.REVIEW)]
    for c in S.build_clusters(em):
        assert not (c.safe_count and c.review_count)


def test_db_safe_pattern_reason_enables_sender_merge():
    em = [mk(i, f"shop sale {i}", has_list_unsubscribe=False) for i in range(4)]
    for e in em:
        e.reasons = ["Safe-Pattern (DB)"]
    cl = S.build_clusters(em, mode="cleanup")
    assert any(c.count >= 3 and "*alle-betreffs*" in c.cluster_key for c in cl)


def test_same_sender_volume_merge_cleanup_only():
    sender = "promo@retailer-d.example"
    em = [mk(i, f"Unique offer {i}", sender=sender, has_list_unsubscribe=False) for i in range(5)]
    cl = S.build_clusters(em, mode="cleanup")
    assert any(c.count == 5 and "*alle-betreffs*" in c.cluster_key for c in cl)
    cl_m = S.build_clusters(em, mode="maintenance")
    assert not any("*alle-betreffs*" in c.cluster_key for c in cl_m)


def test_volume_merge_excludes_invoice_attachment_reply():
    sender = "bulk@retailer-d.example"
    em = [
        mk(i, f"Promo {i}", sender=sender, has_list_unsubscribe=False)
        for i in range(5)
    ]
    em.append(mk(10, "Ihre Rechnung Januar", sender=sender, has_list_unsubscribe=False))
    em.append(mk(11, "Promo extra", sender=sender, has_list_unsubscribe=False, has_attachments=True))
    em.append(mk(12, "Promo reply", sender=sender, has_list_unsubscribe=False, is_reply=True))
    em.append(mk(13, "Promo wichtig", sender=sender, has_list_unsubscribe=False, reasons=["Wichtiger Betreff"]))
    cl = S.build_clusters(em, mode="cleanup")
    vol = [c for c in cl if "*alle-betreffs*" in c.cluster_key]
    assert len(vol) == 1 and vol[0].count == 5


def test_domain_stage_allows_vertrauenswuerdig_reason():
    def apple(uid, subj, auth="spf=pass"):
        e = mk(uid, subj, sender=f"a{uid}@apple.com", auth_results=auth)
        e.reasons = ["Vertrauenswürdiger Absender", "Newsletter (List-Unsubscribe)"]
        return e
    ok = [apple(i, f"Tipps {i}") for i in range(3)]
    assert any("*domain" in c.cluster_key for c in S.build_clusters(ok, mode="cleanup"))
    blocked = [apple(i, f"s{i}", auth="spf=fail") for i in range(3)]
    assert not any("*domain" in c.cluster_key for c in S.build_clusters(blocked))
