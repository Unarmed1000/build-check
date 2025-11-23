# Changelog

All notable changes to the BuildCheck project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **buildCheckDSM.py v1.2.0**: Proactive improvement analysis (`--suggest-improvements`)
  - Single-run refactoring recommendations without requiring a baseline
  - Anti-pattern detection: god objects, cycles, coupling outliers, unstable interfaces, hub nodes
  - ROI calculation with composite scoring (cycle elimination 40%, rebuild reduction 30%, coupling 20%, effort 10%)
  - Break-even analysis: estimated commits until refactoring pays off
  - Severity-based prioritization: 🟢 Quick Wins (ROI ≥60, ≤5 commits), 🔴 Critical (cycles/ROI ≥40), 🟡 Moderate (ROI <40)
  - Precise transitive closure for accurate rebuild impact estimation
  - Team impact estimation (hours saved per year, payback time calculations)
  - Actionable refactoring steps with effort estimates (low/medium/high)
  - Architectural debt scoring (0-100 scale)
- New dataclass `ImprovementCandidate` in `lib/dsm_types.py`
- New functions in `lib/dsm_analysis.py`:
  - `identify_improvement_candidates()` - Anti-pattern detection
  - `estimate_improvement_roi()` - ROI simulation with precise transitive analysis
  - `compute_transitive_dependents()` - Transitive closure helper
  - `estimate_affected_sources()` - Source file impact calculation
  - `rank_improvements_by_impact()` - Priority ranking
  - `display_improvement_suggestions()` - Formatted output display
  - `run_proactive_improvement_analysis()` - Main entry point
- Comprehensive documentation updates:
  - README_buildCheckDSM.md: Full proactive analysis documentation
  - EXAMPLES.md: Proactive analysis workflow examples
  - README.md: Feature overview and integration
  - Updated USE CASES in buildCheckDSM.py docstring

### Changed
- **[BREAKING]** `buildCheckDSM.py`: Precise transitive closure analysis is now the default for differential analysis
  - Removed `--precise-impact` flag (was opt-in)
  - Added `--heuristic-only` flag for fast mode (opt-out)
  - Default behavior now provides 95% confidence with full transitive closure
  - Use `--heuristic-only` for instant results (±5% confidence) during quick iterations
- Updated `lib/dsm_analysis.py`: Changed `compute_precise` parameter default from `False` to `True`
- Updated all documentation to reflect new default behavior and decision guide
- Version bumped to 1.2.0 for buildCheckDSM.py

### Added (previous)
- Decision guide in README.md for when to use `--heuristic-only` flag
- Performance vs accuracy trade-off documentation in all relevant docs

## [1.0.0] - 2025-01-XX

Initial release of BuildCheck - a comprehensive suite of production-ready tools for analyzing C/C++ build dependencies, identifying rebuild bottlenecks, and optimizing compilation times.

### Tools (9)
1. **buildCheckSummary** - Quick rebuild analysis with ninja explain
2. **buildCheckImpact** - Changed header impact analysis
3. **buildCheckIncludeChains** - Cooccurrence pattern analysis
4. **buildCheckIncludeGraph** - Gateway header analysis with clang-scan-deps
5. **buildCheckRippleEffect** - Git commit impact analysis
6. **buildCheckDependencyHell** - Comprehensive multi-metric dependency analysis
7. **buildCheckDSM** - Dependency Structure Matrix visualization with architectural insights
8. **buildCheckLibraryGraph** - Library-level dependency analysis
9. **buildCheckOptimize** - Actionable optimization recommendations

### Library Modules (20)
**Production Modules (15):**
- **clang_utils.py** - Clang-scan-deps integration with caching
- **ninja_utils.py** - Ninja build system utilities
- **git_utils.py** - Git repository integration
- **graph_utils.py** - NetworkX graph operations with centrality metrics
- **dependency_utils.py** - Dependency analysis algorithms
- **dsm_analysis.py** - DSM matrix operations with architectural insights and proactive improvement analysis
- **dsm_serialization.py** - DSM import/export with baseline save/load
- **dsm_types.py** - DSM data structures including ArchitecturalInsights and ImprovementCandidate
- **library_parser.py** - Build.ninja library parsing
- **export_utils.py** - Export to CSV/GraphML/DOT/GEXF/JSON with centrality metrics
- **file_utils.py** - File system utilities with filtering and clustering
- **color_utils.py** - Colored terminal output with graceful fallback
- **constants.py** - Shared constants and thresholds
- **package_verification.py** - Dependency version checking
- **cache_utils.py** - Caching utilities with timestamp validation

**Testing/Scenario Modules (5):**
- **scenario_creators.py** - Test scenario generation for DSM testing
- **scenario_definitions.py** - Architectural scenario definitions
- **scenario_git_utils.py** - Git scenario utilities for testing
- **scenario_test_utils.py** - Testing utilities for scenario validation
- **__init__.py** - Package initialization

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
- **Architectural insights for DSM differential analysis**
  - Coupling statistics with distribution analysis (mean, median, percentiles, outliers)
  - Stability change tracking (headers becoming stable/unstable)
  - Cycle complexity analysis with betweenness centrality
  - Layer movement statistics and depth changes
  - Ripple impact prediction with precise source-level analysis
  - Architecture quality scoring (0-100 scale)
  - Automated recommendations with severity classification
- **PageRank centrality** - Measures architectural importance
- **Betweenness centrality** - Identifies architectural bottlenecks and hub nodes
- **Baseline save/load functionality** - Flexible DSM comparison workflows
- **Precise impact mode** (`--precise-impact`) - Exact transitive analysis for rebuild predictions

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
- demo/EXAMPLES.md - Comprehensive usage examples (619 lines)
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
