"""
Sample failing tests to verify unittest tracer works.
"""

import unittest


class SampleTests(unittest.TestCase):
    """Sample test cases with intentional failures."""

    def test_assertion_failure(self):
        """Test that fails with assertion error."""
        x = 42
        y = "hello"
        z = [1, 2, 3]
        self.assertEqual(x, 100)  # This will fail

    def test_exception_error(self):
        """Test that fails with exception."""
        data = {"key": "value"}
        result = 1 / 0  # This will raise ZeroDivisionError

    def test_passing(self):
        """Test that passes (should not be captured)."""
        self.assertEqual(1 + 1, 2)


if __name__ == "__main__":
    unittest.main()
