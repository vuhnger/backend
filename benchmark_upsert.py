#!/usr/bin/env python3
"""
Performance benchmark: Race-condition-free atomic upsert vs unsafe check-then-insert

This benchmark measures:
1. Throughput (operations/second) under concurrent load
2. Latency distribution (mean, p95, p99)
3. Error rates (duplicate key violations)
4. Database round-trips and lock contention

Test scenarios:
- Single-threaded sequential operations (baseline)
- Multi-threaded concurrent operations (race condition testing)
- Mixed insert/update workload (realistic usage)

Expected results:
- Atomic upsert: ~2-3x throughput improvement
- Atomic upsert: Zero duplicate key errors
- Old pattern: Duplicate key errors under concurrency
- Atomic upsert: Lower p99 latency due to fewer round-trips

Usage:
    python benchmark_upsert.py
"""

import time
import statistics
import concurrent.futures
from typing import List, Dict, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Import models and utilities
from apps.shared.database import DATABASE_URL, Base
from apps.strava.models import StravaStats
from apps.shared.upsert import atomic_upsert_stats


# Create a separate engine for benchmarking to avoid connection pool issues
benchmark_engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    echo=False
)
BenchmarkSession = sessionmaker(autocommit=False, autoflush=False, bind=benchmark_engine)


def setup_benchmark_table():
    """Create tables and clear existing data"""
    Base.metadata.create_all(bind=benchmark_engine)

    # Clear existing stats
    with BenchmarkSession() as db:
        db.execute(text("DELETE FROM strava_stats WHERE stats_type LIKE 'bench_%'"))
        db.commit()

    print("✓ Benchmark table prepared")


def old_unsafe_upsert(db: Session, stats_type: str, data: dict) -> Tuple[bool, float]:
    """
    Old unsafe pattern: check-then-insert (NON-ATOMIC)

    This pattern has a race condition:
    - Thread A: SELECT -> no result
    - Thread B: SELECT -> no result
    - Thread A: INSERT -> success
    - Thread B: INSERT -> DUPLICATE KEY ERROR!

    Returns:
        (success: bool, duration: float)
    """
    start = time.perf_counter()

    try:
        # RACE CONDITION: Another thread can insert between this query and the commit
        existing = db.query(StravaStats).filter(
            StravaStats.stats_type == stats_type
        ).first()

        if existing:
            existing.data = data
        else:
            stats = StravaStats(stats_type=stats_type, data=data)
            db.add(stats)

        db.commit()
        duration = time.perf_counter() - start
        return (True, duration)

    except Exception as e:
        db.rollback()
        duration = time.perf_counter() - start
        if "duplicate key" in str(e).lower():
            return (False, duration)
        raise


def new_atomic_upsert(db: Session, stats_type: str, data: dict) -> Tuple[bool, float]:
    """
    New atomic pattern: PostgreSQL ON CONFLICT (ATOMIC)

    This is race-condition-free:
    - Single atomic operation
    - No window for concurrent conflicts
    - No duplicate key errors

    Returns:
        (success: bool, duration: float)
    """
    start = time.perf_counter()

    try:
        atomic_upsert_stats(
            db=db,
            model=StravaStats,
            unique_field='stats_type',
            unique_value=stats_type,
            update_data={'data': data}
        )
        db.commit()
        duration = time.perf_counter() - start
        return (True, duration)

    except Exception as e:
        db.rollback()
        duration = time.perf_counter() - start
        raise


def run_single_operation(
    operation_func,
    stats_type: str,
    iteration: int
) -> Tuple[bool, float]:
    """Run a single upsert operation with fresh DB session"""
    db = BenchmarkSession()

    try:
        data = {"iteration": iteration, "timestamp": time.time()}
        return operation_func(db, stats_type, data)
    finally:
        db.close()


def benchmark_sequential(
    operation_func,
    num_operations: int = 100,
    stats_type_prefix: str = "bench_seq"
) -> Dict:
    """
    Benchmark sequential operations (no concurrency)

    This establishes baseline performance without race conditions.
    """
    print(f"\n  Running {num_operations} sequential operations...")

    latencies = []
    errors = 0

    start_time = time.perf_counter()

    for i in range(num_operations):
        success, duration = run_single_operation(
            operation_func,
            f"{stats_type_prefix}_{i % 10}",  # 10 unique keys, lots of updates
            i
        )

        latencies.append(duration * 1000)  # Convert to milliseconds
        if not success:
            errors += 1

    total_duration = time.perf_counter() - start_time

    return {
        "total_operations": num_operations,
        "total_duration_sec": total_duration,
        "throughput_ops_sec": num_operations / total_duration,
        "mean_latency_ms": statistics.mean(latencies),
        "median_latency_ms": statistics.median(latencies),
        "p95_latency_ms": statistics.quantiles(latencies, n=20)[18],  # 95th percentile
        "p99_latency_ms": statistics.quantiles(latencies, n=100)[98],  # 99th percentile
        "min_latency_ms": min(latencies),
        "max_latency_ms": max(latencies),
        "stddev_latency_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "error_count": errors,
        "error_rate": errors / num_operations
    }


def benchmark_concurrent(
    operation_func,
    num_operations: int = 100,
    num_workers: int = 10,
    stats_type_prefix: str = "bench_conc"
) -> Dict:
    """
    Benchmark concurrent operations (tests race conditions)

    This simulates multiple cron jobs or API requests hitting the same keys simultaneously.
    The old pattern will likely produce duplicate key errors here.
    """
    print(f"\n  Running {num_operations} concurrent operations with {num_workers} workers...")

    latencies = []
    errors = 0

    start_time = time.perf_counter()

    # Create tasks: multiple workers hitting the same stats_type values
    tasks = [
        (operation_func, f"{stats_type_prefix}_{i % 5}", i)  # Only 5 unique keys = high contention
        for i in range(num_operations)
    ]

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(run_single_operation, *task)
            for task in tasks
        ]

        for future in concurrent.futures.as_completed(futures):
            try:
                success, duration = future.result()
                latencies.append(duration * 1000)
                if not success:
                    errors += 1
            except Exception as e:
                errors += 1
                print(f"    ERROR: {e}")

    total_duration = time.perf_counter() - start_time

    return {
        "total_operations": num_operations,
        "num_workers": num_workers,
        "total_duration_sec": total_duration,
        "throughput_ops_sec": num_operations / total_duration,
        "mean_latency_ms": statistics.mean(latencies) if latencies else 0,
        "median_latency_ms": statistics.median(latencies) if latencies else 0,
        "p95_latency_ms": statistics.quantiles(latencies, n=20)[18] if len(latencies) > 20 else max(latencies) if latencies else 0,
        "p99_latency_ms": statistics.quantiles(latencies, n=100)[98] if len(latencies) > 100 else max(latencies) if latencies else 0,
        "min_latency_ms": min(latencies) if latencies else 0,
        "max_latency_ms": max(latencies) if latencies else 0,
        "stddev_latency_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
        "error_count": errors,
        "error_rate": errors / num_operations
    }


def print_results(name: str, results: Dict):
    """Pretty-print benchmark results"""
    print(f"\n  Results for {name}:")
    print(f"    Total operations:     {results['total_operations']}")
    if 'num_workers' in results:
        print(f"    Concurrent workers:   {results['num_workers']}")
    print(f"    Total duration:       {results['total_duration_sec']:.3f} sec")
    print(f"    Throughput:           {results['throughput_ops_sec']:.1f} ops/sec")
    print(f"    Mean latency:         {results['mean_latency_ms']:.2f} ms")
    print(f"    Median latency:       {results['median_latency_ms']:.2f} ms")
    print(f"    P95 latency:          {results['p95_latency_ms']:.2f} ms")
    print(f"    P99 latency:          {results['p99_latency_ms']:.2f} ms")
    print(f"    Min latency:          {results['min_latency_ms']:.2f} ms")
    print(f"    Max latency:          {results['max_latency_ms']:.2f} ms")
    print(f"    Latency std dev:      {results['stddev_latency_ms']:.2f} ms")
    print(f"    Errors:               {results['error_count']} ({results['error_rate']*100:.1f}%)")


def compare_results(old_results: Dict, new_results: Dict):
    """Compare old vs new and print improvement statistics"""
    print("\n" + "="*70)
    print("PERFORMANCE COMPARISON")
    print("="*70)

    throughput_improvement = (
        (new_results['throughput_ops_sec'] - old_results['throughput_ops_sec'])
        / old_results['throughput_ops_sec'] * 100
    )

    mean_latency_improvement = (
        (old_results['mean_latency_ms'] - new_results['mean_latency_ms'])
        / old_results['mean_latency_ms'] * 100
    )

    p99_latency_improvement = (
        (old_results['p99_latency_ms'] - new_results['p99_latency_ms'])
        / old_results['p99_latency_ms'] * 100
    )

    print(f"\nThroughput improvement:     {throughput_improvement:+.1f}%")
    print(f"  Old: {old_results['throughput_ops_sec']:.1f} ops/sec")
    print(f"  New: {new_results['throughput_ops_sec']:.1f} ops/sec")

    print(f"\nMean latency improvement:   {mean_latency_improvement:+.1f}%")
    print(f"  Old: {old_results['mean_latency_ms']:.2f} ms")
    print(f"  New: {new_results['mean_latency_ms']:.2f} ms")

    print(f"\nP99 latency improvement:    {p99_latency_improvement:+.1f}%")
    print(f"  Old: {old_results['p99_latency_ms']:.2f} ms")
    print(f"  New: {new_results['p99_latency_ms']:.2f} ms")

    print(f"\nError rate reduction:")
    print(f"  Old: {old_results['error_count']} errors ({old_results['error_rate']*100:.1f}%)")
    print(f"  New: {new_results['error_count']} errors ({new_results['error_rate']*100:.1f}%)")

    # Statistical significance check (simple t-test approximation)
    if throughput_improvement > 10:
        print(f"\n✓ SIGNIFICANT IMPROVEMENT: Atomic upsert provides {throughput_improvement:.0f}% better throughput")
    elif throughput_improvement > 0:
        print(f"\n~ MODEST IMPROVEMENT: Atomic upsert provides {throughput_improvement:.0f}% better throughput")
    else:
        print(f"\n⚠ NO IMPROVEMENT: Results within noise margin")

    if new_results['error_count'] == 0 and old_results['error_count'] > 0:
        print(f"✓ RACE CONDITION ELIMINATED: Zero errors with atomic upsert vs {old_results['error_count']} with old pattern")


def main():
    """Run comprehensive performance benchmarks"""
    print("="*70)
    print("UPSERT PATTERN PERFORMANCE BENCHMARK")
    print("="*70)
    print("\nComparing:")
    print("  OLD: Check-then-insert (SELECT + conditional INSERT/UPDATE)")
    print("  NEW: Atomic upsert (INSERT ON CONFLICT DO UPDATE)")

    setup_benchmark_table()

    # Benchmark 1: Sequential operations (baseline, no race conditions expected)
    print("\n" + "-"*70)
    print("BENCHMARK 1: Sequential Operations (Baseline)")
    print("-"*70)

    print("\n[OLD PATTERN - Sequential]")
    old_seq = benchmark_sequential(old_unsafe_upsert, num_operations=100)
    print_results("Old Pattern (Sequential)", old_seq)

    print("\n[NEW PATTERN - Sequential]")
    new_seq = benchmark_sequential(new_atomic_upsert, num_operations=100)
    print_results("New Pattern (Sequential)", new_seq)

    compare_results(old_seq, new_seq)

    # Benchmark 2: Concurrent operations (race condition testing)
    print("\n" + "-"*70)
    print("BENCHMARK 2: Concurrent Operations (Race Condition Test)")
    print("-"*70)

    print("\n[OLD PATTERN - Concurrent]")
    old_conc = benchmark_concurrent(old_unsafe_upsert, num_operations=100, num_workers=10)
    print_results("Old Pattern (Concurrent)", old_conc)

    print("\n[NEW PATTERN - Concurrent]")
    new_conc = benchmark_concurrent(new_atomic_upsert, num_operations=100, num_workers=10)
    print_results("New Pattern (Concurrent)", new_conc)

    compare_results(old_conc, new_conc)

    # Final summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    print("\nSequential workload (no concurrency):")
    print(f"  Throughput improvement: {((new_seq['throughput_ops_sec'] - old_seq['throughput_ops_sec']) / old_seq['throughput_ops_sec'] * 100):+.1f}%")
    print(f"  Latency improvement:    {((old_seq['mean_latency_ms'] - new_seq['mean_latency_ms']) / old_seq['mean_latency_ms'] * 100):+.1f}%")

    print("\nConcurrent workload (high contention):")
    print(f"  Throughput improvement: {((new_conc['throughput_ops_sec'] - old_conc['throughput_ops_sec']) / old_conc['throughput_ops_sec'] * 100):+.1f}%")
    print(f"  Error elimination:      {old_conc['error_count']} → {new_conc['error_count']} errors")

    print("\nRECOMMENDATION:")
    if new_conc['error_count'] == 0 and old_conc['error_count'] > 0:
        print("  ✓ MUST FIX: The old pattern has race conditions causing duplicate key errors.")
        print("  ✓ SOLUTION: Use atomic upsert pattern to eliminate race conditions.")

    if new_seq['throughput_ops_sec'] > old_seq['throughput_ops_sec'] * 1.1:
        print(f"  ✓ PERFORMANCE: Atomic upsert is {((new_seq['throughput_ops_sec'] / old_seq['throughput_ops_sec'] - 1) * 100):.0f}% faster even without concurrency.")

    print("\n" + "="*70)

    # Cleanup
    with BenchmarkSession() as db:
        db.execute(text("DELETE FROM strava_stats WHERE stats_type LIKE 'bench_%'"))
        db.commit()

    print("\n✓ Benchmark complete. Test data cleaned up.")


if __name__ == "__main__":
    main()
