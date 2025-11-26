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
"""Legacy cache invalidation tests - see test_lib_ninja_utils_cache_invalidation_real.py for comprehensive tests.

This file contains basic sanity tests. The comprehensive test suite with 40+ tests is in
test_lib_ninja_utils_cache_invalidation_real.py.
"""
import sys
import subprocess
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.ninja_utils import validate_and_prepare_build_dir, check_ninja_available

pytestmark = pytest.mark.skipif(not check_ninja_available(), reason="ninja not available")


def create_python_generator(build_dir: Path, name: str = "gen.py") -> Path:
    """Create a simple Python generator script."""
    script = build_dir / name
    script.write_text(
        """#!/usr/bin/env python3
import sys
if len(sys.argv) < 3:
    sys.exit(1)
inp, out = sys.argv[1], sys.argv[2]
with open(inp) as f:
    data = f.read()
import os
os.makedirs(os.path.dirname(out) or '.', exist_ok=True)
with open(out, 'w') as f:
    f.write(f'// Generated from {inp}\\n')
    f.write(f'// Data: {data}\\n')
"""
    )
    script.chmod(0o755)
    return script


def create_build_ninja_simple(build_dir: Path, rules: list[dict[str, str]]) -> None:
    """Create a simple build.ninja file."""
    content = ["rule generator\n", "  command = $cmd\n", "  generator = 1\n\n"]
    for rule in rules:
        content.append(f"build {rule['output']}: generator {rule['input']}\n")
        content.append(f"  cmd = {rule['command']}\n")
    (build_dir / "build.ninja").write_text("".join(content))


class TestBasicFunctionality:
    """Basic functionality tests."""

    def test_basic_workflow(self, tmp_path: Path) -> None:
        """Test basic workflow: build, cache, validate."""
        build_dir = tmp_path

        input_file = build_dir / "input.txt.in"
        input_file.write_text("DATA")

        gen = create_python_generator(build_dir)
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt.in", "command": f"python3 {gen.name} input.txt.in output.h"}])

        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)
        assert (build_dir / "output.h").exists()

        validate_and_prepare_build_dir(str(build_dir), verbose=False)
        assert (build_dir / ".buildcheck_generated_cache.json").exists()

    def test_empty_build_directory(self, tmp_path: Path) -> None:
        """Test handling of directory with minimal build.ninja."""
        build_dir = tmp_path
        (build_dir / "build.ninja").write_text("# Empty\n")
        result, _ = validate_and_prepare_build_dir(str(build_dir), verbose=False)
        assert result == str(build_dir)

    def test_multiple_files(self, tmp_path: Path) -> None:
        """Test with multiple generated files."""
        build_dir = tmp_path

        (build_dir / "input1.txt.in").write_text("DATA1")
        (build_dir / "input2.txt.in").write_text("DATA2")

        gen = create_python_generator(build_dir)
        create_build_ninja_simple(
            build_dir,
            [
                {"output": "out1.h", "input": "input1.txt.in", "command": f"python3 {gen.name} input1.txt.in out1.h"},
                {"output": "out2.h", "input": "input2.txt.in", "command": f"python3 {gen.name} input2.txt.in out2.h"},
            ],
        )

        subprocess.run(["ninja"], cwd=build_dir, check=True, capture_output=True)
        result, _ = validate_and_prepare_build_dir(str(build_dir), verbose=False)

        assert result == str(build_dir)
        assert (build_dir / "out1.h").exists()
        assert (build_dir / "out2.h").exists()

    def test_verbose_mode(self, tmp_path: Path) -> None:
        """Test that verbose mode works."""
        build_dir = tmp_path

        input_file = build_dir / "input.txt.in"
        input_file.write_text("DATA")

        gen = create_python_generator(build_dir)
        create_build_ninja_simple(build_dir, [{"output": "output.h", "input": "input.txt.in", "command": f"python3 {gen.name} input.txt.in output.h"}])

        result, _ = validate_and_prepare_build_dir(str(build_dir), verbose=True)
        assert result == str(build_dir)
