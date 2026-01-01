#!/usr/bin/env python3
"""
Git Commit Extractor für App-Dokumentation
Extrahiert alle Commits aus einem Git Repository und erstellt eine Markdown-Datei.

Verwendung:
    python extract_commits.py [--repo-path /pfad/zum/repo] [--output commits.md]
"""

import subprocess
import argparse
from datetime import datetime
from pathlib import Path


def get_commits(repo_path: str = ".") -> list[dict]:
    """Extrahiert alle Commits aus dem Repository."""
    
    # Git log Format: Hash | Autor | Datum | Subject | Body
    # %H  = Full commit hash
    # %h  = Short commit hash
    # %an = Author name
    # %ae = Author email
    # %ai = Author date (ISO format)
    # %s  = Subject (erste Zeile)
    # %b  = Body (Rest der Nachricht)
    
    separator = "<<<COMMIT_SEP>>>"
    field_sep = "<<<FIELD_SEP>>>"
    
    format_string = f"%h{field_sep}%H{field_sep}%an{field_sep}%ai{field_sep}%s{field_sep}%b{separator}"
    
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", f"--format={format_string}", "--reverse"],
            capture_output=True,
            text=True,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Fehler beim Ausführen von git log: {e}")
        print(f"stderr: {e.stderr}")
        return []
    except FileNotFoundError:
        print("Git ist nicht installiert oder nicht im PATH.")
        return []
    
    commits = []
    raw_commits = result.stdout.split(separator)
    
    for raw in raw_commits:
        raw = raw.strip()
        if not raw:
            continue
            
        parts = raw.split(field_sep)
        if len(parts) >= 5:
            commit = {
                "short_hash": parts[0].strip(),
                "full_hash": parts[1].strip(),
                "author": parts[2].strip(),
                "date": parts[3].strip(),
                "subject": parts[4].strip(),
                "body": parts[5].strip() if len(parts) > 5 else ""
            }
            commits.append(commit)
    
    return commits


def format_date(iso_date: str) -> str:
    """Formatiert ISO-Datum zu lesbarem Format."""
    try:
        dt = datetime.fromisoformat(iso_date.replace(" ", "T").split("+")[0])
        return dt.strftime("%d.%m.%Y %H:%M")
    except:
        return iso_date


def generate_markdown(commits: list[dict], repo_name: str = "Repository") -> str:
    """Generiert Markdown-Dokument aus Commits."""
    
    lines = [
        f"# {repo_name} - Commit Historie",
        "",
        f"*Generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}*",
        "",
        f"**Anzahl Commits:** {len(commits)}",
        "",
        "---",
        ""
    ]
    
    # Commits gruppieren nach Monat/Jahr (optional)
    current_month = None
    
    for i, commit in enumerate(commits, 1):
        # Datum parsen für Gruppierung
        try:
            dt = datetime.fromisoformat(commit["date"].replace(" ", "T").split("+")[0])
            month_key = dt.strftime("%B %Y")
        except:
            month_key = "Unbekannt"
        
        # Neue Monatsüberschrift wenn nötig
        if month_key != current_month:
            current_month = month_key
            lines.extend([
                f"## {month_key}",
                ""
            ])
        
        # Commit-Eintrag
        lines.append(f"### {i}. {commit['subject']}")
        lines.append("")
        lines.append(f"- **Commit:** `{commit['short_hash']}`")
        lines.append(f"- **Datum:** {format_date(commit['date'])}")
        lines.append(f"- **Autor:** {commit['author']}")
        
        if commit["body"]:
            lines.append("")
            lines.append("**Beschreibung:**")
            lines.append("")
            # Body einrücken und formatieren
            for body_line in commit["body"].split("\n"):
                if body_line.strip():
                    lines.append(f"> {body_line}")
        
        lines.extend(["", "---", ""])
    
    return "\n".join(lines)


def generate_simple_markdown(commits: list[dict], repo_name: str = "Repository") -> str:
    """Generiert ein einfacheres Markdown-Format (kompakter)."""
    
    lines = [
        f"# {repo_name} - Entwicklungshistorie",
        "",
        f"*{len(commits)} Commits | Generiert am {datetime.now().strftime('%d.%m.%Y')}*",
        "",
        "---",
        ""
    ]
    
    for i, commit in enumerate(commits, 1):
        date_str = format_date(commit["date"])
        lines.append(f"**{i}. [{commit['short_hash']}]** {commit['subject']} *({date_str})*")
        
        if commit["body"]:
            lines.append("")
            for body_line in commit["body"].split("\n"):
                if body_line.strip():
                    lines.append(f"   {body_line}")
        
        lines.append("")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Extrahiert Git-Commits für Dokumentation"
    )
    parser.add_argument(
        "--repo-path", "-r",
        default=".",
        help="Pfad zum Git Repository (Standard: aktuelles Verzeichnis)"
    )
    parser.add_argument(
        "--output", "-o",
        default="commits.md",
        help="Ausgabedatei (Standard: commits.md)"
    )
    parser.add_argument(
        "--name", "-n",
        default="KI-Mail-Helper",
        help="Name des Projekts für die Überschrift"
    )
    parser.add_argument(
        "--simple", "-s",
        action="store_true",
        help="Einfacheres, kompakteres Format verwenden"
    )
    
    args = parser.parse_args()
    
    print(f"Extrahiere Commits aus: {args.repo_path}")
    commits = get_commits(args.repo_path)
    
    if not commits:
        print("Keine Commits gefunden oder kein Git-Repository.")
        return 1
    
    print(f"Gefunden: {len(commits)} Commits")
    
    if args.simple:
        markdown = generate_simple_markdown(commits, args.name)
    else:
        markdown = generate_markdown(commits, args.name)
    
    output_path = Path(args.output)
    output_path.write_text(markdown, encoding="utf-8")
    
    print(f"Dokumentation erstellt: {output_path.absolute()}")
    return 0


if __name__ == "__main__":
    exit(main())
