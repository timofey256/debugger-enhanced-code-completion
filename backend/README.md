# Pytest Smart Debugger Server

This is the **backend server** for the [Pytest Smart Debugger VS Code extension](https://marketplace.visualstudio.com/items?itemName=tymofii-shchetilin.pytest-smart-debugger).  
It runs a small HTTP service that coordinates with the extension to generate patches for failing pytest tests using an LLM.

## Features

- Exposes an HTTP API:
  - `GET /health` : health check
  - `POST /debug` : given a failing test name, generate patch suggestions
- Produces both **structured patches** (JSON) and a **unified diff** string
- Uses project logs (`auto_debug.json`) and the test name to build prompts for the LLM

## Installation

First, create and activate a virtual environment:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
````

Install in editable mode:

```bash
pip install -e .
```

## Usage

Run the server with your project path:

```bash
export DEEPSEEK_API_KEY=...
python -m pytest_smart_debugger_server.server /path/to/your/project
```

By default it listens on port **5000**. You can override with:

```bash
PORT=5123 python -m pytest_smart_debugger_server.server /path/to/your/project
```

## Notes

* This package is **not meant to be used directly** — it is a **supplementary service** for the VS Code extension.
* When the extension is active, it will automatically start and connect to this server.
