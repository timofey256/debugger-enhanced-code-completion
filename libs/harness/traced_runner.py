from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Optional

import docker

from libs.harness.framework_detector import Framework, FrameworkDetector
from libs.harness.trace_output import TraceOutputManager

from swebench.harness.constants import (
    APPLY_PATCH_FAIL,
    APPLY_PATCH_PASS,
    DOCKER_PATCH,
    DOCKER_USER,
    DOCKER_WORKDIR,
    KEY_PREDICTION,
)
from swebench.harness.docker_build import build_instance_image
from swebench.harness.docker_utils import (
    cleanup_container,
    copy_to_container,
    exec_run_with_timeout,
)
from swebench.harness.test_spec.test_spec import TestSpec


_GIT_APPLY_CMDS = [
    "git apply --verbose",
    "git apply --verbose --reject",
    "patch --batch --fuzz=5 -p1 -i",
]


class TraceCollectionError(Exception):
    pass


@dataclass
class RunResult:
    success: bool
    instance_id: str
    framework: str
    trace_path: Optional[str] = None
    num_failures: int = 0
    runtime: float = 0.0
    error: Optional[str] = None
    traceback: Optional[str] = None
    test_output_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


class TracedInstanceRunner:
    def __init__(
        self,
        *,
        client: docker.DockerClient,
        test_spec: TestSpec,
        run_id: str,
        trace_collector_dir: Path,
        output_manager: TraceOutputManager,
        framework_detector: FrameworkDetector,
        logger: logging.Logger,
        timeout: Optional[int] = None,
        force_rebuild: bool = False,
        nocache: bool = False,
    ):
        self._client = client
        self._test_spec = test_spec
        self._run_id = run_id
        self._trace_collector_dir = Path(trace_collector_dir).resolve()
        self._output_manager = output_manager
        self._framework_detector = framework_detector
        self._logger = logger
        self._timeout = timeout
        self._force_rebuild = force_rebuild
        self._nocache = nocache

        self._prepared_spec: Optional[TestSpec] = None
        self._framework: Optional[Framework] = None
        self._image_built = False

    @property
    def framework(self) -> Framework:
        if self._framework is None:
            self._prepare_test_spec()
        return self._framework  # type: ignore[return-value]

    def run(self, pred: Dict[str, Any], *, skip_patch: bool = False) -> RunResult:
        instance_id = self._test_spec.instance_id
        self._logger.info("=" * 60)
        self._logger.info("Processing: %s", instance_id)
        self._logger.info("=" * 60)

        spec = self._prepare_test_spec()
        framework_value = self._framework.value if self._framework else "unknown"

        instance_dir = self._output_manager.prepare_instance_dir(instance_id)
        trace_path = self._output_manager.trace_file(instance_id)
        self._logger.info("Trace output: %s", trace_path)

        container = None
        try:
            self._ensure_image(spec)

            container = self._start_container(spec, instance_dir)

            if not skip_patch:
                self._apply_patch(container, pred, instance_dir)
            else:
                self._logger.info("Skipping patch application (skip_patch=True)")

            test_output_path, runtime = self._execute_eval(
                container, spec, instance_dir
            )

            traces = self._load_traces(trace_path)

            self._logger.info(
                "Successfully collected %d trace(s) for %s",
                len(traces),
                instance_id,
            )
            return RunResult(
                success=True,
                instance_id=instance_id,
                framework=framework_value,
                trace_path=str(trace_path),
                num_failures=len(traces),
                runtime=runtime,
                test_output_path=str(test_output_path),
            )

        except Exception as exc:
            tb_text = traceback.format_exc()
            self._logger.error(
                "Failed to collect traces for %s: %s\n%s",
                instance_id,
                exc,
                tb_text,
            )
            return RunResult(
                success=False,
                instance_id=instance_id,
                framework=framework_value,
                error=str(exc),
                traceback=tb_text,
                trace_path=str(trace_path) if trace_path.exists() else None,
                test_output_path=str(self._output_manager.test_output_file(instance_id))
                if self._output_manager.test_output_file(instance_id).exists()
                else None,
            )

        finally:
            if container is not None:
                self._logger.info("Cleaning up container for %s", instance_id)
                cleanup_container(self._client, container, self._logger)

    def _prepare_test_spec(self) -> TestSpec:
        if self._prepared_spec is None:
            self._framework = self._framework_detector.detect(self._test_spec)
            self._logger.info("Detected framework: %s", self._framework.value)
            self._prepared_spec = self._framework_detector.inject(self._test_spec)
        return self._prepared_spec

    def _ensure_image(self, spec: TestSpec) -> None:
        if self._image_built:
            return
        if self._force_rebuild or not getattr(spec, "is_remote_image", False):
            self._logger.info(
                "Building instance image: %s", spec.instance_image_key
            )
            build_instance_image(spec, self._client, self._logger, self._nocache)
        self._image_built = True

    def _start_container(self, spec: TestSpec, instance_dir: Path):
        instance_id = spec.instance_id
        volumes = self._output_manager.volume_spec(
            instance_id, self._trace_collector_dir
        )
        environment = self._output_manager.environment()
        run_args = spec.docker_specs.get("run_args", {})
        cap_add = run_args.get("cap_add", [])

        self._logger.info("Volume mounts: %s", volumes)
        self._logger.info("Environment: %s", environment)

        container = self._client.containers.create(
            image=spec.instance_image_key,
            name=spec.get_instance_container_name(self._run_id),
            user=DOCKER_USER,
            detach=True,
            command="tail -f /dev/null",
            platform=spec.platform,
            cap_add=cap_add,
            volumes=volumes,
            environment=environment,
        )
        container.start()
        self._logger.info("Traced container started: %s", container.id)

        if not self._verify_setup(container):
            raise TraceCollectionError("Trace setup verification failed")
        return container

    def _verify_setup(self, container) -> bool:
        ok = True
        result = container.exec_run("ls -la /opt/tracers")
        if result.exit_code != 0:
            self._logger.error("/opt/tracers directory not found in container")
            ok = False
        result = container.exec_run("touch /trace_output/test_write")
        if result.exit_code != 0:
            self._logger.error("/trace_output directory not writable")
            ok = False
        else:
            container.exec_run("rm -f /trace_output/test_write")
        return ok

    def _apply_patch(self, container, pred: Dict[str, Any], instance_dir: Path) -> None:
        patch_content = pred.get(KEY_PREDICTION, "") or ""
        if not patch_content.strip():
            self._logger.warning("Empty patch content")

        temp_patch_file = instance_dir / "patch.diff"
        temp_patch_file.write_text(patch_content)
        copy_to_container(container, temp_patch_file, PurePosixPath(DOCKER_PATCH))

        for git_apply_cmd in _GIT_APPLY_CMDS:
            result = container.exec_run(
                f"{git_apply_cmd} {DOCKER_PATCH}",
                workdir=DOCKER_WORKDIR,
                user=DOCKER_USER,
            )
            if result.exit_code == 0:
                self._logger.info("%s: %s", APPLY_PATCH_PASS, git_apply_cmd)
                return
            self._logger.debug("Failed to apply patch with %s", git_apply_cmd)

        raise TraceCollectionError(
            f"{APPLY_PATCH_FAIL}: All git apply strategies failed"
        )

    def _execute_eval(self, container, spec: TestSpec, instance_dir: Path):
        temp_eval_file = instance_dir / "eval.sh"
        temp_eval_file.write_text(spec.eval_script)
        copy_to_container(container, temp_eval_file, PurePosixPath("/eval.sh"))

        self._logger.info("Running tests with trace collection...")
        test_output, timed_out, runtime = exec_run_with_timeout(
            container, "/bin/bash /eval.sh", self._timeout
        )
        self._logger.info("Test runtime: %.2f seconds", runtime)

        test_output_path = self._output_manager.test_output_file(spec.instance_id)
        test_output_path.write_text(test_output)
        self._logger.info("Test output saved to: %s", test_output_path)

        if timed_out:
            raise TraceCollectionError(
                f"Test execution timed out after {self._timeout}s"
            )
        return test_output_path, runtime

    def _load_traces(self, trace_path: Path) -> List[Dict[str, Any]]:
        if not trace_path.exists():
            raise TraceCollectionError(
                f"Trace file not created: {trace_path}. "
                "Tests may not have failed, or trace collection did not activate."
            )
        try:
            import json as _json

            with open(trace_path, "r") as f:
                traces = _json.load(f)
        except Exception as exc:
            raise TraceCollectionError(f"Invalid JSON in trace file: {exc}") from exc
        if not isinstance(traces, list):
            raise TraceCollectionError(
                f"Invalid trace format: expected list, got {type(traces)}"
            )
        return traces
