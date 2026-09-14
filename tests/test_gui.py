from __future__ import annotations

import json
import tempfile
import tkinter as tk
from tkinter import font as tkfont
import unittest
from pathlib import Path
from unittest.mock import patch

from fleet_configurator.gui import FleetConfiguratorApp
from fleet_configurator.storage import ConfigError, load_settings, load_snapshot
from main import main


class GuiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name).resolve()
        self.config_dir = self.directory / "codex"
        self.instructions = self.directory / "AGENTS.md"
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = FleetConfiguratorApp(
            self.root,
            config_dir=self.config_dir,
            instructions_path=self.instructions,
            show_errors=False,
        )
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()
        self.temporary.cleanup()

    def test_startup_and_preview_do_not_write_configuration(self):
        self.assertEqual(len(self.app.rows), 3)
        self.assertEqual(self.app.current_settings().max_concurrent, 8)
        self.assertFalse(self.config_dir.exists())
        self.assertFalse(self.instructions.exists())
        self.app.preview_changes()
        self.assertFalse(self.config_dir.exists())

    def test_fonts_exist_on_the_current_platform(self):
        self.assertIn(self.app.ui_font, tkfont.families(self.root))
        self.assertIn(self.app.mono_font, tkfont.families(self.root))

    def test_destroy_cancels_pending_preview(self):
        self.app.concurrent_var.set('16')
        timer = self.app._preview_after
        self.assertIn(timer, self.root.tk.call('after', 'info'))
        self.app.destroy()
        self.assertNotIn(timer, self.root.tk.call('after', 'info'))

    def test_window_fits_smaller_screen(self):
        with patch.object(self.root, 'winfo_screenheight', return_value=768):
            self.app._configure_window()
            self.root.deiconify()
            self.root.update()
            self.assertLessEqual(self.root.minsize()[1], 688)
            button_bottom = self.app.save_button.winfo_rooty() + self.app.save_button.winfo_height()
            self.assertLessEqual(button_bottom, self.root.winfo_rooty() + self.root.winfo_height())

    def test_preset_keeps_children_independent(self):
        self.app.apply_preset()
        choices = self.app.current_settings()
        self.assertFalse(hasattr(choices, "main"))
        self.assertTrue(all((child.model, child.effort) == ("gpt-5.6-luna", "xhigh") for child in choices.children))
        self.app.rows[1].model_var.set("my-private-model")
        self.app.rows[1].refresh_efforts()
        self.app.rows[1].set_effort("high")
        choices = self.app.current_settings()
        self.assertEqual(choices.children[1].model, "my-private-model")
        self.assertEqual(choices.children[1].effort, "high")
        self.assertEqual(choices.children[0].model, "gpt-5.6-luna")

    def test_model_changes_filter_effort_and_preserve_valid_choice(self):
        row = self.app.rows[0]
        row.model_var.set("gpt-6-astra")
        row.set_effort("ultra")
        row.model_var.set("gpt-5.6-luna")
        row.refresh_efforts()
        self.assertNotIn("ultra", row.allowed_efforts)
        self.assertIn(row.get_choice().effort, row.allowed_efforts)
        row.set_effort("high")
        row.refresh_catalog(self.app.catalog)
        self.assertEqual(row.get_choice().effort, "high")

    def test_manually_entered_unknown_model_requires_explicit_effort(self):
        row = self.app.rows[0]
        row.model_var.set("gpt-6-astra")
        row.set_effort("ultra")
        row.model_var.set("brand-new-unknown-model")
        row.refresh_catalog(self.app.catalog)
        self.assertEqual(row.effort_var.get(), "")
        with self.assertRaises(ConfigError):
            self.app.current_settings()
        row.set_effort("high")
        self.assertEqual(self.app.current_settings().children[0].effort, "high")

    def test_saved_custom_model_keeps_its_explicit_effort_when_loaded(self):
        self.config_dir.mkdir()
        self.app.global_target.config_path.write_text(
            '[agents]\ndefault_subagent_model = "saved-custom-model"\ndefault_subagent_reasoning_effort = "ultra"\n', encoding="utf-8"
        )
        self.app.load_current()
        self.assertEqual(self.app.current_settings().children[0].model, "saved-custom-model")
        self.assertEqual(self.app.current_settings().children[0].effort, "ultra")

    def test_apply_makes_backup_and_restores_only_after_confirmation(self):
        self.config_dir.mkdir()
        original = b'# existing preference\nmodel = "gpt-5.6-sol"\nmodel_reasoning_effort = "high"\n'
        self.app.global_target.config_path.write_bytes(original)
        self.instructions.write_text("# Existing project instructions\n", encoding="utf-8")
        self.app.load_current()
        self.app.apply_preset()
        self.app.save_changes()
        snapshot = load_snapshot(self.app.global_target)
        saved = load_settings(snapshot)
        self.assertEqual(snapshot.config['model'], 'gpt-5.6-sol')
        self.assertEqual(snapshot.config['model_reasoning_effort'], 'high')
        self.assertTrue(all(child.model == 'gpt-5.6-luna' for child in saved.children))
        self.assertTrue(self.app.backup_paths)
        selected = next(iter(self.app.backup_paths))
        self.app.backup_tree.selection_set(selected)
        with patch("fleet_configurator.gui.messagebox.askyesno", return_value=False):
            self.app.restore_selected()
        self.assertNotEqual(self.app.global_target.config_path.read_bytes(), original)
        with patch("fleet_configurator.gui.messagebox.askyesno", return_value=True) as confirm:
            self.app.restore_selected()
        self.assertIn(str(self.app.global_target.config_path), confirm.call_args.args[1])
        self.assertEqual(self.app.global_target.config_path.read_bytes(), original)

    def test_preview_never_dumps_original_secrets(self):
        self.config_dir.mkdir()
        self.app.global_target.config_path.write_text(
            'model = "gpt-5.6-sol"\nsecret_key = "SENTINEL_DO_NOT_PREVIEW"\n', encoding="utf-8"
        )
        self.app.load_current()
        self.app.apply_preset()
        self.app.preview_changes()
        self.assertNotIn("SENTINEL_DO_NOT_PREVIEW", self.app.preview_text.get("1.0", "end"))

    def test_project_providers_include_global_provider(self):
        self.config_dir.mkdir()
        self.app.global_target.config_path.write_text(
            '[model_providers.private_relay]\nname = "Private"\nbase_url = "https://example.invalid/v1"\n',
            encoding="utf-8",
        )
        project = self.directory / "project"
        project.mkdir()
        self.app.project_var.set(str(project))
        self.app.scope_var.set("project")
        self.app.load_current()
        self.assertIn("private_relay", self.app.catalog.providers)
        self.assertEqual(self.app.snapshot.target.config_dir, project / ".codex")

    def test_backend_errors_stay_in_ui(self):
        with patch("fleet_configurator.gui.make_plan", side_effect=ConfigError("模拟配置错误")):
            self.app.save_changes()
        self.assertIn("模拟配置错误", self.app.status_var.get())
        self.assertFalse(self.config_dir.exists())

    def test_target_change_requires_loading_before_save(self):
        self.app.scope_var.set("project")
        self.app.project_var.set(str(self.directory / "different-project"))
        self.app.save_changes()
        self.assertFalse((self.directory / "different-project").exists())
        self.assertIn("读取当前配置", self.app.status_var.get())

    def test_custom_concurrency_can_be_entered_saved_and_reloaded(self):
        for count in (4, 8, 16):
            with self.subTest(count=count):
                self.app.concurrent_entry.delete(0, 'end')
                self.app.concurrent_entry.insert(0, str(count))
                self.app.save_changes()
                self.assertEqual(self.app.current_settings().max_concurrent, count)
                self.assertEqual(load_settings(load_snapshot(self.app.global_target)).max_concurrent, count)
                self.assertEqual(len(self.app.rows), 3)

    def test_model_preset_does_not_reset_concurrency(self):
        self.app.concurrent_var.set('16')
        self.app.apply_preset()
        self.assertEqual(self.app.current_settings().max_concurrent, 16)

    def test_mode_switch_preview_save_reload_and_reenable(self):
        self.assertTrue(self.app.enabled_var.get())
        self.app.concurrent_var.set('16')
        self.app.rows[1].model_var.set('gpt-5.6-sol')
        self.app.rows[1].set_effort('max')
        self.app.mode_switch.invoke()
        self.app.preview_changes()
        self.assertFalse(self.config_dir.exists())
        self.assertIn('非舰队模式', self.app.preview_text.get('1.0', 'end'))
        self.app.save_changes()
        self.assertFalse(self.app.enabled_var.get())
        saved = load_settings(load_snapshot(self.app.global_target))
        self.assertFalse(saved.enabled)
        self.assertEqual(saved.max_concurrent, 16)
        self.assertEqual(saved.children[1].model, 'gpt-5.6-sol')
        self.assertIn('非舰队模式', self.app.status_var.get())
        self.app.mode_switch.invoke()
        self.app.save_changes()
        self.assertTrue(load_settings(load_snapshot(self.app.global_target)).enabled)
        self.assertEqual(self.app.current_settings().children, saved.children)

    def test_model_preset_does_not_enable_fleet_mode(self):
        self.app.enabled_var.set(False)
        self.app.apply_preset()
        self.assertFalse(self.app.current_settings().enabled)
        self.assertFalse(self.config_dir.exists())

    def test_invalid_concurrency_does_not_write(self):
        for value in ('0', '-1', '3.5', '', 'many', str(2**63)):
            with self.subTest(value=value):
                self.app.concurrent_var.set(value)
                self.app.save_changes()
                self.assertIn('保存失败', self.app.status_var.get())
                self.assertFalse(self.config_dir.exists())


class EntryPointTests(unittest.TestCase):
    def test_smoke_test_reports_startup_without_writing_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config_dir = directory / "configuration"
            instructions = directory / "rules.md"
            report = directory / "startup.json"
            result = main(["--config-dir", str(config_dir), "--instructions", str(instructions), "--smoke-test", str(report)])
            self.assertEqual(result, 0)
            status = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(status["started"])
            self.assertTrue(status["configuration_loaded"])
            self.assertEqual(status["rows"], 3)
            self.assertEqual(status["concurrency_input"], "8")
            self.assertTrue(status["fleet_enabled"])
            self.assertFalse(config_dir.exists())
            self.assertFalse(instructions.exists())

    def test_smoke_test_returns_failure_for_invalid_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            config_dir = directory / "configuration"
            config_dir.mkdir()
            original = b"model = [ broken toml"
            (config_dir / "config.toml").write_bytes(original)
            report = directory / "startup.json"
            result = main(["--config-dir", str(config_dir), "--smoke-test", str(report)])
            self.assertEqual(result, 1)
            status = json.loads(report.read_text(encoding="utf-8"))
            self.assertTrue(status["started"])
            self.assertFalse(status["configuration_loaded"])
            self.assertEqual((config_dir / "config.toml").read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
