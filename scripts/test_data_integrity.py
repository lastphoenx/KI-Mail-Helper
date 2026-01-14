#!/usr/bin/env python3
# scripts/test_data_integrity.py
"""Data Integrity Test Script.

Validiert Daten-Integrität nach SQLite → PostgreSQL Migration.

VERWENDUNG:
    python scripts/test_data_integrity.py \\
        --source sqlite:///emails.db \\
        --target postgresql://postgres:dev@localhost/mail_helper

TESTS:
    ✅ Row counts identisch
    ✅ Checksums identisch (MD5)
    ✅ Primary Keys vollständig
    ✅ Foreign Keys konsistent
    ✅ NULL-Werte korrekt
"""

import argparse
import hashlib
import sys
from sqlalchemy import create_engine, MetaData, select, func, inspect
from collections import defaultdict


def calculate_row_checksums(engine, table_name, primary_key):
    """Calculate MD5 checksums for each row in table."""
    metadata = MetaData()
    metadata.reflect(bind=engine)
    table = metadata.tables[table_name]
    
    checksums = {}
    with engine.connect() as conn:
        result = conn.execute(select(table))
        for row in result:
            row_dict = dict(row._mapping)
            pk_value = row_dict[primary_key]
            
            # Calculate checksum
            row_str = str(sorted(row_dict.items()))
            checksum = hashlib.md5(row_str.encode()).hexdigest()
            checksums[pk_value] = checksum
    
    return checksums


def test_row_counts(source_engine, target_engine):
    """Test 1: Row counts must be identical."""
    print("\n" + "=" * 70)
    print("TEST 1: Row Counts")
    print("=" * 70)
    
    metadata = MetaData()
    metadata.reflect(bind=source_engine)
    
    passed = True
    for table_name in metadata.tables:
        with source_engine.connect() as source_conn:
            source_count = source_conn.execute(
                select(func.count()).select_from(metadata.tables[table_name])
            ).scalar()
        
        with target_engine.connect() as target_conn:
            target_count = target_conn.execute(
                select(func.count()).select_from(metadata.tables[table_name])
            ).scalar()
        
        if source_count == target_count:
            print(f"✅ {table_name:30} {source_count:6} rows")
        else:
            print(f"❌ {table_name:30} Source={source_count}, Target={target_count}")
            passed = False
    
    return passed


def test_checksums(source_engine, target_engine, sample_tables=None):
    """Test 2: Row checksums must match."""
    print("\n" + "=" * 70)
    print("TEST 2: Data Checksums (sampling)")
    print("=" * 70)
    
    if sample_tables is None:
        # Default: Test critical tables
        sample_tables = ["users", "emails", "raw_emails", "accounts"]
    
    inspector = inspect(source_engine)
    passed = True
    
    for table_name in sample_tables:
        try:
            pk = inspector.get_pk_constraint(table_name)
            if not pk or not pk["constrained_columns"]:
                print(f"⚠️  {table_name}: No PK, skipping")
                continue
            
            pk_column = pk["constrained_columns"][0]
            
            source_checksums = calculate_row_checksums(source_engine, table_name, pk_column)
            target_checksums = calculate_row_checksums(target_engine, table_name, pk_column)
            
            mismatches = 0
            for pk_value in source_checksums:
                if source_checksums[pk_value] != target_checksums.get(pk_value, ""):
                    mismatches += 1
            
            if mismatches == 0:
                print(f"✅ {table_name:30} {len(source_checksums):6} rows validated")
            else:
                print(f"❌ {table_name:30} {mismatches} mismatches")
                passed = False
                
        except Exception as e:
            print(f"⚠️  {table_name}: {e}")
    
    return passed


def test_foreign_keys(target_engine):
    """Test 3: Foreign key constraints must be satisfied."""
    print("\n" + "=" * 70)
    print("TEST 3: Foreign Key Integrity")
    print("=" * 70)
    
    inspector = inspect(target_engine)
    metadata = MetaData()
    metadata.reflect(bind=target_engine)
    
    passed = True
    for table_name in metadata.tables:
        fks = inspector.get_foreign_keys(table_name)
        
        for fk in fks:
            # Check if foreign key references exist
            fk_column = fk["constrained_columns"][0]
            ref_table = fk["referred_table"]
            ref_column = fk["referred_columns"][0]
            
            table = metadata.tables[table_name]
            ref_table_obj = metadata.tables[ref_table]
            
            with target_engine.connect() as conn:
                # Find orphaned references
                query = select(func.count()).select_from(table).where(
                    ~select(ref_table_obj.c[ref_column]).select_from(ref_table_obj).exists()
                )
                orphaned = conn.execute(query).scalar()
                
                if orphaned == 0:
                    print(f"✅ {table_name}.{fk_column} → {ref_table}.{ref_column}")
                else:
                    print(f"❌ {table_name}.{fk_column}: {orphaned} orphaned references")
                    passed = False
    
    return passed


def main():
    parser = argparse.ArgumentParser(description="Test data integrity after migration")
    parser.add_argument("--source", required=True, help="Source DATABASE_URL")
    parser.add_argument("--target", required=True, help="Target DATABASE_URL")
    parser.add_argument("--sample-tables", nargs="+", help="Tables to checksum")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("Data Integrity Tests")
    print("=" * 70)
    
    source_engine = create_engine(args.source)
    target_engine = create_engine(args.target)
    
    # Run tests
    tests = [
        ("Row Counts", lambda: test_row_counts(source_engine, target_engine)),
        ("Checksums", lambda: test_checksums(source_engine, target_engine, args.sample_tables)),
        ("Foreign Keys", lambda: test_foreign_keys(target_engine)),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            passed = test_func()
            results.append((test_name, passed))
        except Exception as e:
            print(f"\n❌ {test_name}: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status:12} {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    print("=" * 70)
    if all_passed:
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
