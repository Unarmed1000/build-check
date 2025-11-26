# buildCheckIncludeChains.py

**Version:** 1.0.0

## Overview

A production-ready tool for analyzing header cooccurrence patterns in C/C++ projects to understand include chains and transitive dependencies.

## Features

### Core Functionality
- **Cooccurrence Analysis**: Identifies which headers frequently appear together in compilation units
- **Include Chain Detection**: Reveals indirect coupling and gateway headers
- **Transitive Dependency Tracking**: Shows which parent headers cause other headers to be included

### Production-Ready Enhancements

#### Robust Error Handling
- ✅ **Input Validation**: Validates build directory exists and contains `build.ninja`
- ✅ **Ninja Availability Check**: Verifies ninja is installed and accessible
- ✅ **Timeout Protection**: Prevents hanging on large dependency queries (30s per target, 60s for explain)
- ✅ **Graceful Failures**: Handles missing targets without crashing
- ✅ **Exit Codes**: Returns proper exit codes (0=success, 1=error, 130=interrupted)

#### Type Safety & Code Quality
- ✅ **Full Type Hints**: All functions have complete type annotations
- ✅ **Pathlib Usage**: Modern path handling with `pathlib.Path`
- ✅ **Clear Separations**: Functions have single responsibilities and clear contracts

#### Logging & Observability
- ✅ **Structured Logging**: Uses Python's logging module with configurable levels
- ✅ **Progress Indicators**: Shows progress every 100 targets (e.g., "Progress: 500/1000 targets processed")
- ✅ **Debug Mode**: `--verbose` flag for detailed troubleshooting
- ✅ **Informative Messages**: Clear feedback at each processing stage

#### User Experience
- ✅ **Configurable Output**: `--max-results` to limit output per header
- ✅ **Smart Path Display**: Shows relative paths when possible for readability
- ✅ **Color Output**: Uses colorama for better visual distinction (optional dependency)
- ✅ **Truncation Notice**: Indicates when results are truncated ("... and N more")
- ✅ **Interrupt Handling**: Clean Ctrl+C handling with proper cleanup

#### Performance & Scalability
- ✅ **Efficient Data Structures**: Uses defaultdict for O(1) lookups
- ✅ **Batch Progress**: Updates progress in batches to reduce output overhead
- ✅ **System Header Filtering**: Excludes `/usr/`, `/lib/`, `/opt/` paths to reduce noise
- ✅ **Early Returns**: Exits early when no work is needed

## Installation

### Requirements
- Python 3.7+
- ninja build system
- Optional: colorama (for colored output)

## Requirements

- **Python 3.7+** (required)
- **ninja build system** (required)
- **colorama>=0.4.6** (optional, for colored output)

**Note:** This tool does NOT require NumPy, NetworkX, or clang-scan-deps. It uses Ninja's built-in dependency information.

```bash
# Install colorama (optional, for colors)
pip install colorama

# Or install from requirements
pip install -r requirements.txt
```

## Usage

### Basic Usage
```bash
# Analyze changed headers in a build directory
./buildCheckIncludeChains.py /path/to/build/release
```

### Advanced Options
```bash
# Increase threshold to reduce noise
./buildCheckIncludeChains.py /path/to/build/release --threshold 10

# Limit results per header
./buildCheckIncludeChains.py /path/to/build/release --max-results 5

# Enable verbose logging for debugging
./buildCheckIncludeChains.py /path/to/build/release --verbose

# Combine options
./buildCheckIncludeChains.py /path/to/build/release \
    --threshold 15 \
    --max-results 20 \
    --verbose
```

### Command-Line Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `BUILD_DIR` | positional | required | Path to ninja build directory |
| `--threshold` | int | 5 | Minimum cooccurrence count to report |
| `--max-results` | int | 10 | Maximum results to show per header |
| `--verbose`, `-v` | flag | false | Enable verbose logging |

## Output Format

```
INFO: Running ninja -n -d explain...
INFO: Parsing ninja output...
INFO: Found 3 changed header(s) affecting 247 target(s)
INFO: Analyzing 247 rebuild targets...
INFO: Progress: 100/247 targets processed
INFO: Progress: 200/247 targets processed
INFO: Progress: 247/247 targets processed
INFO: Built cooccurrence graph with 156 headers

Include Chain Analysis (headers frequently included with changed headers):

  DemoFramework/FslBase/include/FslBase/String/StringUtil.hpp often appears with:
    DemoFramework/FslBase/include/FslBase/BasicTypes.hpp (89 times)
    DemoFramework/FslBase/include/FslBase/Math/Vector2.hpp (67 times)
    DemoFramework/FslBase/include/FslBase/Optional.hpp (45 times)
    ... and 12 more

  DemoFramework/FslGraphics/include/FslGraphics/Render/Texture.hpp: No frequent cooccurrences (threshold=5)
```

## Error Handling

### Invalid Directory
```bash
$ ./buildCheckIncludeChains.py /invalid/path
ERROR: Directory does not exist: /invalid/path
```

### Missing build.ninja
```bash
$ ./buildCheckIncludeChains.py /some/dir
ERROR: No build.ninja found in /some/dir. This doesn't appear to be a ninja build directory.
```

### Ninja Not Found
```bash
$ ./buildCheckIncludeChains.py /build/dir
ERROR: ninja not found in PATH. Please install ninja or ensure it's in your PATH.
```

### Timeout
```bash
$ ./buildCheckIncludeChains.py /huge/build
INFO: Running ninja -n -d explain...
ERROR: Timeout running ninja -n -d explain. The build graph may be too large.
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success - analysis completed |
| 1 | Error - invalid input, missing tool, or runtime error |
| 130 | Interrupted - user pressed Ctrl+C |

## Implementation Details

### Architecture

The tool follows a pipeline architecture:

1. **Validation Phase**: Check ninja availability and build directory
2. **Query Phase**: Run `ninja -n -d explain` to get rebuild information
3. **Parse Phase**: Extract changed headers and rebuild targets
4. **Analysis Phase**: Build cooccurrence matrix from dependencies
5. **Report Phase**: Format and display results

### Key Functions

#### `validate_build_directory(build_dir: str) -> Path`
Validates the build directory exists and contains `build.ninja`.

#### `get_dependencies(build_dir: Path, target: str) -> List[str]`
Queries ninja for dependencies with timeout and error handling.

#### `build_include_graph(build_dir: Path, rebuild_targets: List[str]) -> Dict[str, Dict[str, int]]`
Builds the cooccurrence matrix with progress updates.

#### `parse_ninja_output(stderr_lines: List[str]) -> Tuple[List[str], Set[str]]`
Extracts rebuild targets and changed headers from ninja explain output.

### Constants

```python
HEADER_EXTENSIONS = ('.h', '.hpp', '.hxx', '.hh')
SYSTEM_PATH_PREFIXES = ('/usr/', '/lib/', '/opt/')
DEFAULT_THRESHOLD = 5
DEFAULT_MAX_RESULTS = 10
```

## Use Cases

### 1. Understanding Rebuild Impact
**Scenario**: Modified a header and want to know why it triggers so many rebuilds.

```bash
./buildCheckIncludeChains.py build/release --threshold 10
```

**Insight**: See which high-level headers include your changed header transitively.

### 2. Finding Gateway Headers
**Scenario**: Investigating which headers act as "gateway" headers pulling in many dependencies.

```bash
./buildCheckIncludeChains.py build/release --max-results 20
```

**Insight**: Headers with many cooccurrences are likely gateway headers.

### 3. Refactoring Opportunities
**Scenario**: Looking for headers with tight coupling that could be decoupled.

```bash
./buildCheckIncludeChains.py build/release --threshold 5
```

**Insight**: High cooccurrence between unrelated headers suggests refactoring opportunities.

## Complementary Tools

This tool is part of the BuildCheck suite:

- **buildCheckImpact.py**: Direct rebuild impact analysis (simpler, faster)
- **buildCheckIncludeGraph.py**: Actual include relationships and gateway analysis
- **buildCheckDependencyHell.py**: Comprehensive transitive dependency metrics
- **buildCheckRippleEffect.py**: Predicts rebuild cascades from changes
- **buildCheckSummary.py**: High-level build health overview

## Troubleshooting

### Slow Performance
If analysis is slow on large projects:

1. Use `--threshold` to increase minimum cooccurrence count
2. Use `--max-results` to limit output
3. Check if `ninja -t deps` is slow (might indicate build system issues)

### Missing Results
If no cooccurrences are found:

1. Lower the `--threshold` (default is 5)
2. Check if headers are actually changed (build must be dirty)
3. Use `--verbose` to see detailed processing

### Debug Mode
```bash
./buildCheckIncludeChains.py build/release --verbose
```

Shows:
- Progress every 100 targets
- Failed dependency queries (debug level)
- Build graph statistics
- Full traceback on errors

## Best Practices

1. **Run after making changes**: Tool analyzes what *would* rebuild
2. **Start with defaults**: Default threshold (5) works for most projects
3. **Use with complementary tools**: Combine with buildCheckIncludeGraph.py for full picture
4. **Monitor large projects**: For projects with 1000+ targets, consider increasing threshold
5. **Capture output**: Redirect output to file for later analysis

## Performance Characteristics

- **Time Complexity**: O(T × D²) where T = targets, D = dependencies per target
- **Space Complexity**: O(H²) where H = unique headers
- **Typical Runtime**: 1-5 seconds for projects with 100-500 targets
- **Large Projects**: May take 10-30 seconds for 1000+ targets

## Technical Notes

### Why Cooccurrence?
Headers that appear together in many compilation units likely have a dependency relationship:
- One directly includes the other
- Both are included by a common parent
- They're part of a tightly coupled module

### Limitations
- **Indirect**: Shows correlation, not direct causation (use buildCheckIncludeGraph.py for direct includes)
- **Heuristic**: Project root detection may fail in unusual layouts
- **System Headers**: Filters out system headers to reduce noise (may miss some dependencies)

## License

BSD 3-Clause License - Copyright (c) 2025, Mana Battery

## Contributing

When contributing, ensure:
- All functions have type hints
- New features include error handling
- Logging uses appropriate levels (INFO for user, DEBUG for developer)
- Exit codes follow Unix conventions
- Tests cover error cases
