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
from typing import List, Tuple, Dict, Any

__version__ = "1.0.0"
__author__ = "Mana Battery"

# Import library modules
from lib.color_utils import Colors, print_error, print_warning, print_success
from lib.ninja_utils import extract_rebuild_info, normalize_reason, validate_build_directory_with_feedback
from lib.constants import (
    EXIT_SUCCESS, EXIT_INVALID_ARGS, EXIT_RUNTIME_ERROR,
    EXIT_KEYBOARD_INTERRUPT
)

# Export for tests
__all__ = ['EXIT_SUCCESS', 'main']

COLORS_ENABLED = True

def disable_colors() -> None:
    """Disable color output globally."""
    global COLORS_ENABLED
    COLORS_ENABLED = False
    Colors.disable()


def signal_handler(signum: int, frame: Any) -> None:
    """Handle interrupt signals gracefully."""
    print_warning("\nInterrupted by user. Exiting...", prefix=False)
    sys.exit(EXIT_KEYBOARD_INTERRUPT)

# RE_OUTPUT moved to lib.ninja_utils
# extract_rebuild_info and normalize_reason moved to lib.ninja_utils


def format_json_output(rebuild_entries: List[Tuple[str, str]], reasons: Dict[str, int], root_causes: Dict[str, int]) -> str:
    """Format output as JSON.
    
    Args:
        rebuild_entries: List of (output_file, reason) tuples
        reasons: Dictionary of reason counts
        root_causes: Dictionary of root cause counts
        
    Returns:
        JSON formatted string
        
    Raises:
        ValueError: If input data is invalid
    """
    if not isinstance(rebuild_entries, list):
        raise ValueError("rebuild_entries must be a list")
    if not isinstance(reasons, dict):
        raise ValueError("reasons must be a dictionary")
    if not isinstance(root_causes, dict):
        raise ValueError("root_causes must be a dictionary")
        
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


def main() -> int:
    """Main entry point for the script.
    
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    parser = argparse.ArgumentParser(
        description='Analyze ninja build explanations and provide rebuild summaries.',
        epilog=f'Version {__version__}\n\nExamples:\n'
               f'  %(prog)s ../build/release/\n'
               f'  %(prog)s ../build/release/ --detailed\n'
               f'  %(prog)s ../build/release/ --format json --output report.json\n',
        formatter_class=argparse.RawDescriptionHelpFormatter
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

    if args.verbose:
        print(f"Build Check Summary v{__version__}", file=sys.stderr)
        print(f"Analyzing: {args.build_directory}", file=sys.stderr)

    # Validate build directory using library helper
    try:
        build_dir, _ = validate_build_directory_with_feedback(args.build_directory, verbose=args.verbose)
    except (ValueError, RuntimeError) as e:
        # Error message already printed by helper
        return EXIT_INVALID_ARGS

    # Extract rebuild information
    try:
        rebuild_entries, reasons, root_causes = extract_rebuild_info(build_dir, args.verbose)
    except KeyboardInterrupt:
        print_warning("\nInterrupted by user.", prefix=False)
        return EXIT_KEYBOARD_INTERRUPT
    except Exception as e:
        print(f"Error: Unexpected failure: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    
    # Handle JSON output format (or when --output is specified)
    if args.format == 'json' and not args.output:
        # JSON to stdout only
        print(format_json_output(rebuild_entries, reasons, root_causes))
        return EXIT_SUCCESS
    
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
            return EXIT_INVALID_ARGS
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
                return EXIT_INVALID_ARGS
        print_success("No files need to be rebuilt. Build is up to date.", prefix=False)
        return EXIT_SUCCESS

    # Print detailed list first if requested
    if args.detailed:
        print(f"\n{Colors.BRIGHT}{Colors.CYAN}=== Detailed Rebuild List ==={Colors.RESET}")
        try:
            for output, reason in rebuild_entries:
                # Color code based on reason type
                if "command line changed" in reason:
                    color = Colors.YELLOW
                elif "input source changed" in reason:
                    color = Colors.RED
                elif "output missing" in reason:
                    color = Colors.GREEN
                else:
                    color = Colors.WHITE
                print(f"  {Colors.DIM}{output}{Colors.RESET} — {color}{reason}{Colors.RESET}")
        except BrokenPipeError:
            # Handle broken pipe gracefully (e.g., when piping to head)
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
            return EXIT_SUCCESS

    # Print summary
    try:
        print(f"\n{Colors.BRIGHT}{Colors.CYAN}=== Rebuild Summary ==={Colors.RESET}")
        print(f"Rebuilt files: {Colors.BRIGHT}{Colors.WHITE}{len(rebuild_entries)}{Colors.RESET}")

        print(f"\n{Colors.BRIGHT}Reasons:{Colors.RESET}")
        for r, count in sorted(reasons.items(), key=lambda x: -x[1]):
            # Color code based on reason type
            if "command line changed" in r:
                color = Colors.YELLOW
            elif "input source changed" in r:
                color = Colors.RED
            elif "output missing" in r:
                color = Colors.GREEN
            elif "header dependency changed" in r:
                color = Colors.MAGENTA
            elif "build.ninja changed" in r:
                color = Colors.BLUE
            else:
                color = Colors.WHITE
            print(f"  {Colors.BRIGHT}{count:3}{Colors.RESET}  → {color}{r}{Colors.RESET}")

        if root_causes:
            print(f"\n{Colors.BRIGHT}Root Causes (from explain output):{Colors.RESET}")
            print(f"  {Colors.DIM}(Note: counts may overlap if files include multiple changed headers){Colors.RESET}")
            for rc, count in sorted(root_causes.items(), key=lambda x: -x[1]):
                print(f"  {Colors.MAGENTA}{rc}{Colors.RESET} → triggered {Colors.BRIGHT}{count}{Colors.RESET} rebuilds")
    except BrokenPipeError:
        # Handle broken pipe gracefully
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return EXIT_SUCCESS
    except Exception as e:
        print(f"\nError during output: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return EXIT_RUNTIME_ERROR
    
    return EXIT_SUCCESS


if __name__ == "__main__":
    from lib.constants import BuildCheckError
    
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print_warning("Interrupted.", prefix=False)
        sys.exit(EXIT_KEYBOARD_INTERRUPT)
    except BuildCheckError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(e.exit_code)
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(EXIT_RUNTIME_ERROR)
