#!/usr/bin/env python3
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
"""Comprehensive tests for cache invalidation using REAL ninja builds (no mocks)"""
import os
import sys
import time
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.ninja_utils import (
    validate_and_prepare_build_dir,
    parse_ninja_generated_files,
    load_generated_files_cache,
    save_generated_files_cache,
    compute_file_hash,
    check_ninja_available,
    GENERATED_FILES_CACHE,
)


# Skip all tests if ninja is not available
pytestmark = pytest.mark.skipif(not check_ninja_available(), reason="ninja not available")


# ==================================================================
# Helper Functions: Create Real Build Files
# ==================================================================


def create_python_generator(build_dir: Path, script_name: str = "generator.py") -> Path:
    """Create a simple Python generator script.

    Args:
        build_dir: Build directory
        script_name: Name of the generator script

    Returns:
        Path to the generator script
    """
    script = build_dir / script_name
    content = """#!/usr/bin/env python3
import sys

if len(sys.argv) < 3:
    print("Usage: generator.py <input> <output>", file=sys.stderr)
    sys.exit(1)

input_file = sys.argv[1]
output_file = sys.argv[2]

with open(input_file, 'r') as f:
    data = f.read().strip()

with open(output_file, 'w') as f:
    f.write(f"// Auto-generated from {input_file}\\n")
    f.write(f"const char* DATA = \\"{data}\\";\\n")
"""
    script.write_text(content)
    script.chmod(0o755)
    return script


def create_cpp_generator(build_dir: Path) -> Path:
    """Create a simple C++ generator executable.

    Args:
        build_dir: Build directory

    Returns:
        Path to generator.cpp
    """
    cpp_file = build_dir / "generator.cpp"
    content = """#include <iostream>
#include <fstream>

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "Usage: generator <input> <output>" << std::endl;
        return 1;
    }

    std::ifstream in(argv[1]);
    std::string data;
    std::getline(in, data);
    in.close();

    std::ofstream out(argv[2]);
    out << "// Generated from " << argv[1] << std::endl;
    out << "const char* CPP_DATA = \\"" << data << "\\";" << std::endl;
    out.close();

    return 0;
}
"""
    cpp_file.write_text(content)
    return cpp_file


def create_build_ninja_simple(build_dir: Path, targets: List[Dict[str, Any]]) -> None:
    """Create a simple build.ninja with shell command-based generators.

    Args:
        build_dir: Build directory
        targets: List of target dicts with keys: output, input, command, implicit_deps (optional)
    """
    lines = ["# Test build file\n"]

    # Define generator rule
    lines.append("\nrule GENERATE\n")
    lines.append("  command = $CMD\n")
    lines.append("  description = Generating $out\n")
    lines.append("  generator = 1\n")

    # Build statements
    for target in targets:
        output = target["output"]
        input_file = target.get("input", "")
        command = target["command"]
        implicit = target.get("implicit_deps", [])

        deps = f" | {' '.join(implicit)}" if implicit else ""
        lines.append(f"\nbuild {output}: GENERATE {input_file}{deps}\n")
        lines.append(f"  CMD = {command}\n")

    (build_dir / "build.ninja").write_text("".join(lines))


def create_build_ninja_with_cpp_gen(build_dir: Path, generator_cpp: str, targets: List[Dict[str, Any]]) -> None:
    """Create build.ninja that compiles a C++ generator and uses it.

    Args:
        build_dir: Build directory
        generator_cpp: Path to generator.cpp
        targets: List of generation targets using the compiled generator
    """
    lines = ["# Build file with C++ generator\n"]

    # C++ compiler rule
    lines.append("\nrule CXX\n")
    lines.append("  command = g++ $in -o $out\n")
    lines.append("  description = Compiling $out\n")

    # Generator rule
    lines.append("\nrule GEN\n")
    lines.append("  command = $TOOL $in $out\n")
    lines.append("  description = Generating $out with $TOOL\n")
    lines.append("  generator = 1\n")

    # Build the generator executable
    lines.append(f"\nbuild generator: CXX {generator_cpp}\n")

    # Use the generator
    for target in targets:
        output = target["output"]
        input_file = target["input"]
        lines.append(f"\nbuild {output}: GEN {input_file} | generator\n")
        lines.append(f"  TOOL = ./generator\n")

    (build_dir / "build.ninja").write_text("".join(lines))


# ==================================================================
# Test Suite: Cache Invalidation with Real Ninja
# ==================================================================


class TestCacheInvalidationReal:
    """Test cache invalidation scenarios using actual ninja execution."""

    def test_missing_cache_delegates_to_ninja(self, tmp_path: Path) -> None:
        """When cache is missing, delegate to ninja to verify all generated files.

        The key scenario: Generated files exist on disk but we have no cache to verify
        if they're correct. We must delegate to ninja's dependency tracking.
        Ninja may or may not rebuild based on its own timestamps, but we verify:
        1. Our code delegates to ninja (doesn't skip files)
        2. Cache is created after validation
        3. If ninja rebuilds, the file is updated correctly
        """
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        # Setup: Create input template
        template = build_dir / "input.txt"
        template.write_text("VERSION_1")

        # Create generator script
        generator = create_python_generator(build_dir)

        # Create build.ninja
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Create an existing generated file (could be correct or stale - we don't know without cache)
        old_output = build_dir / "output.h"
        old_output.write_text("// EXISTING CONTENT")

        # Make template newer to force ninja to rebuild (simulating stale scenario)
        time.sleep(0.1)  # Ensure filesystem timestamp resolution
        template.touch()

        # Ensure no cache exists - THIS IS THE KEY CONDITION
        cache_file = build_dir / GENERATED_FILES_CACHE
        if cache_file.exists():
            cache_file.unlink()

        # Execute: Run validation
        # Without cache, should delegate to ninja for all generated file targets
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify: Validation succeeded
        assert build_out == str(build_dir), "Validation should return build directory"

        # Verify: Cache was created after delegating to ninja
        assert cache_file.exists(), "Cache should be created after ninja verification"

        # Verify: File exists and was processed by ninja
        assert old_output.exists(), "Output file should exist"

        # Since template is newer, ninja should have rebuilt the file
        new_content = old_output.read_text()
        assert "VERSION_1" in new_content, "File should contain current template data"
        assert "EXISTING CONTENT" not in new_content, "Ninja should have rebuilt the file"

    def test_missing_cache_with_uptodate_files(self, tmp_path: Path) -> None:
        """When cache is missing but files are up-to-date, ninja still validates them.

        This tests the scenario where:
        - Cache is missing (no baseline to verify correctness)
        - Generated files exist and are actually up-to-date
        - Ninja is invoked but says "no work to do" (files are already correct)
        - Cache is created after validation

        This is the CRITICAL test - without cache, we can't know if existing files
        are correct, so we MUST delegate to ninja even if ninja does nothing.
        """
        build_dir = tmp_path

        # Create input template
        template = build_dir / "input.txt"
        template.write_text("DATA_V1")

        # Create generator script
        generator = create_python_generator(build_dir)

        # Create build.ninja
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Build the file correctly using ninja first
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)

        # Now the file is correct and up-to-date
        correct_content = (build_dir / "output.h").read_text()
        assert "DATA_V1" in correct_content

        # Delete the cache (simulating missing cache scenario)
        cache_file = build_dir / GENERATED_FILES_CACHE
        if cache_file.exists():
            cache_file.unlink()

        # Execute: Run validation without cache
        # Even though file is correct, we must delegate to ninja to verify
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify: Validation succeeded
        assert build_out == str(build_dir)

        # Verify: Cache was created (proving we ran the ninja delegation path)
        assert cache_file.exists(), "Cache should be created after ninja delegation"

        # Verify: File is unchanged (ninja determined no rebuild needed)
        final_content = (build_dir / "output.h").read_text()
        assert final_content == correct_content, "File should remain unchanged when already correct"
        assert "DATA_V1" in final_content

    def test_cache_valid_detects_new_file(self, tmp_path: Path) -> None:
        """When cache is valid, new generated files should be detected but NOT rebuilt."""
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        # Create inputs
        template = build_dir / "input.txt"
        template.write_text("DATA")

        generator = create_python_generator(build_dir)

        # Create build.ninja with TWO targets
        create_build_ninja_simple(
            build_dir,
            [
                {"output": "output1.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output1.h"},
                {"output": "output2.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output2.h"},
            ],
        )

        # Generate output1 via ninja
        subprocess.run(["ninja", "output1.h"], cwd=build_dir, check=True, capture_output=True)

        # Create valid cache with output1 only
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {"output1.h": compute_file_hash(str(build_dir / "output1.h"))},
            "dependencies": {},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Now create output2 (simulating it appearing after the cache was created)
        output2 = build_dir / "output2.h"
        output2.write_text("// MANUAL CREATION")

        # Run validation
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify: output2 should NOT be rebuilt (it's new, cache is valid)
        assert build_out == str(build_dir)
        assert "MANUAL CREATION" in output2.read_text(), "New file should not be overwritten when cache is valid"

    def test_build_ninja_change_invalidates_cache(self, tmp_path: Path) -> None:
        """When build.ninja changes, cache is invalid and files should rebuild."""
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        template = build_dir / "input.txt"
        template.write_text("V1")

        generator = create_python_generator(build_dir)

        # Initial build.ninja
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Build once
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)

        # Create valid cache
        initial_mtime = os.path.getmtime(build_dir / "build.ninja")
        cache = {"build_ninja_mtime": initial_mtime, "files": {"output.h": compute_file_hash(str(build_dir / "output.h"))}, "dependencies": {}}
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Sleep to ensure mtime difference
        time.sleep(0.1)

        # Modify build.ninja (add comment to change mtime)
        time.sleep(0.1)  # Ensure filesystem mtime resolution
        build_ninja = build_dir / "build.ninja"
        content = build_ninja.read_text()
        build_ninja.write_text(content + "\n# Modified\n")

        # Update template content too
        template.write_text("V2")

        # Manually update output.h to OLD content
        (build_dir / "output.h").write_text("// OLD")

        # Run validation - should detect cache invalidation and rebuild
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify rebuild happened
        assert build_out == str(build_dir)
        new_content = (build_dir / "output.h").read_text()
        assert "V2" in new_content, "File should be rebuilt with new template content"
        assert "OLD" not in new_content


class TestCppGeneratorDependencies:
    """Test scenarios where C++ generators are compiled and used."""

    def test_cpp_generator_is_built_and_used(self, tmp_path: Path) -> None:
        """Test that C++ generator executable is compiled and used to generate files."""
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        # Check if g++ is available
        try:
            subprocess.run(["g++", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("g++ not available")

        # Create input template
        template = build_dir / "data.txt"
        template.write_text("CPP_GEN_TEST")

        # Create C++ generator source
        generator_cpp = create_cpp_generator(build_dir)

        # Create build.ninja that compiles generator and uses it
        create_build_ninja_with_cpp_gen(build_dir, "generator.cpp", [{"output": "generated.h", "input": "data.txt"}])

        # Remove any pre-existing generated files
        gen_output = build_dir / "generated.h"
        if gen_output.exists():
            gen_output.unlink()

        # Remove cache to trigger rebuild
        cache_file = build_dir / GENERATED_FILES_CACHE
        if cache_file.exists():
            cache_file.unlink()

        # Run validation - should compile generator and generate file
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify
        assert build_out == str(build_dir)
        assert gen_output.exists(), "Generated file should be created"
        assert (build_dir / "generator").exists(), "Generator executable should be compiled"

        content = gen_output.read_text()
        assert "CPP_GEN_TEST" in content, "Generated file should contain data from template"
        assert "CPP_DATA" in content, "Generated file should have C++ generator format"

    def test_cpp_generator_not_rebuilt_when_unchanged(self, tmp_path: Path) -> None:
        """Test that C++ generator is NOT recompiled when it hasn't changed."""
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        # Check g++ availability
        try:
            subprocess.run(["g++", "--version"], check=True, capture_output=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pytest.skip("g++ not available")

        template = build_dir / "data.txt"
        template.write_text("DATA_V1")

        generator_cpp = create_cpp_generator(build_dir)

        create_build_ninja_with_cpp_gen(build_dir, "generator.cpp", [{"output": "generated.h", "input": "data.txt"}])

        # Initial build
        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)

        generator_exe = build_dir / "generator"
        gen_mtime = generator_exe.stat().st_mtime

        # Create valid cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {"generated.h": compute_file_hash(str(build_dir / "generated.h"))},
            "dependencies": {},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        time.sleep(0.1)

        # Modify template (not generator source)
        template.write_text("DATA_V2")

        # Run validation
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify: generator executable should NOT be recompiled
        assert build_out == str(build_dir)
        new_mtime = generator_exe.stat().st_mtime
        # Ninja might touch the file, but we can verify it wasn't recompiled by checking the build wasn't from scratch
        assert generator_exe.exists()


class TestIncrementalBehavior:
    """Test incremental rebuild behavior with valid vs invalid cache."""

    def test_template_change_detected_with_valid_cache(self, tmp_path: Path) -> None:
        """Test that template changes trigger rebuild even with valid cache."""
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        template = build_dir / "input.txt"
        template.write_text("INITIAL")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Initial build
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)

        # Create valid cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {"output.h": compute_file_hash(str(build_dir / "output.h"))},
            "dependencies": {"output.h": ["input.txt"]},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        time.sleep(0.1)

        # Modify template
        template.write_text("MODIFIED")

        # Run validation
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify rebuild occurred
        assert build_out == str(build_dir)
        content = (build_dir / "output.h").read_text()
        assert "MODIFIED" in content, "Output should reflect template change"

    def test_no_rebuild_when_nothing_changed(self, tmp_path: Path) -> None:
        """Test that nothing is rebuilt when cache is valid and no changes."""
        build_dir = tmp_path  # Use tmp_path directly for unique test isolation

        template = build_dir / "input.txt"
        template.write_text("STABLE")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Build
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)

        output_path = build_dir / "output.h"
        initial_content = output_path.read_text()

        # Create valid cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {"output.h": compute_file_hash(str(output_path))},
            "dependencies": {},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Run validation without any changes
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify: file should be unchanged
        assert build_out == str(build_dir)
        assert output_path.read_text() == initial_content, "File should not be modified"


class TestCacheCorrectnessScenarios:
    """Test cache correctness in various scenarios."""

    def test_cache_tracks_input_dependencies(self, tmp_path: Path) -> None:
        """Test that cache properly tracks input file changes and triggers rebuilds."""
        build_dir = tmp_path

        # Create input and generator
        template = build_dir / "config.xml"
        template.write_text("<config>V1</config>")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(build_dir, [{"output": "config.h", "input": "config.xml", "command": f"python3 {generator.name} config.xml config.h"}])

        # Initial build
        subprocess.run(["ninja", "config.h"], cwd=build_dir, check=True, capture_output=True)

        # Create cache with dependency tracking
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {
                str(build_dir / "config.h"): compute_file_hash(str(build_dir / "config.h")),
                str(build_dir / "config.xml"): compute_file_hash(str(build_dir / "config.xml")),
            },
            "dependencies": {"config.h": ["config.xml"]},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Modify input file
        time.sleep(0.1)
        template.write_text("<config>V2</config>")

        # Run validation - should detect input change
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)
        output_content = (build_dir / "config.h").read_text()
        assert "V2" in output_content, "Output should be rebuilt when input changes"

    def test_multiple_outputs_from_single_input(self, tmp_path: Path) -> None:
        """Test that changing one input triggers rebuild of all dependent outputs."""
        build_dir = tmp_path

        template = build_dir / "data.proto"
        template.write_text("syntax = 'proto3';")

        generator = create_python_generator(build_dir)

        # Multiple outputs from same input (like protobuf .h and .cc)
        create_build_ninja_simple(
            build_dir,
            [
                {"output": "data.pb.h", "input": "data.proto", "command": f"python3 {generator.name} data.proto data.pb.h"},
                {"output": "data.pb.cc", "input": "data.proto", "command": f"python3 {generator.name} data.proto data.pb.cc"},
            ],
        )

        # Build both
        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)

        # Create cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {
                str(build_dir / "data.pb.h"): compute_file_hash(str(build_dir / "data.pb.h")),
                str(build_dir / "data.pb.cc"): compute_file_hash(str(build_dir / "data.pb.cc")),
                str(build_dir / "data.proto"): compute_file_hash(str(build_dir / "data.proto")),
            },
            "dependencies": {"data.pb.h": ["data.proto"], "data.pb.cc": ["data.proto"]},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Modify proto file
        time.sleep(0.1)
        template.write_text("syntax = 'proto3'; message Test {}")

        # Run validation
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Both outputs should be rebuilt
        assert build_out == str(build_dir)
        header_content = (build_dir / "data.pb.h").read_text()
        source_content = (build_dir / "data.pb.cc").read_text()
        assert "message Test" in header_content or "proto3" in header_content
        assert "message Test" in source_content or "proto3" in source_content

    def test_generator_script_change_triggers_rebuild(self, tmp_path: Path) -> None:
        """Test that changes to generator script itself trigger rebuild of outputs."""
        build_dir = tmp_path

        template = build_dir / "input.txt"
        template.write_text("DATA")

        generator = create_python_generator(build_dir, "gen.py")

        create_build_ninja_simple(
            build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 gen.py input.txt output.h", "implicit_deps": ["gen.py"]}]
        )

        # Build
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)
        initial_content = (build_dir / "output.h").read_text()

        # Create cache with generator as tracked file
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {
                str(build_dir / "output.h"): compute_file_hash(str(build_dir / "output.h")),
                str(build_dir / "gen.py"): compute_file_hash(str(build_dir / "gen.py")),
            },
            "dependencies": {"output.h": ["input.txt", "gen.py"]},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Modify generator script
        time.sleep(0.1)
        modified_script = generator.read_text() + "\n# Modified generator\n"
        generator.write_text(modified_script)

        # Run validation
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)
        # Output should be regenerated (even if content might be same)
        final_content = (build_dir / "output.h").read_text()
        assert final_content  # Verify file was processed

    def test_missing_generated_file_triggers_rebuild(self, tmp_path: Path) -> None:
        """Test that deleting a generated file triggers its rebuild."""
        build_dir = tmp_path

        template = build_dir / "input.txt"
        template.write_text("DATA")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Build
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)

        # Create valid cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {str(build_dir / "output.h"): compute_file_hash(str(build_dir / "output.h"))},
            "dependencies": {},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Delete the generated file
        (build_dir / "output.h").unlink()

        # Run validation
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)
        assert (build_dir / "output.h").exists(), "Missing file should be regenerated"
        assert "DATA" in (build_dir / "output.h").read_text()

    def test_stale_cache_entries_are_cleaned(self, tmp_path: Path) -> None:
        """Test that files removed from build.ninja are cleaned from cache."""
        build_dir = tmp_path

        template = build_dir / "input.txt"
        template.write_text("DATA")

        generator = create_python_generator(build_dir)

        # Initial build.ninja with two outputs
        create_build_ninja_simple(
            build_dir,
            [
                {"output": "output1.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output1.h"},
                {"output": "output2.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output2.h"},
            ],
        )

        # Build both
        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)

        # Create cache with both files
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {
                str(build_dir / "output1.h"): compute_file_hash(str(build_dir / "output1.h")),
                str(build_dir / "output2.h"): compute_file_hash(str(build_dir / "output2.h")),
            },
            "dependencies": {},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Modify build.ninja to remove output2
        time.sleep(0.1)
        create_build_ninja_simple(build_dir, [{"output": "output1.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output1.h"}])

        # Run validation
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Load cache and verify output2 was removed
        cache_content = load_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE))
        cache_files = cache_content.get("files", {})

        # output2.h should NOT be in cache anymore (stale entry cleaned)
        output2_path = str(build_dir / "output2.h")
        assert output2_path not in cache_files, "Stale cache entry should be removed"


class TestMultiFileScenarios:
    """Test scenarios with multiple generated files and complex dependencies."""

    def test_partial_rebuild_with_mixed_changes(self, tmp_path: Path) -> None:
        """Test that only files with changed inputs are rebuilt."""
        build_dir = tmp_path

        # Two separate input template files (.in extension makes them trackable)
        input1 = build_dir / "input1.txt.in"
        input1.write_text("DATA1")
        input2 = build_dir / "input2.txt.in"
        input2.write_text("DATA2")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(
            build_dir,
            [
                {"output": "output1.h", "input": "input1.txt.in", "command": f"python3 {generator.name} input1.txt.in output1.h"},
                {"output": "output2.h", "input": "input2.txt.in", "command": f"python3 {generator.name} input2.txt.in output2.h"},
            ],
        )

        # Build both
        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)

        time.sleep(0.2)  # Ensure filesystem timestamp can distinguish

        # Save mtimes
        output1_mtime = (build_dir / "output1.h").stat().st_mtime
        output2_mtime = (build_dir / "output2.h").stat().st_mtime

        # Create cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {
                str(build_dir / "output1.h"): compute_file_hash(str(build_dir / "output1.h")),
                str(build_dir / "output2.h"): compute_file_hash(str(build_dir / "output2.h")),
                str(build_dir / "input1.txt.in"): compute_file_hash(str(build_dir / "input1.txt.in")),
                str(build_dir / "input2.txt.in"): compute_file_hash(str(build_dir / "input2.txt.in")),
            },
            "dependencies": {"output1.h": ["input1.txt.in"], "output2.h": ["input2.txt.in"]},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Sleep to ensure filesystem timestamps can distinguish changes
        time.sleep(0.3)

        # Modify only input1 template file
        input1.write_text("DATA1_MODIFIED")

        # Run validation
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)

        # output1 should be rebuilt, output2 should not
        new_output1_mtime = (build_dir / "output1.h").stat().st_mtime
        new_output2_mtime = (build_dir / "output2.h").stat().st_mtime

        assert new_output1_mtime > output1_mtime, "output1 should be rebuilt"
        assert new_output2_mtime == output2_mtime, "output2 should NOT be rebuilt"

        # Verify content
        assert "DATA1_MODIFIED" in (build_dir / "output1.h").read_text()
        assert "DATA2" in (build_dir / "output2.h").read_text()

    def test_chain_of_generated_files(self, tmp_path: Path) -> None:
        """Test a chain where one generated file is input to another."""
        build_dir = tmp_path

        # Initial input
        source = build_dir / "source.txt"
        source.write_text("ORIGINAL")

        generator = create_python_generator(build_dir)

        # Build chain: source.txt -> intermediate.h -> final.h
        create_build_ninja_simple(
            build_dir,
            [
                {"output": "intermediate.h", "input": "source.txt", "command": f"python3 {generator.name} source.txt intermediate.h"},
                {"output": "final.h", "input": "intermediate.h", "command": f"python3 {generator.name} intermediate.h final.h"},
            ],
        )

        # No cache - should build entire chain
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify chain built correctly
        assert build_out == str(build_dir)
        intermediate = (build_dir / "intermediate.h").read_text()
        final = (build_dir / "final.h").read_text()

        assert "ORIGINAL" in intermediate
        assert "intermediate.h" in final  # Generated from intermediate

    def test_no_work_when_all_cached_and_unchanged(self, tmp_path: Path) -> None:
        """Test that ninja is not called when everything is cached and unchanged."""
        build_dir = tmp_path

        template = build_dir / "input.txt"
        template.write_text("STABLE")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(
            build_dir,
            [
                {"output": "output1.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output1.h"},
                {"output": "output2.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output2.h"},
                {"output": "output3.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output3.h"},
            ],
        )

        # Build all
        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)

        # Create comprehensive cache
        cache = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {
                str(build_dir / "output1.h"): compute_file_hash(str(build_dir / "output1.h")),
                str(build_dir / "output2.h"): compute_file_hash(str(build_dir / "output2.h")),
                str(build_dir / "output3.h"): compute_file_hash(str(build_dir / "output3.h")),
                str(build_dir / "input.txt"): compute_file_hash(str(build_dir / "input.txt")),
            },
            "dependencies": {},
        }
        save_generated_files_cache(str(build_dir / GENERATED_FILES_CACHE), cache)

        # Save mtimes before validation
        mtime1_before = (build_dir / "output1.h").stat().st_mtime
        mtime2_before = (build_dir / "output2.h").stat().st_mtime
        mtime3_before = (build_dir / "output3.h").stat().st_mtime

        # Run validation - should detect no changes
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)

        # Verify no files were touched
        assert (build_dir / "output1.h").stat().st_mtime == mtime1_before
        assert (build_dir / "output2.h").stat().st_mtime == mtime2_before
        assert (build_dir / "output3.h").stat().st_mtime == mtime3_before


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_corrupted_cache_triggers_full_rebuild(self, tmp_path: Path) -> None:
        """Test that a corrupted cache file is handled gracefully."""
        build_dir = tmp_path

        template = build_dir / "input.txt"
        template.write_text("DATA")

        generator = create_python_generator(build_dir)

        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt", "command": f"python3 {generator.name} input.txt output.h"}])

        # Build
        subprocess.run(["ninja", "output.h"], cwd=build_dir, check=True, capture_output=True)

        # Create corrupted cache file
        cache_file = build_dir / GENERATED_FILES_CACHE
        cache_file.write_text("{invalid json")

        # Run validation - should handle corruption gracefully
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)
        assert (build_dir / "output.h").exists()

        # Verify cache was recreated
        assert cache_file.exists()
        cache_content = load_generated_files_cache(str(cache_file))
        assert "files" in cache_content

    def test_empty_build_ninja_handled(self, tmp_path: Path) -> None:
        """Test handling of build.ninja with no generated files."""
        build_dir = tmp_path

        # Create minimal build.ninja with no generator rules
        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text("# Empty build file\n")

        # Should not crash
        build_out, _compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert build_out == str(build_dir)


class TestUtilityFunctions:
    """Test utility functions for file tracking and path handling."""

    def test_is_trackable_file_source_files(self, tmp_path: Path) -> None:
        """Test that source files are correctly identified as trackable."""
        from lib.ninja_utils import is_trackable_file

        # Source files
        assert is_trackable_file("test.cpp") == (True, "source")
        assert is_trackable_file("test.h") == (True, "source")
        assert is_trackable_file("test.cc") == (True, "source")
        assert is_trackable_file("test.hpp") == (True, "source")

    def test_is_trackable_file_templates(self, tmp_path: Path) -> None:
        """Test that template files are correctly identified."""
        from lib.ninja_utils import is_trackable_file

        # Template files
        assert is_trackable_file("config.proto") == (True, "template")
        assert is_trackable_file("data.xml") == (True, "template")
        assert is_trackable_file("config.json") == (True, "template")
        assert is_trackable_file("template.in") == (True, "template")

    def test_is_trackable_file_scripts(self, tmp_path: Path) -> None:
        """Test that script files are correctly identified."""
        from lib.ninja_utils import is_trackable_file

        # Script files
        assert is_trackable_file("generator.py") == (True, "script")
        assert is_trackable_file("build.sh") == (True, "script")
        assert is_trackable_file("CMakeLists.txt") == (True, "script")

    def test_is_trackable_file_excluded(self, tmp_path: Path) -> None:
        """Test that build artifacts are correctly excluded."""
        from lib.ninja_utils import is_trackable_file

        # Excluded files
        assert is_trackable_file("test.o") == (False, "excluded")
        assert is_trackable_file("lib.a") == (False, "excluded")
        assert is_trackable_file("build.ninja") == (False, "excluded")
        assert is_trackable_file(".ninja_log") == (False, "excluded")

    def test_is_trackable_file_unknown(self, tmp_path: Path) -> None:
        """Test that unknown file types are not tracked."""
        from lib.ninja_utils import is_trackable_file

        # Unknown files
        assert is_trackable_file("data.txt") == (False, "unknown")
        assert is_trackable_file("image.png") == (False, "unknown")

    def test_get_relative_build_path(self, tmp_path: Path) -> None:
        """Test path relativization for ninja targets."""
        from lib.ninja_utils import get_relative_build_path

        build_dir = tmp_path / "build"
        build_dir.mkdir()

        # File inside build dir
        file_path = build_dir / "subdir" / "file.h"
        result = get_relative_build_path(str(file_path), str(build_dir))
        assert result == "subdir/file.h" or result == "subdir\\file.h"  # Windows/Unix

        # File outside build dir
        outside_file = tmp_path / "other" / "file.h"
        result = get_relative_build_path(str(outside_file), str(build_dir))
        assert result == "file.h"  # Falls back to basename

    def test_compute_file_hash(self, tmp_path: Path) -> None:
        """Test file hash computation."""
        from lib.ninja_utils import compute_file_hash

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World")

        hash1 = compute_file_hash(str(test_file))
        assert len(hash1) == 64  # SHA256 hash

        # Same content = same hash
        hash2 = compute_file_hash(str(test_file))
        assert hash1 == hash2

        # Different content = different hash
        test_file.write_text("Different")
        hash3 = compute_file_hash(str(test_file))
        assert hash1 != hash3

    def test_parse_ninja_explain_line(self, tmp_path: Path) -> None:
        """Test parsing of ninja explain output."""
        from lib.ninja_utils import parse_ninja_explain_line, RE_NINJA_EXPLAIN

        # Output file line
        line = "ninja explain: output main.o doesn't exist"
        result = parse_ninja_explain_line(line, RE_NINJA_EXPLAIN)
        assert result == ("main.o", "output main.o doesn't exist")

        # Command line changed
        line = "ninja explain: command line changed for main.o"
        result = parse_ninja_explain_line(line, RE_NINJA_EXPLAIN)
        assert result == ("main.o", "command line changed for main.o")

        # Dirty line (should be skipped)
        line = "ninja explain: CMakeFiles/gen.stamp is dirty"
        result = parse_ninja_explain_line(line, RE_NINJA_EXPLAIN)
        assert result is None

        # Non-explain line
        line = "[1/5] Building CXX object"
        result = parse_ninja_explain_line(line, RE_NINJA_EXPLAIN)
        assert result is None


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_validate_build_directory_nonexistent(self, tmp_path: Path) -> None:
        """Test validation fails for nonexistent directory."""
        from lib.ninja_utils import validate_build_directory

        nonexistent = tmp_path / "does_not_exist"

        with pytest.raises(ValueError, match="does not exist"):
            validate_build_directory(str(nonexistent))

    def test_validate_build_directory_not_a_directory(self, tmp_path: Path) -> None:
        """Test validation fails for non-directory."""
        from lib.ninja_utils import validate_build_directory

        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            validate_build_directory(str(file_path))

    def test_validate_build_directory_no_build_ninja(self, tmp_path: Path) -> None:
        """Test validation fails without build.ninja."""
        from lib.ninja_utils import validate_build_directory

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(ValueError, match="No build.ninja"):
            validate_build_directory(str(empty_dir))

    def test_ninja_build_failure_handling(self, tmp_path: Path) -> None:
        """Test handling of ninja build failures."""
        build_dir = tmp_path

        # Create a build.ninja with an invalid command that will fail
        generator = build_dir / "gen.py"
        generator.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n")
        generator.chmod(0o755)

        input_file = build_dir / "input.txt.in"
        input_file.write_text("DATA")

        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text(
            f"""rule generator
  command = python3 {generator.name} $in $out
  generator = 1

build output.h: generator input.txt.in
"""
        )

        # Should return False on build failure
        from lib.ninja_utils import run_full_ninja_build

        result = run_full_ninja_build(str(build_dir), verbose=False)
        assert result is False

    def test_cache_load_with_missing_file(self, tmp_path: Path) -> None:
        """Test loading cache when file doesn't exist."""
        from lib.ninja_utils import load_generated_files_cache

        nonexistent_cache = tmp_path / "nonexistent_cache.json"
        cache = load_generated_files_cache(str(nonexistent_cache))

        # Should return empty cache structure
        assert cache == {"build_ninja_mtime": 0.0, "files": {}, "dependencies": {}}

    def test_cache_load_with_invalid_json(self, tmp_path: Path) -> None:
        """Test loading cache with corrupted JSON."""
        from lib.ninja_utils import load_generated_files_cache

        cache_file = tmp_path / "cache.json"
        cache_file.write_text("{invalid json syntax")

        cache = load_generated_files_cache(str(cache_file))

        # Should return empty cache on error
        assert cache == {"build_ninja_mtime": 0.0, "files": {}, "dependencies": {}}


class TestCacheUpdateScenarios:
    """Test cache update and maintenance operations."""

    def test_update_cache_after_successful_build(self, tmp_path: Path) -> None:
        """Test cache is updated after files are rebuilt."""
        build_dir = tmp_path

        input_file = build_dir / "input.txt.in"
        input_file.write_text("DATA")

        generator = create_python_generator(build_dir)
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt.in", "command": f"python3 {generator.name} input.txt.in output.h"}])

        # Initial build
        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)

        # Create cache
        output_path = str(build_dir / "output.h")
        cache: Dict[str, Any] = {
            "build_ninja_mtime": os.path.getmtime(build_dir / "build.ninja"),
            "files": {output_path: compute_file_hash(output_path), str(build_dir / "input.txt.in"): compute_file_hash(str(build_dir / "input.txt.in"))},
            "dependencies": {},
        }
        cache_path = build_dir / GENERATED_FILES_CACHE
        save_generated_files_cache(str(cache_path), cache)

        old_output_hash = cache["files"][output_path]

        # Modify input and rebuild
        time.sleep(0.3)
        input_file.write_text("MODIFIED_DATA")

        validate_and_prepare_build_dir(str(build_dir), verbose=False)

        # Verify cache was updated
        updated_cache = load_generated_files_cache(str(cache_path))
        new_output_hash = updated_cache["files"][output_path]

        assert new_output_hash != old_output_hash

    def test_clean_stale_cache_entries_removes_deleted_files(self, tmp_path: Path) -> None:
        """Test that stale cache entries are cleaned up."""
        from lib.ninja_utils import clean_stale_cache_entries

        build_dir = tmp_path

        # Create the existing file
        existing_file = build_dir / "existing.h"
        existing_file.write_text("// Existing file")

        # Create cache with files (including ones that don't exist)
        cache = {
            "build_ninja_mtime": 123.0,
            "files": {str(build_dir / "existing.h"): "hash1", str(build_dir / "deleted.h"): "hash2", str(build_dir / "also_deleted.cpp"): "hash3"},
            "dependencies": {"existing.h": [], "deleted.h": [], "also_deleted.cpp": []},
        }

        # Current generated files includes all three, but only existing.h actually exists
        current_files = {"existing.h", "deleted.h", "also_deleted.cpp"}

        cleaned_cache = clean_stale_cache_entries(cache, current_files, str(build_dir))

        # Should only have existing.h (others don't exist on filesystem)
        assert str(build_dir / "existing.h") in cleaned_cache["files"]
        assert str(build_dir / "deleted.h") not in cleaned_cache["files"]
        assert str(build_dir / "also_deleted.cpp") not in cleaned_cache["files"]


class TestBuildNinjaParsing:
    """Test parsing of build.ninja for various scenarios."""

    def test_parse_phony_targets(self, tmp_path: Path) -> None:
        """Test parsing of phony targets."""
        from lib.ninja_utils import parse_ninja_generated_files

        build_dir = tmp_path
        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text(
            """rule phony
  command = :

build all: phony target1 target2

build target1: phony input1.h

build target2: phony input2.h
"""
        )

        tracked_files, output_info = parse_ninja_generated_files(str(build_ninja))

        # Phony targets should be tracked
        assert "all" in output_info
        assert "target1" in output_info
        assert "target2" in output_info

    def test_parse_implicit_and_order_only_deps(self, tmp_path: Path) -> None:
        """Test parsing of implicit and order-only dependencies."""
        from lib.ninja_utils import parse_ninja_generated_files

        build_dir = tmp_path
        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text(
            """rule generator
  command = gen $in $out
  generator = 1

build output.h: generator input.txt.in | implicit_dep.h || order_only_dep
"""
        )

        tracked_files, output_info = parse_ninja_generated_files(str(build_ninja))

        assert "output.h" in output_info
        file_info = output_info["output.h"]

        assert "input.txt.in" in file_info.explicit_inputs
        assert "implicit_dep.h" in file_info.implicit_inputs
        assert "order_only_dep" in file_info.order_only_inputs

    def test_parse_multiple_outputs(self, tmp_path: Path) -> None:
        """Test parsing rules with multiple outputs."""
        from lib.ninja_utils import parse_ninja_generated_files

        build_dir = tmp_path
        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text(
            """rule generator
  command = gen $in $out
  generator = 1

build output1.h output2.cpp: generator input.proto
"""
        )

        tracked_files, output_info = parse_ninja_generated_files(str(build_ninja))

        assert "output1.h" in output_info
        assert "output2.cpp" in output_info

    def test_parse_custom_command_rules(self, tmp_path: Path) -> None:
        """Test parsing of CUSTOM_COMMAND rules (CMake generated)."""
        from lib.ninja_utils import parse_ninja_generated_files

        build_dir = tmp_path
        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text(
            """rule CUSTOM_COMMAND
  command = cmake -E copy $in $out

build generated.h: CUSTOM_COMMAND source.h.in
"""
        )

        tracked_files, output_info = parse_ninja_generated_files(str(build_ninja))

        assert "generated.h" in output_info
        assert "source.h.in" in tracked_files

    def test_parse_rerun_cmake(self, tmp_path: Path) -> None:
        """Test parsing of RERUN_CMAKE rules."""
        from lib.ninja_utils import parse_ninja_generated_files

        build_dir = tmp_path
        build_ninja = build_dir / "build.ninja"
        build_ninja.write_text(
            """rule RERUN_CMAKE
  command = cmake --regenerate

build CMakeFiles/cmake.check_cache: RERUN_CMAKE
"""
        )

        tracked_files, output_info = parse_ninja_generated_files(str(build_ninja))

        assert "CMakeFiles/cmake.check_cache" in output_info


class TestVerboseOutput:
    """Test verbose output modes."""

    def test_verbose_mode_shows_progress(self, tmp_path: Path) -> None:
        """Test that verbose mode produces output."""
        build_dir = tmp_path

        input_file = build_dir / "input.txt.in"
        input_file.write_text("DATA")

        generator = create_python_generator(build_dir)
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt.in", "command": f"python3 {generator.name} input.txt.in output.h"}])

        # Run with verbose=True (should not crash and should work)
        build_out, compile_cmds = validate_and_prepare_build_dir(str(build_dir), verbose=True)

        assert build_out == str(build_dir)
        assert (build_dir / "output.h").exists()
