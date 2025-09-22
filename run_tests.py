#!/usr/bin/env python
"""
Test runner script for Smart Scout App.

This script provides a convenient way to run different types of tests
with various configurations and options.
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Set Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()


def run_command(command, description):
    """Run a command and handle errors."""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(command)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        print("✅ SUCCESS")
        if result.stdout:
            print("STDOUT:")
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print("❌ FAILED")
        print(f"Return code: {e.returncode}")
        if e.stdout:
            print("STDOUT:")
            print(e.stdout)
        if e.stderr:
            print("STDERR:")
            print(e.stderr)
        return False


def run_unit_tests():
    """Run unit tests."""
    command = ["python", "-m", "pytest", "tests/unit/", "-m", "unit", "-v"]
    return run_command(command, "Unit Tests")


def run_integration_tests():
    """Run integration tests."""
    command = ["python", "-m", "pytest", "tests/integration/", "-m", "integration", "-v"]
    return run_command(command, "Integration Tests")


def run_api_tests():
    """Run API tests."""
    command = ["python", "-m", "pytest", "tests/api/", "-m", "api", "-v"]
    return run_command(command, "API Tests")


def run_validation_tests():
    """Run validation tests."""
    command = ["python", "-m", "pytest", "tests/unit/test_validation.py", "-m", "validation", "-v"]
    return run_command(command, "Validation Tests")


def run_all_tests():
    """Run all tests."""
    command = ["python", "-m", "pytest", "tests/", "-v", "--cov=.", "--cov-report=html"]
    return run_command(command, "All Tests with Coverage")


def run_django_tests():
    """Run Django-specific tests."""
    command = ["python", "manage.py", "test"]
    return run_command(command, "Django Tests")


def run_specific_test(test_path):
    """Run a specific test file or test function."""
    command = ["python", "-m", "pytest", test_path, "-v"]
    return run_command(command, f"Specific Test: {test_path}")


def run_tests_with_coverage():
    """Run tests with coverage report."""
    command = [
        "python", "-m", "pytest", 
        "tests/", 
        "--cov=.", 
        "--cov-report=html", 
        "--cov-report=term-missing",
        "--cov-fail-under=80",
        "-v"
    ]
    return run_command(command, "Tests with Coverage Report")


def run_slow_tests():
    """Run slow tests."""
    command = ["python", "-m", "pytest", "tests/", "-m", "slow", "-v"]
    return run_command(command, "Slow Tests")


def lint_code():
    """Run code linting."""
    command = ["python", "-m", "flake8", "apps/", "tests/", "--max-line-length=100"]
    return run_command(command, "Code Linting")


def format_code():
    """Format code with black."""
    command = ["python", "-m", "black", "apps/", "tests/", "--line-length=100"]
    return run_command(command, "Code Formatting")


def main():
    """Main function to handle command line arguments."""
    parser = argparse.ArgumentParser(description="Smart Scout App Test Runner")
    parser.add_argument(
        "test_type",
        choices=[
            "unit", "integration", "api", "validation", "all", 
            "django", "coverage", "slow", "lint", "format", "specific"
        ],
        help="Type of tests to run"
    )
    parser.add_argument(
        "--test-path",
        help="Path to specific test file or function (for 'specific' test type)"
    )
    
    args = parser.parse_args()
    
    success = True
    
    if args.test_type == "unit":
        success = run_unit_tests()
    elif args.test_type == "integration":
        success = run_integration_tests()
    elif args.test_type == "api":
        success = run_api_tests()
    elif args.test_type == "validation":
        success = run_validation_tests()
    elif args.test_type == "all":
        success = run_all_tests()
    elif args.test_type == "django":
        success = run_django_tests()
    elif args.test_type == "coverage":
        success = run_tests_with_coverage()
    elif args.test_type == "slow":
        success = run_slow_tests()
    elif args.test_type == "lint":
        success = lint_code()
    elif args.test_type == "format":
        success = format_code()
    elif args.test_type == "specific":
        if not args.test_path:
            print("❌ Error: --test-path is required for 'specific' test type")
            sys.exit(1)
        success = run_specific_test(args.test_path)
    
    if success:
        print("\n🎉 All tests completed successfully!")
        sys.exit(0)
    else:
        print("\n💥 Some tests failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
