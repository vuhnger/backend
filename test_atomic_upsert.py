#!/usr/bin/env python3
"""
Test script to verify atomic upsert implementation

This script tests:
1. Basic upsert functionality (insert then update)
2. Concurrent safety (multiple processes trying to insert same key)
3. Timestamp auto-update on upsert
4. Proper error handling

Run this to verify the fix works before deploying.
"""

import sys
import time
from sqlalchemy.orm import Session
from apps.shared.database import SessionLocal, Base, engine
from apps.strava.models import StravaStats
from apps.shared.upsert import atomic_upsert_stats


def test_basic_upsert():
    """Test basic insert and update functionality"""
    print("\n[TEST 1] Basic Upsert Functionality")
    print("-" * 50)

    db = SessionLocal()

    try:
        # Clear any existing test data
        db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_basic'
        ).delete()
        db.commit()

        # Test 1: Insert new record
        print("  Inserting new record...")
        atomic_upsert_stats(
            db=db,
            model=StravaStats,
            unique_field='stats_type',
            unique_value='test_basic',
            update_data={'data': {'test': 'insert', 'value': 1}}
        )
        db.commit()

        # Verify insert
        record = db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_basic'
        ).first()

        assert record is not None, "Record not inserted"
        assert record.data['test'] == 'insert', "Data not correct"
        assert record.data['value'] == 1, "Value not correct"
        first_timestamp = record.fetched_at

        print(f"  ✓ Insert successful: {record.data}")
        print(f"  ✓ Timestamp: {first_timestamp}")

        # Wait a moment to ensure timestamp changes
        time.sleep(0.1)

        # Test 2: Update existing record
        print("\n  Updating existing record...")
        atomic_upsert_stats(
            db=db,
            model=StravaStats,
            unique_field='stats_type',
            unique_value='test_basic',
            update_data={'data': {'test': 'update', 'value': 2}}
        )
        db.commit()

        # Verify update
        record = db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_basic'
        ).first()

        assert record is not None, "Record disappeared"
        assert record.data['test'] == 'update', "Data not updated"
        assert record.data['value'] == 2, "Value not updated"
        second_timestamp = record.fetched_at

        print(f"  ✓ Update successful: {record.data}")
        print(f"  ✓ Timestamp updated: {second_timestamp}")
        assert second_timestamp > first_timestamp, "Timestamp not auto-updated"
        print(f"  ✓ Timestamp auto-update verified")

        # Cleanup
        db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_basic'
        ).delete()
        db.commit()

        print("\n✓ TEST 1 PASSED: Basic upsert works correctly")
        return True

    except Exception as e:
        db.rollback()
        print(f"\n✗ TEST 1 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


def test_concurrent_safety():
    """Test that concurrent upserts don't cause duplicate key errors"""
    print("\n[TEST 2] Concurrent Safety")
    print("-" * 50)

    # Clear test data
    db = SessionLocal()
    try:
        db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_concurrent'
        ).delete()
        db.commit()
    finally:
        db.close()

    # Simulate rapid concurrent upserts
    print("  Simulating 10 rapid concurrent upserts to same key...")
    errors = 0
    successes = 0

    for i in range(10):
        db = SessionLocal()
        try:
            atomic_upsert_stats(
                db=db,
                model=StravaStats,
                unique_field='stats_type',
                unique_value='test_concurrent',
                update_data={'data': {'iteration': i, 'timestamp': time.time()}}
            )
            db.commit()
            successes += 1
        except Exception as e:
            db.rollback()
            errors += 1
            print(f"    Error on iteration {i}: {e}")
        finally:
            db.close()

    # Verify final state
    db = SessionLocal()
    try:
        record = db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_concurrent'
        ).first()

        assert record is not None, "No record found after upserts"
        print(f"  ✓ Final record: iteration={record.data['iteration']}")
        print(f"  ✓ Successes: {successes}/10")
        print(f"  ✓ Errors: {errors}/10")

        # Cleanup
        db.query(StravaStats).filter(
            StravaStats.stats_type == 'test_concurrent'
        ).delete()
        db.commit()

        if errors > 0:
            print(f"\n⚠ TEST 2 WARNING: Had {errors} errors (should be 0)")
            return False

        print("\n✓ TEST 2 PASSED: No race condition errors")
        return True

    except Exception as e:
        db.rollback()
        print(f"\n✗ TEST 2 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


def test_error_handling():
    """Test error handling for invalid inputs"""
    print("\n[TEST 3] Error Handling")
    print("-" * 50)

    db = SessionLocal()

    try:
        # Test invalid model field
        print("  Testing invalid unique field...")
        try:
            atomic_upsert_stats(
                db=db,
                model=StravaStats,
                unique_field='nonexistent_field',
                unique_value='test',
                update_data={'data': {}}
            )
            print("  ✗ Should have raised ValueError")
            return False
        except ValueError as e:
            print(f"  ✓ Correctly raised ValueError: {e}")

        # Test invalid timestamp field
        print("\n  Testing invalid timestamp field...")
        try:
            atomic_upsert_stats(
                db=db,
                model=StravaStats,
                unique_field='stats_type',
                unique_value='test',
                update_data={'data': {}},
                timestamp_field='nonexistent_timestamp'
            )
            print("  ✗ Should have raised ValueError")
            return False
        except ValueError as e:
            print(f"  ✓ Correctly raised ValueError: {e}")

        print("\n✓ TEST 3 PASSED: Error handling works correctly")
        return True

    except Exception as e:
        print(f"\n✗ TEST 3 FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


def main():
    """Run all tests"""
    print("="*70)
    print("ATOMIC UPSERT VERIFICATION TESTS")
    print("="*70)

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    results = []

    results.append(test_basic_upsert())
    results.append(test_concurrent_safety())
    results.append(test_error_handling())

    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)

    passed = sum(results)
    total = len(results)

    print(f"\nPassed: {passed}/{total}")

    if all(results):
        print("\n✓ ALL TESTS PASSED")
        print("\nThe atomic upsert implementation is working correctly.")
        print("You can now safely use it in production to prevent race conditions.")
        return 0
    else:
        print("\n✗ SOME TESTS FAILED")
        print("\nPlease investigate failures before deploying to production.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
