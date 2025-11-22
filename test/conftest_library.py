#!/usr/bin/env python3
"""Library and ninja-specific test fixtures."""

import pytest
import json
from typing import Dict, Set, List, Tuple
from pathlib import Path


@pytest.fixture(scope='module')
def mock_library_mapping_simple() -> Dict[str, str]:
    """Simple library mapping: 3 libraries, 10 headers."""
    return {
        'Core/base.hpp': 'libCore.a',
        'Core/utils.hpp': 'libCore.a',
        'Core/types.hpp': 'libCore.a',
        'UI/window.hpp': 'libUI.a',
        'UI/button.hpp': 'libUI.a',
        'UI/label.hpp': 'libUI.a',
        'Graphics/render.hpp': 'libGraphics.a',
        'Graphics/shader.hpp': 'libGraphics.a',
        'Graphics/texture.hpp': 'libGraphics.a',
        'Graphics/mesh.hpp': 'libGraphics.a',
    }


@pytest.fixture(scope='module')
def mock_library_mapping_medium() -> Dict[str, str]:
    """Medium library mapping: 10 libraries, 50 headers."""
    mapping = {}
    
    libraries = [
        ('Foundation', 8),
        ('Core', 6),
        ('Utils', 5),
        ('Graphics', 7),
        ('UI', 6),
        ('Network', 4),
        ('Audio', 3),
        ('Physics', 5),
        ('AI', 3),
        ('Game', 3),
    ]
    
    for lib_name, count in libraries:
        for i in range(count):
            header = f'{lib_name}/Header{i}.hpp'
            mapping[header] = f'lib{lib_name}.a'
    
    return mapping


@pytest.fixture(scope='module')
def mock_library_mapping_complex() -> Dict[str, str]:
    """Complex library mapping: 25 libraries, 200 headers."""
    mapping = {}
    
    # Foundation layer (5 libraries, 60 headers)
    for lib_idx in range(5):
        for header_idx in range(12):
            header = f'Foundation/Lib{lib_idx}/Header{header_idx}.hpp'
            mapping[header] = f'libFoundation{lib_idx}.a'
    
    # Core layer (8 libraries, 64 headers)
    for lib_idx in range(8):
        for header_idx in range(8):
            header = f'Core/Lib{lib_idx}/Header{header_idx}.hpp'
            mapping[header] = f'libCore{lib_idx}.a'
    
    # Application layer (12 libraries, 72 headers)
    for lib_idx in range(12):
        for header_idx in range(6):
            header = f'App/Module{lib_idx}/Header{header_idx}.hpp'
            mapping[header] = f'libApp{lib_idx}.a'
    
    return mapping


@pytest.fixture
def mock_ninja_libraries() -> Dict[str, List[str]]:
    """Mock ninja library link dependencies."""
    return {
        'libApp.a': ['libCore.a', 'libUI.a', 'libGraphics.a'],
        'libUI.a': ['libCore.a', 'libGraphics.a'],
        'libGraphics.a': ['libCore.a', 'libFoundation.a'],
        'libCore.a': ['libFoundation.a'],
        'libFoundation.a': [],
    }


@pytest.fixture
def mock_compile_commands_multi(temp_dir: str) -> str:
    """Create mock compile_commands.json for multi-library project."""
    build_dir = Path(temp_dir) / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    
    src_dir = Path(temp_dir) / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    
    compile_commands = []
    
    libraries = ['Core', 'UI', 'Graphics', 'Network']
    for lib in libraries:
        lib_src = src_dir / lib
        lib_src.mkdir(exist_ok=True)
        
        for i in range(3):
            source = lib_src / f"file{i}.cpp"
            source.write_text(f"// {lib} source file {i}")
            
            compile_commands.append({
                "directory": str(build_dir),
                "command": f"g++ -I{src_dir} -c {source} -o {build_dir}/{lib}_file{i}.o",
                "file": str(source)
            })
    
    compile_db = build_dir / "compile_commands.json"
    with open(compile_db, 'w') as f:
        json.dump(compile_commands, f, indent=2)
    
    return str(compile_db)


@pytest.fixture
def mock_library_boundaries() -> Dict[str, Dict[str, Set[str]]]:
    """Mock library boundary violations.
    
    Returns:
        Dict mapping library name to {internal_deps, external_deps}
    """
    return {
        'libCore.a': {
            'internal': {'Core/base.hpp', 'Core/utils.hpp'},
            'external': set()  # Foundation layer, no violations
        },
        'libUI.a': {
            'internal': {'UI/window.hpp', 'UI/button.hpp'},
            'external': {'Core/base.hpp', 'Graphics/render.hpp'}  # Allowed
        },
        'libGraphics.a': {
            'internal': {'Graphics/render.hpp', 'Graphics/shader.hpp'},
            'external': {'Core/base.hpp', 'UI/window.hpp'}  # VIOLATION: Graphics -> UI
        },
    }


@pytest.fixture
def mock_cross_library_deps() -> List[Tuple[str, str, str, str]]:
    """Mock cross-library dependency edges."""
    return [
        ('App/main.hpp', 'UI/window.hpp', 'libApp.a', 'libUI.a'),
        ('App/main.hpp', 'Core/base.hpp', 'libApp.a', 'libCore.a'),
        ('UI/window.hpp', 'Graphics/render.hpp', 'libUI.a', 'libGraphics.a'),
        ('Graphics/render.hpp', 'Core/types.hpp', 'libGraphics.a', 'libCore.a'),
        ('Graphics/shader.hpp', 'UI/button.hpp', 'libGraphics.a', 'libUI.a'),  # Violation
    ]
