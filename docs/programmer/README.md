### Overview

This is a programmer's documentation of this project.
It describes project layout, briefly main files, and example of a pipeline with a mention of involved types.

More detailed explanation of each file can be found in granular `README.md` files placed in most folders.

More detailed explanations each of types, as well as UML diagram of the project, can be found in the generated Doxygen-generated HTML documentation.


### Project layout

The repository is split into three domains and they must not be mixed:

```
libs/      :  reusable libraries
research/  :  experiments (must never be imported from apps/ or libs/)
```

Main folders and files:

- `libs/frames/` : fundamental types for the runtime data. Contains `Frame` type, filtering pipelines and serializers which render frames to the text for LLM.
- `libs/harness/` : everything about running one benchmark instance in Docker. Contains `TracedInstanceRunner`, `InstanceComparison`, framework detection and localization metrics.
- `libs/llm/` : LLM integration. Contains `LLMConnector` (providers are configured in `llm_providers.yaml`), the tool catalog in `tooling.py` and patch applying utilities.
- `libs/tracing/` : debugging hooks (tracers) which are mounted into the container and injected into the testing framework (django, pytest, unittest) to collect runtime frames.
- `data/prompts/` : prompt templates.
- `research/swebench/` : SWE-bench Lite evaluation. `evaluation/` contains the entry point `run_swebench_lite_evaluation.py` and metrics scripts, `sft/` contains the fine-tuning pipeline (it has own `README.md`), `harness/` contains the run index.
- `scripts/` : small helper scripts for development and for reporting results.


### Benchmark workflow

Here we describe what happens in the system when one benchmark instance is evaluated.
The entry point is `research/swebench/evaluation/run_swebench_lite_evaluation.py`: it loads the SWE-bench Lite dataset, builds a `TestSpec` for every instance and submits instances to a thread pool.
For each instance it creates one `InstanceComparison` object which drives the whole evaluation and produces a `ComparisonReport`.

The evaluation of one instance goes in the following steps:

1. Baseline collection:
`InstanceComparison` first runs the failing tests without any fix.
It uses `TracedInstanceRunner`, which spins up the Docker image of the instance, mounts the tracers from `libs/tracing/` into `/opt/tracers`, detects the used testing framework with `FrameworkDetector` and injects the corresponding debugging hook.
After test run finishes, the collected trace is written to the output volume as `auto_debug.json` and returned inside a `RunResult`.

2. Frames preparation:
The raw trace is parsed into `Frame` objects and cleaned by filtering pipelines.

3. Tool session:
For each variant (`without_runtime`, `with_runtime`) the comparison builds a `ToolSessionContext` and asks `LLMConnector` to run an interactive session.
The session loop sends chat completions, executes every returned tool call through the `ToolCatalog` and appends results to the message history, until the model calls `apply_patch` or the turn limit is reached.
The result comes back as a `ToolSessionResult` which carries the patch, the full transcript and token usage.

4. Grading:
The generated patch is applied inside the container and the tests are re-run.
The instance is resolved when all `FAIL_TO_PASS` tests pass and `PASS_TO_PASS` tests still pass.
The verdict, statuses and localization metrics are collected into `VariantResult` objects and the final `ComparisonReport` is written to the run output directory together with all artifacts (prompts, responses, patches, traces).

#### Important types

##### `Frame`

The `Frame` class is the basic unit of runtime information.
It is a frozen dataclass which stores the file, the line, the function name, a mapping with local variables and additional metadata.
All collections in the system (`frames`, `exec_path`, `step_frames`) are just sequences of `Frame` objects.

##### `FramesFilteringPipeline`

The `FramesFilteringPipeline` class cleans raw frames before they are shown to the model.
It runs an ordered list of filters over a sequence of `Frame` objects and returns a new filtered list.
Factory functions `default_traceback_pipeline`, `default_exec_path_pipeline` and `default_step_frames_pipeline` build the standard pipelines for the three frame groups.

##### `ToolCatalog` and `BaseTool`

Every tool implements the abstract `BaseTool` class.
A tool declares its `ToolSpec` (name, description, JSON schema of arguments) and an `execute` method which receives a `ToolSessionContext` and returns a `ToolResult`.
The `ToolSessionContext` bundles two contexts: `ProjectToolContext` and `RuntimeToolContext`.
The `ToolCatalog` class holds the set of registered tools, exports their schemas in the OpenAI format via `openai_tools` and dispatches a `ToolInvocation` to the right tool. 

##### TracedInstanceRunner class

The `TracedInstanceRunner` class manages one Docker container of a benchmark instance.
It builds the instance image, mounts the tracer volume, the trace output volume and the project mirror, optionally applies a patch, runs the tests with a timeout and collects the trace.
The result is returned as a `RunResult` dataclass with the success flag, the parsed traces and the path to the test output.

##### LLMConnector class

The `LLMConnector` class hides the concrete LLM provider behind the OpenAI-compatible API.
The provider and the model are validated against `llm_providers.yaml`.
Its main method for the benchmark is the tool session (internally the `_ToolSessionRunner` class), which performs the turn loop described above; on the last turn it forces the `apply_patch` call with the `tool_choice` parameter.
Transient API errors (429 and similar) are retried with a backoff in `create_chat_completion`.


### Doxygen guide
Doxygen documentation should be generated by the `nix develop` command from the root of the project.
Then, the documentation itself is placed in `output/doxygen/`.
You can start exploring it from `output/doxygen/html/index.html`.


### How to extend the project?

The most common extension is a new LLM tool: subclass `BaseTool` in `libs/llm/tooling.py`, define its `ToolSpec` and `execute` method, and register it in the catalog factory.
To support a new testing framework, add a tracer to `libs/tracing/` and teach `FrameworkDetector` to recognize it.
New experiments should live in `research/` and only import from `libs/`, never the other way around.
