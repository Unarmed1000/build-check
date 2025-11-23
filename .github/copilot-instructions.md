# GitHub Copilot Instructions for BuildCheck

## Project Overview

BuildCheck is a comprehensive suite of production-ready tools for analyzing C/C++ build dependencies, identifying rebuild bottlenecks, and optimizing compilation times in large projects. The project consists of nine complementary Python tools that analyze ninja build systems and provide insights into dependency structures, rebuild impacts, and architectural patterns.

## Technology Stack

- **Language**: Python 3.7+ (3.8+ recommended)
- **Build System**: Ninja build system
- **External Tools**: clang-scan-deps (optional, clang-18 or clang-19)

### Required Dependencies
- `networkx>=2.8.8` - Graph analysis and cycle detection
- `GitPython>=3.1.40` - Git operations  
- `packaging>=24.0` - Version checking utilities
- `pytest>=7.0.0` - Test framework (development)
- `pytest-mock>=3.0.0` - Mocking support (development)

### Optional Dependencies
- `colorama>=0.4.6` - Colored terminal output (graceful fallback)
- `scipy>=1.7.0` - PageRank performance optimization
- `pytest-cov>=3.0.0` - Coverage reporting (development)
- `pylint>=2.0.0` - Code quality checking (development)
- `mypy>=0.900` - Type checking (development)

## Project Structure

```
build-check/
├── buildCheck*.py          # Main tool scripts (9 tools)
├── lib/                    # Shared library modules
│   ├── ninja_utils.py     # Ninja build system utilities
│   ├── clang_utils.py     # Clang-scan-deps utilities
│   ├── git_utils.py       # Git integration utilities
│   ├── graph_utils.py     # NetworkX graph utilities
│   ├── dependency_utils.py # Dependency analysis
│   ├── dsm_analysis.py    # Design Structure Matrix analysis
│   ├── color_utils.py     # Terminal color output
│   ├── constants.py       # Shared constants and exceptions
│   └── ...
├── test/                   # Test suite
└── README*.md              # Documentation
```

## Coding Standards

### Python Style

- **Follow PEP 8** with project-specific conventions
- **Line length**: 160 characters (Black formatter configuration)
- **Type hints required**: All functions must include type annotations
- **Docstrings**: Use Google-style docstrings for all public functions and classes
- **Constants**: UPPER_CASE naming
- **Private functions**: Prefix with underscore `_internal_helper()`
- **Type checking**: All code must pass `mypy` type checking

### Type Hints Example

```python
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
```

### Error Handling

Use custom exception classes from `lib/constants.py`:
- `BuildCheckError` - Base exception class
- `ValidationError` - For input validation errors
- `BuildDirectoryError` - For build directory issues
- `ArgumentError` - For command-line argument errors
- `GitRepositoryError` - For git-related errors
- `ExternalToolError` - For ninja/clang tool failures
- `NinjaError` - Specific ninja issues
- `ClangError` - Specific clang issues
- `AnalysisError` - Analysis failures
- `GraphBuildError` - Graph construction failures
- `DependencyAnalysisError` - Dependency analysis failures

### Exit Codes

Standard exit codes from `lib/constants.py`:
- `EXIT_SUCCESS = 0` - Successful execution
- `EXIT_INVALID_ARGS = 1` - Invalid arguments or directory
- `EXIT_RUNTIME_ERROR = 2` - Runtime error
- `EXIT_KEYBOARD_INTERRUPT = 130` - User interrupt

## Key Design Principles

1. **Modularity**: Shared functionality lives in `lib/`, tools import from there
2. **Type Safety**: All new code should use type hints and pass mypy
3. **Error Handling**: Comprehensive error handling with helpful messages
4. **Testing**: All new features require tests
5. **Documentation**: User-facing tools need clear docstrings and examples
6. **Performance**: Tools should be fast and efficient for large codebases
7. **User Experience**: Clear, colored output with progress indicators

## Common Patterns

### File Headers

All Python files must include the BSD 3-Clause License header:

```python
#!/usr/bin/env python3
# ****************************************************************************************************************************************************
# * BSD 3-Clause License
# *
# * Copyright (c) 2025, Mana Battery
# * All rights reserved.
# [... full license text ...]
```

### Tool Script Structure

Main tool scripts follow this pattern:
1. License header
2. Module docstring with description, requirements, usage, and exit codes
3. Imports (standard library, third-party, local modules)
4. Main analysis function
5. Argument parsing with `argparse`
6. Signal handling for graceful interrupts
7. Main entry point with error handling

### Library Module Structure

Library modules in `lib/` should:
1. Include license header
2. Module-level docstring
3. Type hints on all functions
4. Google-style docstrings
5. Comprehensive error handling
6. Helper functions prefixed with `_`

### Using Color Output

Import from `lib/color_utils.py`:

```python
from lib.color_utils import Colors, supports_color

if supports_color():
    print(f"{Colors.BOLD}Header{Colors.RESET}")
```

### Graph Analysis

Use NetworkX for dependency graph analysis:

```python
import networkx as nx
from lib.graph_utils import build_dependency_graph, compute_reverse_dependencies
```

## Tool Categories

### Quick Analysis Tools
- `buildCheckSummary.py` - Fast rebuild analysis
- `buildCheckImpact.py` - Changed header impact

### Dependency Analysis Tools
- `buildCheckIncludeGraph.py` - Visual dependency graphs
- `buildCheckIncludeChains.py` - Long dependency chains
- `buildCheckDependencyHell.py` - Problematic dependencies

### Architectural Analysis Tools
- `buildCheckDSM.py` - Design Structure Matrix
- `buildCheckLibraryGraph.py` - Library-level dependencies

### Impact Analysis Tools
- `buildCheckRippleEffect.py` - Git commit impact
- `buildCheckOptimize.py` - Optimization recommendations

## Quality Standards

BuildCheck maintains **5-STAR quality standards** enforced by `./test/run_quality_check.sh`. All code must pass:

### Required Quality Checks

1. **Type Safety (mypy)**: 100% type safety required
   - Run: `./test/run_mypy.sh`
   - All type hints must be correct
   - No type errors allowed

2. **Code Quality (pylint)**: Minimum 8.0/10 rating
   - Run: `./test/run_pylint.sh`
   - Follow PEP 8 conventions
   - Address all errors and warnings
   - Ratings below 8.0 reduce quality score

3. **Test Suite**: All tests must pass
   - Run: `./test/run_tests.sh`
   - Use `pytest` framework
   - Coverage reports with `pytest-cov`
   - Mock external dependencies (ninja, clang-scan-deps)
   - Test both success and error paths
   - Test files in `test/` directory

4. **Required Documentation**:
   - `README.md` - Project overview and usage
   - `demo/EXAMPLES.md` - Practical usage examples
   - `CONTRIBUTING.md` - Development guidelines
   - `CHANGELOG.md` - Version history

### Quality Scoring System

- **5-STAR ⭐⭐⭐⭐⭐**: No issues, all checks pass
- **4-STAR ⭐⭐⭐⭐**: 1 minor issue (e.g., optional dependency missing)
- **3-STAR ⭐⭐⭐**: 2 minor issues
- **2-STAR ⭐⭐**: 3-4 minor issues or 1 major issue
- **1-STAR ⭐**: Critical failures (mypy, pylint < 5.0, or test failures)

### Before Committing

Always run the complete quality check:

```bash
./test/run_quality_check.sh
```

This script validates:
- Python 3.7+ version
- Required dependencies (networkx, GitPython, pytest, pytest-mock)
- Optional dependencies (colorama, scipy, pytest-cov, pylint)
- External tools (ninja, clang-scan-deps)
- Type checking with mypy
- Code linting with pylint
- Full test suite execution
- Documentation completeness
- Project metrics

## Documentation

- Keep README.md updated for new features
- Tool-specific READMEs for complex tools (e.g., `README_buildCheckDSM.md`)
- Update demo/EXAMPLES.md with practical usage examples
- Maintain CHANGELOG.md for version history
- Update CONTRIBUTING.md for new development practices

## When Creating New Features

Follow this development workflow to maintain 5-STAR quality:

1. **Start with tests**: Write failing tests first (TDD approach)
2. **Reuse utilities**: Check `lib/` for existing functionality
3. **Type everything**: Add type hints to all new code
4. **Implement with quality**:
   - Write clean, idiomatic Python
   - Follow PEP 8 conventions
   - Target pylint 8.0+ rating
   - Use descriptive variable names
   - Add comprehensive error handling
5. **Document thoroughly**: 
   - Add Google-style docstrings
   - Update relevant READMEs
   - Add practical examples to demo/EXAMPLES.md
   - Update CHANGELOG.md
6. **Validate continuously**:
   - Run `./test/run_mypy.sh` - Must pass with no errors
   - Run `./test/run_pylint.sh` - Target 8.0+ rating
   - Run `./test/run_tests.sh` - All tests must pass
   - Run `./test/run_quality_check.sh` - Full validation
7. **Test edge cases**: Consider invalid inputs, large files, missing files, etc.
8. **Performance check**: Profile if dealing with large datasets

### Pre-Commit Checklist

- [ ] All type hints added (mypy passes)
- [ ] Pylint rating ≥ 8.0/10
- [ ] All tests pass
- [ ] Documentation updated
- [ ] Examples added if user-facing
- [ ] Error handling comprehensive
- [ ] Code follows project patterns
- [ ] `run_quality_check.sh` passes

## Performance Considerations

- Cache expensive operations (see `lib/cache_utils.py`)
- Use generators for large datasets
- Avoid loading entire files into memory when possible
- Profile before optimizing
- Consider parallelization for independent operations

## Git Integration

When working with git features:
- Use `GitPython` library via `lib/git_utils.py`
- Handle repository not found gracefully
- Support various commit references (HEAD, hash, range)
- Normalize paths for cross-platform compatibility

## Output Formats

Tools should support multiple output formats:
- **text**: Human-readable colored output (default)
- **json**: Machine-readable for CI/CD integration
- **csv**: For DSM and tabular data
- **dot**: For Graphviz visualization

## License

All code must be BSD 3-Clause licensed. Include the full license header in all new files.
