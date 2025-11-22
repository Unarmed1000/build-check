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
"""Tests for buildCheckOptimize.py"""
import os
import sys
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Set, List, Any
from unittest.mock import Mock, patch, MagicMock
import pytest

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
import buildCheckOptimize
from buildCheckOptimize import (
    Optimization, Effort, Risk,
    run_command,
    analyze_library_impact,
    analyze_header_dependencies,
    analyze_build_system,
    analyze_architectural_issues,
    generate_summary_report
)


class TestOptimizationDataclass:
    """Test the Optimization dataclass."""
    
    def test_optimization_creation(self) -> None:
        """Test creating an Optimization instance."""
        opt = Optimization(
            title="Test Optimization",
            category="library",
            description="Test description",
            impact_score=75.0,
            effort=Effort.MEDIUM,
            risk=Risk.LOW,
            current_state="Current state",
            target_state="Target state",
            action_items=["Action 1", "Action 2"]
        )
        
        assert opt.title == "Test Optimization"
        assert opt.category == "library"
        assert opt.impact_score == 75.0
        assert opt.effort == Effort.MEDIUM
        assert opt.risk == Risk.LOW
        assert len(opt.action_items) == 2
    
    def test_priority_score_calculation(self) -> None:
        """Test priority score calculation."""
        opt1 = Optimization(
            title="High Impact Easy",
            category="build-system",
            description="Test",
            impact_score=90.0,
            effort=Effort.EASY,
            risk=Risk.LOW,
            current_state="Current",
            target_state="Target",
            action_items=["Action"]
        )
        
        opt2 = Optimization(
            title="Low Impact Hard",
            category="architecture",
            description="Test",
            impact_score=30.0,
            effort=Effort.HARD,
            risk=Risk.HIGH,
            current_state="Current",
            target_state="Target",
            action_items=["Action"]
        )
        
        # Priority = impact / (effort * risk)
        # opt1: 90 / (1 * 1) = 90
        # opt2: 30 / (3 * 3) = 3.33
        assert opt1.priority_score == 90.0
        assert opt2.priority_score == pytest.approx(3.33, rel=0.1)
        assert opt1.priority_score > opt2.priority_score
    
    def test_format_output(self) -> None:
        """Test formatting optimization for display."""
        opt = Optimization(
            title="Test Optimization",
            category="library",
            description="Test description",
            impact_score=75.0,
            effort=Effort.MEDIUM,
            risk=Risk.LOW,
            current_state="Current state",
            target_state="Target state",
            action_items=["Action 1", "Action 2"],
            affected_targets=["target1", "target2"],
            evidence={"key1": "value1", "key2": "value2"}
        )
        
        output = opt.format_output(1)
        
        assert "OPTIMIZATION #1" in output
        assert "Test Optimization" in output
        assert "library" in output
        assert "Action 1" in output
        assert "Action 2" in output
        assert "target1" in output
        assert "key1: value1" in output


class TestRunCommand:
    """Test the run_command utility function."""
    
    def test_successful_command(self) -> None:
        """Test running a successful command."""
        returncode, stdout, stderr = run_command(['echo', 'hello'])
        
        assert returncode == 0
        assert 'hello' in stdout
        assert stderr == ''
    
    def test_failed_command(self) -> None:
        """Test running a failed command."""
        returncode, stdout, stderr = run_command(['false'])
        
        assert returncode != 0
    
    def test_command_with_cwd(self, temp_dir: Any) -> None:
        """Test running command with custom working directory."""
        returncode, stdout, stderr = run_command(['pwd'], cwd=temp_dir)
        
        assert returncode == 0
        assert temp_dir in stdout


class TestAnalyzeLibraryImpact:
    """Test library-level optimization analysis."""
    
    def test_high_impact_library_detection(self) -> None:
        """Test detection of high-impact libraries."""
        # Create a library with many transitive dependents
        lib_to_libs = {
            'libA': set(),
            'libB': {'libA'},
            'libC': {'libA'},
            'libD': {'libB'},
            'libE': {'libB'},
            'libF': {'libC'},
            'libG': {'libC'},
        }
        
        # Create 50+ executables that depend on libA
        exe_to_libs = {}
        for i in range(60):
            exe_to_libs[f'exe{i}'] = {'libA'}
        
        all_libs = {'libA', 'libB', 'libC', 'libD', 'libE', 'libF', 'libG'}
        
        optimizations = analyze_library_impact(lib_to_libs, exe_to_libs, all_libs)
        
        # Should suggest splitting libA due to high transitive dependents
        high_impact_opts = [o for o in optimizations if 'high-impact' in o.title.lower()]
        assert len(high_impact_opts) > 0
        
        # Check that libA is mentioned
        libA_opts = [o for o in high_impact_opts if 'libA' in o.title]
        assert len(libA_opts) > 0
        assert libA_opts[0].effort == Effort.HARD
        assert libA_opts[0].risk == Risk.HIGH
    
    def test_complex_library_detection(self) -> None:
        """Test detection of libraries with too many dependencies."""
        lib_to_libs = {
            'libComplex': {f'lib{i}' for i in range(20)},  # Depends on 20 libs
            'libSimple': {'lib1', 'lib2'}
        }
        exe_to_libs = {'exe1': {'libComplex'}}
        all_libs = {'libComplex', 'libSimple'} | {f'lib{i}' for i in range(20)}
        
        optimizations = analyze_library_impact(lib_to_libs, exe_to_libs, all_libs)
        
        # Should suggest reducing dependencies
        complex_opts = [o for o in optimizations if 'reduce dependencies' in o.title.lower()]
        assert len(complex_opts) > 0
        
        libComplex_opts = [o for o in complex_opts if 'libComplex' in o.title]
        assert len(libComplex_opts) > 0
        assert libComplex_opts[0].effort == Effort.MEDIUM
    
    def test_unused_libraries_detection(self) -> None:
        """Test detection of unused libraries."""
        lib_to_libs: Dict[str, Set[str]] = {
            'libUsed': set(),
            'libUnused1': set(),
            'libUnused2': set(),
            'libUnused3': set(),
            'libUnused4': set(),
            'libUnused5': set(),
            'libUnused6': set(),
        }
        exe_to_libs = {'exe1': {'libUsed'}}
        all_libs = set(lib_to_libs.keys())
        
        optimizations = analyze_library_impact(lib_to_libs, exe_to_libs, all_libs)
        
        # Should detect unused libraries
        unused_opts = [o for o in optimizations if 'unused' in o.title.lower()]
        assert len(unused_opts) > 0
        assert unused_opts[0].effort == Effort.EASY
        assert unused_opts[0].risk == Risk.LOW
        assert 'libUnused' in str(unused_opts[0].evidence)
    
    def test_circular_dependency_detection(self) -> None:
        """Test detection of circular library dependencies."""
        lib_to_libs = {
            'libA': {'libB'},
            'libB': {'libC'},
            'libC': {'libA'},  # Creates a cycle
            'libD': set()
        }
        exe_to_libs = {'exe1': {'libA'}}
        all_libs = {'libA', 'libB', 'libC', 'libD'}
        
        optimizations = analyze_library_impact(lib_to_libs, exe_to_libs, all_libs)
        
        # Should detect circular dependency
        cycle_opts = [o for o in optimizations if 'circular' in o.title.lower()]
        assert len(cycle_opts) > 0
        assert cycle_opts[0].category == 'cycle'
        assert cycle_opts[0].effort == Effort.HARD
        assert cycle_opts[0].risk == Risk.HIGH


class TestAnalyzeHeaderDependencies:
    """Test header-level optimization analysis."""
    
    def test_quick_mode(self, temp_dir: Any) -> None:
        """Test quick mode that skips expensive analysis."""
        # Create minimal build directory
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule CXX\n  command = g++\n")
        
        optimizations = analyze_header_dependencies(str(build_dir), quick=True)
        
        # Should return generic recommendations in quick mode
        assert len(optimizations) > 0
        assert any('header' in opt.category.lower() for opt in optimizations)
    
    def test_missing_clang_scan_deps(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test behavior when clang-scan-deps is not available."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule CXX\n  command = g++\n")
        
        # Mock which command to always fail
        def mock_run_command(cmd: list[str], cwd: Any = None) -> tuple[int, str, str]:
            if cmd[0] == 'which':
                return (1, '', 'not found')
            return (0, '', '')
        
        monkeypatch.setattr(buildCheckOptimize, 'run_command', mock_run_command)
        
        optimizations = analyze_header_dependencies(str(build_dir), quick=False)
        
        # Should return empty list when clang-scan-deps not available
        assert len(optimizations) == 0


class TestAnalyzeBuildSystem:
    """Test build system configuration analysis."""
    
    def test_missing_precompiled_headers(self, temp_dir: Any) -> None:
        """Test detection of missing precompiled headers."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        
        # Create CMakeCache.txt without PCH
        cmake_cache = build_dir / "CMakeCache.txt"
        cmake_cache.write_text("CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/g++\n")
        
        optimizations = analyze_build_system(str(build_dir))
        
        # Should recommend enabling PCH
        pch_opts = [o for o in optimizations if 'precompiled' in o.title.lower()]
        assert len(pch_opts) > 0
        assert pch_opts[0].effort == Effort.MEDIUM
        assert pch_opts[0].impact_score >= 70
    
    def test_has_precompiled_headers(self, temp_dir: Any) -> None:
        """Test when precompiled headers are already enabled."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        
        # Create CMakeCache.txt with PCH
        cmake_cache = build_dir / "CMakeCache.txt"
        cmake_cache.write_text("""
CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/g++
PRECOMPILED_HEADER:STRING=ON
target_precompile_headers:STRING=pch.hpp
""")
        
        optimizations = analyze_build_system(str(build_dir))
        
        # Should not recommend PCH if already enabled
        pch_opts = [o for o in optimizations if 'precompiled' in o.title.lower()]
        assert len(pch_opts) == 0
    
    def test_missing_ccache(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test detection of missing ccache."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        
        # Mock which command to indicate ccache not found
        def mock_run_command(cmd: list[str], cwd: Any = None) -> tuple[int, str, str]:
            if cmd[0] == 'which' and cmd[1] == 'ccache':
                return (1, '', 'not found')
            return (0, '', '')
        
        monkeypatch.setattr(buildCheckOptimize, 'run_command', mock_run_command)
        
        optimizations = analyze_build_system(str(build_dir))
        
        # Should recommend installing ccache
        ccache_opts = [o for o in optimizations if 'ccache' in o.title.lower()]
        assert len(ccache_opts) > 0
        assert ccache_opts[0].effort == Effort.EASY
        assert ccache_opts[0].impact_score >= 80
    
    def test_missing_unity_builds(self, temp_dir: Any) -> None:
        """Test detection of missing unity builds."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        
        # Create CMakeCache.txt without unity builds
        cmake_cache = build_dir / "CMakeCache.txt"
        cmake_cache.write_text("CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/g++\n")
        
        optimizations = analyze_build_system(str(build_dir))
        
        # Should recommend unity builds
        unity_opts = [o for o in optimizations if 'unity' in o.title.lower()]
        assert len(unity_opts) > 0
        assert unity_opts[0].effort == Effort.EASY
        assert unity_opts[0].risk == Risk.MEDIUM


class TestAnalyzeArchitecturalIssues:
    """Test architectural pattern analysis."""
    
    def test_architectural_recommendations(self, temp_dir: Any) -> None:
        """Test generation of architectural recommendations."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        
        optimizations = analyze_architectural_issues(str(build_dir))
        
        # Should provide architectural recommendations
        assert len(optimizations) >= 2
        
        # Check for layering recommendation
        layer_opts = [o for o in optimizations if 'layer' in o.title.lower()]
        assert len(layer_opts) > 0
        assert layer_opts[0].category == 'architecture'
        
        # Check for interface/implementation recommendation
        interface_opts = [o for o in optimizations if 'interface' in o.title.lower()]
        assert len(interface_opts) > 0


class TestGenerateSummaryReport:
    """Test summary report generation."""
    
    def test_summary_with_optimizations(self) -> None:
        """Test generating summary with multiple optimizations."""
        optimizations = [
            Optimization(
                title="Quick Win 1",
                category="build-system",
                description="Test",
                impact_score=85.0,
                effort=Effort.EASY,
                risk=Risk.LOW,
                current_state="Current",
                target_state="Target",
                action_items=["Action"]
            ),
            Optimization(
                title="Hard Change",
                category="architecture",
                description="Test",
                impact_score=90.0,
                effort=Effort.HARD,
                risk=Risk.HIGH,
                current_state="Current",
                target_state="Target",
                action_items=["Action"]
            ),
            Optimization(
                title="Medium Impact",
                category="library",
                description="Test",
                impact_score=60.0,
                effort=Effort.MEDIUM,
                risk=Risk.MEDIUM,
                current_state="Current",
                target_state="Target",
                action_items=["Action"]
            ),
        ]
        
        report = generate_summary_report(optimizations)
        
        assert "BUILD OPTIMIZATION SUMMARY" in report
        assert "Total opportunities identified: 3" in report
        assert "By Category:" in report
        assert "By Effort:" in report
        assert "QUICK WINS" in report
        assert "TOP 5 PRIORITIES" in report
        assert "Quick Win 1" in report
    
    def test_empty_optimizations(self) -> None:
        """Test generating summary with no optimizations."""
        optimizations: List[Optimization] = []
        
        report = generate_summary_report(optimizations)
        
        assert "Total opportunities identified: 0" in report


class TestMainFunction:
    """Test the main() function and CLI."""
    
    def test_invalid_build_directory(self, capsys: Any) -> None:
        """Test handling of invalid build directory."""
        with patch('sys.argv', ['buildCheckOptimize.py', '/nonexistent/build']):
            result = buildCheckOptimize.main()
        
        assert result == 1
        captured = capsys.readouterr()
        assert 'Error' in captured.out or 'Error' in captured.err
    
    def test_valid_build_directory(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test with valid build directory."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("""
rule CXX
  command = g++ $in -o $out

build lib1: CXX lib1.cpp
build lib2: CXX lib2.cpp
build exe: CXX main.cpp | lib1 lib2
""")
        
        # Mock parse_ninja_libraries to avoid parsing complexity
        def mock_parse_ninja(*args: Any) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], set[str]]:
            return (
                {'lib2': {'lib1'}, 'lib1': set()},  # lib_to_libs
                {'exe': {'lib1', 'lib2'}},  # exe_to_libs
                {'lib1', 'lib2'},  # all_libs
                {'exe'}  # all_exes
            )
        
        monkeypatch.setattr('lib.library_parser.parse_ninja_libraries', mock_parse_ninja)
        
        with patch('sys.argv', ['buildCheckOptimize.py', str(build_dir), '--quick']):
            result = buildCheckOptimize.main()
        
        # Should complete successfully
        assert result == 0
    
    def test_focus_option(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test --focus option to limit analysis."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule CXX\n  command = g++\n")
        
        def mock_parse_ninja(*args: Any) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], set[str]]:
            return ({}, {}, set(), set())
        
        monkeypatch.setattr('lib.library_parser.parse_ninja_libraries', mock_parse_ninja)
        
        with patch('sys.argv', ['buildCheckOptimize.py', str(build_dir), '--focus', 'build-system']):
            result = buildCheckOptimize.main()
        
        assert result == 0
    
    def test_top_option(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test --top option to limit results."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule CXX\n  command = g++\n")
        
        def mock_parse_ninja(*args: Any) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], set[str]]:
            return ({}, {}, set(), set())
        
        monkeypatch.setattr('lib.library_parser.parse_ninja_libraries', mock_parse_ninja)
        
        with patch('sys.argv', ['buildCheckOptimize.py', str(build_dir), '--top', '5', '--quick']):
            result = buildCheckOptimize.main()
        
        assert result == 0
    
    def test_report_output(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test --report option to write to file."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule CXX\n  command = g++\n")
        
        report_file = Path(temp_dir) / "report.txt"
        
        def mock_parse_ninja(*args: Any) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], set[str]]:
            return ({}, {}, set(), set())
        
        monkeypatch.setattr('lib.library_parser.parse_ninja_libraries', mock_parse_ninja)
        
        with patch('sys.argv', ['buildCheckOptimize.py', str(build_dir), 
                               '--report', str(report_file), '--quick']):
            result = buildCheckOptimize.main()
        
        assert result == 0
        # Report file should be created
        assert report_file.exists()
        content = report_file.read_text()
        assert "BUILD OPTIMIZATION REPORT" in content
    
    def test_min_impact_filter(self, temp_dir: Any, monkeypatch: Any) -> None:
        """Test --min-impact option to filter optimizations."""
        build_dir = Path(temp_dir) / "build"
        build_dir.mkdir()
        (build_dir / "build.ninja").write_text("rule CXX\n  command = g++\n")
        
        def mock_parse_ninja(*args: Any) -> tuple[dict[str, set[str]], dict[str, set[str]], set[str], set[str]]:
            return ({}, {}, set(), set())
        
        monkeypatch.setattr('lib.library_parser.parse_ninja_libraries', mock_parse_ninja)
        
        with patch('sys.argv', ['buildCheckOptimize.py', str(build_dir), 
                               '--min-impact', '80', '--quick']):
            result = buildCheckOptimize.main()
        
        assert result == 0


class TestEnumTypes:
    """Test Effort and Risk enums."""
    
    def test_effort_values(self) -> None:
        """Test Effort enum values."""
        assert Effort.EASY.value == 1
        assert Effort.MEDIUM.value == 2
        assert Effort.HARD.value == 3
    
    def test_risk_values(self) -> None:
        """Test Risk enum values."""
        assert Risk.LOW.value == 1
        assert Risk.MEDIUM.value == 2
        assert Risk.HIGH.value == 3
