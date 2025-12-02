# Cache Isolation Test Implementation Summary

## Problem Identified

The scenario 9 test in `test_git_scenario_equivalence.py` was exhibiting flaky behavior:
- **First run (cache miss)**: 25 headers found ✅ CORRECT
- **Second run (cache hit)**: 23 headers found ❌ INCORRECT  
- **Coupling calculation**: DSM-direct=8, Git-based=-2 (mismatch)

## Root Cause

Potential cache contamination where:
1. Cache from one test repository instance leaks into another
2. Cache keys don't properly isolate different repository paths
3. Stale cache data persists across test runs

## Implementation

### 1. Created Comprehensive Test Suite
**File**: `test/test_clang_cache_repo_isolation.py`

Six critical tests to catch caching bugs:

#### `test_different_repos_get_independent_cache_directories()`
- Verifies each repo has its own `.buildcheck_cache/` directory
- Ensures cache files are at different absolute paths
- **Purpose**: Fundamental isolation requirement

#### `test_cache_doesnt_leak_between_repo_instances()` ⭐ CRITICAL
- Creates two separate repos with same scenario but different paths
- Verifies both return identical correct results (25 headers)
- **Catches**: The exact bug seen in scenario 9 test failure
- **Regression test** for: "Cache miss shows 25 headers, cache hit shows 23 headers"

#### `test_same_repo_multiple_scans_produces_consistent_results()`
- Scans same repo 3 times consecutively  
- Verifies all scans return identical results
- **Catches**: Cache state changing between invocations

#### `test_cache_properly_invalidates_on_file_changes()`
- Adds new files to repo after initial scan
- Verifies cache invalidates and detects new files
- **Catches**: Stale cache serving old data

#### `test_cache_isolation_with_different_scenarios()`
- Creates repos for scenarios 8 and 9 in same temp dir
- Verifies each gets independent cache
- **Catches**: Cross-scenario cache contamination

#### `test_cache_path_includes_build_dir()`
- Unit test for `get_cache_path()` function
- Verifies different build_dirs produce different cache paths
- **Catches**: Cache path construction bugs

### 2. Enhanced Debug Logging

#### In `lib/clang_utils.py`:
```python
# Line ~1170: Log cache path on creation
logger.debug("Cache path: %s for build_dir: %s", cache_path, build_dir)

# Line ~1221: Log cache save location
logger.debug("Saved cache to: %s (build_dir: %s)", cache_path, build_dir)
```

#### In `lib/cache_utils.py`:
```python
# Line ~226: Log cache hit with filtered_db path
logger.debug("Cache hit: %s (filtered_db: %s)", cache_path, filtered_db_path)
```

### 3. Enhanced Test Logging in test_git_scenario_equivalence.py

Already implemented baseline reconstruction logging that shows:
- Working tree header count
- Baseline (HEAD) header count  
- Source file count
- Project root
- Sample headers and graph edges

## How to Use

### Run the cache isolation tests:
```bash
cd /home/dev/code/build-check
python -m pytest test/test_clang_cache_repo_isolation.py -v -s
```

### Run with debug logging:
```bash
python -m pytest test/test_clang_cache_repo_isolation.py -v -s --log-cli-level=DEBUG
```

### Check specific failing test:
```bash
python -m pytest test/test_clang_cache_repo_isolation.py::TestCacheRepoIsolation::test_cache_doesnt_leak_between_repo_instances -xvs
```

## Expected Behavior

All tests should **PASS**, confirming:
1. ✅ Each repo gets its own cache directory
2. ✅ No cross-contamination between repo instances
3. ✅ Consistent results across multiple scans
4. ✅ Proper cache invalidation on file changes
5. ✅ No cross-scenario contamination
6. ✅ Cache paths properly include build_dir

## If Tests Fail

### Cache contamination detected:
- Check if cache is being stored globally instead of per-repo
- Verify `CACHE_DIR` constant is `.buildcheck_cache` (repo-local)
- Check if cache keys include absolute repo path

### Inconsistent scan results:
- May indicate module-level caching (e.g., `@lru_cache` decorators)
- Check for global state in clang_utils or ninja_utils
- Verify cache validation logic in `is_cache_valid()`

### Wrong header count:
- Scenario 9 MUST return exactly 25 headers (5 modules × 5 headers)
- If getting 23 or 20, cache is returning stale/wrong data
- Check `reconstruct_head_graph()` for git HEAD vs disk confusion

## Key Files Modified

1. **test/test_clang_cache_repo_isolation.py** - New comprehensive test suite
2. **lib/clang_utils.py** - Enhanced cache path logging
3. **lib/cache_utils.py** - Enhanced cache hit/miss logging
4. **test/test_git_scenario_equivalence.py** - Already has baseline reconstruction logging

## Verification

The cache isolation tests serve as:
- **Regression tests**: Catch if the bug reappears
- **Documentation**: Show expected cache behavior
- **Debug tool**: Logging helps diagnose cache issues

## Architecture Notes

Current cache design:
- Cache stored in `{repo_path}/.buildcheck_cache/`
- Cache filename: `clang_scan_deps_output.pickle` (constant)
- Cache key: Based on filtered_db mtime/size + build.ninja mtime
- **Isolation**: Achieved through per-repo cache directory

This design SHOULD provide proper isolation if:
1. Each repo has unique absolute path ✅
2. Cache path uses `build_dir` (repo path) ✅  
3. No global/module-level caching interferes ❓

The tests will reveal if assumption #3 holds.
