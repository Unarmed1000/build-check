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
"""Test script to validate buildCheckRippleEffect.py against actual ninja rebuild detection

WARNING: This test is hardcoded to an internal test case (gtec-demo-framework) and should
not be run externally. It requires:
- A git repository with build history
- FslBuildGen.py build system
- Ninja build files
- Specific test commits with C/C++ file changes

This test is designed for internal validation only.
"""

import os
import sys
import subprocess
import json
import tempfile
import shutil
from pathlib import Path
from typing import List, Set, Tuple

# ANSI color codes
class Colors:
    RED = '\033[0;31m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    CYAN = '\033[0;36m'
    NC = '\033[0m'  # No Color

def print_colored(message: str, color: str = Colors.NC):
    """Print a colored message"""
    print(f"{color}{message}{Colors.NC}")

def run_command(cmd: List[str], cwd: str = None, check: bool = True, capture_output: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            check=check,
            capture_output=capture_output,
            text=True
        )
        return result
    except subprocess.CalledProcessError as e:
        print_colored(f"Command failed: {' '.join(cmd)}", Colors.RED)
        print_colored(f"Exit code: {e.returncode}", Colors.RED)
        if e.stderr:
            print_colored(f"Error output: {e.stderr}", Colors.RED)
        raise

def get_git_info(repo_dir: str) -> Tuple[str, str, str]:
    """Get current commit, branch, and previous commit"""
    current_commit = run_command(['git', 'rev-parse', 'HEAD'], cwd=repo_dir).stdout.strip()
    current_branch = run_command(['git', 'branch', '--show-current'], cwd=repo_dir).stdout.strip()
    prev_commit = run_command(['git', 'rev-parse', 'HEAD~1'], cwd=repo_dir).stdout.strip()
    return current_commit, current_branch, prev_commit

def has_uncommitted_changes(repo_dir: str) -> bool:
    """Check if there are uncommitted changes"""
    result = run_command(['git', 'status', '--porcelain'], cwd=repo_dir)
    return bool(result.stdout.strip())

def stash_changes(repo_dir: str) -> bool:
    """Stash uncommitted changes, return True if stashed"""
    if has_uncommitted_changes(repo_dir):
        print_colored("Warning: You have uncommitted changes. Stashing them...", Colors.YELLOW)
        import time
        stash_name = f"test_ripple_effect_stash_{int(time.time())}"
        run_command(['git', 'stash', 'push', '-m', stash_name], cwd=repo_dir)
        return True
    return False

def get_changed_files(repo_dir: str, commit1: str = 'HEAD~1', commit2: str = 'HEAD') -> List[str]:
    """Get C/C++ files changed between two commits"""
    result = run_command(['git', 'diff', '--name-only', commit1, commit2], cwd=repo_dir)
    changed_files = []
    for line in result.stdout.splitlines():
        if line.endswith(('.cpp', '.c', '.cc', '.cxx', '.h', '.hpp', '.hxx')):
            changed_files.append(line)
    return changed_files

def build_with_fslbuildgen(repo_dir: str, build_params: str) -> bool:
    """Run FslBuildGen.py with specified parameters"""
    print_colored("Running FslBuildGen.py to generate build files...", Colors.BLUE)
    cmd = ['FslBuildGen.py'] + build_params.split()
    try:
        run_command(cmd, cwd=repo_dir, capture_output=False)
        return True
    except subprocess.CalledProcessError:
        print_colored("FslBuildGen.py failed", Colors.RED)
        return False

def build_with_ninja(build_dir: str, clean: bool = False) -> bool:
    """Build with ninja"""
    print_colored("Building with ninja...", Colors.BLUE)
    try:
        if clean:
            run_command(['ninja', 'clean'], cwd=build_dir, capture_output=False)
        
        nproc = os.cpu_count() or 1
        run_command(['ninja', f'-j{nproc}'], cwd=build_dir, capture_output=False)
        return True
    except subprocess.CalledProcessError:
        print_colored("Build failed", Colors.RED)
        return False

def get_ripple_effect_data(script_dir: str, build_dir: str, repo_dir: str) -> dict:
    """Get ripple effect data from buildCheckRippleEffect.py"""
    print_colored("\nRunning buildCheckRippleEffect.py to predict rebuild...", Colors.BLUE)
    
    # Import the helper function
    sys.path.insert(0, script_dir)
    try:
        from buildCheckRippleEffect import get_ripple_effect_data as get_data
        result = get_data(build_dir, repo_dir, 'HEAD')
        return result
    except Exception as e:
        print_colored(f"Error running buildCheckRippleEffect: {e}", Colors.RED)
        raise

def get_ninja_rebuild_list(build_dir: str) -> List[str]:
    """Get list of files ninja would rebuild (dry run)"""
    print_colored("\nGetting actual ninja rebuild plan...", Colors.BLUE)
    result = run_command(['ninja', '-n'], cwd=build_dir, check=False)
    
    rebuild_list = []
    output = result.stdout + result.stderr
    for line in output.splitlines():
        # Match lines like: [1/100] Compiling CXX object path/to/file.cpp.o
        if '] ' in line and ('Compiling' in line or 'Building' in line):
            parts = line.split()
            for part in parts:
                if part.endswith(('.cpp.o', '.c.o', '.cc.o', '.cxx.o')):
                    rebuild_list.append(part)
                    break
    
    return rebuild_list

def compare_results(script_sources: Set[str], ninja_sources: Set[str]) -> Tuple[Set[str], Set[str], Set[str]]:
    """Compare script predictions with actual ninja rebuild list"""
    only_in_script = script_sources - ninja_sources
    only_in_ninja = ninja_sources - script_sources
    in_both = script_sources & ninja_sources
    return only_in_script, only_in_ninja, in_both

def save_report(temp_dir: str, repo_dir: str, build_dir: str, current_commit: str,
                ripple_data: dict, predicted_count: int, actual_count: int,
                match_count: int, accuracy: float, only_in_script: Set[str],
                only_in_ninja: Set[str]) -> str:
    """Save comparison report to file"""
    from datetime import datetime
    
    report_file = os.path.join(temp_dir, 'comparison_report.txt')
    with open(report_file, 'w') as f:
        f.write("=== Ripple Effect Test Report ===\n")
        f.write(f"Date: {datetime.now()}\n")
        f.write(f"Repository: {repo_dir}\n")
        f.write(f"Build directory: {build_dir}\n")
        f.write(f"Commit: {current_commit}\n")
        f.write("\n")
        f.write(f"Predicted rebuilds: {predicted_count}\n")
        f.write(f"Actual rebuilds: {actual_count}\n")
        f.write(f"Matches: {match_count}\n")
        f.write(f"Accuracy: {accuracy:.1f}%\n")
        f.write("\n")
        f.write("=== Ripple Effect Data (JSON) ===\n")
        json.dump(ripple_data, f, indent=2)
        f.write("\n\n")
        f.write("=== Files predicted but not in ninja ===\n")
        for file in sorted(only_in_script):
            f.write(f"{file}\n")
        f.write("\n")
        f.write("=== Files in ninja but not predicted ===\n")
        for file in sorted(only_in_ninja):
            f.write(f"{file}\n")
    
    return report_file

def main():
    # IMPORTANT: This test is hardcoded for internal gtec-demo-framework testing only.
    # It assumes specific repository structure, build system (FslBuildGen.py), and ninja setup.
    # Do not run this test on external projects without modification.
    
    # Get script directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Parse command line arguments
    repo_dir = sys.argv[1] if len(sys.argv) > 1 else '/home/dev/code/gtec-demo-framework'
    build_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(repo_dir, 'build/Ubuntu/Ninja/release')
    
    # NOTE: Default paths are hardcoded for internal testing environment
    print_colored("=== Testing buildCheckRippleEffect.py ===", Colors.CYAN)
    print_colored(f"Repository: {repo_dir}", Colors.BLUE)
    print_colored(f"Build directory: {build_dir}", Colors.BLUE)
    
    # Check if directories exist
    if not os.path.isdir(os.path.join(repo_dir, '.git')):
        print_colored(f"Error: {repo_dir} is not a git repository", Colors.RED)
        sys.exit(1)
    
    # Save current git state
    print_colored("\nSaving current git state...", Colors.BLUE)
    current_commit, current_branch, prev_commit = get_git_info(repo_dir)
    print_colored(f"Current: {current_commit[:8]} ({current_branch})", Colors.GREEN)
    
    # Check for uncommitted changes
    stashed = stash_changes(repo_dir)
    
    print_colored(f"Previous commit: {prev_commit[:8]}", Colors.BLUE)
    
    # Checkout previous commit
    print_colored("\nChecking out previous commit...", Colors.BLUE)
    run_command(['git', 'checkout', '-q', prev_commit], cwd=repo_dir)
    
    # Build parameters
    # HARDCODED: These parameters are specific to gtec-demo-framework build configuration
    #fsl_build_params = "-t sdk -vv --BuildTime --UseFeatures [ConsoleHost,WindowHost,Test_RequireUserInputToExit,EarlyAccess,EGL,GoogleBenchmark,GoogleUnitTest,OpenGLES2,OpenGLES3,OpenGLES3.1,OpenGLES3.2,OpenVG,OpenVX1.2,Vulkan,Lib_NlohmannJson,Lib_pugixml] --Variants [config=Release]"
    fsl_build_params = "-t sdk -vv --BuildTime --UseFeatures [ConsoleHost,WindowHost,OpenGLES2] --Variants [config=Release]"
    
    try:
        # Build previous commit
        print_colored("\nBuilding previous commit using FslBuildGen.py...", Colors.BLUE)
        if not build_with_fslbuildgen(repo_dir, fsl_build_params):
            print_colored("FslBuildGen.py failed at previous commit", Colors.RED)
            run_command(['git', 'checkout', '-q', current_commit], cwd=repo_dir)
            if stashed:
                run_command(['git', 'stash', 'pop'], cwd=repo_dir)
            sys.exit(1)
        
        if not build_with_ninja(build_dir, clean=True):
            print_colored("Build failed at previous commit", Colors.RED)
            run_command(['git', 'checkout', '-q', current_commit], cwd=repo_dir)
            if stashed:
                run_command(['git', 'stash', 'pop'], cwd=repo_dir)
            sys.exit(1)
        
        print_colored("Previous commit built successfully", Colors.GREEN)
        
        # Checkout latest commit
        print_colored("\nChecking out latest commit...", Colors.BLUE)
        run_command(['git', 'checkout', '-q', current_commit], cwd=repo_dir)
        
        # Regenerate build files for latest commit
        print_colored("Running FslBuildGen.py for latest commit...", Colors.BLUE)
        if not build_with_fslbuildgen(repo_dir, fsl_build_params):
            print_colored("FslBuildGen.py failed at latest commit", Colors.RED)
            if stashed:
                run_command(['git', 'stash', 'pop'], cwd=repo_dir)
            sys.exit(1)
        
        # Get changed files
        print_colored("\nGetting changed files from git...", Colors.BLUE)
        changed_files = get_changed_files(repo_dir, prev_commit, current_commit)
        
        if not changed_files:
            print_colored("No C/C++ files changed in the last commit", Colors.YELLOW)
            if stashed:
                run_command(['git', 'stash', 'pop'], cwd=repo_dir)
            sys.exit(0)
        
        print_colored("Changed files:", Colors.GREEN)
        for file in changed_files:
            print_colored(f"  {file}", Colors.CYAN)
        
        # Get ripple effect prediction
        ripple_data = get_ripple_effect_data(script_dir, build_dir, repo_dir)
        
        predicted_count = len(ripple_data['all_affected_sources'])
        changed_headers = len(ripple_data['changed_headers'])
        changed_sources = len(ripple_data['changed_sources'])
        
        print_colored("Ripple effect analysis:", Colors.GREEN)
        print(f"  Changed headers: {changed_headers}")
        print(f"  Changed sources: {changed_sources}")
        print(f"  Predicted affected sources: {predicted_count}")
        
        # Get actual ninja rebuild list
        ninja_rebuild_list = get_ninja_rebuild_list(build_dir)
        actual_count = len(ninja_rebuild_list)
        
        print_colored(f"Ninja will rebuild {actual_count} object files", Colors.GREEN)
        
        # Prepare sets for comparison (remove .o extensions)
        script_sources = {s[:-2] if s.endswith('.o') else s 
                         for s in ripple_data['all_affected_sources']}
        ninja_sources = {s[:-2] if s.endswith('.o') else s 
                        for s in ninja_rebuild_list}
        
        # Compare the lists
        print_colored("\nComparing predictions...", Colors.BLUE)
        only_in_script, only_in_ninja, in_both = compare_results(script_sources, ninja_sources)
        
        match_count = len(in_both)
        print_colored(f"Matches: {match_count}", Colors.GREEN)
        
        # Display differences
        if only_in_script:
            print_colored(f"Predicted by script but NOT in ninja rebuild ({len(only_in_script)}):", Colors.YELLOW)
            for i, file in enumerate(sorted(only_in_script)[:10]):
                print_colored(f"  {file}", Colors.YELLOW)
            if len(only_in_script) > 10:
                print_colored(f"  ... and {len(only_in_script) - 10} more", Colors.YELLOW)
        
        if only_in_ninja:
            print_colored(f"In ninja rebuild but NOT predicted ({len(only_in_ninja)}):", Colors.YELLOW)
            for i, file in enumerate(sorted(only_in_ninja)[:10]):
                print_colored(f"  {file}", Colors.YELLOW)
            if len(only_in_ninja) > 10:
                print_colored(f"  ... and {len(only_in_ninja) - 10} more", Colors.YELLOW)
        
        # Calculate accuracy
        if actual_count > 0:
            accuracy = (match_count * 100.0) / actual_count
            print_colored(f"\nAccuracy: {accuracy:.1f}% ({match_count}/{actual_count} matches)", Colors.BLUE)
            
            if match_count == actual_count:
                print_colored("✓ Perfect match! The script correctly predicted all rebuilds.", Colors.GREEN)
            elif accuracy > 90:
                print_colored("✓ Excellent accuracy (>90%)", Colors.GREEN)
            elif accuracy > 70:
                print_colored("⚠ Good accuracy (>70%) but could be improved", Colors.YELLOW)
            else:
                print_colored("✗ Low accuracy (<70%) - needs investigation", Colors.RED)
        else:
            accuracy = 0.0
            print_colored("No actual rebuilds detected by ninja", Colors.YELLOW)
        
        # Save report
        temp_dir = tempfile.mkdtemp()
        report_file = save_report(temp_dir, repo_dir, build_dir, current_commit,
                                 ripple_data, predicted_count, actual_count,
                                 match_count, accuracy, only_in_script, only_in_ninja)
        
        print_colored(f"\nFull report saved to: {report_file}", Colors.BLUE)
        
    finally:
        # Restore git state
        print_colored("\nRestoring git state...", Colors.BLUE)
        run_command(['git', 'checkout', '-q', current_commit], cwd=repo_dir, check=False)
        if stashed:
            run_command(['git', 'stash', 'pop'], cwd=repo_dir, check=False)
            print_colored("Restored stashed changes", Colors.GREEN)
    
    print_colored("Test complete!", Colors.GREEN)

if __name__ == '__main__':
    main()
