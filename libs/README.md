Source code in this folder contains reusable libraries of the project.
Code here can be imported from `research/`, but must never import anything from there.

#### Description of content

- `frames/` :
fundamental types for the runtime data.
Contains the `Frame` type, filtering pipelines (`pipeline.py`, `filters.py`), trace selection (`selection.py`) and serializers which render frames to the text for LLM (`serializer.py`).

- `harness/` :
everything about running one benchmark instance in Docker.
`traced_runner.py` contains `TracedInstanceRunner` which manages the container, mounts the tracers and collects the trace.
`instance_comparison.py` contains `InstanceComparison` which drives the whole evaluation of one instance (baseline collection, tool session, grading).
Also contains framework detection (`framework_detector.py`) and localization metrics (`localization_metrics.py`).

- `llm/` :
LLM integration.
`connector.py` contains `LLMConnector` which hides the concrete provider behind the OpenAI-compatible API (providers are configured in `llm_providers.yaml`).
`tooling.py` contains the tool catalog: all the tools the model can call during the tool session.
`patch_apply.py` and `patch_utils.py` contain the patch applying utilities.

- `prompts/` :
prompt utilities.
`PromptBuilder` assembles a prompt from named XML-like sections and `load_prompt` loads prompt templates from `data/prompts/`.

- `tracing/` :
debugging hooks (tracers) which are mounted into the container and injected into the testing framework to collect runtime frames.
One tracer per supported framework (`django_tracer.py`, `pytest_tracer.py`, `unittest_tracer.py`, `sympy_tracer.py`).
`sitecustomize.py` is the injection entry point inside the container.

- `env.py` :
loads `.env` and provides `require_env` for reading mandatory environment variables.

- `log.py` :
provides `create_logger`, a common logger factory used by all entry points.
