# Pytest Smart Debugger

**Pytest Smart Debugger** is a Visual Studio Code extension that helps you analyze and fix failing pytest tests.
It integrates with a backend service to generate patch suggestions for failing tests, then applies them directly in your workspace.

---

## Features

- Run all tests directly from the command palette
- Try to debug failed tests → automatically query the backend for patch suggestions
- Apply suggested patches with one click
- Integrated backend server (Flask-based) that can be auto-started or run manually
- Unified diff preview and structured patch application
- Configurable Python, pytest, and server settings

---

## Commands

The extension contributes the following commands (⇧⌘P or Ctrl+Shift+P):

- `Pytest: Run All Tests` → run all tests in the current workspace
- `Pytest: Try to Debug Failed Test` → analyze the last failing test and request patch suggestions
- `Pytest: Apply Suggested Patch` → apply patches returned from the backend
- `Pytest: Start Backend Server` → manually start the local server if auto-start is disabled

---

## Configuration

Settings are available under **`pytestSmartDebugger.*`**:

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `pytestSmartDebugger.pythonPath` | string | `python` | Path to Python executable |
| `pytestSmartDebugger.pytestPath` | string | `pytest` | Path to pytest executable |
| `pytestSmartDebugger.pytestArgs` | array | `["-q", "-s"]` | Extra arguments to pass to pytest |
| `pytestSmartDebugger.serverCommand` | string | `${workspaceFolder}/python/server.py` | Command to start the backend server |
| `pytestSmartDebugger.serverPort` | number | `5123` | Port used by the local backend server |
| `pytestSmartDebugger.autoStartServer` | boolean | `true` | Whether to auto-start the server when needed |
| `pytestSmartDebugger.useGitApply` | boolean | `true` | Use `git apply` for unified diffs |

---

## Backend Server

This extension depends on the **Pytest Smart Debugger Backend**, a small Flask HTTP service that:

- Generates prompts from `auto_debug.json` logs
- Queries an LLM for patch suggestions
- Returns both structured patches and unified diffs

👉 See the [backend README](../backend/README.md) for installation and usage.

---

## Typical Workflow

1. Run all tests (`Pytest: Run All Tests`)
2. If a test fails, run `Pytest: Try to Debug Failed Test`
3. Review suggested patch
4. Apply it with `Pytest: Apply Suggested Patch`
5. Re-run tests

---

## Requirements

- Python 3.10+  
- pytest installed in your environment  
- Backend package installed (`pip install -e backend/`)  

---

## Development

- Build: `npm run compile`  
- Watch mode: `npm run watch`  
- Package: `npm run package`  
- Publish: `npm run publish`  
