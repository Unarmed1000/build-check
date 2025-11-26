# buildCheckSummary.py

**Version:** 1.0.0

A production-ready tool for analyzing ninja build explanations and providing comprehensive rebuild summaries.

## Features

- **Rebuild Analysis**: Analyzes what files would be rebuilt and categorizes the reasons
- **Root Cause Identification**: Identifies which files (e.g., commonly included headers) trigger cascading rebuilds
- **Multiple Output Formats**: Supports text (colored) and JSON output
- **Robust Error Handling**: Comprehensive error handling with proper exit codes
- **Signal Handling**: Graceful handling of interrupts (Ctrl+C)
- **Broken Pipe Handling**: Works correctly when piping to tools like `head` or `grep`
- **Verbose Mode**: Optional detailed progress information
- **No External Dependencies**: Only requires Python 3.6+ (colorama is optional)

## Requirements

- **Python 3.7+** (required)
- **ninja build system** (required)
- **colorama>=0.4.6** (optional, for colored output)

**Note:** This tool does NOT require NumPy, NetworkX, or clang-scan-deps. It only uses Ninja's built-in explain functionality.

## Installation

No installation required. Just make the script executable:

```bash
chmod +x buildCheckSummary.py
```

## Usage

### Basic Usage

```bash
./buildCheckSummary.py /path/to/build/directory
```

### Show Detailed File List

```bash
./buildCheckSummary.py /path/to/build/directory --detailed
```

### JSON Output

```bash
./buildCheckSummary.py /path/to/build/directory --format json
```

### Disable Colors

```bash
./buildCheckSummary.py /path/to/build/directory --no-color
```

### Verbose Mode

```bash
./buildCheckSummary.py /path/to/build/directory --verbose
```

### Combined Options

```bash
./buildCheckSummary.py /path/to/build/directory --detailed --verbose --no-color
```

## Exit Codes

- `0`: Success
- `1`: Invalid arguments or directory
- `2`: Ninja execution failed
- `3`: Unexpected error

## Output Format

### Text Format (Default)

The script provides a summary showing:

1. **Detailed Rebuild List** (with `--detailed`): Lists each file being rebuilt with its reason
2. **Rebuild Summary**: Total count of files being rebuilt
3. **Reasons**: Breakdown of rebuild reasons with counts
4. **Root Causes**: Files that triggered the most rebuilds

Example output:

```
=== Rebuild Summary ===
Rebuilt files: 571

Reasons:
  542  → input source changed
   29  → output missing (initial build)

Root Causes (from explain output):
  (Note: counts may overlap if files include multiple changed headers)
  /path/to/BasicTypes.hpp → triggered 541 rebuilds
  /path/to/ReleaseVersionTag.hpp → triggered 1 rebuilds
```

### JSON Format

With `--format json`, the output is structured JSON suitable for programmatic analysis:

```json
{
  "summary": {
    "total_files": 571,
    "version": "1.0.0"
  },
  "reasons": {
    "input source changed": 542,
    "output missing (initial build)": 29
  },
  "root_causes": {
    "/path/to/BasicTypes.hpp": 541,
    "/path/to/ReleaseVersionTag.hpp": 1
  },
  "files": [
    {
      "output": "path/to/file.o",
      "reason": "input source changed"
    }
  ]
}
```

## Requirements

- Python 3.6 or later
- Ninja build system
- A valid ninja build directory with `build.ninja` file

### Optional Dependencies

- `colorama`: For colored terminal output (falls back to plain text if not available)

```bash
pip install colorama
```

## Examples

### Analyze a CMake/Ninja Build

```bash
# After making a change to a header file
./buildCheckSummary.py ./build --detailed | head -20

# Check impact in JSON for automation
./buildCheckSummary.py ./build --format json | jq '.root_causes'
```

### Continuous Integration

```bash
#!/bin/bash
# Check rebuild impact before committing
./buildCheckSummary.py ./build --format json > rebuild_report.json

# Alert if too many files would rebuild
REBUILD_COUNT=$(jq '.summary.total_files' rebuild_report.json)
if [ "$REBUILD_COUNT" -gt 100 ]; then
    echo "Warning: Change affects $REBUILD_COUNT files"
fi
```

### Development Workflow

```bash
# Quick check without colors for log files
./buildCheckSummary.py ./build --no-color >> build_analysis.log

# Verbose analysis for debugging
./buildCheckSummary.py ./build --verbose --detailed 2>&1 | tee detailed_analysis.txt
```

## How It Works

1. Changes to the specified build directory
2. Runs `ninja -n -d explain` (dry-run with explain debugging)
3. Parses the ninja output to extract rebuild information
4. Categorizes and normalizes rebuild reasons
5. Identifies root cause files from dependency information
6. Formats and displays the results

## Rebuild Reason Categories

The script normalizes ninja's explain messages into these categories:

- **input source changed**: Source file or dependency is newer than output
- **output missing (initial build)**: Target doesn't exist yet
- **command line changed**: Compile flags or options changed
- **header dependency changed**: Header file dependency changed
- **build.ninja changed**: CMake reconfiguration occurred
- **rule changed**: Build rule was modified

## Error Handling

The script includes comprehensive error handling for:

- Invalid or non-existent directories
- Missing `build.ninja` files
- Ninja command failures
- Ninja not installed or not in PATH
- Timeout (5 minute limit)
- Broken pipes (when piping to other commands)
- Keyboard interrupts (Ctrl+C)

## Performance

- Typical execution time: 1-5 seconds for medium-sized projects
- Timeout protection: 5 minutes maximum
- Memory efficient: Streams ninja output

## Version

Current version: 1.0.0

View version:
```bash
./buildCheckSummary.py --version
```

## Troubleshooting

### "ninja: command not found"

Install ninja build system:
```bash
# Ubuntu/Debian
sudo apt-get install ninja-build

# macOS
brew install ninja
```

### "does not contain a build.ninja file"

Ensure you're pointing to the actual build directory (not source directory):
```bash
# Wrong
./buildCheckSummary.py ./src

# Correct
./buildCheckSummary.py ./build
```

### Colors not working

Install colorama or use `--no-color`:
```bash
pip install colorama
# or
./buildCheckSummary.py ./build --no-color
```

### ccache-related issues

While this tool doesn't use clang-scan-deps directly, if you encounter any build system issues with ccache, see the detailed troubleshooting section in [README_buildCheckDSM.md](README_buildCheckDSM.md#troubleshooting) for comprehensive ccache compatibility information.

## License

Part of the Build Check Tools suite.

## See Also

- `buildCheckRippleEffect.py`: Analyze ripple effects of file changes
- `buildCheckDependencyHell.py`: Find circular dependencies
- `buildCheckIncludeGraph.py`: Visualize include dependencies
