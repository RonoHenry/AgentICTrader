# Test-Driven Development (TDD) Process

## Overview

This document outlines our TDD workflow for AgentI.C.Trader development.

## TDD Cycle

1. **RED**: Write a failing test first
   - Write test for new functionality
   - Run tests to verify it fails
   - Use: `.\run_tests.ps1`

2. **GREEN**: Write minimal code to pass
   - Implement just enough code to pass
   - Run tests to verify pass
   - Use: `.\run_tests.ps1`

3. **REFACTOR**: Clean up the code
   - Improve code without changing behavior
   - Run tests to ensure nothing breaks
   - Use: `.\run_tests.ps1`

## Test Categories

1. **Unit Tests**
   - Run without dependencies: `.\run_tests.ps1 -UnitOnly`
   - Quick feedback cycle
   - Test individual components

2. **Integration Tests**
   - Require Docker services
   - Run full suite: `.\run_tests.ps1`
   - Test component interactions

## Current Test Status

- Total Tests: 53
- Passing: 28
- Failing: 21
- Errors: 4
- Coverage: 68%

## Priority Areas

1. Infrastructure Tests
   - InfluxDB connection
   - API client mocks
   - Database interactions

2. Trading Logic Tests
   - Pattern recognition
   - Market analysis
   - Trade execution

3. Integration Tests
   - Component interaction
   - Data flow
   - System stability

## Best Practices

1. Always run unit tests before committing:
   ```powershell
   .\run_tests.ps1 -UnitOnly
   ```

2. Run full test suite before pushing:
   ```powershell
   .\run_tests.ps1
   ```

3. Add tests for bug fixes:
   - Create test that reproduces bug
   - Fix bug until test passes
   - Add regression test to suite

4. Maintain test coverage:
   - Aim for >80% coverage
   - Focus on critical paths
   - Test edge cases

## Test Command Reference

```powershell
# Run all tests
.\run_tests.ps1

# Run unit tests only
.\run_tests.ps1 -UnitOnly

# Run specific test file
.\run_tests.ps1 "tests/test_specific.py"

# Run tests with specific marker
.\run_tests.ps1 -m "not slow"

# Run with detailed coverage
.\run_tests.ps1 --cov-report=html
```

## Continuous Integration

Tests are automatically run on:
- Every push to master
- Pull request creation
- Pull request updates

## Test Organization

```
backend/tests/
├── infrastructure/     # Infrastructure tests
├── trader/            # Trading logic tests
├── conftest.py        # Test configuration
└── test_*.py         # Main test files
```

## Adding New Tests

1. Create test file in appropriate directory
2. Follow naming convention: `test_*.py`
3. Use pytest fixtures for setup
4. Include docstrings explaining test purpose
5. Run tests to verify setup

Example:
```python
"""Test module for pattern recognition."""
import pytest
from trader.analysis.patterns import PatternRecognizer

def test_pattern_recognition():
    """Test basic pattern recognition functionality."""
    recognizer = PatternRecognizer()
    result = recognizer.analyze(data)
    assert result.pattern == "expected_pattern"
```
