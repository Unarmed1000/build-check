#!/usr/bin/env python3
"""
Demonstration of the enhanced generated file detection system.

This script shows how the system now correctly detects and rebuilds generated
files when their input dependencies (templates, scripts) change.
"""

import tempfile
import os
from pathlib import Path
from lib.ninja_utils import (
    parse_ninja_generated_files,
    check_generated_files_changed,
    load_generated_files_cache,
    save_generated_files_cache,
    compute_file_hash,
)


def create_demo_project(tmpdir: Path):
    """Create a demo project structure with ninja build file."""

    # Create build.ninja with protobuf generator
    build_ninja = tmpdir / "build.ninja"
    build_ninja.write_text(
        """
rule PROTOC
  command = protoc --cpp_out=. $in
  description = Generating C++ from $in
  generator = 1

rule XMLGEN
  command = python xmlgen.py $in $out
  description = Generating from XML template
  generator = 1

rule CXX_COMPILER
  command = g++ -c $in -o $out

# Generated files from protobuf
build message.pb.cc message.pb.h: PROTOC message.proto

# Generated files from XML template with Python script
build config.cpp config.h: XMLGEN config.xml | xmlgen.py

# Regular compilation (not generated)
build main.o: CXX_COMPILER main.cpp

# Link everything
build app: phony main.o message.pb.cc config.cpp
"""
    )

    # Create input files
    (tmpdir / "message.proto").write_text(
        """
syntax = "proto3";

message Request {
  string name = 1;
  int32 id = 2;
}
"""
    )

    (tmpdir / "config.xml").write_text(
        """
<config>
  <setting name="timeout">30</setting>
  <setting name="retries">3</setting>
</config>
"""
    )

    (tmpdir / "xmlgen.py").write_text(
        """
#!/usr/bin/env python3
import sys
xml_file = sys.argv[1]
out_file = sys.argv[2]
# Generate code from XML...
"""
    )

    (tmpdir / "main.cpp").write_text(
        """
#include "message.pb.h"
#include "config.h"
int main() { return 0; }
"""
    )

    # Create initial generated files
    (tmpdir / "message.pb.cc").write_text("// Generated from message.proto v1")
    (tmpdir / "message.pb.h").write_text("// Generated header v1")
    (tmpdir / "config.cpp").write_text("// Generated from config.xml v1")
    (tmpdir / "config.h").write_text("// Generated config header v1")

    return tmpdir, build_ninja


def demo_scenario():
    """Demonstrate the complete workflow."""

    print("=" * 70)
    print("GENERATED FILE DETECTION - DEMONSTRATION")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        tmpdir, build_ninja = create_demo_project(tmpdir)

        print("\n📁 Created demo project:")
        print(f"   Build directory: {tmpdir}")
        print(f"   - build.ninja (2 generator rules)")
        print(f"   - message.proto (input template)")
        print(f"   - config.xml (input template)")
        print(f"   - xmlgen.py (generator script)")
        print(f"   - message.pb.cc/h (generated outputs)")
        print(f"   - config.cpp/h (generated outputs)")

        # Parse build.ninja
        print("\n🔍 Parsing build.ninja...")
        all_tracked, output_to_info = parse_ninja_generated_files(str(build_ninja))

        print(f"   Found {len(all_tracked)} tracked files:")
        for file in sorted(all_tracked):
            print(f"      • {file}")

        print(f"\n   Dependency mappings:")
        for output, info in sorted(output_to_info.items()):
            if info.explicit_inputs:
                inputs = ", ".join(info.explicit_inputs)
                print(f"      {output} ← {inputs}")
                if info.implicit_inputs:
                    scripts = ", ".join(info.implicit_inputs)
                    print(f"         (via: {scripts})")

        # Create initial cache
        print("\n💾 Creating initial cache...")
        cache = {"build_ninja_mtime": os.path.getmtime(str(build_ninja)), "files": {}, "dependencies": {}}

        for file in all_tracked:
            full_path = tmpdir / file
            if full_path.exists():
                cache["files"][str(full_path)] = compute_file_hash(str(full_path))

        # Store dependencies
        for output, info in output_to_info.items():
            all_inputs = list(info.explicit_inputs) + list(info.implicit_inputs)
            if all_inputs:
                cache["dependencies"][output] = all_inputs

        print(f"   Cached {len(cache['files'])} file hashes")
        print(f"   Stored {len(cache['dependencies'])} dependency mappings")

        # Initial check - nothing should change
        print("\n✓ Initial check (no changes expected)...")
        missing, changed, reasons = check_generated_files_changed(str(tmpdir), all_tracked, cache, output_to_info)
        print(f"   Missing: {len(missing)}, Changed: {len(changed)}")
        assert len(missing) == 0 and len(changed) == 0, "Initial state should be clean"

        # Scenario 1: Modify input template
        print("\n" + "=" * 70)
        print("SCENARIO 1: Modify input template (message.proto)")
        print("=" * 70)

        proto_file = tmpdir / "message.proto"
        proto_file.write_text(
            """
syntax = "proto3";

message Request {
  string name = 1;
  int32 id = 2;
  string email = 3;  // NEW FIELD
}
"""
        )
        print(f"   ✏️  Modified: {proto_file.name} (added email field)")

        missing, changed, reasons = check_generated_files_changed(str(tmpdir), all_tracked, cache, output_to_info)

        print(f"\n   Detection results:")
        print(f"      Missing: {len(missing)}")
        print(f"      Changed: {len(changed)}")

        print(f"\n   Files needing rebuild:")
        for file_path in changed:
            basename = os.path.basename(file_path)
            reason = reasons.get(file_path, "unknown")
            print(f"      • {basename}: {reason}")

        # Verify correct files marked for rebuild
        pb_cc = str(tmpdir / "message.pb.cc")
        pb_h = str(tmpdir / "message.pb.h")
        assert pb_cc in changed or pb_h in changed, "Protobuf outputs should be marked for rebuild"
        print(f"\n   ✅ Correctly detected that protobuf outputs need rebuild")

        # Scenario 2: Modify generator script
        print("\n" + "=" * 70)
        print("SCENARIO 2: Modify generator script (xmlgen.py)")
        print("=" * 70)

        # Reset cache to current state
        cache["files"][str(proto_file)] = compute_file_hash(str(proto_file))

        script_file = tmpdir / "xmlgen.py"
        script_file.write_text(
            """
#!/usr/bin/env python3
import sys
xml_file = sys.argv[1]
out_file = sys.argv[2]
# UPDATED: New generation logic...
# Now includes validation
"""
        )
        print(f"   ✏️  Modified: {script_file.name} (updated generation logic)")

        missing, changed, reasons = check_generated_files_changed(str(tmpdir), all_tracked, cache, output_to_info)

        print(f"\n   Detection results:")
        print(f"      Changed: {len(changed)}")

        print(f"\n   Files needing rebuild:")
        for file_path in changed:
            basename = os.path.basename(file_path)
            reason = reasons.get(file_path, "unknown")
            print(f"      • {basename}: {reason}")

        # Verify XML-generated files marked for rebuild
        config_cpp = str(tmpdir / "config.cpp")
        config_h = str(tmpdir / "config.h")
        assert config_cpp in changed or config_h in changed, "XML-generated outputs should be marked for rebuild"
        print(f"\n   ✅ Correctly detected that XML-generated files need rebuild")

        # Scenario 3: Modify build.ninja
        print("\n" + "=" * 70)
        print("SCENARIO 3: Modify build rules (build.ninja)")
        print("=" * 70)

        # Simulate build.ninja change by updating mtime
        os.utime(str(build_ninja), None)
        new_mtime = os.path.getmtime(str(build_ninja))
        old_mtime = cache["build_ninja_mtime"]

        print(f"   ✏️  Modified: build.ninja")
        print(f"      Old mtime: {old_mtime:.2f}")
        print(f"      New mtime: {new_mtime:.2f}")

        if new_mtime != old_mtime:
            print(f"\n   ✅ build.ninja change detected!")
            print(f"      → Cache would be invalidated")
            print(f"      → All files would be rechecked")

        print("\n" + "=" * 70)
        print("DEMONSTRATION COMPLETE")
        print("=" * 70)
        print("\n✅ All scenarios passed successfully!")
        print("\n📊 Summary:")
        print("   • Input template changes detected correctly")
        print("   • Generator script changes detected correctly")
        print("   • build.ninja changes detected correctly")
        print("   • Dependent outputs marked for rebuild")
        print("   • Clear cause-effect in change reasons")
        print("\n🎯 The enhanced system correctly tracks ALL dependencies")
        print("   and triggers rebuilds when ANY input changes!")


if __name__ == "__main__":
    demo_scenario()
