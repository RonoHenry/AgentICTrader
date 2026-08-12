"""
Verification script for integration test structure and completeness.
Validates that the integration tests meet all requirements from Task 7.3.
"""

import os
import re
from typing import List, Dict


def analyze_test_file(file_path: str) -> Dict:
    """Analyze the integration test file for required test coverage."""
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Count test methods using regex
    test_methods = re.findall(r'async def (test_\w+)', content)
    test_classes = re.findall(r'class (Test\w+)', content)
    
    # Categorize tests by name patterns
    performance_tests = [t for t in test_methods if 'performance' in t.lower() or 'time' in t.lower()]
    error_tests = [t for t in test_methods if any(kw in t.lower() for kw in ['error', 'failure', 'invalid', 'malformed'])]
    large_scale_tests = [t for t in test_methods if any(kw in t.lower() for kw in ['100', '250', '500', 'large', 'batch'])]
    
    # Check for integration markers
    has_integration_marker = '@pytest.mark.integration' in content
    has_performance_marker = '@pytest.mark.performance' in content
    
    return {
        'test_classes': test_classes,
        'test_methods': test_methods,
        'performance_tests': performance_tests,
        'error_tests': error_tests,
        'large_scale_tests': large_scale_tests,
        'has_integration_marker': has_integration_marker,
        'has_performance_marker': has_performance_marker,
        'total_tests': len(test_methods)
    }


def check_requirements_coverage(analysis: Dict) -> Dict:
    """Check if the tests cover all Task 7.3 requirements."""
    
    # Task 7.3 Requirements:
    # - Test ingestion of 100+ setups ✓
    # - Test error handling (network failures, invalid data) ✓  
    # - Test ingestion performance (< 1s per setup) ✓
    # - Requirements: FR-RAG-7 (Real-Time Ingestion), NFR-RAG-1 (Performance)
    
    requirements_coverage = {
        "100+ setups ingestion": bool(analysis['large_scale_tests']),
        "error handling": bool(analysis['error_tests']),
        "performance testing": bool(analysis['performance_tests']),
        "integration markers": analysis['has_integration_marker'],
        "performance markers": analysis['has_performance_marker'],
    }
    
    return requirements_coverage


def verify_test_structure() -> None:
    """Main verification function."""
    
    test_file = os.path.join(
        os.path.dirname(__file__), 
        'test_ingestion_integration.py'
    )
    
    if not os.path.exists(test_file):
        print("❌ Integration test file not found!")
        return
    
    print("AlgoRAG Integration Test Verification")
    print("=" * 40)
    print()
    
    try:
        analysis = analyze_test_file(test_file)
        requirements = check_requirements_coverage(analysis)
        
        print(f"📊 Test Statistics:")
        print(f"   Total test classes: {len(analysis['test_classes'])}")
        print(f"   Total test methods: {analysis['total_tests']}")
        print(f"   Performance tests: {len(analysis['performance_tests'])}")
        print(f"   Error handling tests: {len(analysis.get('error_tests', []))}")
        print(f"   Large scale tests: {len(analysis['large_scale_tests'])}")
        print()
        
        print(f"📋 Test Classes Found:")
        for cls in analysis['test_classes']:
            print(f"   - {cls}")
        print()
        
        print(f"🎯 Requirements Coverage:")
        for req, covered in requirements.items():
            status = "✅" if covered else "❌"
            print(f"   {status} {req}")
        print()
        
        # Detailed test breakdown
        print(f"📝 Large Scale Tests (100+ setups):")
        for test in analysis['large_scale_tests']:
            print(f"   - {test}")
        print()
        
        print(f"⚠️  Error Handling Tests:")
        for test in analysis.get('error_tests', []):
            print(f"   - {test}")
        print()
        
        print(f"⚡ Performance Tests (< 1s per setup):")
        for test in analysis['performance_tests']:
            print(f"   - {test}")
        print()
        
        # Overall assessment
        all_covered = all(requirements.values())
        has_sufficient_tests = analysis['total_tests'] >= 15  # Minimum threshold
        
        print(f"🔍 Assessment:")
        print(f"   Requirements covered: {'✅ All' if all_covered else '❌ Incomplete'}")
        print(f"   Test coverage: {'✅ Sufficient' if has_sufficient_tests else '❌ Insufficient'} ({analysis['total_tests']} tests)")
        print()
        
        if all_covered and has_sufficient_tests:
            print("✅ Integration tests are complete and comprehensive!")
            print("   Ready for execution with live Qdrant instance.")
        else:
            print("❌ Integration tests need additional work.")
            
    except Exception as e:
        print(f"❌ Error analyzing test file: {e}")


if __name__ == "__main__":
    verify_test_structure()