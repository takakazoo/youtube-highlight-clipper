import unittest
import sys
import os

# Add parent directory to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def run_regression_tests():
    print("=" * 70)
    print("  [TEST SUITE] YouTube Highlight Clipper - Regression Tests")
    print("=" * 70)

    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.dirname(__file__), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "=" * 70)
    if result.wasSuccessful():
        print(f"  [SUCCESS] ALL REGRESSION TESTS PASSED! ({result.testsRun} tests executed)")
        print("=" * 70)
        return 0
    else:
        print(f"  [FAILURE] SOME TESTS FAILED! (Failures: {len(result.failures)}, Errors: {len(result.errors)})")
        print("=" * 70)
        return 1

if __name__ == '__main__':
    exit_code = run_regression_tests()
    sys.exit(exit_code)
