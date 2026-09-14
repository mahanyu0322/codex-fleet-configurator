from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock

from fleet_configurator import storage
from fleet_configurator.catalog import Catalog


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.target = storage.Target(self.root / '.codex', self.root / 'AGENTS.md')
        self.target.config_dir.mkdir()
        self.original = (b'# keep this comment\r\nmodel = "gpt-5.5"\r\n'
                         b'model_provider = "local_proxy"\r\n'
                         b'approval_policy = "never"\r\n'
                         b'[model_providers.local_proxy]\r\n'
                         b'name = "proxy"\r\nbase_url = "https://example.invalid"\r\n'
                         b'http_headers = { "X-Key" = "SECRET_SHOULD_NEVER_BE_PREVIEWED" }\r\n')
        self.target.config_path.write_bytes(self.original)
        self.target.instructions_path.write_bytes('原来的规则\n不擅自提交。\n'.encode())
        self.settings = storage.Settings(
            (storage.Choice('gpt-5.6-luna', 'xhigh', 'openai'),
             storage.Choice('gpt-5.6-sol', 'max', 'openai'),
             storage.Choice('gpt-5.5', 'high', 'local_proxy')),
            3,
        )

    def plan(self):
        return storage.make_plan(storage.load_snapshot(self.target), self.settings)

    def test_minimal_config_update_and_each_agent_choice(self):
        plan = self.plan()
        data = tomllib.loads(plan.changes['config'].after.decode('utf-8-sig'))
        self.assertEqual(data['model'], 'gpt-5.5')
        self.assertEqual(data['model_provider'], 'local_proxy')
        self.assertNotIn('model_reasoning_effort', data)
        self.assertEqual(data['approval_policy'], 'never')
        self.assertEqual(data['model_providers']['local_proxy']['http_headers']['X-Key'],
                         'SECRET_SHOULD_NEVER_BE_PREVIEWED')
        self.assertIn(b'# keep this comment\r\n', plan.changes['config'].after)
        self.assertEqual(data['agents']['default_subagent_reasoning_effort'], 'xhigh')
        self.assertEqual(data['agents']['max_concurrent_threads_per_session'], 3)
        for key, choice in zip(storage.ROLE_NAMES, self.settings.children):
            role = tomllib.loads(plan.changes[key].after.decode())
            self.assertEqual((role['model'], role['model_reasoning_effort'], role['model_provider']),
                             (choice.model, choice.effort, choice.provider))
        self.assertNotIn('SECRET_SHOULD_NEVER_BE_PREVIEWED', plan.preview())

    def test_apply_restore_exact_original_bytes(self):
        plan = self.plan()
        backup = storage.apply_plan(plan)
        self.assertTrue((backup / 'manifest.json').is_file())
        self.assertEqual(storage.load_settings(storage.load_snapshot(self.target)), self.settings)
        storage.restore_backup(self.target, backup)
        self.assertEqual(self.target.config_path.read_bytes(), self.original)
        self.assertEqual(self.target.instructions_path.read_text(encoding='utf-8'), '原来的规则\n不擅自提交。\n')
        for name in storage.ROLE_NAMES:
            self.assertFalse((self.target.config_dir / 'agents' / f'{name}.toml').exists())

    @unittest.skipIf(os.name == 'nt', 'POSIX file modes do not represent Windows ACLs')
    def test_backup_directory_and_files_are_private(self):
        backup = storage.apply_plan(self.plan())
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        for path in backup.iterdir():
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_reapply_is_idempotent_and_no_backup_for_noop(self):
        storage.apply_plan(self.plan())
        plan = self.plan()
        self.assertFalse(plan.dirty)
        self.assertIsNone(storage.apply_plan(plan))
        rules = self.target.instructions_path.read_text(encoding='utf-8')
        self.assertEqual(rules.count(storage.RULE_START), 1)

    def test_external_edit_before_apply_is_preserved(self):
        plan = self.plan()
        self.target.config_path.write_bytes(self.original + b'\n# external edit\n')
        with self.assertRaisesRegex(storage.ConfigError, '修改'):
            storage.apply_plan(plan)
        self.assertIn(b'external edit', self.target.config_path.read_bytes())
        self.assertFalse((self.target.config_dir / 'agents').exists())

    def test_external_edit_before_restore_is_preserved(self):
        backup = storage.apply_plan(self.plan())
        self.target.instructions_path.write_text('later changes', encoding='utf-8')
        with self.assertRaisesRegex(storage.ConfigError, '修改'):
            storage.restore_backup(self.target, backup)
        self.assertEqual(self.target.instructions_path.read_text(encoding='utf-8'), 'later changes')

    def test_write_failure_rolls_back_prior_files(self):
        real_write = storage.atomic_write
        calls = []
        def failing_write(path, data, **kwargs):
            calls.append(path)
            if len(calls) == 3:
                raise OSError('simulated disk failure')
            return real_write(path, data, **kwargs)
        with mock.patch.object(storage, 'atomic_write', side_effect=failing_write):
            with self.assertRaisesRegex(storage.ConfigError, 'simulated disk failure'):
                storage.apply_plan(self.plan())
        self.assertEqual(self.target.config_path.read_bytes(), self.original)
        self.assertEqual(self.target.instructions_path.read_text(encoding='utf-8'), '原来的规则\n不擅自提交。\n')
        self.assertFalse((self.target.config_dir / 'agents' / 'fleet_code.toml').exists())

    def test_invalid_toml_blocks_plan(self):
        self.target.config_path.write_text('model = [broken', encoding='utf-8')
        with self.assertRaises(storage.ConfigError):
            self.plan()

    def test_external_edit_during_staging_is_preserved(self):
        plan = self.plan()
        real_fsync = storage.os.fsync
        edited = False
        def edit_during_flush(fd):
            nonlocal edited
            real_fsync(fd)
            if not edited:
                edited = True
                self.target.config_path.write_bytes(self.original + b'\n# changed while staging\n')
        with mock.patch.object(storage.os, 'fsync', side_effect=edit_during_flush):
            with self.assertRaisesRegex(storage.ConfigError, '修改'):
                storage.apply_plan(plan)
        self.assertIn(b'changed while staging', self.target.config_path.read_bytes())

    def test_unknown_existing_role_is_not_overwritten(self):
        roles = self.target.config_dir / 'agents'
        roles.mkdir()
        (roles / 'fleet_code.toml').write_text('name = "mine"', encoding='utf-8')
        with self.assertRaisesRegex(storage.ConfigError, '角色'):
            self.plan()

    def test_invalid_rule_markers_are_not_overwritten(self):
        self.target.instructions_path.write_text(storage.RULE_START, encoding='utf-8')
        with self.assertRaisesRegex(storage.ConfigError, '标记'):
            self.plan()

    def test_unsupported_effort_rejected(self):
        bad = storage.Settings(
            (storage.Choice('gpt-5.6-luna', 'ultra', 'openai'),) * 3, 3)
        with self.assertRaisesRegex(storage.ConfigError, 'ultra'):
            storage.make_plan(storage.load_snapshot(self.target), bad)

    def test_cache_capabilities_override_builtin_validation(self):
        catalog = Catalog({'gpt-5.6-luna': ('medium',)}, ('openai',))
        with self.assertRaisesRegex(storage.ConfigError, 'xhigh'):
            storage.make_plan(storage.load_snapshot(self.target), self.settings, catalog=catalog)

    def test_cache_can_enable_new_effort_for_existing_model(self):
        catalog = Catalog({'gpt-5.6-luna': ('ultra',)}, ('openai',))
        updated = storage.Settings(
            (storage.Choice('gpt-5.6-luna', 'ultra', 'openai'),) * 3, 3)
        self.assertTrue(storage.make_plan(storage.load_snapshot(self.target), updated, catalog=catalog).dirty)

    def test_registered_same_name_role_is_not_silently_shadowed(self):
        self.target.config_path.write_bytes(self.original + b'\n[agents.fleet_code]\nconfig_file = "other.toml"\n')
        with self.assertRaisesRegex(storage.ConfigError, '角色'):
            self.plan()

    def test_legacy_concurrency_alias_is_replaced(self):
        self.target.config_path.write_bytes(self.original + b'\r\n[agents]\r\nmax_threads = 8\r\n')
        data = tomllib.loads(self.plan().changes['config'].after.decode())
        self.assertNotIn('max_threads', data['agents'])
        self.assertEqual(data['agents']['max_concurrent_threads_per_session'], 3)

    def test_restore_rejects_corrupted_backup(self):
        backup = storage.apply_plan(self.plan())
        (backup / 'config.before').write_bytes(b'corrupted')
        current = self.target.config_path.read_bytes()
        with self.assertRaisesRegex(storage.ConfigError, '校验'):
            storage.restore_backup(self.target, backup)
        self.assertEqual(self.target.config_path.read_bytes(), current)

    def test_restore_rejects_foreign_backup_directory(self):
        backup = self.root / 'foreign'
        backup.mkdir()
        (backup / 'manifest.json').write_text('{}')
        with self.assertRaises(storage.ConfigError):
            storage.restore_backup(self.target, backup)

    def test_restore_rejects_wrong_target_in_manifest(self):
        backup = storage.apply_plan(self.plan())
        path = backup / 'manifest.json'
        manifest = json.loads(path.read_text(encoding='utf-8'))
        manifest['target']['instructions_path'] = str(self.root / 'unrelated.txt')
        path.write_text(json.dumps(manifest), encoding='utf-8')
        with self.assertRaises(storage.ConfigError):
            storage.restore_backup(self.target, backup)

    def test_new_project_without_config_can_roundtrip(self):
        target = storage.Target(self.root / 'new project' / '.codex', self.root / 'new project' / 'AGENTS.md')
        plan = storage.make_plan(storage.load_snapshot(target), self.settings)
        data = tomllib.loads(plan.changes['config'].after.decode())
        for key in ('model', 'model_reasoning_effort', 'model_provider'):
            self.assertNotIn(key, data)
        backup = storage.apply_plan(plan)
        self.assertTrue(target.config_path.exists())
        storage.restore_backup(target, backup)
        self.assertFalse(target.config_path.exists())
        self.assertFalse(target.instructions_path.exists())

    def test_restore_keeps_main_changes_made_after_save(self):
        backup = storage.apply_plan(self.plan())
        current = self.target.config_path.read_bytes().replace(
            b'model = "gpt-5.5"', b'model = "gpt-6-astra"')
        current = b'model_reasoning_effort = "max"\r\n' + current
        current += b'\r\n[unrelated]\r\nkeep = true\r\n'
        self.target.config_path.write_bytes(current)
        storage.restore_backup(self.target, backup)
        data = tomllib.loads(self.target.config_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(data['model'], 'gpt-6-astra')
        self.assertEqual(data['model_reasoning_effort'], 'max')
        self.assertEqual(data['model_provider'], 'local_proxy')
        self.assertTrue(data['unrelated']['keep'])
        self.assertNotIn('agents', data)

    def test_legacy_backup_restores_children_without_reverting_main(self):
        plan = self.plan()
        change = plan.changes['config']
        legacy_after = change.after.replace(b'model = "gpt-5.5"', b'model = "gpt-6-astra"')
        legacy_after = legacy_after.replace(b'model_provider = "local_proxy"', b'model_provider = "openai"')
        legacy_after = b'model_reasoning_effort = "ultra"\r\n' + legacy_after
        plan.changes['config'] = storage.FileChange(change.path, change.before, legacy_after)
        backup = storage.apply_plan(plan)
        storage.restore_backup(self.target, backup)
        data = tomllib.loads(self.target.config_path.read_text(encoding='utf-8-sig'))
        self.assertEqual(data['model'], 'gpt-6-astra')
        self.assertEqual(data['model_reasoning_effort'], 'ultra')
        self.assertEqual(data['model_provider'], 'openai')
        self.assertNotIn('agents', data)

    def test_restore_rejects_later_child_setting_change(self):
        backup = storage.apply_plan(self.plan())
        current = self.target.config_path.read_bytes().replace(
            b'max_concurrent_threads_per_session = 3', b'max_concurrent_threads_per_session = 2')
        self.target.config_path.write_bytes(current)
        with self.assertRaisesRegex(storage.ConfigError, '修改'):
            storage.restore_backup(self.target, backup)
        self.assertEqual(self.target.config_path.read_bytes(), current)

    def test_restore_rejects_child_setting_type_changes(self):
        backup = storage.apply_plan(self.plan())
        saved = self.target.config_path.read_bytes()
        for before, after in (
            (b'max_concurrent_threads_per_session = 3', b'max_concurrent_threads_per_session = 3.0'),
            (b'enabled = true', b'enabled = 1'),
        ):
            with self.subTest(change=after):
                current = saved.replace(before, after)
                self.target.config_path.write_bytes(current)
                with self.assertRaisesRegex(storage.ConfigError, '修改'):
                    storage.restore_backup(self.target, backup)
                self.assertEqual(self.target.config_path.read_bytes(), current)

    def test_custom_concurrency_above_three_roundtrips(self):
        for count in (4, 8, 16):
            with self.subTest(count=count):
                self.target.config_path.write_bytes(self.original + f'\r\n[agents]\r\nmax_concurrent_threads_per_session = {count}\r\n'.encode())
                snapshot = storage.load_snapshot(self.target)
                loaded = storage.load_settings(snapshot)
                self.assertEqual(loaded.max_concurrent, count)
                plan = storage.make_plan(snapshot, loaded)
                storage.apply_plan(plan)
                self.assertEqual(storage.load_settings(storage.load_snapshot(self.target)).max_concurrent, count)
                self.assertIn(f'并发上限为 {count} 个', self.target.instructions_path.read_text(encoding='utf-8'))

    def test_default_concurrency_is_eight(self):
        self.assertEqual(storage.Settings(self.settings.children).max_concurrent, 8)
        self.assertEqual(storage.load_settings(storage.load_snapshot(self.target)).max_concurrent, 8)

    def test_mode_off_on_roundtrip_keeps_preferences_and_main(self):
        storage.apply_plan(self.plan())
        original_roles = {name: self.target.paths()[name].read_bytes() for name in storage.ROLE_NAMES}
        before = storage.load_snapshot(self.target)
        off = replace(self.settings, enabled=False)
        plan = storage.make_plan(before, off)
        self.assertIn('非舰队模式', plan.preview())
        self.assertNotIn('按需使用以下三个', plan.preview())
        backup = storage.apply_plan(plan)
        saved = storage.load_snapshot(self.target)
        self.assertFalse(saved.config['agents']['enabled'])
        self.assertFalse(saved.config['features']['multi_agent'])
        self.assertEqual(storage.load_settings(saved), off)
        expected = tomllib.loads(before.originals['config'].decode())
        expected['agents']['enabled'] = False
        expected['features']['multi_agent'] = False
        expected['features']['multi_agent_v2'] = False
        self.assertEqual(saved.config, expected)
        for name, raw in original_roles.items():
            self.assertEqual(saved.originals[name], raw)
        self.assertIn('不创建或委派子 Agent', saved.originals['instructions'].decode())
        self.assertIn('原来的规则', saved.originals['instructions'].decode())
        self.assertFalse(storage.make_plan(saved, off).dirty)
        storage.restore_backup(self.target, backup)
        self.assertEqual(storage.load_snapshot(self.target).originals, before.originals)
        storage.apply_plan(storage.make_plan(storage.load_snapshot(self.target), off))
        storage.apply_plan(storage.make_plan(storage.load_snapshot(self.target), self.settings))
        reenabled = storage.load_snapshot(self.target)
        self.assertEqual(storage.load_settings(reenabled), self.settings)
        self.assertEqual(reenabled.originals['instructions'], before.originals['instructions'])
        self.assertFalse(reenabled.config['features']['multi_agent_v2'])

    def test_load_mode_from_explicit_and_legacy_switches(self):
        for text, enabled in (
            ('', True),
            ('[agents]\nenabled = false\n', False),
            ('[agents]\nenabled = true\n', True),
            ('[features]\nmulti_agent = false\n', False),
            ('[features]\nmulti_agent = true\n', True),
            ('[agents]\nenabled = true\n[features]\nmulti_agent = false\n', True),
            ('[agents]\nenabled = false\n[features]\nmulti_agent = true\n', False),
        ):
            with self.subTest(text=text):
                self.target.config_path.write_bytes(self.original + text.encode())
                self.assertEqual(storage.load_settings(storage.load_snapshot(self.target)).enabled, enabled)

    def test_mixed_flags_are_normalized_to_selected_mode_with_preview(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled):
                self.target.config_path.write_bytes(self.original + (
                    f'\n[agents]\nenabled = {str(enabled).lower()}\n'
                    f'[features]\nmulti_agent = {str(not enabled).lower()}\n').encode())
                snapshot = storage.load_snapshot(self.target)
                settings = storage.load_settings(snapshot)
                plan = storage.make_plan(snapshot, settings)
                self.assertIn(f'agents.enabled={str(enabled).lower()}', plan.preview())
                self.assertIn(f'features.multi_agent={str(enabled).lower()}', plan.preview())
                storage.apply_plan(plan)
                saved = storage.load_snapshot(self.target).config
                self.assertIs(saved['agents']['enabled'], enabled)
                self.assertIs(saved['features']['multi_agent'], enabled)

    def test_mode_requires_boolean(self):
        for value in ('false', 0, None):
            with self.subTest(value=value):
                with self.assertRaises(storage.ConfigError):
                    storage.make_plan(storage.load_snapshot(self.target), replace(self.settings, enabled=value))

    def test_disable_v2_and_restore_previous_engine(self):
        self.target.config_path.write_bytes(self.original + b'\n[agents]\nenabled = false\n[features]\nmulti_agent = false\nmulti_agent_v2 = true\n')
        before = storage.load_snapshot(self.target)
        self.assertTrue(storage.load_settings(before).enabled)
        backup = storage.apply_plan(storage.make_plan(before, replace(self.settings, enabled=False)))
        saved = storage.load_snapshot(self.target)
        self.assertFalse(saved.config['features']['multi_agent_v2'])
        self.assertFalse(storage.load_settings(saved).enabled)
        storage.restore_backup(self.target, backup)
        self.assertEqual(storage.load_snapshot(self.target).originals, before.originals)

    def test_legacy_backup_does_not_restore_unmanaged_v2_flag(self):
        self.target.config_path.write_bytes(self.original + b'\n[features]\nmulti_agent_v2 = false\n')
        backup = storage.apply_plan(self.plan())
        current = self.target.config_path.read_bytes().replace(b'multi_agent_v2 = false', b'multi_agent_v2 = true')
        self.target.config_path.write_bytes(current)
        storage.restore_backup(self.target, backup)
        self.assertTrue(storage.load_snapshot(self.target).config['features']['multi_agent_v2'])

    def test_invalid_concurrency_rejected(self):
        for count in (0, -1, True, 3.0, '8', 2**63):
            with self.subTest(count=count):
                with self.assertRaises(storage.ConfigError):
                    storage.make_plan(storage.load_snapshot(self.target), storage.Settings(self.settings.children, count))


if __name__ == '__main__':
    unittest.main()
