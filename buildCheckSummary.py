#!/usr/bin/env python3
#****************************************************************************************************************************************************
#* BSD 3-Clause License
#*
#* Copyright (c) 2025, Mana Battery
#* All rights reserved.
#*
#* Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#*
#* 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#* 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
#*    documentation and/or other materials provided with the distribution.
#* 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
#*    software without specific prior written permission.
#*
#* THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
#* THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
#* CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
#* PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
#* LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
#* EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#****************************************************************************************************************************************************

"""Analyze ninja build explanations and provide rebuild summaries.

This script runs ninja in dry-run mode with explain debugging enabled to analyze
what files would be rebuilt and why. It categorizes rebuild reasons and identifies
root cause files (e.g., commonly included headers) that trigger cascading rebuilds.

Requirements:
    - Python 3.7+
    - ninja build system
    - colorama (optional, for colored output): pip install colorama

Usage:
    buildCheckSummary.py <build_directory> [--detailed] [--format=text|json]
    
Exit Codes:
    0: Success
    1: Invalid arguments or directory
    2: Ninja execution failed
    3: Unexpected error
"""

import subprocess
import re
import os
import sys
import argparse
import signal
import json
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple, Dict

__version__ = "1.0.0"
__author__ = "Mana Battery"

# Exit codes
EXIT_SUCCESS = 0
EXIT_INVALID_ARGS = 1
EXIT_NINJA_FAILED = 2
EXIT_UNEXPECTED = 3

# Colorama support (optional)
COLORS_ENABLED = True
try:
    from colorama import Fore, Style, init
    init(autoreset=False)
except ImportError:
    COLORS_ENABLED = False
    class Fore:
        RED = YELLOW = GREEN = BLUE = MAGENTA = CYAN = WHITE = LIGHTBLACK_EX = RESET = ''
    class Style:
        RESET_ALL = BRIGHT = DIM = ''


def disable_colors():
    """Disable color output globally."""
    global COLORS_ENABLED
    COLORS_ENABLED = False
    for attr in dir(Fore):
        if not attr.startswith('_'):
            setattr(Fore, attr, '')
    for attr in dir(Style):
        if not attr.startswith('_'):
            setattr(Style, attr, '')


def signal_handler(signum, frame):
    """Handle interrupt signals gracefully."""
    print(f"\n{Fore.YELLOW}Interrupted by user. Exiting...{Style.RESET_ALL}", file=sys.stderr)
    sys.exit(EXIT_UNEXPECTED)

RE_OUTPUT = re.compile(r"ninja explain: (.*)")


def extract_rebuild_info(build_dir: str, verbose: bool = False) -> Tuple[List[Tuple[str, str]], Dict[str, int], Dict[str, int]]:
    """Extract rebuild information from ninja explain output.
    
    Args:
        build_dir: Path to the ninja build directory
        verbose: If True, print detailed progress information
    
    Returns:
        tuple: (rebuild_entries, reasons, root_causes) where:
            - rebuild_entries: list of (output_file, reason) tuples
            - reasons: dict mapping normalized reason to count
            - root_causes: dict mapping changed file to rebuild count
            
    Raises:
        SystemExit: If ninja execution fails
    """
    if verbose:
        print(f"Analyzing build directory: {build_dir}", file=sys.stderr)
    
    # Save current directory and change to build directory
    original_dir = os.getcwd()
    try:
        os.chdir(build_dir)
    except OSError as e:
        print(f"Error: Cannot change to directory '{build_dir}': {e}", file=sys.stderr)
        sys.exit(EXIT_INVALID_ARGS)

    # Run ninja -n -d explain (dry-run with explain debug mode)
    if verbose:
        print("Running: ninja -n -d explain", file=sys.stderr)
    
    try:
        result = subprocess.run(
            ["ninja", "-n", "-d", "explain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=300  # 5 minute timeout
        )
    except FileNotFoundError:
        print("Error: 'ninja' command not found. Please ensure ninja is installed and in PATH.", file=sys.stderr)
        sys.exit(EXIT_NINJA_FAILED)
    except subprocess.TimeoutExpired:
        print("Error: Ninja command timed out after 5 minutes.", file=sys.stderr)
        sys.exit(EXIT_NINJA_FAILED)
    except subprocess.CalledProcessError as e:
        print(f"Error: Ninja command failed with exit code {e.returncode}", file=sys.stderr)
        if e.stderr:
            print(f"Stderr output:\n{e.stderr}", file=sys.stderr)
        sys.exit(EXIT_NINJA_FAILED)
    except Exception as e:
        print(f"Unexpected error running ninja: {e}", file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)
    finally:
        # Restore original directory
        os.chdir(original_dir)

    # Ninja debug output goes to stderr, not stdout
    lines = result.stderr.splitlines()

    if verbose:
        print(f"Processing {len(lines)} lines of ninja output", file=sys.stderr)

    rebuild_entries = []
    reasons = defaultdict(int)
    root_causes = defaultdict(int)

    for line in lines:
        m = RE_OUTPUT.search(line)
        if not m:
            continue

        explain_msg = m.group(1)
        
        # Skip "is dirty" lines as they're redundant
        if "is dirty" in explain_msg:
            continue
        
        # Extract target from the message
        output_file = "unknown"
        if explain_msg.startswith("output "):
            parts = explain_msg.split(" ", 2)
            if len(parts) > 1:
                output_file = parts[1]
        elif "command line changed for " in explain_msg:
            output_file = explain_msg.split("command line changed for ", 1)[1]
        
        reason_norm = normalize_reason(explain_msg)

        rebuild_entries.append((output_file, reason_norm))
        reasons[reason_norm] += 1

        # Try to extract header file name from reason text
        m2 = re.search(r"([^\s]+\.h\w*)", explain_msg)
        if m2:
            root_causes[m2.group(1)] += 1
    
    return rebuild_entries, reasons, root_causes


def normalize_reason(msg: str) -> str:
    """Normalize a ninja explain message into a human-readable rebuild reason.
    
    Args:
        msg: Raw ninja explain message
        
    Returns:
        Normalized, user-friendly reason string
    """
    if not msg:
        return "unknown reason"
    
    msg_lower = msg.lower()

    if "output missing" in msg_lower or "doesn't exist" in msg_lower:
        return "output missing (initial build)"

    if "older than most recent input" in msg_lower:
        return "input source changed"

    if "command line changed" in msg_lower:
        return "command line changed (compile flags/options)"

    if "input" in msg_lower and "newer" in msg_lower:
        return "input source changed"

    if "depfile" in msg_lower:
        return "header dependency changed"

    if "build.ninja" in msg_lower:
        return "build.ninja changed (cmake reconfigure)"

    if "rule changed" in msg_lower:
        return "rule changed (compile flags/options)"

    if "is dirty" in msg_lower:
        return "[marked dirty]"

    return msg


def format_json_output(rebuild_entries: List[Tuple[str, str]], reasons: Dict[str, int], root_causes: Dict[str, int]) -> str:
    """Format output as JSON.
    
    Args:
        rebuild_entries: List of (output_file, reason) tuples
        reasons: Dictionary of reason counts
        root_causes: Dictionary of root cause counts
        
    Returns:
        JSON formatted string
    """
    output = {
        "summary": {
            "total_files": len(rebuild_entries),
            "version": __version__
        },
        "reasons": dict(reasons),
        "root_causes": dict(root_causes),
        "files": [
            {"output": output, "reason": reason}
            for output, reason in rebuild_entries
        ]
    }
    return json.dumps(output, indent=2)


def main():
    """Main entry point for the script."""
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(
        description='Analyze ninja build explanations and provide rebuild summaries.',
        epilog=f'Version {__version__}'
    )
    
    parser.add_argument(
        'build_directory',
        help='Path to the ninja build directory containing build.ninja'
    )
    
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed list of all files being rebuilt'
    )
    
    parser.add_argument(
        '--format',
        choices=['text', 'json'],
        default='text',
        help='Output format (default: text)'
    )
    
    parser.add_argument(
        '--output', '-o',
        metavar='FILE',
        help='Save JSON output to file and print summary to stdout'
    )
    
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output to stderr'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    args = parser.parse_args()
    
    # Disable colors if requested or if output is not a TTY
    if args.no_color or not sys.stdout.isatty():
        disable_colors()

    build_dir = os.path.realpath(os.path.abspath(args.build_directory))
    
    if args.verbose:
        print(f"Build Check Summary v{__version__}", file=sys.stderr)
        print(f"Analyzing: {build_dir}", file=sys.stderr)

    # Validate directory
    if not os.path.isdir(build_dir):
        print(f"Error: '{build_dir}' is not a directory.", file=sys.stderr)
        sys.exit(EXIT_INVALID_ARGS)

    ninja_file = os.path.realpath(os.path.join(build_dir, "build.ninja"))
    # Validate ninja_file is within build_dir
    if not ninja_file.startswith(build_dir + os.sep):
        print(f"Error: Path traversal detected.", file=sys.stderr)
        sys.exit(EXIT_INVALID_ARGS)
    if not os.path.isfile(ninja_file):
        print(f"Error: '{build_dir}' does not contain a build.ninja file.", file=sys.stderr)
        sys.exit(EXIT_INVALID_ARGS)

    # Extract rebuild information
    try:
        rebuild_entries, reasons, root_causes = extract_rebuild_info(build_dir, args.verbose)
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted by user.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)
    except Exception as e:
        print(f"Error: Unexpected failure: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)
    
    # Handle JSON output format (or when --output is specified)
    if args.format == 'json' and not args.output:
        # JSON to stdout only
        print(format_json_output(rebuild_entries, reasons, root_causes))
        sys.exit(EXIT_SUCCESS)
    
    # Save JSON to file if --output is specified
    if args.output:
        json_output = format_json_output(rebuild_entries, reasons, root_causes)
        try:
            with open(args.output, 'w') as f:
                f.write(json_output)
            if args.verbose:
                print(f"JSON output saved to: {args.output}", file=sys.stderr)
        except IOError as e:
            print(f"Error: Cannot write to file '{args.output}': {e}", file=sys.stderr)
            sys.exit(EXIT_INVALID_ARGS)
        # Continue to print summary to stdout
    
    # Handle case with no rebuilds
    if not rebuild_entries:
        if args.output:
            # Save empty result as JSON
            json_output = format_json_output(rebuild_entries, reasons, root_causes)
            try:
                with open(args.output, 'w') as f:
                    f.write(json_output)
                if args.verbose:
                    print(f"JSON output saved to: {args.output}", file=sys.stderr)
            except IOError as e:
                print(f"Error: Cannot write to file '{args.output}': {e}", file=sys.stderr)
                sys.exit(EXIT_INVALID_ARGS)
        print(f"{Fore.GREEN}No files need to be rebuilt. Build is up to date.{Style.RESET_ALL}")
        sys.exit(EXIT_SUCCESS)

    # Print detailed list first if requested
    if args.detailed:
        print(f"\n{Style.BRIGHT}{Fore.CYAN}=== Detailed Rebuild List ==={Style.RESET_ALL}")
        try:
            for output, reason in rebuild_entries:
                # Color code based on reason type
                if "command line changed" in reason:
                    color = Fore.YELLOW
                elif "input source changed" in reason:
                    color = Fore.RED
                elif "output missing" in reason:
                    color = Fore.GREEN
                else:
                    color = Fore.WHITE
                print(f"  {Fore.LIGHTBLACK_EX}{output}{Style.RESET_ALL} — {color}{reason}{Style.RESET_ALL}")
        except BrokenPipeError:
            # Handle broken pipe gracefully (e.g., when piping to head)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            sys.exit(EXIT_SUCCESS)

    # Print summary
    try:
        print(f"\n{Style.BRIGHT}{Fore.CYAN}=== Rebuild Summary ==={Style.RESET_ALL}")
        print(f"Rebuilt files: {Style.BRIGHT}{Fore.WHITE}{len(rebuild_entries)}{Style.RESET_ALL}")

        print(f"\n{Style.BRIGHT}Reasons:{Style.RESET_ALL}")
        for r, count in sorted(reasons.items(), key=lambda x: -x[1]):
            # Color code based on reason type
            if "command line changed" in r:
                color = Fore.YELLOW
            elif "input source changed" in r:
                color = Fore.RED
            elif "output missing" in r:
                color = Fore.GREEN
            elif "header dependency changed" in r:
                color = Fore.MAGENTA
            elif "build.ninja changed" in r:
                color = Fore.BLUE
            else:
                color = Fore.WHITE
            print(f"  {Style.BRIGHT}{count:3}{Style.RESET_ALL}  → {color}{r}{Style.RESET_ALL}")

        if root_causes:
            print(f"\n{Style.BRIGHT}Root Causes (from explain output):{Style.RESET_ALL}")
            print(f"  {Fore.LIGHTBLACK_EX}(Note: counts may overlap if files include multiple changed headers){Style.RESET_ALL}")
            for rc, count in sorted(root_causes.items(), key=lambda x: -x[1]):
                print(f"  {Fore.MAGENTA}{rc}{Style.RESET_ALL} → triggered {Style.BRIGHT}{count}{Style.RESET_ALL} rebuilds")
    except BrokenPipeError:
        # Handle broken pipe gracefully
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(EXIT_SUCCESS)
    except Exception as e:
        print(f"\nError during output: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Interrupted.{Style.RESET_ALL}", file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(EXIT_UNEXPECTED)
