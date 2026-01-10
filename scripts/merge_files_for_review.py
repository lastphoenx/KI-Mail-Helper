#!/usr/bin/env python3
"""
File Merger für AI Code Review
================================
Merged Dateien aus Ordnern oder nach Pattern (*.md) in separate Dateien pro Dateityp.
Jede Datei bekommt einen klaren Header-Rahmen für bessere Lesbarkeit.

Usage:
    python scripts/merge_files_for_review.py src templates scripts
    python scripts/merge_files_for_review.py "*.md"
    python scripts/merge_files_for_review.py src "*.yaml" templates
    
Output:
    review_merged_python.txt
    review_merged_html.txt
    review_merged_markdown.txt
    etc.
"""

import os
import sys
import glob
from pathlib import Path
from collections import defaultdict
from datetime import datetime


# Mapping: File-Extension → Lesbare Bezeichnung + Kommentar-Syntax
EXTENSION_MAP = {
    '.py': ('Python', '#'),
    '.html': ('HTML', '<!--', '-->'),
    '.jinja2': ('Jinja2 Template', '{#', '#}'),
    '.md': ('Markdown', '<!--', '-->'),
    '.yaml': ('YAML', '#'),
    '.yml': ('YAML', '#'),
    '.json': ('JSON', '//'),
    '.sh': ('Shell Script', '#'),
    '.js': ('JavaScript', '//'),
    '.css': ('CSS', '/*', '*/'),
    '.txt': ('Text', '#'),
    '.sql': ('SQL', '--'),
}


def get_comment_style(ext):
    """Gibt Kommentar-Syntax für Extension zurück"""
    if ext not in EXTENSION_MAP:
        return ('#', None, None)  # Default: Hash-Kommentar
    
    data = EXTENSION_MAP[ext]
    if len(data) == 2:
        return (data[1], None, None)  # Single-line comment
    else:
        return (data[1], data[2], None)  # Multi-line comment (start, end)


def create_header(filepath, filetype, comment_start, comment_end=None):
    """Erstellt visuellen Header-Rahmen für eine Datei"""
    rel_path = os.path.relpath(filepath)
    abs_path = os.path.abspath(filepath)
    
    # Rahmen-Breite
    width = 100
    
    if comment_end:  # Multi-line comments (HTML, CSS, etc.)
        header = f"{comment_start}\n"
        header += "=" * width + "\n"
        header += f" FILE: {rel_path}\n"
        header += f" PATH: {abs_path}\n"
        header += f" TYPE: {filetype}\n"
        header += "=" * width + "\n"
        header += f"{comment_end}\n\n"
        
        footer = f"\n{comment_start}\n"
        footer += "=" * width + "\n"
        footer += f" END OF FILE: {rel_path}\n"
        footer += "=" * width + "\n"
        footer += f"{comment_end}\n\n\n"
    else:  # Single-line comments (Python, Shell, etc.)
        header = comment_start * width + "\n"
        header += f"{comment_start} FILE: {rel_path}\n"
        header += f"{comment_start} PATH: {abs_path}\n"
        header += f"{comment_start} TYPE: {filetype}\n"
        header += comment_start * width + "\n\n"
        
        footer = f"\n{comment_start * width}\n"
        footer += f"{comment_start} END OF FILE: {rel_path}\n"
        footer += f"{comment_start * width}\n\n\n"
    
    return header, footer


def collect_files(patterns):
    """Sammelt alle Dateien basierend auf Patterns (Ordner oder Glob)"""
    files_by_type = defaultdict(list)
    
    for pattern in patterns:
        # Ist es ein Ordner?
        if os.path.isdir(pattern):
            for root, dirs, files in os.walk(pattern):
                # Skip __pycache__, .git, etc.
                dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
                
                for file in files:
                    if file.startswith('.'):
                        continue
                    filepath = os.path.join(root, file)
                    ext = os.path.splitext(file)[1]
                    files_by_type[ext].append(filepath)
        
        # Ist es ein Glob-Pattern?
        elif '*' in pattern or '?' in pattern:
            matched = glob.glob(pattern, recursive=True)
            for filepath in matched:
                if os.path.isfile(filepath):
                    ext = os.path.splitext(filepath)[1]
                    files_by_type[ext].append(filepath)
        
        # Einzelne Datei?
        elif os.path.isfile(pattern):
            ext = os.path.splitext(pattern)[1]
            files_by_type[ext].append(pattern)
        
        else:
            print(f"⚠️  Pattern nicht gefunden: {pattern}", file=sys.stderr)
    
    return files_by_type


def merge_files(files_by_type, output_dir='review_output'):
    """Merged Dateien nach Typ und erstellt Output-Dateien"""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stats = {}
    
    for ext, filepaths in sorted(files_by_type.items()):
        if not filepaths:
            continue
        
        # Extension → lesbare Bezeichnung
        filetype_name = EXTENSION_MAP.get(ext, ('Unknown', '#'))[0]
        safe_name = filetype_name.lower().replace(' ', '_')
        
        output_file = os.path.join(output_dir, f"merged_{safe_name}.txt")
        comment_start, comment_end, _ = get_comment_style(ext)
        
        file_count = 0
        total_lines = 0
        
        with open(output_file, 'w', encoding='utf-8') as outf:
            # Meta-Header für die merged-Datei
            if comment_end:
                outf.write(f"{comment_start}\n")
                outf.write("=" * 100 + "\n")
                outf.write(f" MERGED FILE: {filetype_name} Files\n")
                outf.write(f" GENERATED: {timestamp}\n")
                outf.write(f" FILE COUNT: {len(filepaths)}\n")
                outf.write("=" * 100 + "\n")
                outf.write(f"{comment_end}\n\n\n")
            else:
                outf.write(comment_start * 100 + "\n")
                outf.write(f"{comment_start} MERGED FILE: {filetype_name} Files\n")
                outf.write(f"{comment_start} GENERATED: {timestamp}\n")
                outf.write(f"{comment_start} FILE COUNT: {len(filepaths)}\n")
                outf.write(comment_start * 100 + "\n\n\n")
            
            # Sortiere Dateien alphabetisch
            for filepath in sorted(filepaths):
                try:
                    with open(filepath, 'r', encoding='utf-8') as inf:
                        content = inf.read()
                    
                    header, footer = create_header(
                        filepath, 
                        filetype_name, 
                        comment_start, 
                        comment_end
                    )
                    
                    outf.write(header)
                    outf.write(content)
                    if not content.endswith('\n'):
                        outf.write('\n')
                    outf.write(footer)
                    
                    file_count += 1
                    total_lines += len(content.splitlines())
                
                except Exception as e:
                    print(f"⚠️  Fehler bei {filepath}: {e}", file=sys.stderr)
        
        stats[filetype_name] = {
            'output': output_file,
            'files': file_count,
            'lines': total_lines
        }
        
        print(f"✅ {filetype_name:20} → {output_file:40} ({file_count} Dateien, {total_lines} Zeilen)")
    
    return stats


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nBeispiele:")
        print("  python scripts/merge_files_for_review.py src templates")
        print("  python scripts/merge_files_for_review.py '*.md'")
        print("  python scripts/merge_files_for_review.py src 'docs/*.md'")
        sys.exit(1)
    
    patterns = sys.argv[1:]
    
    print("🔍 Sammle Dateien...")
    files_by_type = collect_files(patterns)
    
    if not files_by_type:
        print("❌ Keine Dateien gefunden!")
        sys.exit(1)
    
    print(f"\n📊 Gefunden: {sum(len(files) for files in files_by_type.values())} Dateien")
    print(f"   Dateitypen: {len(files_by_type)}\n")
    
    print("📝 Merge Dateien...\n")
    stats = merge_files(files_by_type)
    
    print("\n✨ Fertig! Review-Dateien erstellt:")
    print(f"   Ordner: review_output/")
    print(f"\n💡 Tipp: Diese Dateien kannst du direkt an eine KI übergeben für Code-Review!")


if __name__ == '__main__':
    main()
