# Third-party software

The application source is licensed under MIT. Packaged applications also contain the following software under its own license:

| Component | License text included in this package | Source |
| --- | --- | --- |
| Python 3.11 | `licenses/Python.txt` (PSF license), `licenses/Python-incorporated.rst` (incorporated component notices from Python 3.11.9) | https://github.com/python/cpython |
| Windows Python runtime | `licenses/Python-Windows-runtime.txt` in Windows binaries, copied from the exact build interpreter's complete `LICENSE.txt` (including Microsoft, bzip2 and OpenSSL notices) | https://www.python.org/downloads/windows/ |
| OpenSSL 3 in macOS Python | `licenses/OpenSSL-3.txt` (Apache 2.0) | https://github.com/openssl/openssl/tree/openssl-3.0.13 |
| Tcl/Tk 8.6 | `licenses/Tcl.txt`, `licenses/Tk.txt` | https://github.com/tcltk |
| tomlkit 0.13.2 | `licenses/tomlkit.txt` (MIT) | https://github.com/python-poetry/tomlkit |
| PyInstaller bootloader | `licenses/PyInstaller.txt` (GPL with the distribution exception for generated applications) | https://github.com/pyinstaller/pyinstaller |

Build-time tools are listed in `requirements-build.txt`; they are not part of the application's runtime API. The copied license texts are retained without alteration, and archive creation checks their bytes. Some notices cover optional Python components which this application does not use. Operating-system libraries retain their original licenses.

Codex and OpenAI are trademarks of their respective owners. This is an independent community utility, not an official OpenAI product. It does not include or redistribute Codex.
