from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Dict, List


class TraceOutputManager:
    def __init__(self, base_dir: Path):
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def prepare_instance_dir(self, instance_id: str) -> Path:
        instance_dir = self._base_dir / instance_id
        instance_dir.mkdir(parents=True, exist_ok=True)
        instance_dir.chmod(0o777)
        return instance_dir

    def instance_dir(self, instance_id: str) -> Path:
        return self._base_dir / instance_id

    def trace_file(self, instance_id: str) -> Path:
        return self._base_dir / instance_id / "auto_debug.json"

    def test_output_file(self, instance_id: str) -> Path:
        return self._base_dir / instance_id / "test_output.txt"

    def trace_exists(self, instance_id: str) -> bool:
        return self.trace_file(instance_id).exists()

    def load_traces(self, instance_id: str) -> List[Dict[str, Any]]:
        path = self.trace_file(instance_id)
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def volume_spec(
        self, instance_id: str, tracer_dir: Path
    ) -> Dict[str, Dict[str, str]]:
        instance_dir = self.prepare_instance_dir(instance_id)
        tracer_path = Path(tracer_dir).resolve()
        return {
            str(tracer_path): {"bind": "/opt/tracers", "mode": "ro"},
            str(instance_dir): {"bind": "/trace_output", "mode": "rw"},
        }

    def environment(self) -> Dict[str, str]:
        return {
            "PYTHONPATH": "/opt/tracers:/testbed",
            "AUTO_DEBUG_JSON": "/trace_output/auto_debug.json",
        }

    def cleanup(self, instance_id: str) -> None:
        target = self.instance_dir(instance_id)
        if target.exists():
            shutil.rmtree(target)

    def list_instances(self) -> List[str]:
        return [item.name for item in self._base_dir.iterdir() if item.is_dir()]
