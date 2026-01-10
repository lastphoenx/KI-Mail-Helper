#!/usr/bin/env python3
"""
Migration: Add optimize_confidence column to processed_emails table
Phase Y2: Optimize Pass Confidence Tracking

This adds optimize_confidence to track confidence scores from the optimize pass,
complementing the initial ai_confidence column.

Run: python migrations/add_optimize_confidence.py
"""

import sqlite3
import os
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


def add_optimize_confidence_column():
    """Add optimize_confidence column to processed_emails table"""
    
    console.print("[bold blue]🔄 Phase Y2: Adding optimize_confidence column...[/bold blue]")
    
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
            
            if "optimize_confidence" in columns:
                console.print("[yellow]⚠️ Column 'optimize_confidence' already exists. Skipping migration.[/yellow]")
                progress.update(task, completed=1)
                return
            
            progress.update(task, completed=1)
            
            # Add column
            task = progress.add_task("Adding optimize_confidence column...", total=1)
            cursor.execute("""
                ALTER TABLE processed_emails 
                ADD COLUMN optimize_confidence REAL
            """)
            conn.commit()
            progress.update(task, completed=1)
            
            # Verify
            task = progress.add_task("Verifying migration...", total=1)
            cursor.execute("PRAGMA table_info(processed_emails)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if "optimize_confidence" in columns:
                console.print("[bold green]✅ Migration successful![/bold green]")
                console.print("\n[dim]Column details:[/dim]")
                console.print(f"  • Type: REAL (SQLite FLOAT)")
                console.print(f"  • Nullable: Yes")
                console.print(f"  • Default: NULL")
                console.print(f"  • Purpose: Track confidence from optimize pass (second AI analysis)")
            else:
                console.print("[bold red]❌ Verification failed - column not found![/bold red]")
                
            progress.update(task, completed=1)
            
            # Statistics
            task = progress.add_task("Gathering statistics...", total=1)
            cursor.execute("""
                SELECT 
                    COUNT(*) as total,
                    COUNT(optimize_confidence) as with_opt_conf,
                    COUNT(ai_confidence) as with_init_conf,
                    COUNT(CASE WHEN optimization_status = 'done' THEN 1 END) as optimized_count
                FROM processed_emails
            """)
            stats = cursor.fetchone()
            progress.update(task, completed=1)
            
            console.print("\n[bold]📊 Current State:[/bold]")
            console.print(f"  • Total emails: {stats[0]:,}")
            console.print(f"  • With optimize_confidence: {stats[1]:,}")
            console.print(f"  • With ai_confidence (initial): {stats[2]:,}")
            console.print(f"  • Optimized emails: {stats[3]:,}")
            console.print("\n[dim]  • Future optimize passes will populate optimize_confidence[/dim]")
                
    except Exception as e:
        conn.rollback()
        console.print(f"[bold red]❌ Migration failed: {e}[/bold red]")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    console.print("[bold cyan]═══════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]  Phase Y2: Optimize Confidence Tracking Migration[/bold cyan]")
    console.print("[bold cyan]═══════════════════════════════════════════════════[/bold cyan]\n")
    
    add_optimize_confidence_column()
    
    console.print("\n[bold green]✅ Migration complete![/bold green]")
    console.print("\n[dim]Future optimize passes will automatically populate optimize_confidence.[/dim]")
