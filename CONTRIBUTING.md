# Contributing to BuildCheck

Thank you for your interest in contributing to BuildCheck! This document provides guidelines and information for contributors.

## Table of Contents

1. [Code of Conduct](#code-of-conduct)
2. [Getting Started](#getting-started)
3. [Development Setup](#development-setup)
4. [Project Structure](#project-structure)
5. [Coding Standards](#coding-standards)
6. [Testing](#testing)
7. [Pull Request Process](#pull-request-process)
8. [Release Process](#release-process)

## Code of Conduct

This project adheres to a code of conduct that all contributors are expected to follow:

- Be respectful and inclusive
- Focus on constructive feedback
- Prioritize the project's goals and user needs
- Help create a welcoming environment for all contributors

## Getting Started

### Prerequisites

- Python 3.7 or higher
- ninja build system
- clang-19 or clang-18 (for tools using clang-scan-deps)
- git

### Development Dependencies

```bash
# Install runtime dependencies
pip install networkx colorama

# Install development dependencies
pip install -r test/requirements-test.txt

# This includes:
# - pytest (testing framework)
# - pytest-cov (coverage reporting)
# - pytest-mock (mocking support)
# - mypy (type checking)
```

## Development Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/Unarmed1000/build-check.git
   cd build-check
   ```

2. **Set up your environment**
   ```bash
   # Make scripts executable
   chmod +x *.py
   chmod +x test/*.sh
   
   # Verify tools are available
   ninja --version
   clang-scan-deps --version
   python3 --version
   ```

3. **Run tests to verify setup**
   ```bash
   cd test
   ./run_tests.sh
   ```

## Project Structure

```
build-check/
├── buildCheck*.py          # Main tool scripts
├── lib/                    # Shared library modules
│   ├── clang_utils.py     # Clang-scan-deps utilities
│   ├── ninja_utils.py     # Ninja build system utilities
│   ├── git_utils.py       # Git integration utilities
│   ├── graph_utils.py     # NetworkX graph utilities
│   ├── dependency_utils.py # Dependency analysis
│   ├── color_utils.py     # Terminal color output
│   ├── constants.py       # Shared constants
│   └── ...
├── test/                   # Test suite
│   ├── test_*.py          # Unit and integration tests
│   ├── conftest.py        # Pytest fixtures
│   ├── run_tests.sh       # Test runner script
│   └── ...
├── demo/                   # Demo scripts and documentation
│   ├── demo_*.py          # Demo scripts
│   ├── EXAMPLES.md        # Usage examples
│   └── DEMO_SUMMARY.md    # Demo summaries
├── README*.md              # Documentation
└── LICENSE                 # BSD 3-Clause License
```

### Key Design Principles

1. **Modularity**: Shared functionality lives in `lib/`, tools import from there
2. **Type Safety**: All new code should use type hints
3. **Error Handling**: Comprehensive error handling with helpful messages
4. **Testing**: All new features require tests
5. **Documentation**: User-facing tools need clear docstrings and examples

## Coding Standards

### Python Style

We follow PEP 8 with some project-specific conventions:

```python
# Type hints are required
def analyze_dependencies(build_dir: str, threshold: int = 50) -> Dict[str, int]:
    """Analyze build dependencies.
    
    Args:
        build_dir: Path to ninja build directory
        threshold: Minimum dependency count to report
        
    Returns:
        Dictionary mapping headers to dependency counts
        
    Raises:
        ValueError: If build_dir is invalid
        RuntimeError: If analysis fails
    """
    pass

# Use descriptive variable names
header_dependency_count = {}  # Good
hdc = {}                      # Bad

# Constants in UPPER_CASE
DEFAULT_THRESHOLD = 50
MAX_DISPLAY_ITEMS = 100

# Private functions start with _
def _internal_helper(data: List[str]) -> Set[str]:
    """Private helper function."""
    pass
```

### Type Checking

All code must pass mypy type checking:

```bash
# Run type checker
cd test
bash run_mypy.sh

# Should output: Success: no issues found
```

### Documentation Standards

#### Docstrings

Use Google-style docstrings:

```python
def compute_transitive_deps(
    graph: nx.DiGraph,
    node: str,
    cache: Optional[Dict[str, Set[str]]] = None
) -> Set[str]:
    """Compute all transitive dependencies of a node.
    
    This function uses NetworkX to efficiently compute the transitive
    closure (all descendants) of a given node in the dependency graph.
    Results can be cached for performance.
    
    Args:
        graph: NetworkX directed graph of dependencies
        node: Starting node to analyze
        cache: Optional cache dictionary for memoization
        
    Returns:
        Set of all nodes reachable from the starting node
        
    Raises:
        ValueError: If node is not in graph
        NetworkXError: If graph contains cycles
        
    Example:
        >>> G = nx.DiGraph([('a', 'b'), ('b', 'c')])
        >>> compute_transitive_deps(G, 'a')
        {'b', 'c'}
    """
    pass
```

#### Comments

- Use comments for complex algorithms or non-obvious behavior
- Prefer self-documenting code over excessive comments
- Document "why" not "what"

```python
# Good - explains reasoning
# Use realpath to resolve symlinks and prevent path traversal attacks
build_dir = os.path.realpath(build_dir)

# Bad - states the obvious
# Get the real path of build_dir
build_dir = os.path.realpath(build_dir)
```

### Error Handling

Always provide helpful error messages:

```python
# Good
if not os.path.isdir(build_dir):
    raise ValueError(
        f"Build directory not found: {build_dir}\n"
        f"Tip: Ensure you've run CMake to generate the build directory:\n"
        f"  cmake -G Ninja -B ./build"
    )

# Bad
if not os.path.isdir(build_dir):
    raise ValueError("Invalid directory")
```

### Security Considerations

1. **Path Traversal Prevention**
   ```python
   # Always validate paths are within expected directory
   build_dir = os.path.realpath(os.path.abspath(build_dir))
   file_path = os.path.realpath(os.path.join(build_dir, filename))
   if not file_path.startswith(build_dir + os.sep):
       raise ValueError("Path traversal detected")
   ```

2. **Command Injection Prevention**
   ```python
   # Use list arguments, not shell=True
   subprocess.run(
       ["ninja", "-t", "deps", target],  # Good
       capture_output=True
   )
   
   # Never do this:
   subprocess.run(f"ninja -t deps {target}", shell=True)  # Bad!
   ```

3. **Input Validation**
   ```python
   # Validate all user inputs
   if threshold <= 0:
       raise ValueError(f"Threshold must be positive, got {threshold}")
   
   # Sanitize file paths
   if '..' in filename or filename.startswith('/'):
       raise ValueError("Invalid filename")
   ```

## Testing

### Running Tests

```bash
# Run all tests
cd test
./run_tests.sh

# Run specific test file
pytest test_buildCheckSummary.py -v

# Run with coverage
pytest --cov=.. --cov-report=html

# Run specific test
pytest test_buildCheckSummary.py::test_format_json_output -v
```

### Writing Tests

1. **Unit Tests**: Test individual functions in isolation
   ```python
   def test_normalize_reason():
       """Test reason string normalization."""
       from lib.ninja_utils import normalize_reason
       
       assert normalize_reason("input source changed: foo.cpp") == "input source changed"
       assert normalize_reason("output missing") == "output missing"
   ```

2. **Integration Tests**: Test complete workflows
   ```python
   def test_full_analysis_workflow(mock_build_dir):
       """Test complete dependency analysis workflow."""
       result = analyze_dependency_hell(
           mock_build_dir,
           rebuild_targets=[],
           threshold=50
       )
       assert isinstance(result, DependencyAnalysisResult)
       assert len(result.problematic) >= 0
   ```

3. **Fixtures**: Use pytest fixtures for common test data
   ```python
   @pytest.fixture
   def mock_build_dir(tmp_path):
       """Create a mock build directory with ninja files."""
       build_dir = tmp_path / "build"
       build_dir.mkdir()
       (build_dir / "build.ninja").write_text("# mock")
       return str(build_dir)
   ```

### Test Coverage

- Aim for >80% code coverage
- All public APIs must have tests
- Critical paths (error handling, security) require thorough testing

## Pull Request Process

### Before Submitting

1. **Run tests locally**
   ```bash
   cd test
   ./run_tests.sh
   ```

2. **Run type checking**
   ```bash
   cd test
   bash run_mypy.sh
   ```

3. **Update documentation**
   - Update relevant README files
   - Add examples for new features
   - Update CHANGELOG if applicable

4. **Check code quality**
   - Remove debug print statements
   - Ensure code follows style guide
   - Add type hints to new functions

### PR Guidelines

1. **Title**: Clear, descriptive title
   - Good: "Add progress indicators to buildCheckDependencyHell"
   - Bad: "Fix stuff"

2. **Description**: Include:
   - What changed and why
   - Related issues (if any)
   - Testing performed
   - Screenshots (for UI changes)

3. **Commits**: 
   - Logical, atomic commits
   - Clear commit messages
   - Squash work-in-progress commits

4. **Size**: Keep PRs focused
   - One feature/fix per PR
   - Break large changes into smaller PRs
   - Large refactorings should be discussed first

### Review Process

1. Maintainers will review within 1-2 weeks
2. Address feedback promptly
3. Keep discussion professional and constructive
4. Be patient - quality takes time!

## Release Process

### Version Numbers

We use semantic versioning (MAJOR.MINOR.PATCH):

- **MAJOR**: Breaking changes to command-line interface or output format
- **MINOR**: New features, backward compatible
- **PATCH**: Bug fixes, performance improvements

### Checklist

1. Update version numbers in all tool files
2. Update CHANGELOG.md
3. Run full test suite
4. Create git tag
5. Update documentation

## Common Development Tasks

### Adding a New Tool

1. Create `buildCheckNewTool.py` in root directory
2. Import shared utilities from `lib/`
3. Follow existing tool structure:
   - Comprehensive docstring at top
   - Import library modules
   - Define constants
   - Implement main logic
   - Add argument parser
   - Include helpful examples in docstring

4. Add tests in `test/test_buildCheckNewTool.py`
5. Update README.md with new tool description
6. Add examples to demo/EXAMPLES.md
7. Update `buildcheck-completion.bash` with new tool's completion function

### Adding Command-Line Options

When adding new command-line options to existing tools:

1. Add the option using `parser.add_argument()` in the tool's argument parser
2. Update the tool's docstring with the new option
3. Update `buildcheck-completion.bash`:
   - Add the option to the `opts` variable in the tool's completion function
   - If the option takes arguments, add a `case` statement to handle completion
4. Test the completion: `source buildcheck-completion.bash && ./test/test-completion.sh`
5. Update the tool's README if applicable

### Adding a Library Function

1. Add to appropriate `lib/*.py` file
2. Include type hints and docstring
3. Add unit tests in `test/test_lib_*.py`
4. Export from `lib/__init__.py` if needed
5. Document in `lib/README.md`

### Improving Performance

1. Profile first: `python -m cProfile -o profile.stats script.py`
2. Focus on hot paths (use cProfile output)
3. Consider:
   - Caching computed results
   - Parallelizing with multiprocessing
   - Using more efficient data structures
   - Reducing I/O operations
4. Add performance tests
5. Document performance characteristics

### Adding Documentation

1. Tool-specific: Update docstring and README_*.md
2. General usage: Update demo/EXAMPLES.md
3. API documentation: Update lib/README.md
4. Contributing: Update this file

## Questions?

- Open an issue for discussion
- Check existing issues and PRs
- Review demo/EXAMPLES.md for usage patterns
- Read tool docstrings for implementation details

## License

By contributing, you agree that your contributions will be licensed under the BSD 3-Clause License.

---

Thank you for contributing to BuildCheck! Your efforts help make C++ build analysis better for everyone.
