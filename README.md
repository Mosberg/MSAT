# Mosberg Server Automation Toolkit

Lightweight Python-based server automation and orchestration toolkit.

## Quickstart

- Create a virtual environment and install dependencies:

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.\\.venv\\Scripts\\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

- Show CLI help:

```bash
mosberg --help
```

- Run a command against your inventory:

```bash
mosberg run "uname -a" -i examples/inventory.yml
```

## Project layout

- `src/mosberg/` — core package and CLI
- `examples/` — inventory, templates, and sample playbooks
- `tests/` — basic unit tests
