# Internal Tests

This directory contains tests that are specific to internal development and validation.

## Warning

**These tests are hardcoded for specific internal projects and should not be run externally.**

### testBuildCheckRippleEffect.py

Tests the `buildCheckRippleEffect.py` script by:
- Checking out previous and current commits
- Building with FslBuildGen.py and ninja
- Comparing predicted rebuild impact with actual ninja rebuild plan

**Requirements:**
- gtec-demo-framework repository
- FslBuildGen.py build system
- Ninja build system
- Git repository with test commits containing C/C++ changes

This test validates that the ripple effect analysis correctly predicts which source files will be rebuilt when headers change.
