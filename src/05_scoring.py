"""
Mail Helper - Scoring & 3x3-Matrix-Mapping
Berechnet Score, Matrix-Position und Ampelfarbe
"""

from typing import Tuple, Dict


def calculate_score(dringlichkeit: int, wichtigkeit: int) -> int:
    """
    Berechnet den Prioritäts-Score

    Args:
        dringlichkeit: 1-3 (niedrig bis hoch)
        wichtigkeit: 1-3 (niedrig bis hoch)

    Returns:
        Score 3-9
    """
    # Formel: Dringlichkeit zählt doppelt
    score = dringlichkeit * 2 + wichtigkeit
    return min(max(score, 3), 9)  # Clamp auf 3-9


def get_matrix_position(dringlichkeit: int, wichtigkeit: int) -> Tuple[int, int]:
    """
    Bestimmt Position in 3x3-Matrix

    Args:
        dringlichkeit: 1-3
        wichtigkeit: 1-3

    Returns:
        (x, y) wobei:
            x = Wichtigkeit (1=links, 3=rechts)
            y = Dringlichkeit (1=unten, 3=oben)
    """
    x = max(1, min(wichtigkeit, 3))
    y = max(1, min(dringlichkeit, 3))
    return (x, y)


def get_color(score: int) -> str:
    """
    Bestimmt Ampelfarbe basierend auf Score

    Args:
        score: 3-9

    Returns:
        "rot", "gelb" oder "grün"
    """
    if score >= 8:
        return "rot"
    elif score >= 5:
        return "gelb"
    else:
        return "grün"


def get_color_hex(color: str) -> str:
    """
    Liefert Hex-Code für Ampelfarbe

    Args:
        color: "rot", "gelb" oder "grün"

    Returns:
        Hex-Farbcode
    """
    colors = {
        "rot": "#dc3545",  # Bootstrap danger
        "gelb": "#ffc107",  # Bootstrap warning
        "grün": "#28a745",  # Bootstrap success
    }
    return colors.get(color, "#6c757d")  # Default: grau


def analyze_priority(dringlichkeit: int, wichtigkeit: int) -> Dict:
    """
    Vollständige Prioritäts-Analyse

    Args:
        dringlichkeit: 1-3
        wichtigkeit: 1-3

    Returns:
        Dict mit score, matrix_x, matrix_y, farbe, farbe_hex
    """
    score = calculate_score(dringlichkeit, wichtigkeit)
    matrix_x, matrix_y = get_matrix_position(dringlichkeit, wichtigkeit)
    farbe = get_color(score)

    return {
        "score": score,
        "matrix_x": matrix_x,
        "matrix_y": matrix_y,
        "farbe": farbe,
        "farbe_hex": get_color_hex(farbe),
        "quadrant": f"{matrix_x}{matrix_y}",  # z.B. "23" für Wichtig:2, Dringend:3
    }


def get_priority_label(score: int) -> str:
    """
    Liefert lesbares Label für Priorität

    Args:
        score: 3-9

    Returns:
        "Sehr hoch", "Hoch", "Mittel", "Niedrig"
    """
    if score >= 8:
        return "Sehr hoch"
    elif score >= 6:
        return "Hoch"
    elif score >= 5:
        return "Mittel"
    else:
        return "Niedrig"


if __name__ == "__main__":
    # Test aller Kombinationen (3x3 = 9 Felder)
    print("=== 3x3 Prioritäts-Matrix ===\n")
    print("Format: (Wichtigkeit, Dringlichkeit) → Score | Farbe | Quadrant\n")

    for dringlichkeit in range(3, 0, -1):  # 3 -> 1 (oben nach unten)
        for wichtigkeit in range(1, 4):  # 1 -> 3 (links nach rechts)
            result = analyze_priority(dringlichkeit, wichtigkeit)
            print(
                f"({wichtigkeit}, {dringlichkeit}) → Score: {result['score']:2d} | "
                f"{result['farbe']:4s} | Q: {result['quadrant']}",
                end="  ",
            )
        print()  # Neue Zeile nach jeder Reihe

    print("\n=== Beispiel-Analysen ===")
    examples = [
        (3, 3, "Sehr wichtig + sehr dringend"),
        (1, 1, "Unwichtig + nicht dringend"),
        (3, 1, "Sehr wichtig, aber nicht dringend"),
        (1, 3, "Unwichtig, aber sehr dringend"),
        (2, 2, "Mittlere Priorität"),
    ]

    for wichtigkeit, dringlichkeit, beschreibung in examples:
        result = analyze_priority(dringlichkeit, wichtigkeit)
        print(f"\n{beschreibung}:")
        print(f"  Score: {result['score']} ({get_priority_label(result['score'])})")
        print(f"  Farbe: {result['farbe']} ({result['farbe_hex']})")
        print(f"  Position: ({result['matrix_x']}, {result['matrix_y']})")
