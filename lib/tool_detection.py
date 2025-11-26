#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# ****************************************************************************************************************************************************
# * BSD 3-Clause License
# *
# * Copyright (c) 2025, Mana Battery
# * All rights reserved.
# *
# * Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
# *
# * 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
# * 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the
# *    documentation and/or other materials provided with the distribution.
# * 3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products derived from this
# *    software without specific prior written permission.
# *
# * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# * THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
# * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF
# * LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE,
# * EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
# ****************************************************************************************************************************************************
"""Centralized external tool detection for build-check.

This module provides unified detection for all external tools used by build-check,
including system tools (ninja, clang-scan-deps) and Python development tools (mypy, pylint, pytest).

Tool detection results are cached within the Python process session to avoid repeated
subprocess calls. Detection includes version extraction and command validation.

CLI Interface:
    python3 -m lib.tool_detection --find-<tool>    # Output command name, exit 0/1
    python3 -m lib.tool_detection --check-all      # Output JSON with all tools
    python3 -m lib.tool_detection --verbose        # Enable debug logging
"""

import sys
import json
import shutil
import logging
import argparse
import subprocess
from typing import Optional, Dict, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Tool command variants to try (in order of preference)
CLANG_SCAN_DEPS_COMMANDS = ["clang-scan-deps-20", "clang-scan-deps-19", "clang-scan-deps-18", "clang-scan-deps"]
NINJA_COMMANDS = ["ninja", "ninja-build"]
MYPY_COMMANDS = [["python3", "-m", "mypy"], ["mypy"]]
PYLINT_COMMANDS = [["python3", "-m", "pylint"], ["pylint"]]
PYTEST_COMMANDS = [["python3", "-m", "pytest"], ["pytest"]]
PYTEST_COV_COMMANDS = [["python3", "-m", "pytest_cov"], ["pytest-cov"]]

# Session-level cache for tool detection results (keyed by function name)
_tool_cache: Dict[str, "ToolInfo"] = {}


@dataclass
class ToolInfo:
    """Information about a detected external tool.

    Attributes:
        command: Simple command name for bash compatibility (e.g., "ninja", "python3", "mypy")
        full_command: Full invocation string (e.g., "python3 -m mypy", "ninja")
        version: Raw version string as reported by tool (e.g., "1.11.1", "mypy 1.8.0")
    """

    command: Optional[str]
    full_command: Optional[str]
    version: Optional[str]

    def is_found(self) -> bool:
        """Check if tool was found.

        Returns:
            True if command is not None
        """
        return self.command is not None


def clear_cache() -> None:
    """Clear the tool detection cache.

    Useful for testing or when environment changes during process lifetime.
    """
    global _tool_cache
    _tool_cache.clear()
    logger.debug("Tool detection cache cleared")


def _try_command(cmd_parts: List[str], timeout: int = 5) -> Optional[str]:
    """Try to run a command with --version and return version output.

    Args:
        cmd_parts: Command parts (e.g., ["python3", "-m", "mypy"] or ["ninja"])
        timeout: Timeout in seconds for subprocess call

    Returns:
        Version output string if successful, None otherwise
    """
    try:
        result = subprocess.run(cmd_parts + ["--version"], capture_output=True, text=True, check=True, timeout=timeout)
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _extract_version(output: str) -> str:
    """Extract version string from command output.

    Args:
        output: Raw version output from command

    Returns:
        Cleaned version string (preserves original format)
    """
    # Return first line, stripped
    lines = output.split("\n")
    return lines[0].strip() if lines else output.strip()


def find_clang_scan_deps() -> ToolInfo:
    """Find an available clang-scan-deps executable.

    Tries commands in order: clang-scan-deps-20, clang-scan-deps-19, clang-scan-deps-18, clang-scan-deps

    Returns:
        ToolInfo with command and version if found, or empty ToolInfo if not found
    """
    cache_key = "find_clang_scan_deps"
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    for cmd in CLANG_SCAN_DEPS_COMMANDS:
        logger.debug("Trying %s...", cmd)
        version_output = _try_command([cmd])

        if version_output:
            # Validate command exists in PATH
            if shutil.which(cmd):
                version = _extract_version(version_output)
                logger.debug("Found %s version %s", cmd, version)
                tool_info = ToolInfo(command=cmd, full_command=cmd, version=version)
                _tool_cache[cache_key] = tool_info
                return tool_info
            else:
                logger.debug("%s responded but not in PATH", cmd)
        else:
            logger.debug("%s not found", cmd)

    logger.debug("clang-scan-deps not found")
    tool_info = ToolInfo(command=None, full_command=None, version=None)
    _tool_cache[cache_key] = tool_info
    return tool_info


def find_ninja() -> ToolInfo:
    """Find an available ninja build tool executable.

    Tries commands in order: ninja, ninja-build

    Returns:
        ToolInfo with command and version if found, or empty ToolInfo if not found
    """
    cache_key = "find_ninja"
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    for cmd in NINJA_COMMANDS:
        logger.debug("Trying %s...", cmd)
        version_output = _try_command([cmd])

        if version_output:
            # Validate command exists in PATH
            if shutil.which(cmd):
                version = _extract_version(version_output)
                logger.debug("Found %s version %s", cmd, version)
                tool_info = ToolInfo(command=cmd, full_command=cmd, version=version)
                _tool_cache[cache_key] = tool_info
                return tool_info
            else:
                logger.debug("%s responded but not in PATH", cmd)
        else:
            logger.debug("%s not found", cmd)

    logger.debug("ninja not found")
    tool_info = ToolInfo(command=None, full_command=None, version=None)
    _tool_cache[cache_key] = tool_info
    return tool_info


def find_mypy() -> ToolInfo:
    """Find an available mypy type checker.

    Tries commands in order: python3 -m mypy, mypy

    Returns:
        ToolInfo with command and version if found, or empty ToolInfo if not found
    """
    cache_key = "find_mypy"
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    for cmd_parts in MYPY_COMMANDS:
        cmd_str = " ".join(cmd_parts)
        logger.debug("Trying %s...", cmd_str)
        version_output = _try_command(cmd_parts)

        if version_output:
            # Validate first command part exists in PATH
            if shutil.which(cmd_parts[0]):
                version = _extract_version(version_output)
                logger.debug("Found %s version %s", cmd_str, version)
                tool_info = ToolInfo(command=cmd_parts[0], full_command=cmd_str, version=version)
                _tool_cache[cache_key] = tool_info
                return tool_info
            else:
                logger.debug("%s responded but %s not in PATH", cmd_str, cmd_parts[0])
        else:
            logger.debug("%s not found", cmd_str)

    logger.debug("mypy not found")
    tool_info = ToolInfo(command=None, full_command=None, version=None)
    _tool_cache[cache_key] = tool_info
    return tool_info


def find_pylint() -> ToolInfo:
    """Find an available pylint linter.

    Tries commands in order: python3 -m pylint, pylint

    Returns:
        ToolInfo with command and version if found, or empty ToolInfo if not found
    """
    cache_key = "find_pylint"
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    for cmd_parts in PYLINT_COMMANDS:
        cmd_str = " ".join(cmd_parts)
        logger.debug("Trying %s...", cmd_str)
        version_output = _try_command(cmd_parts)

        if version_output:
            # Validate first command part exists in PATH
            if shutil.which(cmd_parts[0]):
                version = _extract_version(version_output)
                logger.debug("Found %s version %s", cmd_str, version)
                tool_info = ToolInfo(command=cmd_parts[0], full_command=cmd_str, version=version)
                _tool_cache[cache_key] = tool_info
                return tool_info
            else:
                logger.debug("%s responded but %s not in PATH", cmd_str, cmd_parts[0])
        else:
            logger.debug("%s not found", cmd_str)

    logger.debug("pylint not found")
    tool_info = ToolInfo(command=None, full_command=None, version=None)
    _tool_cache[cache_key] = tool_info
    return tool_info


def find_pytest() -> ToolInfo:
    """Find an available pytest test framework.

    Tries commands in order: python3 -m pytest, pytest

    Returns:
        ToolInfo with command and version if found, or empty ToolInfo if not found
    """
    cache_key = "find_pytest"
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    for cmd_parts in PYTEST_COMMANDS:
        cmd_str = " ".join(cmd_parts)
        logger.debug("Trying %s...", cmd_str)
        version_output = _try_command(cmd_parts)

        if version_output:
            # Validate first command part exists in PATH
            if shutil.which(cmd_parts[0]):
                version = _extract_version(version_output)
                logger.debug("Found %s version %s", cmd_str, version)
                tool_info = ToolInfo(command=cmd_parts[0], full_command=cmd_str, version=version)
                _tool_cache[cache_key] = tool_info
                return tool_info
            else:
                logger.debug("%s responded but %s not in PATH", cmd_str, cmd_parts[0])
        else:
            logger.debug("%s not found", cmd_str)

    logger.debug("pytest not found")
    tool_info = ToolInfo(command=None, full_command=None, version=None)
    _tool_cache[cache_key] = tool_info
    return tool_info


def find_pytest_cov() -> ToolInfo:
    """Find an available pytest-cov coverage plugin.

    Tries commands in order: python3 -m pytest_cov, pytest-cov

    Returns:
        ToolInfo with command and version if found, or empty ToolInfo if not found
    """
    cache_key = "find_pytest_cov"
    if cache_key in _tool_cache:
        return _tool_cache[cache_key]

    for cmd_parts in PYTEST_COV_COMMANDS:
        cmd_str = " ".join(cmd_parts)
        logger.debug("Trying %s...", cmd_str)
        version_output = _try_command(cmd_parts)

        if version_output:
            # Validate first command part exists in PATH
            if shutil.which(cmd_parts[0]):
                version = _extract_version(version_output)
                logger.debug("Found %s version %s", cmd_str, version)
                tool_info = ToolInfo(command=cmd_parts[0], full_command=cmd_str, version=version)
                _tool_cache[cache_key] = tool_info
                return tool_info
            else:
                logger.debug("%s responded but %s not in PATH", cmd_str, cmd_parts[0])
        else:
            logger.debug("%s not found", cmd_str)

    logger.debug("pytest-cov not found")
    tool_info = ToolInfo(command=None, full_command=None, version=None)
    _tool_cache[cache_key] = tool_info
    return tool_info


def check_all_tools() -> Dict[str, Dict[str, str]]:
    """Check all known tools and return their status.

    Returns:
        Dictionary with tool names as keys, each containing command and version.
        Missing tools are omitted from the result.
    """
    tools: Dict[str, Dict[str, str]] = {}

    # Check all tools
    tool_checks = [
        ("clang-scan-deps", find_clang_scan_deps),
        ("ninja", find_ninja),
        ("mypy", find_mypy),
        ("pylint", find_pylint),
        ("pytest", find_pytest),
        ("pytest-cov", find_pytest_cov),
    ]

    for tool_name, find_func in tool_checks:
        tool_info = find_func()
        if tool_info.is_found():
            assert tool_info.command is not None  # For type checker
            tools[tool_name] = {"command": tool_info.command, "version": tool_info.version or "unknown"}

    return tools


def main() -> int:
    """Main entry point for CLI usage.

    Returns:
        Exit code: 0 if tool found (or check-all succeeds), 1 if not found
    """
    parser = argparse.ArgumentParser(description="Detect external tools for build-check", formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument("--find-clang-scan-deps", action="store_true", help="Find clang-scan-deps command")
    parser.add_argument("--find-ninja", action="store_true", help="Find ninja build tool")
    parser.add_argument("--find-mypy", action="store_true", help="Find mypy type checker")
    parser.add_argument("--find-pylint", action="store_true", help="Find pylint linter")
    parser.add_argument("--find-pytest", action="store_true", help="Find pytest test framework")
    parser.add_argument("--find-pytest-cov", action="store_true", help="Find pytest-cov plugin")
    parser.add_argument("--check-all", action="store_true", help="Check all tools and output JSON")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose debug logging")

    args = parser.parse_args()

    # Configure logging
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(message)s", stream=sys.stderr)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Handle --check-all
    if args.check_all:
        tools = check_all_tools()
        output = {"tools": tools}
        print(json.dumps(output, indent=2))
        return 0

    # Handle individual tool checks
    tool_map = {
        "find_clang_scan_deps": (args.find_clang_scan_deps, find_clang_scan_deps),
        "find_ninja": (args.find_ninja, find_ninja),
        "find_mypy": (args.find_mypy, find_mypy),
        "find_pylint": (args.find_pylint, find_pylint),
        "find_pytest": (args.find_pytest, find_pytest),
        "find_pytest_cov": (args.find_pytest_cov, find_pytest_cov),
    }

    for flag_name, (flag_value, find_func) in tool_map.items():
        if flag_value:
            tool_info = find_func()
            if tool_info.is_found():
                print(tool_info.command)
                return 0
            else:
                # Output nothing for not found
                return 1

    # No arguments provided
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
