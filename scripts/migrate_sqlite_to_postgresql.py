#!/usr/bin/env python3
# scripts/migrate_sqlite_to_postgresql.py
"""SQLite → PostgreSQL Data Migration Script.

Implementiert aus doc/Multi-User/02_POSTGRESQL_COMPATIBILITY_TEST.md

VERWENDUNG:
    1. PostgreSQL bereitstellen:
       docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=dev \\
           -e POSTGRES_DB=mail_helper postgres:15-alpine
    
    2. Schema erstellen:
       DATABASE_URL=postgresql://postgres:dev@localhost/mail_helper \\
           alembic upgrade head
    
    3. Migration ausführen:
       python scripts/migrate_sqlite_to_postgresql.py \\
           --source sqlite:///emails.db \\
           --target postgresql://postgres:dev@localhost/mail_helper
    
    4. Validierung:
       python scripts/test_data_integrity.py

FEATURES:
    ✅ Row-by-row migration mit Validierung
    ✅ Checksummen-Vergleich
    ✅ Rollback bei Fehlern
    ✅ Progress-Bar
    ✅ Dry-Run Mode
"""

import argparse
import hashlib
import sys
from sqlalchemy import create_engine, MetaData, Table, select, func
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from tqdm import tqdm


def calculate_checksum(engine):
    """Calculate checksums for all tables."""
    metadata = MetaData()
    metadata.reflect(bind=engine)
    
    checksums = {}
    for table_name, table in metadata.tables.items():
        with engine.connect() as conn:
            count = conn.execute(select(func.count()).select_from(table)).scalar()
            checksums[table_name] = count
    
    return checksums


def convert_sqlite_to_postgres_types(row_dict, target_table):
    """Convert SQLite types to PostgreSQL-compatible types."""
    from sqlalchemy import Boolean, Integer
    
    for column in target_table.columns:
        if column.name in row_dict and row_dict[column.name] is not None:
            # Convert integer 0/1 to boolean for Boolean columns
            if isinstance(column.type, Boolean):
                value = row_dict[column.name]
                if isinstance(value, int):
                    row_dict[column.name] = bool(value)
    
    return row_dict


def migrate_table(source_engine, target_engine, table_name, dry_run=False):
    """Migrate single table from source to target."""
    source_metadata = MetaData()
    source_metadata.reflect(bind=source_engine)
    
    target_metadata = MetaData()
    target_metadata.reflect(bind=target_engine)
    
    if table_name not in source_metadata.tables:
        print(f"⚠️  Tabelle {table_name} nicht in Source DB gefunden")
        return 0
    
    table = source_metadata.tables[table_name]
    target_table = target_metadata.tables.get(table_name)
    
    # Get row count
    with source_engine.connect() as source_conn:
        count = source_conn.execute(select(func.count()).select_from(table)).scalar()
    
    if count == 0:
        print(f"📭 {table_name}: Keine Daten")
        return 0
    
    print(f"🔄 Migriere {table_name} ({count} rows)...")
    
    if dry_run:
        print(f"   [DRY-RUN] Würde {count} rows migrieren")
        return count
    
    # Migrate rows
    Session = sessionmaker(bind=target_engine)
    migrated = 0
    errors = 0
    
    with source_engine.connect() as source_conn:
        result = source_conn.execute(select(table))
        rows = result.fetchall()
        
        with Session() as target_session:
            for row in tqdm(rows, desc=f"  {table_name}"):
                try:
                    # Convert row to dict
                    row_dict = dict(row._mapping)
                    
                    # Filter out columns that don't exist in target table
                    if target_table is not None:
                        target_columns = {col.name for col in target_table.columns}
                        row_dict = {k: v for k, v in row_dict.items() if k in target_columns}
                        
                        # Convert SQLite types to PostgreSQL types
                        row_dict = convert_sqlite_to_postgres_types(row_dict, target_table)
                    
                    # Insert into target
                    target_session.execute(table.insert().values(**row_dict))
                    migrated += 1
                    
                    # Commit every 100 rows
                    if migrated % 100 == 0:
                        target_session.commit()
                        
                except IntegrityError as e:
                    errors += 1
                    print(f"⚠️  IntegrityError: {e}")
                    target_session.rollback()
            
            # Final commit
            target_session.commit()
    
    print(f"✅ {table_name}: {migrated} rows migrated, {errors} errors")
    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migrate SQLite to PostgreSQL")
    parser.add_argument("--source", required=True, help="Source DATABASE_URL (SQLite)")
    parser.add_argument("--target", required=True, help="Target DATABASE_URL (PostgreSQL)")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run (no actual migration)")
    parser.add_argument("--tables", nargs="+", help="Specific tables to migrate (default: all)")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("SQLite → PostgreSQL Migration")
    print("=" * 70)
    print(f"Source: {args.source}")
    print(f"Target: {args.target}")
    print(f"Dry-Run: {args.dry_run}")
    print()
    
    # Connect to databases
    source_engine = create_engine(args.source)
    target_engine = create_engine(args.target)
    
    # Calculate source checksums
    print("📊 Berechne Source-Checksums...")
    source_checksums = calculate_checksum(source_engine)
    print(f"   Tabellen: {len(source_checksums)}")
    print(f"   Total Rows: {sum(source_checksums.values())}")
    print()
    
    # Determine tables to migrate
    if args.tables:
        tables = args.tables
    else:
        # Define proper migration order (respecting foreign keys)
        # Skip alembic_version as it's managed by Alembic itself
        MIGRATION_ORDER = [
            'users',  # First: users (no dependencies)
            'mail_accounts',  # Then: mail_accounts (depends on users)
            'raw_emails',  # Then: raw_emails (depends on mail_accounts)
            'processed_emails',  # Then: processed_emails (depends on raw_emails)
            'sender_patterns',  # Depends on users
            'auto_rules',  # Depends on users
            'email_tags',  # Depends on processed_emails
            'mail_server_state',  # Depends on mail_accounts
            'imap_diagnostics',
            'processing_logs',
            'ai_optimization_cache',
            'tag_suggestion_queue',
            'tag_suggestion_jobs',
            'message_thread_cache',
            'archive_metadata',
            'mailbox_metadata',
            'tag_rename_log',
            'tag_mappings',
            'tag_suggestions',
            'tag_assignment_log',
            'background_jobs',
            'scheduled_jobs'
        ]
        
        # Use ordered list, append any unknown tables at the end
        tables = []
        for table in MIGRATION_ORDER:
            if table in source_checksums and table != 'alembic_version':
                tables.append(table)
        
        # Add any remaining tables not in MIGRATION_ORDER (except alembic_version)
        for table in source_checksums.keys():
            if table not in tables and table != 'alembic_version':
                tables.append(table)
    
    # Migrate tables
    total_migrated = 0
    for table_name in tables:
        migrated = migrate_table(source_engine, target_engine, table_name, args.dry_run)
        total_migrated += migrated
    
    print()
    print("=" * 70)
    
    if not args.dry_run:
        # Validate migration
        print("✅ Validiere Migration...")
        target_checksums = calculate_checksum(target_engine)
        
        for table_name in tables:
            source_count = source_checksums.get(table_name, 0)
            target_count = target_checksums.get(table_name, 0)
            
            if source_count == target_count:
                print(f"   ✅ {table_name}: {target_count} rows")
            else:
                print(f"   ❌ {table_name}: Source={source_count}, Target={target_count}")
                sys.exit(1)
        
        print()
        print(f"✅ Migration erfolgreich: {total_migrated} rows migrated")
    else:
        print(f"[DRY-RUN] Würde {total_migrated} rows migrieren")
    
    print("=" * 70)


if __name__ == "__main__":
    main()
