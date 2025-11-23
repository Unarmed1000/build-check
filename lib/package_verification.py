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
"""Centralized package verification for build-check dependencies.

This module provides version checking and validation for all runtime dependencies.
Each lib module should export a verify_requirements() function that uses these
utilities to validate its dependencies at import time.

Minimum versions are based on Ubuntu 24.04 LTS or actual code requirements,
whichever is higher.
"""

import sys
import logging
import argparse
from typing import Tuple, Optional, Dict

# Enforce Python 3.8+ before any other imports
if sys.version_info < (3, 8):
    print(
        f"Error: Python 3.8 or higher is required. You have Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}", file=sys.stderr
    )
    print("Upgrade Python with: sudo apt-get install python3.8 python3.8-dev", file=sys.stderr)
    sys.exit(1)

# Bootstrap check for packaging library (required for version comparison)
try:
    from importlib.metadata import version, PackageNotFoundError
    from packaging.version import parse
except ImportError as e:
    print("Error: 'packaging' library is required for build-check.", file=sys.stderr)
    print("Install with: pip install packaging>=24.0", file=sys.stderr)
    print(f"Technical details: {e}", file=sys.stderr)
    sys.exit(1)

from lib.color_utils import print_error, print_warning, print_success
from lib.constants import EXIT_RUNTIME_ERROR

logger = logging.getLogger(__name__)

# Package version requirements (minimum versions)
# Based on max(Ubuntu 24.04 LTS, actual code requirements)
PACKAGE_REQUIREMENTS: Dict[str, str] = {
    "networkx": "2.8.8",  # Ubuntu 24.04 LTS (code needs 2.6+ for minimum_feedback_arc_set)
    "GitPython": "3.1.40",  # Max of Ubuntu 24.04 (3.1.37) and existing requirement (3.1.40)
    "packaging": "24.0",  # Ubuntu 24.04 LTS (required for this module itself)
    "colorama": "0.4.6",  # Ubuntu 24.04 LTS (optional - for colored output only)
}

# Optional packages that enhance performance but are not required
OPTIONAL_PACKAGES: Dict[str, str] = {"scipy": "1.11.4"}  # Ubuntu 24.04 LTS (optional - improves NetworkX PageRank performance)


def check_package_version(package_name: str, min_version: Optional[str] = None, raise_on_error: bool = True) -> Tuple[bool, bool, Optional[str]]:
    """Check if a package is installed and meets minimum version requirement.

    Args:
        package_name: PyPI package name (e.g., 'GitPython', 'networkx')
        min_version: Minimum required version string (e.g., '3.1.40').
                    If None, uses PACKAGE_REQUIREMENTS if available.
        raise_on_error: If True, raises ImportError on failure

    Returns:
        Tuple of (is_installed: bool, meets_version: bool, installed_version: str or None)

    Raises:
        ImportError: If raise_on_error=True and package is missing or too old

    Example:
        >>> check_package_version('networkx', '2.8.8')
        (True, True, '3.2.1')
    """
    # Use registry if min_version not specified
    if min_version is None:
        min_version = PACKAGE_REQUIREMENTS.get(package_name)
        if min_version is None:
            raise ValueError(f"No version requirement specified for {package_name}")

    try:
        installed_version = version(package_name)
        meets_version = parse(installed_version) >= parse(min_version)

        if not meets_version and raise_on_error:
            raise ImportError(
                f"{package_name} {installed_version} is too old. "
                f"Version >={min_version} is required. "
                f"Upgrade with: pip install --upgrade '{package_name}>={min_version}'"
            )

        return True, meets_version, installed_version

    except PackageNotFoundError as exc:
        if raise_on_error:
            raise ImportError(f"{package_name} is not installed. " f"Install with: pip install '{package_name}>={min_version}'") from exc
        return False, False, None


def require_package(package_name: str, context: str = "this tool") -> None:
    """Check if a package is available with correct version, exit with helpful message if not.

    This should be called at the start of scripts that require specific packages.
    Exits the process with EXIT_RUNTIME_ERROR if package is missing or too old.

    Args:
        package_name: PyPI package name (e.g., 'networkx', 'GitPython')
        context: Description of what needs the package (e.g., "DSM analysis", "git operations")

    Exits:
        With EXIT_RUNTIME_ERROR (2) if package is missing or too old

    Example:
        >>> require_package('networkx', 'dependency graph analysis')
    """
    min_ver = PACKAGE_REQUIREMENTS.get(package_name)
    if min_ver is None:
        print_error(f"Unknown package '{package_name}' - no version requirement defined")
        sys.exit(EXIT_RUNTIME_ERROR)

    try:
        installed_version = version(package_name)
        if parse(installed_version) < parse(min_ver):
            print_error(f"{package_name} {installed_version} is too old for {context}.")
            print(f"Version >={min_ver} is required.", file=sys.stderr)
            print(f"Upgrade with: pip install --upgrade '{package_name}>={min_ver}'", file=sys.stderr)
            sys.exit(EXIT_RUNTIME_ERROR)
    except PackageNotFoundError:
        print_error(f"{package_name} is required for {context}.")
        print(f"Install with: pip install '{package_name}>={min_ver}'", file=sys.stderr)
        sys.exit(EXIT_RUNTIME_ERROR)


def check_all_packages() -> bool:
    """Check all known runtime packages and display status.

    This is used by checkEnvironment.sh to validate the environment.
    Checks packages in dependency order (packaging first).

    Returns:
        True if all required packages are OK, False otherwise
    """
    print("🔍 BuildCheck Package Verification")
    print("=" * 40)
    print()

    all_ok = True

    # Check packaging first (required for this module)
    print("Checking packaging library...")
    try:
        is_installed, meets_version, installed_ver = check_package_version("packaging", PACKAGE_REQUIREMENTS["packaging"], raise_on_error=False)
        if is_installed and meets_version:
            print_success(f"packaging {installed_ver}", prefix=False)
        elif is_installed:
            print_error(f"packaging {installed_ver} (need >={PACKAGE_REQUIREMENTS['packaging']})", prefix=False)
            all_ok = False
        else:
            print_error("packaging not installed", prefix=False)
            all_ok = False
    except Exception as e:
        print_error(f"packaging check failed: {e}", prefix=False)
        all_ok = False

    # Check other required packages
    for pkg_name in ["networkx", "GitPython"]:
        print(f"Checking {pkg_name}...")
        try:
            is_installed, meets_version, installed_ver = check_package_version(pkg_name, PACKAGE_REQUIREMENTS[pkg_name], raise_on_error=False)
            if is_installed and meets_version:
                print_success(f"{pkg_name} {installed_ver}", prefix=False)
            elif is_installed:
                print_error(f"{pkg_name} {installed_ver} (need >={PACKAGE_REQUIREMENTS[pkg_name]})", prefix=False)
                all_ok = False
            else:
                print_error(f"{pkg_name} not installed", prefix=False)
                all_ok = False
        except Exception as e:
            print_error(f"{pkg_name} check failed: {e}", prefix=False)
            all_ok = False

    # Check optional packages (colorama)
    print("Checking colorama (optional)...")
    try:
        is_installed, meets_version, installed_ver = check_package_version("colorama", PACKAGE_REQUIREMENTS["colorama"], raise_on_error=False)
        if is_installed and meets_version:
            print_success(f"colorama {installed_ver}", prefix=False)
        elif is_installed:
            print_warning(f"colorama {installed_ver} (recommended >={PACKAGE_REQUIREMENTS['colorama']})", prefix=False)
        else:
            print_warning("colorama not installed (optional, for colored output)", prefix=False)
    except Exception as e:
        print_warning(f"colorama check failed: {e}", prefix=False)

    # Check scipy (optional for NetworkX performance)
    print("Checking scipy (optional)...")
    try:
        is_installed, meets_version, installed_ver = check_package_version("scipy", OPTIONAL_PACKAGES["scipy"], raise_on_error=False)
        if is_installed and meets_version:
            print_success(f"scipy {installed_ver}", prefix=False)
        elif is_installed:
            print_warning(f"scipy {installed_ver} (recommended >={OPTIONAL_PACKAGES['scipy']})", prefix=False)
        else:
            print_warning("scipy not installed (optional, improves NetworkX PageRank performance)", prefix=False)
    except Exception as e:
        print_warning(f"scipy check failed: {e}", prefix=False)

    print()
    print("=" * 40)
    if all_ok:
        print_success("All required packages are available", prefix=False)
        return True

    print_error("Some required packages are missing or too old", prefix=False)
    print()
    print("Install missing packages with:")
    print("  pip install networkx>=2.8.8 GitPython>=3.1.40 packaging>=24.0")
    print()
    print("Optional packages (recommended):")
    print("  pip install colorama>=0.4.6 scipy>=1.11.4")
    return False


def main() -> int:
    """Main entry point for CLI usage.

    Returns:
        Exit code: 0 for success, 1 for failures
    """
    parser = argparse.ArgumentParser(description="Verify build-check package dependencies", formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check-all", action="store_true", help="Check all known runtime packages")

    args = parser.parse_args()

    if args.check_all:
        success = check_all_packages()
        return 0 if success else 1

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
