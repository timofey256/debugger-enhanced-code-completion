"""
Unit tests for framework detection.
"""

import sys
import unittest
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from swebench_integration.framework_detector import FrameworkDetector


class TestFrameworkDetector(unittest.TestCase):
    """Test framework detection logic."""

    def setUp(self):
        """Set up test fixtures."""
        self.detector = FrameworkDetector(cache_path="test_cache.json")

    def test_detect_pytest(self):
        """Test detection of pytest from command."""
        framework = self.detector._detect_from_command("pytest tests/")
        self.assertEqual(framework, "pytest")

    def test_detect_unittest(self):
        """Test detection of unittest from command."""
        framework = self.detector._detect_from_command("python -m unittest discover")
        self.assertEqual(framework, "unittest")

    def test_detect_django(self):
        """Test detection of Django from command."""
        framework = self.detector._detect_from_command("./manage.py test")
        self.assertEqual(framework, "django")

    def test_detect_custom(self):
        """Test detection of custom test runners."""
        framework = self.detector._detect_from_command("bin/test -C --verbose")
        self.assertEqual(framework, "custom")

    def test_default_to_pytest(self):
        """Test that unknown commands default to pytest."""
        framework = self.detector._detect_from_command("unknown command")
        self.assertEqual(framework, "pytest")

    def test_cache_works(self):
        """Test that caching works correctly."""
        # TODO: Implement test
        pass

    def test_batch_detect(self):
        """Test batch detection of multiple instances."""
        # TODO: Implement test
        pass


if __name__ == "__main__":
    unittest.main()
