# Repository guidance

- Keep the utility local-only. Never read or publish real authentication files or configuration backups.
- Preserve primary-model selection in the Codex UI, unknown TOML fields, comments, and instructions outside the managed block.
- Use temporary directories for every configuration test. Both enabled and disabled fleet states must round-trip.
- Run `python -m unittest discover -s tests -v` and `python -m ruff check fleet_configurator main.py build.py scripts tests`.
- Build native packages with `python build.py`; macOS packages must be built on macOS.
- Keep Windows and both macOS CI jobs passing. Update documentation for behavior or packaging changes.
- Do not commit build output, user configuration, backups, private screenshots or local session history.
