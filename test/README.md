# BuildCheck Test Suite

This directory contains integration and security tests for the BuildCheck tools.

## Requirements

```bash
pip install pytest pytest-cov
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
- `test_buildCheckSummary.py` - Tests for buildCheckSummary.py
- `test_buildCheckImpact.py` - Tests for buildCheckImpact.py
- `test_buildCheckRippleEffect.py` - Tests for buildCheckRippleEffect.py
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
