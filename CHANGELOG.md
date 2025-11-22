# Changelog

All notable changes to the BuildCheck project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2025-01-XX

Initial release of BuildCheck - a comprehensive suite of production-ready tools for analyzing C/C++ build dependencies, identifying rebuild bottlenecks, and optimizing compilation times.

### Tools (9)
1. **buildCheckSummary** - Quick rebuild analysis with ninja explain
2. **buildCheckImpact** - Changed header impact analysis
3. **buildCheckIncludeChains** - Cooccurrence pattern analysis
4. **buildCheckIncludeGraph** - Gateway header analysis with clang-scan-deps
5. **buildCheckRippleEffect** - Git commit impact analysis
6. **buildCheckDependencyHell** - Comprehensive multi-metric dependency analysis
7. **buildCheckDSM** - Dependency Structure Matrix visualization
8. **buildCheckLibraryGraph** - Library-level dependency analysis
9. **buildCheckOptimize** - Actionable optimization recommendations

### Library Modules (15)
- **clang_utils.py** - Clang-scan-deps integration with caching
- **ninja_utils.py** - Ninja build system utilities
- **git_utils.py** - Git repository integration
- **graph_utils.py** - NetworkX graph operations
- **dependency_utils.py** - Dependency analysis algorithms
- **dsm_analysis.py** - DSM matrix operations
- **dsm_serialization.py** - DSM import/export
- **dsm_types.py** - DSM data structures
- **library_parser.py** - Build.ninja library parsing
- **export_utils.py** - Export to CSV/GraphML
- **file_utils.py** - File system utilities
- **color_utils.py** - Colored terminal output with graceful fallback
- **constants.py** - Shared constants and thresholds
- **package_verification.py** - Dependency version checking

### Features
- Multi-core parallel processing using all CPU cores
- Intelligent caching with timestamp validation
- Progress indicators for long-running operations
- Color-coded output for easy interpretation
- Multiple output formats (text, JSON, CSV, GraphML)
- Comprehensive metrics (transitive deps, build impact, rebuild cost)
- Severity classification (CRITICAL/HIGH/MODERATE)
- Circular dependency detection
- Layered architecture analysis
- Gateway header identification
- Optimization recommendations with priority scoring
- Enhanced error messages with actionable suggestions

### Testing
- Comprehensive test suite with pytest (38+ test files, 9,500+ LOC)
- 495 passing tests with 85.44% code coverage
- Unit tests for all library modules
- Integration tests for main tools
- Security tests for path traversal prevention
- Mock fixtures for reproducible testing
- Type checking with mypy
- Automated quality validation script

### Documentation
- README.md - Project overview and quick start (890 lines)
- EXAMPLES.md - Comprehensive usage examples (619 lines)
- CONTRIBUTING.md - Contributor guidelines (457 lines)
- CHANGELOG.md - Version tracking
- TEST_SUITE_SUMMARY.md - Test suite documentation
- Tool-specific READMEs for complex tools (DSM, IncludeChains, LibraryGraph, Summary)
- lib/README.md - Library module documentation (347 lines)

### Security
- Path traversal protection with realpath validation
- Command injection prevention using subprocess list arguments
- Input validation for all user-provided parameters
- Dedicated security test suite (244 LOC)
- Timeout protection on all external commands

### Requirements
- Python 3.8+ (required)
- ninja build system (required)
- networkx>=2.8.8 (required)
- GitPython>=3.1.40 (required)
- packaging>=24.0 (required)
- colorama>=0.4.6 (optional, for colored output)
- clang-scan-deps (optional, for source-level dependency analysis)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details on how to contribute to this project.

## License

BSD 3-Clause License - See [LICENSE](LICENSE) for details.
