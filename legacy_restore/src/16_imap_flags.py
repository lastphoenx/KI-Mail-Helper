"""
IMAP Flags Utilities
Hilft bei der Analyse und Verwaltung von IMAP-Flags
"""

from typing import List, Optional
import json


class IMAPFlagParser:
    """Parser für IMAP-Flags

    IMAP Standard Flags:
    - \\Seen: E-Mail wurde gelesen
    - \\Answered: E-Mail wurde beantwortet
    - \\Flagged: E-Mail ist markiert/wichtig
    - \\Deleted: E-Mail ist zum Löschen markiert
    - \\Draft: E-Mail ist ein Entwurf
    - \\Recent: E-Mail ist neu auf dem Server
    """

    STANDARD_FLAGS = {
        "\\Seen": "seen",
        "\\Answered": "answered",
        "\\Flagged": "flagged",
        "\\Deleted": "deleted",
        "\\Draft": "draft",
        "\\Recent": "recent",
    }

    @staticmethod
    def parse_flags_string(flags_str: str) -> List[str]:
        """
        Parst Flag-String in Liste

        Input: '\\Seen \\Answered'
        Output: ['\\Seen', '\\Answered']
        """
        if not flags_str or not flags_str.strip():
            return []
        return [f.strip() for f in flags_str.split() if f.strip()]

    @staticmethod
    def is_seen(flags_str: str) -> bool:
        """Überprüft ob E-Mail gelesen ist"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return "\\Seen" in flags

    @staticmethod
    def is_answered(flags_str: str) -> bool:
        """Überprüft ob E-Mail beantwortet wurde"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return "\\Answered" in flags

    @staticmethod
    def is_flagged(flags_str: str) -> bool:
        """Überprüft ob E-Mail markiert ist"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return "\\Flagged" in flags

    @staticmethod
    def is_deleted(flags_str: str) -> bool:
        """Überprüft ob E-Mail zum Löschen markiert ist"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return "\\Deleted" in flags

    @staticmethod
    def is_draft(flags_str: str) -> bool:
        """Überprüft ob E-Mail ein Entwurf ist"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return "\\Draft" in flags

    @staticmethod
    def is_recent(flags_str: str) -> bool:
        """Überprüft ob E-Mail neu auf dem Server ist"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return "\\Recent" in flags

    @staticmethod
    def flags_changed(
        old_flags_str: Optional[str], new_flags_str: Optional[str]
    ) -> bool:
        """
        Überprüft ob sich Flags geändert haben

        Args:
            old_flags_str: Alte Flags (z.B. beim Processing)
            new_flags_str: Neue Flags (aktuelle vom Server)

        Returns:
            True wenn Flags unterschiedlich sind
        """
        old_flags = set(IMAPFlagParser.parse_flags_string(old_flags_str or ""))
        new_flags = set(IMAPFlagParser.parse_flags_string(new_flags_str or ""))
        return old_flags != new_flags

    @staticmethod
    def get_flag_changes(
        old_flags_str: Optional[str], new_flags_str: Optional[str]
    ) -> dict:
        """
        Zeigt welche Flags sich geändert haben

        Returns:
            {
                'added': ['\\Seen'],
                'removed': ['\\Recent'],
                'unchanged': ['\\Answered']
            }
        """
        old_flags = set(IMAPFlagParser.parse_flags_string(old_flags_str or ""))
        new_flags = set(IMAPFlagParser.parse_flags_string(new_flags_str or ""))

        return {
            "added": list(new_flags - old_flags),
            "removed": list(old_flags - new_flags),
            "unchanged": list(old_flags & new_flags),
        }

    @staticmethod
    def to_json(flags_str: str) -> str:
        """Konvertiert Flag-String zu JSON-Array"""
        flags = IMAPFlagParser.parse_flags_string(flags_str)
        return json.dumps(flags)

    @staticmethod
    def from_json(flags_json: str) -> str:
        """Konvertiert JSON-Array zu Flag-String"""
        try:
            flags = json.loads(flags_json)
            return " ".join(flags)
        except (json.JSONDecodeError, TypeError):
            return ""
