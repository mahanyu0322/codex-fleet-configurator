# v1.0.0 release verification

Verified on 2026-09-15 (Asia/Shanghai).

- Public repository: https://github.com/mahanyu0322/codex-fleet-configurator
- License: MIT; GitHub private vulnerability reporting enabled.
- Release: https://github.com/mahanyu0322/codex-fleet-configurator/releases/tag/v1.0.0
- Tested and tagged source: `a011ed82834f027480db08d4aed04e1b1ba60f15`.
- Successful native CI: https://github.com/mahanyu0322/codex-fleet-configurator/actions/runs/34881610405

## Implementation and review

System fonts and adaptive window height replace Windows-only UI assumptions. macOS backups use owner-only directory and file permissions. A pending Tk preview callback is cancelled when its widget is destroyed. Native builds produce a Windows EXE and separate Apple Silicon / Intel Mac applications, preserving macOS application symlinks and executable permissions.

The primary model remains controlled by the Codex UI. Existing fleet switching, editable child concurrency, child role settings, preview, backup, restore and unknown configuration preservation remain covered by regression tests.

Python and general code reviews approved the final source. The public source scan found no credentials or private configuration in the initial tracked files. Private development history, screenshots, build output and real Codex configuration are excluded from Git. License review identified missing runtime notices; these were added before binary publication, including the exact Windows Python distribution license, incorporated Python notices and OpenSSL 3 terms. Packaging checks every included license file byte-for-byte.

## Native verification

| Platform | Runner | Tests | Packaged startup |
| --- | --- | --- | --- |
| Windows x64 | windows-2022 | 56 passed, 1 POSIX-only check skipped | 4/4 passed |
| macOS arm64 | macos-14 | 57 passed | 4/4 passed |
| macOS x64 | macos-15-intel | 57 passed | 4/4 passed |

All three jobs passed Ruff, PyInstaller builds and archive license checks. Startup probes cover fresh configuration, enabled mode, disabled mode and invalid TOML; they use disposable paths and verify that startup does not write configuration. Mac probes launch the `.app` through Launch Services; both applications passed `codesign --verify --deep --strict`. The final Windows CI executable also passed all four probes on the local Windows workstation.

The first release publishes artifacts from the successful manual CI run at the exact tagged commit. Tag creation triggered a redundant workflow, which was cancelled to avoid republishing existing assets. Future new version tags use the automatic release job after all three platform builds succeed.

## Public download verification

All four release assets were downloaded again through unauthenticated public URLs. The aggregate checksum file and all three ZIPs matched the pre-upload files byte-for-byte. ZIP contents were checked for version `1.0.0`, license files and architecture (Windows PE x64, Mach-O arm64 / x64); Mac symlinks were retained. No real configuration or authentication files were packaged.

| Asset | Bytes | SHA-256 |
| --- | ---: | --- |
| Codex-Fleet-Configurator-windows-x64.zip | 11199493 | `ece16e4e0fe6b44a57380ba586a39cce669aadcc81eed8c0f2cb479998af8d60` |
| Codex-Fleet-Configurator-macos-arm64.zip | 10769510 | `b21fa545485c42a4eeb5bc1529ec357f4db512b8da87bb0c168f1f5a0306950d` |
| Codex-Fleet-Configurator-macos-x64.zip | 11597197 | `e33c5078391a7a9fab12050127991f6d575c78fe1244618948647d38fc4c7b38` |

## Limits

The initial Windows binary has no Authenticode signature. Mac apps use ad-hoc signatures without Apple Developer ID or notarization; fresh downloads may require explicit user approval in system security settings. CI startup checks do not prove Gatekeeper acceptance on every personal Mac. Supported package targets are Windows 10/11 x64, macOS 14+ Apple Silicon and macOS 15+ Intel; older systems, Windows ARM and Linux packages are not verified. This release does not test account model access, quota or configuration reload in an already-running Codex task.
