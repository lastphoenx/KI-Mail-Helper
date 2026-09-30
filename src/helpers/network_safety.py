# src/helpers/network_safety.py
"""SSRF-Schutz fuer nutzerkonfigurierte Mail-Server (IMAP/SMTP).

Jeder eingeloggte User kann in "Mail-Account hinzufuegen" einen beliebigen
IMAP/SMTP-Host+Port eintragen. Ohne Pruefung kann dieser Host auf interne
Adressen zeigen (127.0.0.1, RFC1918, Link-Local/Cloud-Metadata 169.254.x.x),
sodass die Diagnose-/Fetch-/Sende-Funktionen den Server zu einem
SSRF-Werkzeug fuer internes Port-Scanning/Banner-Grabbing machen.

assert_safe_mail_host() wird direkt vor jedem echten Verbindungsaufbau
aufgerufen (nicht nur beim Speichern des Accounts), damit ein Hostname,
dessen DNS-Eintrag sich nachtraeglich auf eine interne Adresse aendert
(DNS-Rebinding), ebenfalls abgefangen wird.
"""

from __future__ import annotations

import ipaddress
import os
import socket


class UnsafeMailHostError(ValueError):
    """Der konfigurierte Mail-Host loest auf eine gesperrte Netzadresse auf."""


def _private_hosts_allowed() -> bool:
    return os.environ.get("ALLOW_PRIVATE_MAIL_HOSTS", "false").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def assert_safe_mail_host(host: str) -> None:
    """Bricht mit UnsafeMailHostError ab, wenn `host` intern/privat aufloest.

    Deaktivierbar ueber ALLOW_PRIVATE_MAIL_HOSTS=true fuer bewusstes
    Self-Hosting im eigenen (vertrauenswuerdigen) Netz.
    """
    if _private_hosts_allowed():
        return

    if not host:
        raise UnsafeMailHostError("Leerer Hostname")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeMailHostError(f"Hostname konnte nicht aufgeloest werden: {host}") from exc

    if not infos:
        raise UnsafeMailHostError(f"Hostname konnte nicht aufgeloest werden: {host}")

    for info in infos:
        raw_ip = info[4][0].split("%", 1)[0]  # IPv6 Zone-ID abschneiden
        try:
            ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue

        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeMailHostError(
                f"Mail-Server-Host '{host}' loest auf eine interne/private Adresse "
                f"({ip}) auf - aus Sicherheitsgruenden blockiert (SSRF-Schutz). "
                "Fuer Self-Hosting im eigenen Netz kann ALLOW_PRIVATE_MAIL_HOSTS=true "
                "gesetzt werden."
            )
