#!/usr/bin/env python3
"""Run cache isolation tests directly."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Import the test class
from test.test_clang_cache_repo_isolation import TestCacheRepoIsolation, TestCachePathConstruction

print("=" * 70)
print("RUNNING CACHE ISOLATION TESTS")
print("=" * 70)

# Instantiate test classes
cache_tests = TestCacheRepoIsolation()
path_tests = TestCachePathConstruction()

# Run critical test
print("\n[1/3] Testing cache path construction...")
try:
    path_tests.test_cache_path_includes_build_dir()
    print("✅ PASS: Cache paths properly include build_dir")
except AssertionError as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

print("\n[2/3] Testing independent cache directories...")
try:
    cache_tests.test_different_repos_get_independent_cache_directories()
    print("✅ PASS: Each repo gets independent cache directory")
except AssertionError as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

print("\n[3/3] Testing for cache contamination between repos...")
try:
    cache_tests.test_cache_doesnt_leak_between_repo_instances()
    print("✅ PASS: No cache contamination detected!")
except AssertionError as e:
    print(f"❌ FAIL: CACHE CONTAMINATION DETECTED!")
    print(f"   {e}")
    sys.exit(1)

print("\n" + "=" * 70)
print("ALL CACHE ISOLATION TESTS PASSED ✅")
print("=" * 70)
