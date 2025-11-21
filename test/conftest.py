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
"""Pytest configuration and shared fixtures for BuildCheck tests."""
import os
import sys
import json
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Tuple
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    tmpdir = tempfile.mkdtemp(prefix="buildcheck_test_")
    yield tmpdir
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def mock_build_dir(temp_dir):
    """Create a mock ninja build directory with build.ninja."""
    build_dir = Path(temp_dir) / "build" / "release"
    build_dir.mkdir(parents=True, exist_ok=True)
    
    # Create build.ninja
    build_ninja = build_dir / "build.ninja"
    build_ninja.write_text("""
rule CXX_COMPILER
  command = g++ -c $in -o $out

build main.cpp.o: CXX_COMPILER ../src/main.cpp
build utils.cpp.o: CXX_COMPILER ../src/utils.cpp

build app: phony main.cpp.o utils.cpp.o
""")
    
    return str(build_dir)


@pytest.fixture
def mock_compile_commands(mock_build_dir):
    """Create a mock compile_commands.json in the build directory."""
    compile_commands = [
        {
            "directory": mock_build_dir,
            "command": "g++ -c -o main.cpp.o ../src/main.cpp",
            "file": "../src/main.cpp"
        },
        {
            "directory": mock_build_dir,
            "command": "g++ -c -o utils.cpp.o ../src/utils.cpp",
            "file": "../src/utils.cpp"
        }
    ]
    
    compile_db_path = Path(mock_build_dir) / "compile_commands.json"
    with open(compile_db_path, 'w') as f:
        json.dump(compile_commands, f, indent=2)
    
    return str(compile_db_path)


@pytest.fixture
def mock_source_files(temp_dir):
    """Create mock C++ source files."""
    src_dir = Path(temp_dir) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    
    # Create header files
    (src_dir / "utils.hpp").write_text("""
#ifndef UTILS_HPP
#define UTILS_HPP

int add(int a, int b);

#endif
""")
    
    (src_dir / "config.hpp").write_text("""
#ifndef CONFIG_HPP
#define CONFIG_HPP

#define VERSION "1.0.0"

#endif
""")
    
    # Create source files
    (src_dir / "main.cpp").write_text("""
#include "utils.hpp"
#include "config.hpp"

int main() {
    return add(1, 2);
}
""")
    
    (src_dir / "utils.cpp").write_text("""
#include "utils.hpp"

int add(int a, int b) {
    return a + b;
}
""")
    
    return str(src_dir)


@pytest.fixture
def mock_git_repo(temp_dir, mock_source_files):
    """Create a mock git repository."""
    import subprocess
    
    repo_dir = temp_dir
    
    try:
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], 
                      cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], 
                      cwd=repo_dir, check=True, capture_output=True)
        
        # Add files and commit
        subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], 
                      cwd=repo_dir, check=True, capture_output=True)
        
        # Make a change to utils.hpp
        utils_hpp = Path(mock_source_files) / "utils.hpp"
        utils_hpp.write_text("""
#ifndef UTILS_HPP
#define UTILS_HPP

int add(int a, int b);
int subtract(int a, int b);  // Added function

#endif
""")
        
        subprocess.run(["git", "add", "src/utils.hpp"], cwd=repo_dir, 
                      check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "Add subtract function"], 
                      cwd=repo_dir, check=True, capture_output=True)
        
        yield repo_dir
        
    except subprocess.CalledProcessError as e:
        pytest.skip(f"Git not available or failed: {e}")


@pytest.fixture
def mock_ninja_explain_output():
    """Mock output from ninja -n -d explain."""
    return """
ninja explain: output main.cpp.o doesn't exist
ninja explain: output utils.cpp.o is dirty
ninja explain: src/utils.hpp is dirty
ninja explain: output utils.cpp.o older than most recent input src/utils.hpp (1234567890 vs 1234567891)
[1/2] Building CXX object main.cpp.o
[2/2] Building CXX object utils.cpp.o
"""


def create_mock_clang_scan_deps_output(source_files: List[str], 
                                       dependencies: Dict[str, List[str]]) -> str:
    """Create mock output from clang-scan-deps in makefile format.
    
    Args:
        source_files: List of source file paths
        dependencies: Dict mapping source files to their header dependencies
    
    Returns:
        Mock makefile-format output
    """
    output = []
    for source in source_files:
        deps = dependencies.get(source, [])
        output.append(f"{source}.o: {source} \\\n  " + " \\\n  ".join(deps))
    return "\n".join(output)
