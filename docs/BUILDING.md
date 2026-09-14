# Build and release

## Development

Use Python 3.11 with working Tkinter. `python -m tkinter` should open a demonstration window. The release environment uses `actions/setup-python` on each native OS.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe build.py
```

macOS Terminal:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python build.py
```

Use a Python installation that includes Tcl/Tk (for example the python.org macOS installer). The macOS system Python is not the project's build environment. Finder normally does not inherit `CODEX_HOME` exported only in a shell; use the default `~/.codex`, choose a project in the UI, or launch the executable from a configured shell when using a custom Codex home.

## Native packages

`build.py` detects the current OS and CPU. Windows produces a one-file GUI EXE; macOS produces an `.app` directory. macOS builds use `ditto` to preserve app symlinks, executable permissions and code signatures in the ZIP. The script starts the packaged application against temporary empty/on/off/invalid configurations before packaging it. macOS probes launch the bundle through Launch Services with `open`.

Output: `dist/release/Codex-Fleet-Configurator-<platform>.zip` and a matching `.zip.sha256` file. Archives include the application, usage instructions, version and licenses.

| Platform | Native CI runner | Support baseline |
| --- | --- | --- |
| Windows x64 | `windows-2022` | Windows 10/11 x64 |
| macOS arm64 | `macos-14` | macOS 14+ on Apple Silicon |
| macOS x64 | `macos-15-intel` | macOS 15+ on Intel |

Packages are built and tested separately; Windows cannot build a working macOS application. Earlier macOS releases, Windows ARM64 and Linux binaries are not release targets.

## Publish a release

1. Update `fleet_configurator.__version__` and `docs/RELEASE_NOTES.md`.
2. Run tests and review the commit, including source/license and secret checks.
3. Tag that commit as `v<version>` and push the tag.
4. The workflow runs tests, lint, native builds and packaged GUI probes on all three platforms. When all succeed, a separate job verifies the three archives and checksums, then creates the GitHub Release. A failed platform prevents release publication.

Manual workflow runs build CI artifacts without publishing a release. Pull requests have read-only permissions. Only the release job has `contents: write`; no signing credentials are required for this initial workflow.

macOS packages use ad-hoc signatures, not Apple Developer ID notarization. Windows packages do not have an Authenticode signature. OS download verification prompts remain expected. Future signed distributions require the maintainer's signing identities and a separate documented workflow change.

References: [PyInstaller usage](https://pyinstaller.org/en/stable/usage.html), [GitHub standard runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
