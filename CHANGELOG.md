# Changelog

All notable changes to the BuildCheck project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Comprehensive main README.md**: Complete rewrite with professional documentation
  - Added two Mermaid flowchart diagrams (GitHub-compatible):
    * Tool Selection Guide: Interactive decision tree helping users choose the right tool
    * Typical Workflow: Visual representation of how tools work together
  - Core tools overview table comparing all 9 tools with clear use cases
  - Expanded Quick Start section with 5 detailed examples and real output samples
  - Deep dive sections for 5 most important tools (buildCheckDSM, buildCheckSummary, buildCheckRippleEffect, buildCheckDependencyHell, buildCheckOptimize)
  - Installation guide with prerequisites (Python 3.7+, Ninja, Clang 18/19)
  - Comprehensive troubleshooting section (ccache, large projects, performance)
  - Testing section highlighting 749+ test coverage
  - Project structure visualization and learning resources
  - Use case scenarios for different development workflows

### Changed
- **README_buildCheckDSM.md**: Updated dependencies section
  - Added `numpy>=1.24.0` requirement (critical for statistical analysis)
  - Added `scipy>=1.14.1` requirement (for advanced statistics)
  - Standardized all dependency versions with `>=` notation
  - Updated `networkx>=2.8.8` and `colorama>=0.4.6`

- **README_buildCheckSummary.md**: Enhanced with version and requirements
  - Added version number (1.0.0) at document top
  - Added comprehensive Requirements section
  - **Important clarification**: NumPy, NetworkX, and clang-scan-deps are NOT required
  - Added ccache troubleshooting reference linking to DSM README
  - Standardized dependency format (Python 3.7+, ninja, optional colorama>=0.4.6)

- **README_buildCheckIncludeChains.md**: Standardized documentation
  - Added version number (1.0.0) at document top
  - Added formal Requirements section with version numbers
  - Clarified that NumPy, NetworkX, and clang-scan-deps are NOT required
  - Standardized dependency format matching other READMEs
  - Added helpful note explaining tool's minimal dependencies

- **README_buildCheckLibraryGraph.md**: Standardized documentation
  - Added version number (1.0.0) at document top
  - Standardized Requirements section with version numbers
  - Updated `networkx>=2.8.8` and `colorama>=0.4.6`
  - Clarified that NumPy and clang-scan-deps are NOT required
  - Added helpful note about tool's minimal dependencies

### Documentation
- **Cross-document consistency**: All tool-specific READMEs now follow consistent format
  - Standardized Requirements sections across all documentation
  - Version numbers added to all tool-specific READMEs
  - Clear notes about which tools require NumPy/NetworkX/clang-scan-deps vs which don't
  - Dependency versions now match requirements.txt
  - Improved cross-references between related tools
- **User experience improvements**:
  - Visual decision flowcharts for tool selection
  - "What Does BuildCheck Do?" section with clear value propositions
  - Real example outputs showing what users will see
  - Copy-paste ready command examples
  - Comprehensive troubleshooting sections

