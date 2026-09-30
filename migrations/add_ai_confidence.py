#!/usr/bin/env python3
"""
Migration: Add ai_confidence column to processed_emails table
Phase Y2: AI Confidence Tracking

This migration adds the ai_confidence column to track confidence scores
from AI analyses (0.0-1.0 scale), particularly useful for Phase Y hybrid analyses.

Run: python migrations/add_ai_confidence.py
"""

import sqlite3
import os
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def add_ai_confidence_column():
    """Add ai_confidence column to processed_emails table"""
    
    console.print("[bold blue]🔄 Phase Y2: Adding ai_confidence column...[/bold blue]")
    
    # Get database path
    db_path = os.getenv("DATABASE_PATH", "emails.db")
    if not Path(db_path).is_absolute():
        db_path = Path(__file__).parent.parent / db_path
    
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            # Check if column already exists
            task = progress.add_task("Checking existing schema...", total=1)
            cursor.execute("PRAGMA table_info(processed_emails)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "ai_confidence" in columns:
                console.print("[yellow]⚠️ Column 'ai_confidence' already exists. Skipping migration.[/yellow]")
                progress.update(task, completed=1)
                return
            
            progress.update(task, completed=1)
            
            # Add column
            task = progress.add_task("Adding ai_confidence column...", total=1)
            cursor.execute("""
                ALTER TABLE processed_emails 
                ADD COLUMN ai_confidence REAL
            """)
            conn.commit()
            progress.update(task, completed=1)
            
            # Verify
            task = progress.add_task("Verifying migration...", total=1)
            cursor.execute("PRAGMA table_info(processed_emails)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "ai_confidence" in columns:
                console.print("[bold green]✅ Migration successful![/bold green]")
                console.print("\n[dim]Column details:[/dim]")
                console.print(f"  • Type: REAL (SQLite FLOAT)")
                console.print(f"  • Nullable: Yes")
                console.print(f"  • Default: NULL")
                console.print(f"  • Range: 0.0-1.0 (e.g., 0.65-0.9 for Phase Y)")
            else:
                console.print("[bold red]❌ Verification failed - column not found![/bold red]")
                
            progress.update(task, completed=1)
            
            # Statistics
            task = progress.add_task("Gathering statistics...", total=1)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(ai_confidence) as with_confidence,
                    MIN(ai_confidence) as min_conf,
                    MAX(ai_confidence) as max_conf,
                    AVG(ai_confidence) as avg_conf
                FROM processed_emails
            """)
            stats = cursor.fetchone()
            progress.update(task, completed=1)
            
            console.print("\n[bold]📊 Current State:[/bold]")
            console.print(f"  • Total emails: {stats[0]:,}")
            percent = (stats[1]/stats[0]*100) if stats[0] > 0 else 0
            console.print(f"  • With confidence: {stats[1]:,} ({percent:.1f}%)")
            if stats[1] > 0:
                console.print(f"  • Confidence range: {stats[2]:.2f} - {stats[3]:.2f}")
                console.print(f"  • Average confidence: {stats[4]:.2f}")
            else:
                console.print("[dim]  • No confidence data yet (will be populated for new analyses)[/dim]")
                
    except Exception as e:
        conn.rollback()
        console.print(f"[bold red]❌ Migration failed: {e}[/bold red]")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    console.print("[bold cyan]═══════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Phase Y2: AI Confidence Tracking Migration       [/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════[/bold cyan]\n")
    
    add_ai_confidence_column()
    
    console.print("\n[bold green]✅ Migration complete![/bold green]")
    console.print("\n[dim]Next analyses will automatically populate ai_confidence.[/dim]")
