from datetime import datetime
from src.services.folder_audit_service import (
    FolderAuditService as S, TrashEmailInfo, TrashCategory,
)


def mk(uid, subj, sender="news@shop.ch", cat=TrashCategory.SAFE, **kw):
    kw.setdefault("has_list_unsubscribe", True)
    return TrashEmailInfo(uid=uid, subject=subj, sender=sender, sender_name="x",
                          date=datetime(2026, 1, 1), has_attachments=kw.pop("has_attachments", False),
                          flags=[], size=100, category=cat, **kw)


def test_normalization_streak_and_decimals():
    n = S.normalize_subject_for_clustering
    assert n("Du hast einen 5-tägigen Streak") == n("Du hast einen 3-tägigen Streak")
    assert n("Im Jackpot: 26.7 Millionen") == n("Im Jackpot: 9.6 Millionen")
    assert n("⏰ Nur heute") == n("Nur heute")


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
    em = [mk(i, f"s{i}x", sender="news@shop.example") for i in range(4)]
    em += [mk(10 + i, f"t{i}x", has_list_unsubscribe=False) for i in range(4)]
    assert all(c.count == 1 for c in S.build_clusters(em))


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


def test_merged_clusters_never_mix_categories():
    em = [mk(1, "a1x"), mk(2, "b2x"), mk(3, "c3x"),
          mk(4, "d4x", cat=TrashCategory.REVIEW), mk(5, "e5x", cat=TrashCategory.REVIEW),
          mk(6, "f6x", cat=TrashCategory.REVIEW)]
    for c in S.build_clusters(em):
        assert not (c.safe_count and c.review_count)
