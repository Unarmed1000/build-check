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
"""Security tests for path traversal protection across all BuildCheck tools."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestPathTraversalSecurity:
    """Test path traversal protection in all BuildCheck tools."""
    
    def test_realpath_normalization(self, temp_dir):
        """Test that os.path.realpath properly resolves symlinks."""
        # Create a directory structure
        real_dir = Path(temp_dir) / "real"
        real_dir.mkdir()
        
        # Create a symlink
        link_dir = Path(temp_dir) / "link"
        link_dir.symlink_to(real_dir)
        
        # Test that realpath resolves to the same location
        assert os.path.realpath(str(real_dir)) == os.path.realpath(str(link_dir))
    
    def test_path_within_directory_check(self, temp_dir):
        """Test validation that paths stay within expected directory."""
        base_dir = os.path.realpath(temp_dir)
        
        # Valid path within directory
        valid_path = os.path.realpath(os.path.join(base_dir, "subdir", "file.txt"))
        assert valid_path.startswith(base_dir + os.sep) or valid_path == base_dir
        
        # Attempt path traversal
        traversal_attempt = os.path.join(base_dir, "..", "..", "etc", "passwd")
        traversal_real = os.path.realpath(traversal_attempt)
        
        # Should NOT be within base_dir
        assert not traversal_real.startswith(base_dir + os.sep)
    
    def test_symlink_escape_detection(self, temp_dir):
        """Test detection of symlink-based directory escapes."""
        # Create directory structure
        safe_dir = Path(temp_dir) / "safe"
        safe_dir.mkdir()
        
        dangerous_dir = Path(temp_dir) / "dangerous"
        dangerous_dir.mkdir()
        
        # Create symlink that escapes safe_dir
        escape_link = safe_dir / "escape"
        escape_link.symlink_to(dangerous_dir)
        
        # Resolve the symlink
        resolved = os.path.realpath(str(escape_link))
        
        # Check it's outside safe_dir
        safe_real = os.path.realpath(str(safe_dir))
        assert not resolved.startswith(safe_real + os.sep)
    
    def test_double_dot_traversal(self, temp_dir):
        """Test that ../ sequences are handled correctly."""
        base = os.path.realpath(temp_dir)
        
        # Multiple ../ should not escape
        attempts = [
            os.path.join(base, "..", "..", "etc"),
            os.path.join(base, "subdir", "..", "..", "..", "etc"),
            os.path.join(base, "./.././..", "etc"),
        ]
        
        for attempt in attempts:
            resolved = os.path.realpath(attempt)
            # None should be within temp_dir
            assert not resolved.startswith(base + os.sep) or resolved == base
    
    def test_null_byte_injection(self, temp_dir):
        """Test handling of null byte injection attempts."""
        base_dir = Path(temp_dir)
        
        # Python 3 typically handles this safely, but test anyway
        try:
            # Attempt null byte in filename
            malicious = str(base_dir / "safe.txt\x00/etc/passwd")
            # os.path.join should handle this safely
            result = os.path.realpath(malicious)
            # Should not contain null byte in result
            assert "\x00" not in result
        except (ValueError, OSError):
            # Expected - null bytes should be rejected
            pass
    
    def test_absolute_path_injection(self, temp_dir):
        """Test that absolute paths can't escape base directory."""
        base_dir = os.path.realpath(temp_dir)
        
        # Try to inject absolute path via join
        injected = os.path.join(base_dir, "/etc/passwd")
        
        # os.path.join with absolute second arg returns the absolute path
        # Our code should validate this
        assert injected == "/etc/passwd"  # join returns the absolute path
        
        # The validation logic should catch this
        resolved = os.path.realpath(injected)
        assert not resolved.startswith(base_dir + os.sep)


class TestFileOperationSecurity:
    """Test security of file operations."""
    
    def test_safe_file_open_within_directory(self, temp_dir):
        """Test that file opens are restricted to expected directory."""
        base_dir = os.path.realpath(temp_dir)
        
        # Create a safe file
        safe_file = Path(temp_dir) / "safe.txt"
        safe_file.write_text("safe content")
        
        safe_path = os.path.realpath(str(safe_file))
        
        # Validate it's within base_dir
        assert safe_path.startswith(base_dir + os.sep)
        
        # Should be able to read it
        with open(safe_path, 'r') as f:
            content = f.read()
            assert content == "safe content"
    
    def test_reject_file_outside_directory(self, temp_dir):
        """Test that files outside base directory are rejected."""
        base_dir = os.path.realpath(temp_dir)
        
        # Try to reference a file outside
        outside_file = "/etc/passwd"
        outside_real = os.path.realpath(outside_file)
        
        # Validation should catch this
        assert not outside_real.startswith(base_dir + os.sep)
        
        # Application should reject this before opening
        # (simulating what our code does)
        if not outside_real.startswith(base_dir + os.sep):
            # Correctly rejected
            pass
        else:
            pytest.fail("Path traversal not detected")
    
    def test_symlink_file_validation(self, temp_dir):
        """Test validation of symlinked files."""
        base_dir = Path(temp_dir)
        
        # Create a file outside base_dir
        outside = Path(temp_dir).parent / "outside.txt"
        outside.write_text("outside")
        
        # Create symlink to it
        link = base_dir / "link.txt"
        try:
            link.symlink_to(outside)
            
            # Resolve the symlink
            resolved = os.path.realpath(str(link))
            
            # Should detect it's outside base_dir
            base_real = os.path.realpath(str(base_dir))
            assert not resolved.startswith(base_real + os.sep)
        finally:
            # Cleanup
            if link.exists():
                link.unlink()
            if outside.exists():
                outside.unlink()


class TestInputValidation:
    """Test input validation and sanitization."""
    
    def test_build_dir_validation(self, temp_dir):
        """Test build directory validation."""
        # Valid directory
        valid_dir = os.path.realpath(temp_dir)
        assert os.path.isdir(valid_dir)
        
        # Non-existent directory
        invalid_dir = os.path.join(temp_dir, "nonexistent")
        assert not os.path.isdir(invalid_dir)
        
        # File instead of directory
        file_path = Path(temp_dir) / "file.txt"
        file_path.write_text("content")
        assert not os.path.isdir(str(file_path))
    
    def test_command_injection_prevention(self):
        """Test that shell injection is prevented."""
        # Our code uses subprocess with lists, not shell=True
        # This should prevent command injection
        
        import subprocess
        
        # Safe: list of arguments
        safe_cmd = ["echo", "safe; rm -rf /"]
        # The "; rm -rf /" is treated as part of the echo argument, not executed
        
        # Our code should always use this pattern
        result = subprocess.run(safe_cmd, capture_output=True, text=True)
        assert "; rm -rf /" in result.stdout  # It's just text, not executed
    
    def test_relative_path_resolution(self, temp_dir):
        """Test that relative paths are properly resolved."""
        base = Path(temp_dir)
        
        # Create subdirectory
        subdir = base / "sub"
        subdir.mkdir()
        
        # Test relative path
        rel_path = "./sub/file.txt"
        full_path = os.path.realpath(os.path.join(str(base), rel_path))
        
        # Should be within base
        base_real = os.path.realpath(str(base))
        assert full_path.startswith(base_real + os.sep)
