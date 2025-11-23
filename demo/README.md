# BuildCheck Demo Scripts and Examples

This directory contains demonstration scripts and usage examples for BuildCheck tools.

## Contents

### Demo Scripts

- **`demo_dsm_scenario_patterns.py`** - Demonstrates DSM baseline comparison by creating git repos, saving baseline, and running buildCheckDSM.py --load-baseline
- **`demo_git_scenario_equivalence.py`** - Demonstrates Git working tree impact analysis by creating temporary git repositories and running buildCheckDSM.py --git-impact on each scenario

### Documentation

- **`EXAMPLES.md`** - Comprehensive usage examples for all BuildCheck tools with practical scenarios
- **`DEMO_SUMMARY.md`** - Summary of the demo scripts and architectural scenarios

## Running the Demos

### DSM Scenario Patterns Demo

```bash
# Run all scenarios
python demo/demo_dsm_scenario_patterns.py

# Run with verbose output
python demo/demo_dsm_scenario_patterns.py --verbose
```

This demo demonstrates DSM baseline comparison workflow across 10 architectural scenarios:
1. Creates git repository with baseline
2. Saves baseline with --save-results
3. Applies scenario changes and commits
4. Runs --load-baseline to show differential analysis
5. Displays architectural insights (statistics, ripple impact, recommendations)

### Git Scenario Equivalence Demo

```bash
# Run all scenarios
python demo/demo_git_scenario_equivalence.py

# Run with verbose buildCheckDSM.py output
python demo/demo_git_scenario_equivalence.py --verbose
```

This demo creates physical git repositories for each scenario and runs
buildCheckDSM.py --git-impact to demonstrate real-world git working tree
analysis. Shows authentic tool output including:
- Changed headers and sources
- Rebuild percentage and impact
- Architectural risks (cycles, coupling changes)
- Severity-based recommendations

## Notes

- Demo scripts are self-contained and create their own test data
- No external dependencies beyond the BuildCheck library modules
- All demos run from the project root directory
- Git impact demo creates temporary git repositories for realistic testing
