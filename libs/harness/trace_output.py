from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ProjectScope:
    def __init__(self, path: Path):
        self._path = path
        self._closed = False

    @property
    def path(self) -> Path:
        return self._path

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._path.exists():
            try:
                shutil.rmtree(self._path)
                logger.info("Cleaned up project mirror: %s", self._path)
            except OSError:
                logger.warning(
                    "Failed to clean up project mirror: %s",
                    self._path,
                    exc_info=True,
                )

    def __enter__(self) -> ProjectScope:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()


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

    def project_dir(self, instance_id: str) -> Path:
        target = self._base_dir / instance_id / "project"
        target.mkdir(parents=True, exist_ok=True)
        return target

    def project_scope(self, instance_id: str) -> ProjectScope:
        target = self.project_dir(instance_id)
        if any(target.iterdir()):
            shutil.rmtree(target)
            target.mkdir(parents=True, exist_ok=True)
        return ProjectScope(target)

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
        project_dir = self.project_dir(instance_id)
        tracer_path = Path(tracer_dir).resolve()
        return {
            str(tracer_path): {"bind": "/opt/tracers", "mode": "ro"},
            str(instance_dir): {"bind": "/trace_output", "mode": "rw"},
            str(project_dir): {"bind": "/project_mirror", "mode": "rw"},
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
