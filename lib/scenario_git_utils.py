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
"""Git repository generation utilities for scenario testing.

This module provides utilities to generate physical git repositories from
abstract dependency graphs for testing git-based architectural analysis.
"""

import os
import subprocess
from typing import DefaultDict, Dict, List, Set


def infer_namespace_from_path(header_path: str) -> str:
    """Extract namespace from header file path.

    Args:
        header_path: Path like "Engine/Core.hpp" or "Utils/Logger.hpp"

    Returns:
        Namespace string like "Engine" or "Utils"

    Examples:
        >>> infer_namespace_from_path("Engine/Core.hpp")
        'Engine'
        >>> infer_namespace_from_path("Graphics/Shader.hpp")
        'Graphics'
    """
    # Extract the directory/module name before the filename
    parts = header_path.split("/")
    if len(parts) >= 2:
        return parts[0]
    return "Global"


def generate_header_content(header_path: str, dependencies: Set[str]) -> str:
    """Generate C++ header file content from dependencies.

    Creates a minimal valid C++ header with:
    - Header guards (#pragma once)
    - #include directives for all dependencies
    - Namespace matching the module path
    - Minimal class stub

    Args:
        header_path: Path like "Engine/Core.hpp"
        dependencies: Set of header paths this header depends on

    Returns:
        Complete C++ header file content as string

    Example:
        >>> deps = {"Utils/Logger.hpp", "Graphics/Texture.hpp"}
        >>> content = generate_header_content("Game/Player.hpp", deps)
        >>> "#pragma once" in content
        True
        >>> "namespace Game" in content
        True
    """
    # Extract class name from path
    filename = header_path.split("/")[-1]
    class_name = filename.replace(".hpp", "").replace(".h", "")
    namespace = infer_namespace_from_path(header_path)

    lines = ["#pragma once"]

    # Add includes
    for dep in sorted(dependencies):
        lines.append(f'#include "{dep}"')

    if dependencies:
        lines.append("")  # Blank line after includes

    # Add namespace and minimal class
    lines.append(f"namespace {namespace} {{")
    lines.append(f"    class {class_name} {{")
    lines.append("    public:")
    lines.append(f"        {class_name}() = default;")
    lines.append(f"        ~{class_name}() = default;")
    lines.append("    };")
    lines.append("}")
    lines.append("")  # Trailing newline

    return "\n".join(lines)


def generate_source_content(cpp_path: str, header_path: str) -> str:
    """Generate C++ source file content.

    Creates a minimal .cpp file that includes its header.

    Args:
        cpp_path: Path like "src/Engine/Core.cpp" (unused but for signature consistency)
        header_path: Path like "Engine/Core.hpp"

    Returns:
        Complete C++ source file content as string

    Example:
        >>> content = generate_source_content("src/Core.cpp", "Engine/Core.hpp")
        >>> '#include "Engine/Core.hpp"' in content
        True
    """
    lines = [f'#include "{header_path}"', "", f"// Source file for {header_path}", ""]
    return "\n".join(lines)


def create_physical_file_structure(
    repo_path: str, all_headers: Set[str], header_to_headers: DefaultDict[str, Set[str]], source_to_deps: Dict[str, List[str]]
) -> None:
    """Create physical file structure from dependency graphs.

    Writes all .hpp and .cpp files to disk with proper directory structure.

    Args:
        repo_path: Root path of repository
        all_headers: Set of all header paths (e.g., {"Engine/Core.hpp", ...})
        header_to_headers: Mapping of headers to their dependencies
        source_to_deps: Mapping of source files to headers they include

    Directory structure created:
        repo_path/
            include/
                Engine/
                    Core.hpp
                    Renderer.hpp
                Graphics/
                    Shader.hpp
            src/
                Engine/
                    Core.cpp
    """
    include_dir = os.path.join(repo_path, "include")
    src_dir = os.path.join(repo_path, "src")

    # Create headers
    for header in all_headers:
        header_file_path = os.path.join(include_dir, header)
        os.makedirs(os.path.dirname(header_file_path), exist_ok=True)

        dependencies = header_to_headers.get(header, set())
        content = generate_header_content(header, dependencies)

        with open(header_file_path, "w") as f:
            f.write(content)

    # Create source files
    for source_file, deps in source_to_deps.items():
        # Source files are like "Engine/Core.cpp", map to src directory
        source_file_path = os.path.join(src_dir, source_file)
        os.makedirs(os.path.dirname(source_file_path), exist_ok=True)

        # First dependency is typically the header itself
        header_path = deps[0] if deps else ""
        content = generate_source_content(source_file, header_path)

        with open(source_file_path, "w") as f:
            f.write(content)


def generate_build_ninja(build_dir: str, source_files: List[str], include_dir: str) -> None:
    """Generate build.ninja file directly (no CMake).

    Creates a minimal ninja build file with compilation rules for all source files.
    Includes implicit header dependencies (like real CMake-generated build.ninja).

    Args:
        build_dir: Path to build directory
        source_files: List of source file paths like "Engine/Core.cpp" (without src/ prefix)
        include_dir: Path to include directory

    Example build.ninja content:
        rule cxx
          command = clang++ -std=c++17 -I$include_dir -c $in -o $out

        build obj/Engine/Core.o: cxx src/Engine/Core.cpp | include/Engine/Core.hpp
    """
    ninja_path = os.path.join(build_dir, "build.ninja")
    os.makedirs(build_dir, exist_ok=True)

    lines = [
        "# Generated build.ninja for scenario testing",
        "",
        "rule cxx",
        f"  command = clang++ -std=c++17 -I{include_dir} -c $in -o $out",
        "  description = Compiling $in",
        "",
    ]

    # Add build rules for each source file with implicit header dependencies
    for source_file in source_files:
        # Ensure source_file has src/ prefix
        if not source_file.startswith("src/"):
            source_file = f"src/{source_file}"

        # Convert src/Engine/Core.cpp -> obj/Engine/Core.o
        obj_file = source_file.replace("src/", "obj/").replace(".cpp", ".o")

        # Derive corresponding header file: src/Engine/Core.cpp -> include/Engine/Core.hpp
        header_file = source_file.replace("src/", "include/").replace(".cpp", ".hpp")

        # Add build rule with implicit header dependency (after |)
        # Format: build output: rule explicit_input | implicit_input1 implicit_input2
        lines.append(f"build {obj_file}: cxx {source_file} | {header_file}")

    lines.append("")  # Trailing newline

    with open(ninja_path, "w") as f:
        f.write("\n".join(lines))


def generate_compile_commands_from_ninja(build_dir: str) -> None:
    """Generate compile_commands.json from build.ninja using ninja tool.

    Args:
        build_dir: Path to build directory containing build.ninja

    Raises:
        RuntimeError: If ninja command fails
    """
    try:
        # Generate compile_commands.json using ninja -t compdb with the cxx rule
        result = subprocess.run(["ninja", "-t", "compdb", "cxx"], cwd=build_dir, capture_output=True, text=True, check=True)

        compile_commands_path = os.path.join(build_dir, "compile_commands.json")
        with open(compile_commands_path, "w") as f:
            f.write(result.stdout)

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to generate compile_commands.json: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError("ninja command not found. Please install ninja build system.") from None


def setup_git_repo(repo_path: str) -> None:
    """Initialize git repository with configuration.

    Args:
        repo_path: Path to repository directory

    Raises:
        RuntimeError: If git commands fail
    """
    try:
        subprocess.run(["git", "init"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to setup git repo: {e.stderr}") from e
    except FileNotFoundError:
        raise RuntimeError("git command not found. Please install git.") from None


def commit_all_files(repo_path: str, message: str) -> None:
    """Stage and commit all files in repository.

    Args:
        repo_path: Path to repository directory
        message: Commit message

    Raises:
        RuntimeError: If git commands fail
    """
    try:
        subprocess.run(["git", "add", "-A"], cwd=repo_path, capture_output=True, check=True)
        subprocess.run(["git", "commit", "-m", message], cwd=repo_path, capture_output=True, check=True)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Failed to commit files: {e.stderr}") from e
