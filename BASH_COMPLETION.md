# Bash Completion for buildCheck Tools

This directory includes a bash completion script that provides tab-completion for all buildCheck command-line tools.

## Features

- **Tab-completion for all buildCheck scripts**: Works with all tools including `buildCheckSummary`, `buildCheckDSM`, `buildCheckIncludeChains`, etc.
- **Option completion**: Press Tab after typing `--` to see all available options
- **Smart argument completion**: 
  - Directory paths for build directories
  - File paths for export/output options
  - Format choices (text/json) where applicable
- **Works with both direct script names and `.py` extensions**: Completes for both `buildCheckSummary` and `buildCheckSummary.py`

## Quick Demo

```bash
# Source the completion script
$ source buildcheck-completion.bash

# Tab completion for commands
$ buildCheck<Tab><Tab>
buildCheckDSM                buildCheckIncludeChains      buildCheckOptimize
buildCheckDependencyHell     buildCheckIncludeGraph       buildCheckRippleEffect
buildCheckImpact             buildCheckLibraryGraph       buildCheckSummary

# Tab completion for options
$ buildCheckSummary --<Tab><Tab>
--detailed   --format     --help       --no-color   --output     --verbose    --version

# Tab completion for option values
$ buildCheckSummary --format <Tab><Tab>
json  text

# Directory completion for build paths
$ buildCheckDSM ../build/<Tab>
../build/debug/    ../build/release/

# File completion for export options
$ buildCheckDSM --export report<Tab>
report.csv  report.json  report_old.csv
```

## Installation

### Method 1: Source in your shell session (temporary)

```bash
source buildcheck-completion.bash
```

This enables completion for your current shell session only.

### Method 2: Add to your ~/.bashrc (permanent, user-only)

Add this line to your `~/.bashrc`:

```bash
source /path/to/build-check/buildcheck-completion.bash
```

Then reload your shell:

```bash
source ~/.bashrc
```

### Method 3: System-wide installation (permanent, all users)

Copy the completion script to the system bash completion directory:

```bash
sudo cp buildcheck-completion.bash /etc/bash_completion.d/buildcheck
```

Or for user-local installation:

```bash
mkdir -p ~/.local/share/bash-completion/completions
cp buildcheck-completion.bash ~/.local/share/bash-completion/completions/buildcheck
```

Then start a new shell session.

## Usage Examples

### Basic completion

```bash
# Type the script name and press Tab to see directory suggestions
buildCheckSummary <Tab>

# Press Tab twice to see all available options
buildCheckDSM --<Tab><Tab>
```

### Common workflows

```bash
# Complete build directory path
buildCheckSummary build/<Tab>

# Complete option names
buildCheckDSM --ex<Tab>  # Expands to --export or shows matching options

# Complete format choices
buildCheckSummary --format <Tab>  # Shows: text json

# Complete file paths for output
buildCheckDSM --export report<Tab>  # Completes filename
```

## Supported Commands

The completion script supports all buildCheck tools:

- `buildCheckSummary` / `buildCheckSummary.py`
- `buildCheckDSM` / `buildCheckDSM.py`
- `buildCheckIncludeChains` / `buildCheckIncludeChains.py`
- `buildCheckDependencyHell` / `buildCheckDependencyHell.py`
- `buildCheckRippleEffect` / `buildCheckRippleEffect.py`
- `buildCheckLibraryGraph` / `buildCheckLibraryGraph.py`
- `buildCheckImpact` / `buildCheckImpact.py`
- `buildCheckIncludeGraph` / `buildCheckIncludeGraph.py`
- `buildCheckOptimize` / `buildCheckOptimize.py`

## Troubleshooting

### Completion not working

1. **Check if bash-completion is installed:**
   ```bash
   # On Ubuntu/Debian
   sudo apt-get install bash-completion
   
   # On macOS with Homebrew
   brew install bash-completion@2
   ```

2. **Verify the script is sourced:**
   ```bash
   complete -p buildCheckSummary
   ```
   Should output: `complete -F _buildCheckSummary buildCheckSummary buildCheckSummary.py`

3. **Check for errors:**
   ```bash
   bash -x buildcheck-completion.bash
   ```

### Completion shows wrong suggestions

The completion script uses the current directory as context for path completion. Make sure you're in the correct directory or provide absolute paths.

## Testing

To verify the completion script works correctly:

```bash
# Run basic registration test
./test/test-completion.sh

# Run advanced functionality tests
./test/test-completion-advanced.sh
```

## Customization

If you need to customize the completion behavior, you can edit `buildcheck-completion.bash` and modify the completion functions. Each tool has its own completion function (e.g., `_buildCheckSummary`, `_buildCheckDSM`) that you can adjust.

## Contributing

If you add new options to any buildCheck tool, please update the corresponding completion function in `buildcheck-completion.bash` to ensure the completion stays up to date.
