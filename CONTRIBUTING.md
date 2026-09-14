# Contributing

Use Python 3.11 with Tkinter. Create a virtual environment and install `requirements-build.txt` before changing code.

```text
python -m unittest discover -s tests -v
python -m ruff check fleet_configurator main.py build.py scripts tests
python build.py
```

Keep changes scoped. Configuration tests must use temporary directories; do not point them at a real Codex home. Preserve unknown TOML fields, comments, the primary model selection, and instructions outside this tool's managed block. Never submit configuration backups, authentication files, model caches, screenshots with personal data, or tokens.

Explain the user-visible change and relevant validation in your pull request. Platform changes should pass the Windows and both macOS CI jobs. Versioned releases are created by maintainers using the workflow described in `docs/BUILDING.md`.
