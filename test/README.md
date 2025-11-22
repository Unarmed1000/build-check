# BuildCheck Test Suite

This directory contains comprehensive tests for the BuildCheck scripts and library modules.

## Test Organization

### Library Module Tests
Tests for shared functionality in the `lib/` directory:

- **test_lib_ninja_utils.py** - Tests for `lib.ninja_utils`
  - `normalize_reason()` - Rebuild reason normalization
  - `extract_rebuild_info()` - Ninja rebuild analysis
  - `get_dependencies()` - Dependency extraction
  - `check_ninja_available()` - Ninja availability check
  - `validate_build_directory()` - Build directory validation

- **test_lib_library_parser.py** - Tests for `lib.library_parser`
  - `parse_ninja_libraries()` - Library dependency parsing
  - `compute_library_metrics()` - Library metrics calculation
  - `find_library_cycles()` - Circular dependency detection

- **test_lib_git_utils.py** - Tests for `lib.git_utils`
  - `find_git_repo()` - Git repository location
  - `get_changed_files_from_commit()` - Changed file detection
  - `categorize_changed_files()` - File categorization

### Main Script Tests
Integration tests for the main BuildCheck scripts:

- **test_buildCheckSummary.py** - Tests for `buildCheckSummary.py`
- **test_buildCheckImpact.py** - Tests for `buildCheckImpact.py`
- **test_buildCheckRippleEffect.py** - Tests for `buildCheckRippleEffect.py`
- **test_buildCheckOptimize.py** - Tests for `buildCheckOptimize.py`

### Security Tests
- **test_path_security.py** - Path traversal and security tests

## Requirements

```bash
pip install pytest pytest-cov pytest-mock GitPython scipy
```

Or install all test requirements at once:

```bash
pip install -r test/requirements-test.txt
```

## Test Fixtures

### Fixture Organization

Test fixtures are organized by domain in separate conftest files:

#### Base Fixtures (`conftest.py`)
- `temp_dir` - Temporary directory for file I/O
- `mock_build_dir` - Mock ninja build directory
- `mock_compile_commands` - Mock compilation database
- `mock_source_files` - Mock C++ source/header files
- `mock_git_repo` - Mock git repository with history

#### DSM Fixtures (`conftest_dsm.py`)
- `mock_dsm_graph_simple` - 5 nodes, 1 cycle
- `mock_dsm_graph_medium` - 20 nodes, 3 cycles
- `mock_dsm_graph_complex` - 100 nodes, 8 cycles
- `mock_dsm_metrics_*` - Corresponding metrics for each graph
- `mock_dsm_analysis_results_*` - Complete analysis results
- `mock_dsm_delta` - Differential analysis delta

#### Graph Fixtures (`conftest_graph.py`)
- `sample_dependency_graph_simple` - Linear chain
- `sample_dependency_graph_medium` - Tree with 15 nodes
- `sample_dependency_graph_complex` - DAG with 50 nodes
- `mock_cycles_simple` - Single 3-node cycle
- `mock_cycles_complex` - Multiple nested cycles
- `mock_topological_layers` - Layer assignments

#### Library Fixtures (`conftest_library.py`)
- `mock_library_mapping_simple` - 3 libraries, 10 headers
- `mock_library_mapping_medium` - 10 libraries, 50 headers
- `mock_library_mapping_complex` - 25 libraries, 200 headers
- `mock_ninja_libraries` - Library link dependencies
- `mock_library_boundaries` - Boundary violations
- `mock_cross_library_deps` - Cross-library edges

### Fixture Complexity Levels

Fixtures provide three complexity levels for comprehensive testing:

- **Simple**: 5-10 nodes, 1-2 cycles, < 50ms execution
  - Use for: Basic functionality, edge cases, error handling
  - Example: `mock_dsm_graph_simple`

- **Medium**: 15-25 nodes, 3-5 cycles, < 200ms execution
  - Use for: Realistic scenarios, integration testing
  - Example: `mock_dsm_graph_medium`

- **Complex**: 50-200 nodes, 5-10 cycles, < 1s execution
  - Use for: Performance testing, stress testing, scalability
  - Example: `mock_dsm_graph_complex`

### Parametrized Fixtures

Use parametrized fixtures to test across all complexity levels:

```python
def test_with_all_complexities(mock_dsm_graph_parametrized):
    """Test runs 3 times: simple, medium, complex"""
    assert mock_dsm_graph_parametrized.number_of_nodes() > 0
```

### Fixture Scopes

Fixtures use appropriate scopes for performance:

- `scope='function'` (default): Recreated for each test
- `scope='module'`: Shared across tests in one file
- `scope='session'`: Shared across entire test run

Complex fixtures use `scope='module'` to avoid expensive recreation.

## Coverage Requirements

### Overall Target: 85%

Per-module coverage goals:

- **Tier 1 (95%)**: Utilities
  - `lib/file_utils.py`
  - `lib/color_utils.py`
  - `lib/export_utils.py`

- **Tier 2 (90%)**: Core Libraries
  - `lib/graph_utils.py`
  - `lib/dependency_utils.py`
  - `lib/clang_utils.py`
  - `lib/ninja_utils.py`
  - `lib/git_utils.py`

- **Tier 3 (85%)**: Analysis Modules
  - `lib/dsm_analysis.py`
  - `lib/library_parser.py`

### Running with Coverage

```bash
# Run tests with coverage
pytest test/ --cov=lib

# Generate HTML report
pytest test/ --cov=lib --cov-report=html
open htmlcov/index.html

# Check specific module
pytest test/test_lib_file_utils.py --cov=lib.file_utils --cov-report=term-missing

# Fail if coverage below 85%
pytest test/ --cov=lib --cov-fail-under=85
```

### Coverage Configuration

Coverage settings are in:
- `.coveragerc` - Main coverage configuration
- `pytest.ini` - Pytest integration

Excluded from coverage:
- `pragma: no cover` comments
- Type checking blocks (`if TYPE_CHECKING:`)
- Abstract methods
- `__repr__` and `__str__` methods
- Unreachable code (`if False:`, `if 0:`)

## Requirements

```bash
pip install pytest pytest-cov pytest-mock GitPython scipy
```

Or install all test requirements at once:

```bash
pip install -r test/requirements-test.txt
```

## Running Tests

### Run all tests
```bash
cd BuildCheck
pytest test/
```

### Run with coverage report
```bash
pytest test/ --cov=. --cov-report=html
```

### Run specific test file
```bash
pytest test/test_buildCheckSummary.py -v
```

### Run tests matching a pattern
```bash
pytest test/ -k "security" -v
```

### Run only security tests
```bash
pytest test/test_path_security.py -v
```

## Test Structure

- `conftest.py` - Pytest fixtures and shared test utilities
- `test_lib_ninja_utils.py` - Library tests for ninja utilities
- `test_lib_library_parser.py` - Library tests for library parsing
- `test_lib_git_utils.py` - Library tests for git utilities
- `test_buildCheckSummary.py` - Integration tests for buildCheckSummary.py
- `test_buildCheckImpact.py` - Integration tests for buildCheckImpact.py
- `test_buildCheckRippleEffect.py` - Integration tests for buildCheckRippleEffect.py
- `test_buildCheckOptimize.py` - Integration tests for buildCheckOptimize.py
- `test_path_security.py` - Security tests for path traversal protection

## Test Categories

### Unit Tests
Individual function and method tests with mocked dependencies.

### Integration Tests
End-to-end tests with mock build directories and git repositories.

### Security Tests
Path traversal, symlink attacks, and input validation tests.

## Fixtures

### `temp_dir`
Creates a temporary directory for tests, automatically cleaned up.

### `mock_build_dir`
Creates a mock ninja build directory with build.ninja file.

### `mock_compile_commands`
Creates a mock compile_commands.json file.

### `mock_source_files`
Creates mock C++ source and header files.

### `mock_git_repo`
Creates a mock git repository with commits.

## Adding New Tests

1. Create a new test file: `test_buildCheckNewFeature.py`
2. Import the module to test
3. Use fixtures from `conftest.py`
4. Follow the existing test patterns

Example:
```python
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckNewFeature


class TestNewFeature:
    def test_something(self, mock_build_dir):
        result = buildCheckNewFeature.do_something(mock_build_dir)
        assert result is not None
```

## Continuous Integration

These tests are designed to run in CI/CD environments. They:
- Don't require actual C++ build tools (mocked)
- Clean up temporary files automatically
- Skip tests when dependencies are unavailable
- Provide clear error messages

## Coverage Goals

- Aim for >80% code coverage
- 100% coverage for security-critical code paths
- All error handling paths should be tested

## Known Limitations

- Tests requiring `clang-scan-deps` are skipped if not available
- Tests requiring `git` are skipped if not available
- Some integration tests may fail on Windows due to path handling
