# Project Structure: debugger-enhanced-code-completion

A research project that augments LLM code completion with runtime debugging information collected via pytest/unittest tracers, exposed through a Flask backend and a VSCode extension, and evaluated against SWE-bench Lite.

## Root files

- `README.md` — Project overview, research/technical objectives, methodology.
- `flake.nix` / `flake.lock` / `shell.nix` — Nix dev environment definitions.
- `auto_debug.json` — Sample/last-run trace dump produced by the tracers.
- `package-lock.json` — Top-level Node lockfile (extension build).

## `assets/`
- `diagram.png` — Logic/architecture diagram referenced in the README.

## `backend/` — Python Flask server that turns traces into LLM patches
- `pyproject.toml` — Package metadata for `pytest-smart-debugger-server`.
- `default.nix` — Nix build for the backend package.
- `src/pytest_smart_debugger_server/server.py` — Flask HTTP server: receives traces, calls LLM, returns patches.
- `src/pytest_smart_debugger_server/generate_prompt.py` — Builds the LLM prompt (template + runtime trace) from trace JSON.
- `src/pytest_smart_debugger_server/completion_model.py` — Processes trace logs and constructs LLM context.
- `src/pytest_smart_debugger_server/apply_patch.py` — Parses unified diff text into structured hunks.
- `tests/` — Backend tests (currently empty placeholder).

## `infra/` — Shared infrastructure package
- `pyproject.toml` — Defines the `infra` Python package.
- `src/infra/llm_connector.py` — Unified LLM client wrapping multiple providers via OpenAI-compatible APIs.
- `src/infra/llm_providers.yaml` — Provider/model configuration (endpoints, env-var keys).

## `pytest-smart-debugger-extension/` — VSCode extension (TypeScript)
- `package.json` — Extension manifest (commands, configuration, activation events).
- `tsconfig.json` — TS compiler config.
- `pytest-smart-debugger-0.0.1.vsix` — Packaged extension artifact.
- `src/extension.ts` — Entry point: registers commands, spawns the backend server.
- `src/testDiscovery.ts` — Discovers pytest tests via `pytest --collect-only`.
- `src/pytestRunner.ts` — Runs pytest, captures failures and exposes them to the Test UI.
- `src/server.ts` — Talks to backend HTTP server; ensures it's alive, sends payloads.
- `src/patchFormat.ts` — Types and unified-diff text builder for structured patches.
- `src/patch.ts` — Applies structured hunk patches to workspace files.
- `src/diffWebview.ts` — Webview UI to preview a unified diff and accept/dismiss it.
- `templates/conftest.py` — pytest hook template installed in user's project to capture failures.

## `swebench-trace-collection/` — SWE-bench Lite benchmark + trace collection harness
- `requirements.txt` — Python deps for the harness.
- `analyze_traces.py` — CLI to print stats about a collected trace JSON file.
- `config/framework_cache.json` — Cached per-instance test-framework detection results.

### `swebench-trace-collection/scripts/`
- `collect_swebench_traces.py` — Main CLI: collects traces across SWE-bench instances.
- `run_swebench_with_traces.py` — Wraps SWE-bench's harness to run with trace collection.
- `run_debugger_patch_comparison.py` — Per-instance baseline vs LLM-patch (with/without trace) comparison.
- `run_swebench_lite_evaluation.py` — Dataset-scale runner for the patch-comparison eval.
- `calculate_swebench_lite_metrics.py` — Computes benchmark metrics from index records.
- `generate_report.py` — Aggregates trace coverage stats into a report.
- `validate_traces.py` — Validates collected trace files for completeness.

### `swebench-trace-collection/swebench_integration/`
- `wrapper.py` — Orchestrates SWE-bench `run_instance` with trace collection added.
- `instance_processor.py` — Processes a single SWE-bench instance.
- `framework_detector.py` — Detects pytest/unittest/Django framework per repo.
- `eval_script_injector.py` — Injects trace-collection setup into SWE-bench eval scripts.
- `container_hooks.py` — Creates Docker containers with trace volumes/env vars.
- `testspec_hooks.py` — Hooks into SWE-bench `TestSpec` to enable tracing.
- `volume_manager.py` — Manages host dirs and Docker volume mounts for trace output.
- `trace_aggregator.py` — Aggregates per-instance `auto_debug.json` into JSONL dataset.
- `benchmark_index.py` — Helpers for dataset-level benchmark run index records.

### `swebench-trace-collection/trace_collectors/`
- `pytest_tracer.py` — pytest conftest hook capturing failure stack frames + locals.
- `unittest_tracer.py` — Patches `unittest.TestResult` to capture live tracebacks/locals.
- `django_tracer_new.py` — Django/unittest tracer variant.
- `sitecustomize.py` — Auto-activates the right tracer on Python startup via PYTHONPATH.
- `injection_helpers.py` — Helpers to copy conftest/tracers into target test dirs.

### `swebench-trace-collection/tests/`
- `test_framework_detection.py` — Unit tests for `FrameworkDetector`.
- `test_swebench_integration.py` — Integration tests for the SWE-bench layer.
- `test_unittest_tracer.py` — Unit tests for the unittest tracer.
- `test_unittest_runner.py` — Demonstration runner for `DebugTestResult`.
- `sample_failing_tests.py` — Sample failing tests fixture.

### Other `swebench-trace-collection/` subdirs
- `test_data/` — Vendored sample repos (e.g., `jsonschema`) used in tests.
- `traces/`, `traces_test/`, `traces_test_run/` — Output dirs of collected traces (per-instance JSON).
- `debugger_patch_comparison/` — Artifacts from baseline vs with/without-runtime LLM patch runs.

## `benchmarks/`
- `run_automated_testing.py` — WIP automated benchmarking harness across projects.

## `benchmark_runs/` — Recorded benchmark run outputs.

## `example/` — Example/target Python projects used for local experiments
- `flask/`, `pytest/`, `jsonschema/` — Cloned reference projects to debug against.
- `templates/conftest.py` — Example conftest with the tracer hook.

## `scripts/`
- `start-server.sh` — Bootstraps venv and starts the backend server against an example project.
- `publish.sh` — Builds and publishes the backend Python package.
- `clean.sh` — Removes Python build artifacts and caches.

## `openspec/` — OpenSpec change proposals and specs (project planning)
- `config.yaml` — OpenSpec project config.
- `changes/` — Active proposals (e.g., `extract-llm-connector`, `benchmark-swebench-lite-evaluation`, `datasets-and-metrics-documentation`, `fill-thesis-runtime-info-section`) plus `archive/`.
- `specs/` — Capability specs (currently empty).

## `thesis/` — LaTeX thesis sources, figures, Docker build, CI workflows.

## `references/` — Bibliography/reference materials for the thesis.

## `infra/` is reused by both `backend/` and trace-collection tooling for LLM calls.
