from __future__ import annotations

import json
from dataclasses import replace
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional


class Framework(str, Enum):
    PYTEST = "pytest"
    UNITTEST = "unittest"
    DJANGO = "django"
    UNKNOWN = "unknown"


_PYTEST_INDICATORS = ("pytest", "py.test")
_DJANGO_INDICATORS = ("manage.py test", "runtests.py")
_UNITTEST_INDICATORS = ("python -m unittest", "unittest")


class FrameworkDetector:
    def __init__(self, *, cache_path: Optional[Path] = None):
        self._cache_path = Path(cache_path) if cache_path is not None else None
        self._cache: Dict[str, str] = self._load_cache()

    def _load_cache(self) -> Dict[str, str]:
        if self._cache_path is None or not self._cache_path.exists():
            return {}
        try:
            return json.loads(self._cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_cache(self) -> None:
        if self._cache_path is None:
            return
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._cache, indent=2), encoding="utf-8"
        )

    def detect(self, test_spec) -> Framework:
        instance_id = getattr(test_spec, "instance_id", None)
        if instance_id and instance_id in self._cache:
            return Framework(self._cache[instance_id])

        eval_script = " ".join(test_spec.eval_script_list).lower()
        framework = self._classify(eval_script)

        if instance_id:
            self._cache[instance_id] = framework.value
            self._save_cache()
        return framework

    def _classify(self, eval_script: str) -> Framework:
        if any(indicator in eval_script for indicator in _PYTEST_INDICATORS):
            return Framework.PYTEST
        if any(indicator in eval_script for indicator in _DJANGO_INDICATORS):
            return Framework.DJANGO
        if any(indicator in eval_script for indicator in _UNITTEST_INDICATORS):
            return Framework.UNITTEST
        return Framework.UNKNOWN

    def inject(self, test_spec):
        framework = self.detect(test_spec)
        preamble = self._common_preamble(framework)
        if framework is Framework.PYTEST:
            preamble = preamble + self._pytest_conftest_commands()
        new_eval_script_list = preamble + list(test_spec.eval_script_list)
        return replace(test_spec, eval_script_list=new_eval_script_list)

    def _common_preamble(self, framework: Framework) -> List[str]:
        return [
            "export PYTHONPATH=/opt/tracers:/testbed:$PYTHONPATH",
            "export AUTO_DEBUG_JSON=/trace_output/auto_debug.json",
            f"export AUTO_DEBUG_FRAMEWORK={framework.value}",
            "chmod 777 /trace_output || true",
            "pip install jsonpickle -q || true",
        ]

    def _pytest_conftest_commands(self) -> List[str]:
        return self._load_template("pytest_conftest_setup.sh")

    @staticmethod
    def _load_template(name: str) -> List[str]:
        template_path = Path(__file__).resolve().parent.parent / "tracing" / "templates" / name
        text = template_path.read_text(encoding="utf-8")
        return [line for line in text.splitlines() if line != ""]
