"""
Known Newsletter Senders und Patterns
Erkennt typische Newsletter basierend auf Sender, Domain und Subject-Patterns
"""

NEWSLETTER_DOMAINS = {
    "gmx.de",
    "gmx.com",
    "gmx.at",
    "newsletter@",
    "promo@",
    "marketing@",
    "noreply@",
    "no-reply@",
    "updates@",
    "notifications@",
    "news@",
    "info@",
    "hello@",
    "support@",
    "service@",
    "mailchimp.com",
    "sendgrid.com",
    "brevo.com",
    "klaviyo.com",
    "substack.com",
    "substack.co",
    "mirror.xyz",
    "medium.com",
    "dev.to",
    "hashnode.com",
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "slack.com",
    "discord.com",
    "telegram.org",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "youtube.com",
    "twitch.tv",
    "reddit.com",
    "amazon.de",
    "amazon.com",
    "ebay.de",
    "aliexpress.com",
    "spotify.com",
    "netflix.com",
    "apple.com",
    "uber.com",
    "lyft.com",
    "airbnb.com",
    "stripe.com",
    "paypal.com",
    "square.com",
    "aws.amazon.com",
    "google.com",
    "microsoft.com",
    "shopify.com",
    "woocommerce.com",
    "magento.com",
    "eventbrite.com",
    "meetup.com",
    "lanyrd.com",
}

NEWSLETTER_SENDER_PATTERNS = {
    "newsletter",
    "promo",
    "marketing",
    "updates",
    "news",
    "digest",
    "alerts",
    "notifications",
    "broadcast",
    "no-reply",
    "noreply",
    "donotreply",
    "do-not-reply",
    "hello",
    "support",
    "service",
    "info",
    "contact",
    "team",
    "crew",
    "group",
}

NEWSLETTER_SUBJECT_PATTERNS = {
    "newsletter",
    "digest",
    "roundup",
    "weekly",
    "monthly",
    "daily",
    "update",
    "news",
    "alert",
    "notification",
    "reminder",
    "podcast",
    "blog",
    "article",
    "post",
    "story",
    "trending",
    "trend",
    "popular",
    "top",
    "best",
    "highlight",
    "curated",
    "handpicked",
    "must-read",
    "must-see",
    "this week",
    "this month",
    "last week",
    "breaking",
    "offer",
    "deal",
    "promo",
    "discount",
    "sale",
    "limited time",
    "exclusive",
    "special",
    "flash sale",
    "unsubscribe",
    "manage preferences",
    "abmelden",
    "manage subscription",
}


def is_known_newsletter_sender(sender: str) -> bool:
    """
    Prüft ob Sender eine bekannte Newsletter-Domain/Pattern ist.

    Args:
        sender: Email-Adresse des Senders (z.B. "newsletter@gmx.de")

    Returns:
        True wenn Newsletter erkannt
    """
    if not sender:
        return False

    sender_lower = sender.lower()

    for domain in NEWSLETTER_DOMAINS:
        if domain in sender_lower:
            return True

    local_part = sender_lower.split("@")[0] if "@" in sender_lower else sender_lower
    for pattern in NEWSLETTER_SENDER_PATTERNS:
        if pattern in local_part:
            return True

    return False


def is_newsletter_subject(subject: str) -> bool:
    """
    Prüft ob Subject typische Newsletter-Patterns enthält.

    Args:
        subject: Email-Betreff

    Returns:
        True wenn Newsletter erkannt
    """
    if not subject:
        return False

    subject_lower = subject.lower()
    pattern_count = sum(
        1 for pattern in NEWSLETTER_SUBJECT_PATTERNS if pattern in subject_lower
    )

    return pattern_count >= 1


def classify_newsletter_confidence(sender: str, subject: str, body: str = "") -> float:
    """
    Berechnet Konfidenz dass eine Email ein Newsletter ist (0.0 - 1.0).

    Args:
        sender: Email-Adresse
        subject: Betreff
        body: Email-Text

    Returns:
        Konfidenz (0.0 = kein Newsletter, 1.0 = definitiv Newsletter)
    """
    confidence = 0.0

    if is_known_newsletter_sender(sender):
        confidence += 0.5

    if is_newsletter_subject(subject):
        confidence += 0.3

    if body:
        body_lower = body.lower()
        if "unsubscribe" in body_lower or "abmelden" in body_lower:
            confidence += 0.2

    return min(1.0, confidence)


if __name__ == "__main__":
    test_cases = [
        ("newsletter@gmx.de", "Newsletter KW45", ""),
        ("support@spotify.com", "Account Security Alert", ""),
        ("hello@substack.com", "Weekly Digest #52", ""),
        ("info@example.com", "Important: Action Required", ""),
        ("noreply@mailchimp.com", "Campaign Report", ""),
    ]

    for sender, subject, body in test_cases:
        conf = classify_newsletter_confidence(sender, subject, body)
        print(f"{sender:30} | {subject:35} → {conf:.1%}")
