Source code in this folder is used to facilitate benchmark runs on SWE-Bench Lite.

#### Description of content

- `evaluation/` :
contains the entry point of the benchmark --- `run_swebench_lite_evaluation.py`.
It loads the dataset, runs `InstanceComparison` for every instance (in a thread pool) and writes all artifacts to the run output directory.
See `docs/programmer/README.md` for the description of the whole workflow.

- `harness/` :
helper code for the benchmark runs.
`helpers.py` maintains the run index (`index/instance_status_index.json`): it creates the index at the start of the run, appends a record for each finished instance and finalizes the index at the end.
This index is later consumed by the reporting scripts and by the SFT pipeline.

- `sft/` :
the fine-tuning pipeline (data collection, tokenization, training, serving).
It has own `README.md` with the description of each script.
