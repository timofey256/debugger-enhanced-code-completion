# User documentation 

The system gives an LLM access to runtime debugging information (execution traces, stack frames, local variable values) collected from a failing test, and measures whether this information improves automatic bug fixing on the repository level.
The evaluation is performed on [SWE-bench Lite](https://www.swebench.com/): for each instance the model runs twice, once with only static code-inspection tools (`without_runtime`) and once with the additional runtime tools (`with_runtime`), and the resulting patches are graded by the official SWE-bench tests.

This README is a user documentation on how to use the presented system.

## Repository layout

Most folders contain their own `README.md` with the description of their content.
The detailed explanation of the architecture and the benchmark workflow is in [`docs/programmer/README.md`](./docs/programmer/README.md).

## Building the project

For reprodicibility we use [Nix flakes](https://nixos.wiki/wiki/Flakes), therefore the only dependency is Nix.
The flake pins everything including the exact SWE-bench commit, so the environment is fully reproducible.
You also need a running Docker daemon (benchmark instances execute inside SWE-bench Docker images).

To enter the development environment, run:
```bash
nix develop
```

If you want to run benchmarks, you must supply your API keys inside `.env`.
The structure is defined in `.env.example`.
The catalog of supported models is in `libs/llm/llm_providers.yaml`.

## Available tools

- `nix develop` : setups the development environment.
- `nix run .#benchmark` : runs the reference experiment (see below). Extra arguments are passed through and override the defaults.
- `nix build .#docs` : builds the Doxygen HTML documentation (UML class diagrams included) into `result/html/index.html`.

## Running experiments 

As mentioned above, the running `nix run .#benchmark` runs an example reference benchmark.
See `flake.nix` for used parameters.
You can override them:

```bash
# different model and run id
nix run .#benchmark -- --model deepseek-v4-flash --run_id my_run

# only django instances, sequentially
nix run .#benchmark -- --filter_for django --max_workers 1
```

Results are written to `output/benchmark-runs/<run_id>/`: per-instance artifacts (prompts, responses, patches, traces, `comparison_report.json`) and the run index.

Alternatively, run the evaluation script directly from the dev shell:

```bash
python -m research.swebench.evaluation.run_swebench_lite_evaluation \
    --provider deepseek --model deepseek-chat \
    --context_lines 30 --max_workers 6 --run_id my_run --verbose
```

### Parameters of the evaluation script

- `--dataset`, `--split` : the HuggingFace dataset and split (default `princeton-nlp/SWE-bench_Lite`, `test`).
- `--predictions_path` : reference predictions; default `gold` uses the reference patches from the dataset.
- `--provider`, `--model` : LLM provider and model from `libs/llm/llm_providers.yaml`.
- `--runtime_tools` : ablation subset of runtime tools for the `with_runtime` variant (`exec_path`, `frames`, `step_frames`, or `all` / `none`).
- `--max_tokens`, `--context_lines`, `--test_context_lines`, `--max_context_files` : prompt and context size knobs.
- `--run_id`, `--output_dir` : where the run artifacts are written.
- `--max_workers` : number of instances evaluated concurrently.
- `--timeout`, `--force_rebuild`, `--nocache`, `--build_only` : Docker execution knobs.
- `--filter_for`, `--exclude_repos` : select or exclude instances by repository/instance id prefix.
- `--verbose` : debug logging.

The full list of required and optional parameters is always available via:

```bash
python -m research.swebench.evaluation.run_swebench_lite_evaluation --help
```

## Measuring the results

Finished runs are measured with the scripts in `scripts/research/`.
All of them take the benchmark run directory (the one containing `artifacts/`) as the argument:

```bash
# main statistics: resolved instances, apply rate, localization hits, token usage
python scripts/research/report_metrics.py output/benchmark-runs/<run_id>

# precision/recall/F1 of bug localization on file, function and line level
python scripts/research/report_localization.py output/benchmark-runs/<run_id>

# how many times each tool was called, per variant
python scripts/research/report_tool_usage.py output/benchmark-runs/<run_id> [--json OUT.json]
```

## Fine-tuning

The pipeline which builds the SFT dataset from benchmark trajectories and fine-tunes Qwen2.5-Coder-7B-Instruct is described in `research/swebench/sft/README.md`.
The final training dataset is versioned in `data/datasets/train.jsonl` and the resulting model is published at [tymofii256/qwen2.5-coder-7b-ft-runtime](https://huggingface.co/tymofii256/qwen2.5-coder-7b-ft-runtime).
