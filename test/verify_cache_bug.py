#!/usr/bin/env python3
"""Quick verification script to check if cache bug exists."""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lib.clang_utils import build_include_graph
from lib.scenario_creators import create_git_repo_from_scenario

print("=" * 70)
print("CACHE BUG VERIFICATION TEST")
print("=" * 70)

with tempfile.TemporaryDirectory() as tmp_dir:
    # Test 1: Create first repo instance
    print("\n[TEST 1] Creating first repo instance...")
    repo1_path = Path(tmp_dir) / "instance1"
    create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo1_path), baseline_as_head=True, current_as_working=True)

    print(f"  Repo path: {repo1_path}")
    print("  Scanning...")
    scan1 = build_include_graph(str(repo1_path), verbose=False)
    headers1 = len(scan1.all_headers)
    print(f"  ✓ Headers found: {headers1}")

    # Test 2: Create second repo instance
    print("\n[TEST 2] Creating second repo instance (different path)...")
    repo2_path = Path(tmp_dir) / "instance2"
    create_git_repo_from_scenario(scenario_id=9, repo_path=str(repo2_path), baseline_as_head=True, current_as_working=True)

    print(f"  Repo path: {repo2_path}")
    print("  Scanning...")
    scan2 = build_include_graph(str(repo2_path), verbose=False)
    headers2 = len(scan2.all_headers)
    print(f"  ✓ Headers found: {headers2}")

    # Verify results
    print("\n" + "=" * 70)
    print("RESULTS:")
    print("=" * 70)
    print(f"  Repo 1: {headers1} headers")
    print(f"  Repo 2: {headers2} headers")
    print(f"  Expected: 25 headers (5 modules × 5 headers)")

    if headers1 == headers2 == 25:
        print("\n✅ PASS: No cache contamination detected")
        print("   Both repos returned correct, identical results")
        sys.exit(0)
    elif headers1 != headers2:
        print(f"\n❌ FAIL: CACHE CONTAMINATION DETECTED!")
        print(f"   Repo 1 and Repo 2 returned different results")
        print(f"   This indicates cache is leaking between repository instances")
        sys.exit(1)
    elif headers1 != 25 or headers2 != 25:
        print(f"\n❌ FAIL: WRONG HEADER COUNT")
        print(f"   Expected 25 headers, got {headers1} and {headers2}")
        print(f"   This indicates cache is returning stale/incorrect data")
        sys.exit(1)
    else:
        print("\n⚠️  UNEXPECTED: Both got same wrong count")
        sys.exit(1)
