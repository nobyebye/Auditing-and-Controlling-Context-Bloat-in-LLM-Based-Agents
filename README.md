# Context Bloat Auditor

A personal Python project by [nobyebye](https://github.com/nobyebye) for inspecting and reducing redundant context in LLM agents.

The tool records the messages an agent sends to a model, tracks where context comes from, measures duplication, and compares context reduction strategies across repeatable runs.

## Features

- Capture context from retrieval, memory and tool-use workflows.
- Measure context size, redundancy and source dominance.
- Evaluate exact-duplicate removal and irrelevant-context filtering against a baseline.
- Run controlled workflows through custom ReAct and LangChain integrations.
- Export JSONL traces, CSV metrics and JSON reports with configuration and dataset hashes.

## Quick start

Requires Python 3.11 or newer; Python 3.11 and 3.12 are listed as supported versions in the package metadata. Run commands from the repository root.

```bash
git clone https://github.com/nobyebye/Auditing-and-Controlling-Context-Bloat-in-LLM-Based-Agents.git
cd Auditing-and-Controlling-Context-Bloat-in-LLM-Based-Agents
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install and run the bundled example:

```bash
python -m pip install -e ".[langchain,dev]"
context-auditor run --config configs/experiments/pilot_custom_react_v1.json
```

The example uses a mock model and a bundled synthetic dataset. It requires no API key. The command prints the output directory under `runs/`.

To compare both framework integrations:

```bash
context-auditor run-suite
```

## Results and configuration

Each run creates a separate directory. Start with `reports/summary.json`, then inspect `metrics/tasks.csv` and `metrics/invocations.csv`. Invocation records are in `traces/invocations.jsonl`; `manifest.json` records the configuration, versions and artifact hashes.

Experiment settings live in [`configs/experiments/`](configs/experiments/). Copy an existing configuration to change retrieval depth, memory, tool-output repetition or mitigation strategy, then pass its path to `context-auditor run --config`.

The default trace mode is `redacted`. Configuration also supports `hash-only` and `full`; use `full` only with data suitable for complete recording.

## Project goals

1. Make agent context observable: identify what enters each model call and its source.
2. Quantify unnecessary context: distinguish duplicate material from useful task information.
3. Evaluate reduction strategies: compare context size and task outcomes under the same configuration.
4. Keep results reproducible: retain traces, configuration hashes and separate run artifacts.

The bundled mock workflows verify measurement and execution behavior. They do not establish quality, latency or cost improvements for production models. Local token counts use a regex-based estimator; they are not provider billing counts.

## Development

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Implementation: [`src/context_auditor/`](src/context_auditor/) · Tests: [`tests/`](tests/) · Design: [architecture](thesis/engineering/architecture.md) · History: [CHANGELOG.md](CHANGELOG.md)
