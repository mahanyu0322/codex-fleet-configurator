"""Desktop entry point; configuration is never applied automatically."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fleet_configurator import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(description="Codex 舰队配置器")
    parser.add_argument("--version", action="version", version=f"Codex Fleet Configurator {__version__}")
    parser.add_argument("--config-dir", type=Path, help="Override the global Codex configuration directory.")
    parser.add_argument("--instructions", type=Path, help="Override the global AGENTS.md path.")
    parser.add_argument("--smoke-test", type=Path, metavar="OUTPUT_JSON", help="Open and close the UI, writing only a startup report.")
    args = parser.parse_args(argv)
    root = None
    exit_code = 0
    try:
        import tkinter as tk

        from fleet_configurator.gui import FleetConfiguratorApp

        root = tk.Tk()
        app = FleetConfiguratorApp(root, config_dir=args.config_dir, instructions_path=args.instructions, show_errors=args.smoke_test is None)
        root.report_callback_exception = app.report_callback_exception
        if args.smoke_test is not None:
            def finish_smoke_test():
                nonlocal exit_code
                try:
                    root.update_idletasks()
                    report = {
                        "started": True,
                        "rows": len(app.rows),
                        "concurrency_input": app.concurrent_var.get(),
                        "fleet_enabled": app.enabled_var.get(),
                        "window_size": [root.winfo_width(), root.winfo_height()],
                        "configuration_loaded": app.snapshot is not None,
                        "status": app.status_var.get(),
                        "writes_to_configuration": False,
                    }
                    args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
                    args.smoke_test.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                    if app.snapshot is None:
                        exit_code = 1
                except OSError:
                    exit_code = 1
                finally:
                    root.destroy()

            root.after(350, finish_smoke_test)
        root.mainloop()
        return exit_code
    except Exception as exc:
        if args.smoke_test is not None:
            try:
                args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
                args.smoke_test.write_text(json.dumps({"started": False, "error": str(exc)}, ensure_ascii=False, indent=2), encoding="utf-8")
            except OSError:
                pass
        else:
            try:
                from tkinter import messagebox

                messagebox.showerror("启动失败", f"无法启动 Codex 舰队配置器：\n{exc}", parent=root)
            except Exception:
                pass
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
