# buildCheck Library Modules

This directory contains shared library modules for the buildCheck suite of C/C++ build analysis tools.

## Overview

The `lib/` directory provides reusable functionality that was previously duplicated across multiple buildCheck scripts. By extracting common code into these modules, we improve:

- **Maintainability**: Changes to shared functionality only need to be made in one place
- **Consistency**: All tools use the same implementations for common operations
- **Testability**: Library modules can be tested independently
- **Reusability**: Other projects can use these modules

**Module Count**: 20 modules (15 production, 5 testing/scenario modules)

## Modules

### Core Modules

### `ninja_utils.py`
Utilities for interacting with the Ninja build system.

**Key Functions:**
- `check_ninja_available()`: Check if ninja is installed
- `validate_build_directory()`: Validate build directory structure
- `run_ninja_explain()`: Run ninja explain for rebuild analysis
- `parse_ninja_explain_output()`: Parse ninja explain output
- `extract_rebuild_info()`: Extract complete rebuild information
- `normalize_reason()`: Normalize rebuild reasons to user-friendly strings
- `get_dependencies()`: Get dependencies for a target using `ninja -t deps`
- `generate_compile_commands()`: Generate compile_commands.json

**Constants:**
- `RE_NINJA_EXPLAIN`: Regex for parsing ninja explain output
- `EXIT_SUCCESS`, `EXIT_INVALID_ARGS`, etc.: Exit codes

### `clang_utils.py`
Utilities for using clang-scan-deps and analyzing C/C++ dependencies.

**Key Functions:**
- `find_clang_scan_deps()`: Find available clang-scan-deps executable
- `is_valid_source_file()`: Check if file is C/C++ source
- `is_valid_header_file()`: Check if file is C/C++ header
- `is_system_header()`: Check if header is system header
- `create_filtered_compile_commands()`: Create filtered compile_commands.json
- `extract_include_paths()`: Extract -I paths from compile commands
- `run_clang_scan_deps()`: Run clang-scan-deps to analyze dependencies
- `parse_clang_scan_deps_output()`: Parse makefile-style output
- `compute_transitive_deps()`: Compute transitive dependencies recursively

**Constants:**
- `CLANG_SCAN_DEPS_COMMANDS`: List of clang-scan-deps versions to try
- `VALID_SOURCE_EXTENSIONS`, `VALID_HEADER_EXTENSIONS`: File extensions
- `SYSTEM_PATH_PREFIXES`: System header path prefixes

### `graph_utils.py`
Graph utilities for dependency analysis using NetworkX.

**Key Functions:**
- `build_dependency_graph()`: Build NetworkX DiGraph from include graph
- `find_strongly_connected_components()`: Find cycles in graph
- `compute_topological_layers()`: Compute dependency layers
- `compute_transitive_closure()`: Get all reachable nodes
- `compute_reverse_transitive_closure()`: Get all nodes that reach target
- `build_transitive_dependents_map()`: Build reverse dependency map
- `compute_fan_in_fan_out()`: Calculate in/out degree for nodes
- `find_hub_nodes()`: Find highly connected nodes
- `compute_betweenness_centrality()`: Calculate centrality metrics
- `export_graph_to_graphml()`: Export to GraphML format
- `export_graph_to_dot()`: Export to DOT format for Graphviz

**Note:** Requires `networkx` package. Gracefully degrades if not available.

### `library_parser.py`
Parser for build.ninja to extract library dependency information.

**Key Functions:**
- `parse_ninja_libraries()`: Parse build.ninja for library/executable dependencies
- `compute_library_metrics()`: Calculate fan-in, fan-out, depth, transitive dependents
- `find_unused_libraries()`: Find libraries not used by any target
- `find_library_cycles()`: Find circular library dependencies
- `infer_library_from_path()`: Infer library name from file path

**Returns:**
- Library → Library dependency mappings
- Executable → Library dependency mappings
- Metrics for each library

### `git_utils.py`
Utilities for Git operations using GitPython library.

**Dependencies:**
- GitPython >= 3.1.40

**Key Functions:**
- `find_git_repo()`: Find git repository root
- `check_git_available()`: Check if git is installed
- `get_changed_files_from_commit()`: Get changed files from commit/range
- `get_staged_files()`: Get staged files ready to commit
- `get_uncommitted_changes()`: Get uncommitted file changes
- `get_current_branch()`: Get current branch name
- `get_commit_hash()`: Get full commit hash
- `categorize_changed_files()`: Categorize files into headers/sources/other
- `get_file_history()`: Get commit history for a file
- `is_ancestor()`: Check if one commit is ancestor of another
- `get_working_tree_changes_from_commit()`: Get all changes from commit to working tree

**Supports:**
- Single commits: `HEAD`, `abc123`
- Commit ranges: `HEAD~5..HEAD`
- Uncommitted changes (staged and unstaged)
- Security: Path traversal protection for all file operations

### `cache_utils.py`
Caching utilities for expensive operations.

**Key Functions:**
- `compute_hash()`: Compute hash of file or directory contents
- `is_cache_valid()`: Check if cached result is still valid
- `save_to_cache()`: Save analysis results to cache file
- `load_from_cache()`: Load cached analysis results
- `clear_cache()`: Clear expired cache entries

**Features:**
- Timestamp-based cache validation
- Content hashing for integrity checking
- Automatic cache expiration
- JSON serialization for complex data structures

**Use Cases:**
- Caching clang-scan-deps results (expensive operation)
- Storing dependency graph computations
- Reusing analysis results across tool runs

### `dsm_analysis.py`
Comprehensive DSM (Dependency Structure Matrix) analysis functions.

**Key Functions:**
- `run_dsm_analysis()`: Complete DSM analysis with metrics, cycles, layers
- `display_analysis_results()`: Format and display DSM results
- `compare_dsm_results()`: Compare two DSM analyses (differential analysis)
- `run_differential_analysis()`: Compare DSMs from two build directories
- `run_differential_analysis_with_baseline()`: Compare with saved baseline
- `run_git_working_tree_analysis()`: Analyze uncommitted git changes
- `run_proactive_improvement_analysis()`: Identify refactoring opportunities (NEW v1.2.0)
- `identify_improvement_candidates()`: Detect anti-patterns
- `estimate_improvement_roi()`: Calculate ROI for refactoring
- `rank_improvements_by_impact()`: Priority ranking
- `calculate_matrix_statistics()`: Compute sparsity, coupling, quality scores
- `compute_ripple_impact()`: Estimate rebuild impact of changes

**Features:**
- Circular dependency detection with SCC analysis
- Layered architecture computation
- Coupling metrics (fan-in, fan-out, stability)
- Architectural quality scoring (0-100)
- Statistical analysis (mean, median, percentiles, outliers)
- Precise transitive closure for rebuild predictions
- ROI-based improvement recommendations

**Metrics:**
- Architecture quality score (sparsity, cycles, coupling, stability)
- ADP score (Acyclic Dependencies Principle compliance)
- Interface ratio (percentage of stable interfaces)
- PageRank and betweenness centrality

### `dsm_serialization.py`
Save and load DSM analysis results for baseline comparison.

**Key Functions:**
- `save_dsm_results()`: Save DSM to compressed JSON (gzip)
- `load_dsm_results()`: Load DSM from saved file
- `validate_baseline()`: Check baseline compatibility

**Features:**
- Compressed storage (~200-500KB for 1000 headers)
- Metadata tracking (build dir, filters, timestamp)
- Version compatibility checking
- Cross-platform path normalization

**Use Cases:**
- Save baseline for later comparison
- Flexible comparison workflows
- CI/CD architectural regression testing

### `dsm_types.py`
Type definitions and dataclasses for DSM analysis.

**Key Classes:**
- `MatrixStatistics`: DSM matrix stats (sparsity, coupling, quality)
- `DSMAnalysisResults`: Complete analysis results container
- `DSMDelta`: Differences between two DSM analyses
- `CouplingStatistics`: Statistical coupling analysis
- `CycleComplexityStats`: Cycle analysis results
- `StabilityChange`: Stability threshold crossings
- `RippleImpactAnalysis`: Build impact assessment
- `ArchitecturalInsights`: Comprehensive change analysis
- `FutureRebuildPrediction`: Rebuild reduction predictions
- `LayerMovementStats`: Layer depth changes
- `ImprovementCandidate`: Refactoring opportunity (NEW v1.2.0)

**Features:**
- Type safety with dataclasses
- Comprehensive architectural metrics
- Severity classification support

### `export_utils.py`
Export utilities for analysis results.

**Key Functions:**
- `export_dsm_to_csv()`: Export DSM matrix to CSV
- `export_dependency_graph()`: Export graph to GraphML/DOT/GEXF/JSON
- `export_library_graph()`: Export library dependencies
- `format_json_output()`: Format results as JSON
- `generate_html_report()`: Create HTML visualization

**Supported Formats:**
- CSV: Spreadsheet analysis
- GraphML: Gephi, yEd, Cytoscape
- DOT: Graphviz visualization
- GEXF: Gephi format
- JSON: Custom tools, D3.js

**Features:**
- Relative path normalization
- Metadata embedding
- Library/module grouping
- Centrality metrics inclusion

### `file_utils.py`
File system utilities and filtering.

**Key Functions:**
- `filter_headers_by_pattern()`: Glob-based header filtering
- `exclude_headers_by_patterns()`: Exclude patterns
- `filter_system_headers()`: Remove system headers
- `cluster_headers_by_directory()`: Group by directory
- `normalize_path()`: Cross-platform path normalization
- `find_project_root()`: Detect project root directory

**Classes:**
- `FilterStatistics`: Track filtering operations

**Features:**
- Glob pattern support (*, **, ?)
- System header detection (/usr/*, /lib/*, /opt/*)
- Statistics tracking
- Progress indicators for large datasets

### `package_verification.py`
Dependency version checking and validation.

**Key Functions:**
- `check_python_version()`: Verify Python version
- `check_package_version()`: Check package version
- `verify_all_dependencies()`: Verify all requirements
- `suggest_installation()`: Installation suggestions

**Features:**
- Version comparison (semantic versioning)
- Graceful degradation for optional packages
- User-friendly error messages
- Installation instructions

### `scenario_creators.py`
Test scenario creation for DSM testing (internal).

**Key Functions:**
- `create_test_headers()`: Generate test header files
- `create_cycle_scenario()`: Create circular dependency scenario
- `create_layer_scenario()`: Create layered architecture
- `create_coupling_scenario()`: Create high-coupling scenario

**Use Cases:**
- Unit testing DSM analysis
- Demo script generation
- Regression testing

### `scenario_definitions.py`
Architectural scenario definitions for testing (internal).

**Defines:**
- 10 architectural scenarios (baseline, cycles, coupling, etc.)
- Expected outcomes for each scenario
- Test data structures

### `scenario_git_utils.py`
Git scenario utilities for testing (internal).

**Key Functions:**
- `create_git_scenario()`: Create git repository with scenario
- `apply_scenario_changes()`: Apply changes to git repo
- `commit_scenario()`: Commit scenario changes

### `scenario_test_utils.py`
Testing utilities for scenario validation (internal).

**Key Functions:**
- `validate_scenario_output()`: Check analysis results
- `compare_scenarios()`: Compare scenario outcomes

### `color_utils.py`
Colorama wrapper utilities for colored terminal output.

**Key Classes:**
- `Colors`: Color and style constants (with fallback if colorama unavailable)

**Key Functions:**
- `colored()`: Return colored text string
- `print_colored()`: Print colored text
- `print_success()`, `print_error()`, `print_warning()`, `print_info()`: Convenience functions
- `is_color_supported()`: Check if colorama is available
- `should_use_color()`: Determine if color should be used (checks TTY, env vars)
- `get_severity_color()`: Get color for severity level
- `print_severity()`: Print with severity-appropriate coloring
- `format_table_row()`: Format colored table row
- `progress_bar()`: Create colored progress bar

**Severity Levels:**
- `critical`: Red + bright
- `high`: Red
- `moderate`: Yellow
- `low`: Green
- `info`: Cyan

**Environment Support:**
- Respects `NO_COLOR` environment variable
- Detects TTY for automatic color disabling
- Graceful fallback if colorama not installed

### `dependency_utils.py`
Utilities for analyzing header cooccurrence and dependency relationships.

**Key Functions:**
- `compute_header_cooccurrence()`: Compute cooccurrence matrix for headers appearing together
  - Analyzes how often headers appear together in compilation units
  - Supports both full matrix and targeted analysis for specific headers
  - High cooccurrence indicates dependency relationships (direct or transitive)
  - Returns `Dict[str, Dict[str, int]]` mapping header -> (header -> cooccurrence_count)

- `find_dependency_fanout()`: Targeted fanout analysis for specific problematic headers
  - Optimized version for analyzing which headers are frequently pulled in with specific targets
  - Used by buildCheckDependencyHell.py to understand header coupling patterns
  - Takes custom filter functions for header/system detection
  - Returns cooccurrence counts for target headers only

- `compute_header_cooccurrence_from_deps_lists()`: Convenience wrapper with progress tracking
  - Same as compute_header_cooccurrence but with built-in progress logging for large analyses
  - Useful when processing many build targets

**Use Cases:**
- Finding coupling patterns between headers
- Identifying "gateway" headers that pull in many others
- Understanding transitive dependencies through cooccurrence patterns
- Analyzing fanout (which headers are frequently pulled in together)

**Examples:**
```python
from lib.dependency_utils import compute_header_cooccurrence

# Compute full cooccurrence matrix
cooccur = compute_header_cooccurrence(
    source_to_deps, 
    is_header_filter=lambda p: p.endswith('.h'),
    is_system_filter=lambda p: p.startswith('/usr/')
)

# Targeted analysis for specific headers only
problematic = ['foo.h', 'bar.h']
cooccur = compute_header_cooccurrence(
    source_to_deps,
    is_header_filter=lambda p: p.endswith('.h'),
    is_system_filter=lambda p: p.startswith('/usr/'),
    target_headers=problematic
)

# Fanout analysis (high-level API for dependency analysis)
from lib.dependency_utils import find_dependency_fanout
fanout = find_dependency_fanout(
    build_dir, rebuild_targets, ['problematic.h'],
    source_to_deps,
    is_header_filter=lambda p: p.endswith('.h'),
    is_system_filter=lambda p: p.startswith('/usr/')
)
# Returns which headers frequently appear with 'problematic.h'
print(fanout['problematic.h'])  # {'other.h': 42, 'another.h': 15, ...}

# With progress tracking
from lib.dependency_utils import compute_header_cooccurrence_from_deps_lists
cooccur = compute_header_cooccurrence_from_deps_lists(
    deps_by_target,
    is_header_filter=lambda p: p.endswith('.h'),
    is_system_filter=lambda p: p.startswith('/usr/'),
    show_progress=True
)
```

## Usage Examples

### Using ninja_utils
```python
from lib.ninja_utils import validate_build_directory, run_ninja_explain

build_dir = validate_build_directory("/path/to/build")
result = run_ninja_explain(build_dir)
rebuild_targets, changed_files = parse_ninja_explain_output(result.stderr.splitlines())
```

### Using clang_utils
```python
from lib.clang_utils import find_clang_scan_deps, create_filtered_compile_commands

clang_cmd = find_clang_scan_deps()
if clang_cmd:
    filtered_db = create_filtered_compile_commands(build_dir)
    stdout, elapsed = run_clang_scan_deps(build_dir, filtered_db)
```

### Using graph_utils
```python
from lib.graph_utils import build_dependency_graph, find_strongly_connected_components

graph = build_dependency_graph(include_graph, all_headers)
cycles = find_strongly_connected_components(graph)
print(f"Found {len(cycles)} circular dependencies")
```

### Using library_parser
```python
from lib.library_parser import parse_ninja_libraries, compute_library_metrics

lib_to_libs, exe_to_libs, all_libs, all_exes = parse_ninja_libraries(build_ninja_path)
metrics = compute_library_metrics(lib_to_libs, exe_to_libs, all_libs)
```

### Using git_utils
```python
from lib.git_utils import find_git_repo, get_changed_files_from_commit

repo_dir = find_git_repo(os.getcwd())
changed_files, commit_desc = get_changed_files_from_commit(repo_dir, "HEAD")
```

### Using color_utils
```python
from lib.color_utils import print_success, print_error, Colors, colored

print_success("Build completed successfully!")
print_error("Failed to compile")

# Manual coloring
text = colored("Warning:", Colors.YELLOW, Colors.BRIGHT) + " File not found"
print(text)
```

## Migrating Existing Scripts

To migrate a buildCheck script to use these libraries:

1. **Import the modules:**
   ```python
   from lib.ninja_utils import extract_rebuild_info
   from lib.clang_utils import find_clang_scan_deps
   from lib.color_utils import Colors, print_success
   ```

2. **Replace direct code with library calls:**
   - Replace inline ninja command execution → `ninja_utils.run_ninja_explain()`
   - Replace colorama imports → `from lib.color_utils import Colors`
   - Replace git operations → `git_utils.get_changed_files_from_commit()`

3. **Update imports in other scripts that depend on your script:**
   - If other scripts import functions from your script, they should now import from `lib.*` instead

4. **Remove duplicate code:**
   - Delete inline implementations now available in lib modules

## Dependencies

**Required:**
- Python 3.7+

**Optional (for full functionality):**
- `networkx`: Graph analysis features (`pip install networkx`)
- `colorama`: Colored terminal output (`pip install colorama`)
- `ninja`: Build system (system package)
- `clang-scan-deps`: Dependency scanning (part of clang/LLVM)
- `git`: Version control (system package)

The library modules gracefully degrade when optional dependencies are unavailable.

## Testing

Each module can be tested independently. Example:

```bash
# Test ninja_utils
python3 -c "from lib.ninja_utils import check_ninja_available; print(check_ninja_available())"

# Test clang_utils
python3 -c "from lib.clang_utils import find_clang_scan_deps; print(find_clang_scan_deps())"

# Test color_utils
python3 -c "from lib.color_utils import print_success; print_success('Test passed!')"
```

## Design Principles

1. **Single Responsibility**: Each module has a focused purpose
2. **Fail Gracefully**: Handle missing dependencies elegantly
3. **Logging**: Use Python logging for debug/info messages
4. **Type Hints**: All functions have type annotations
5. **Documentation**: Comprehensive docstrings for all public functions
6. **Error Handling**: Proper exception handling with informative messages

## Module Summary

**Production Modules** (15):
- Core utilities: `ninja_utils`, `clang_utils`, `git_utils`, `color_utils`, `constants`
- Analysis: `dsm_analysis`, `graph_utils`, `dependency_utils`, `library_parser`
- Data structures: `dsm_types`, `dsm_serialization`
- I/O: `export_utils`, `file_utils`, `cache_utils`, `package_verification`

**Testing/Scenario Modules** (5):
- `scenario_creators`, `scenario_definitions`, `scenario_git_utils`, `scenario_test_utils`
- Used by demo scripts and test suite

## Contributing

When adding shared functionality:

1. Choose the appropriate module or create a new one
2. Add comprehensive docstrings
3. Include type hints
4. Handle errors gracefully
5. Add logging where appropriate
6. Update this README

## License

Same as buildCheck tools (BSD 3-Clause License).
