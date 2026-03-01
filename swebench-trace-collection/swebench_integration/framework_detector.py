"""
Framework detection for SWE-bench repositories.

Detects whether a repository uses pytest, unittest, Django, or custom test frameworks.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import re


class FrameworkDetector:
    """
    Detect test framework used by SWE-bench instances.

    Detection priority:
    1. SWE-bench constants (test commands)
    2. Config files (pytest.ini, setup.cfg, pyproject.toml)
    3. Test file analysis (imports and patterns)
    4. Default to pytest (most common)
    """

    def __init__(self, cache_path: str = "config/framework_cache.json"):
        self.cache_path = Path(cache_path)
        self.cache: Dict[str, str] = self._load_cache()

    def _load_cache(self) -> Dict[str, str]:
        """Load cached framework detection results."""
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text())
            except Exception as e:
                print(f"Warning: Failed to load cache: {e}")
        return {}

    def _save_cache(self):
        """Save framework detection results to cache."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self.cache, indent=2))
        except Exception as e:
            print(f"Warning: Failed to save cache: {e}")

    def detect(self, instance_id: str, test_command: Optional[str] = None) -> str:
        """
        Detect framework for a single instance.

        Args:
            instance_id: SWE-bench instance ID
            test_command: Optional test command from SWE-bench constants

        Returns:
            Framework name: "pytest", "unittest", "django", or "custom"
        """
        # Check cache first
        if instance_id in self.cache:
            return self.cache[instance_id]

        # Detect based on test command
        framework = self._detect_from_command(test_command)

        # Cache the result
        self.cache[instance_id] = framework
        self._save_cache()

        return framework

    def _detect_from_command(self, test_command: Optional[str]) -> str:
        """Detect framework from test command string."""
        if not test_command:
            return "pytest"  # Default

        command = test_command.lower()

        # Check for pytest
        if "pytest" in command or "py.test" in command:
            return "pytest"

        # Check for unittest
        if "unittest" in command or "python -m unittest" in command:
            return "unittest"

        # Check for Django
        if "manage.py test" in command or "django" in command:
            return "django"

        # Check for custom test runners
        if "bin/test" in command or "runtests.py" in command:
            return "custom"

        # Default to pytest (most common in SWE-bench)
        return "pytest"

    def batch_detect(self, instances: List[Dict]) -> Dict[str, str]:
        """
        Detect frameworks for multiple instances.

        Args:
            instances: List of SWE-bench instance dicts

        Returns:
            Mapping of instance_id -> framework
        """
        results = {}

        for instance in instances:
            instance_id = instance.get("instance_id")
            test_command = instance.get("test_command")

            if instance_id:
                framework = self.detect(instance_id, test_command)
                results[instance_id] = framework

        return results

    def parse_swebench_constants(self, constants_path: str) -> Dict[str, str]:
        """
        Parse SWE-bench constants.py to extract test commands.

        Args:
            constants_path: Path to swebench/harness/constants/python.py

        Returns:
            Mapping of repo -> test command
        """
        # TODO: Implement parsing of constants.py
        # This will extract TEST_PYTEST, TEST_DJANGO, etc. and map to repos
        return {}
