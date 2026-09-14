"""Launch the packaged GUI against disposable files; never touch real Codex data."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def smoke(application: Path):
    application = application.resolve(strict=True)
    bundle = application.suffix == '.app' and sys.platform == 'darwin'
    command = ['/usr/bin/open', '-W', '-n', str(application), '--args'] if bundle else [str(application)]
    with tempfile.TemporaryDirectory(prefix='fleet-package-') as folder:
        root = Path(folder)
        for name, content, enabled in (
            ('new', None, True),
            ('on', '[agents]\nenabled = true\nmax_concurrent_threads_per_session = 16\n', True),
            ('off', '[agents]\nenabled = false\n[features]\nmulti_agent = false\nmulti_agent_v2 = false\n', False),
            ('invalid', 'model = [broken', None),
        ):
            config_dir = root / name / 'config'
            rules = root / name / 'AGENTS.md'
            if content is not None:
                config_dir.mkdir(parents=True)
                (config_dir / 'config.toml').write_text(content, encoding='utf-8')
            before = {str(p.relative_to(root)): p.read_bytes() for p in (root / name).rglob('*') if p.is_file()}
            report = root / f'{name}-startup.json'
            env = dict(os.environ, CODEX_HOME=str(config_dir))
            proc = subprocess.run([*command, '--config-dir', str(config_dir), '--instructions', str(rules),
                                   '--smoke-test', str(report)], cwd=root, env=env,
                                  capture_output=True, text=True, timeout=60)
            if not report.exists():
                raise RuntimeError(f'{name}: no GUI startup report; exit={proc.returncode}; stderr={proc.stderr[-2000:]}')
            data = json.loads(report.read_text(encoding='utf-8'))
            if enabled is None:
                assert data['started'] and not data['configuration_loaded'], data
                assert proc.returncode == (0 if bundle else 1), (name, proc.returncode)
            else:
                assert proc.returncode == 0 and data['configuration_loaded'], (name, proc.returncode, data)
                assert data['rows'] == 3 and data['fleet_enabled'] is enabled, data
                assert data['concurrency_input'] == ('16' if name == 'on' else '8'), data
            after = {str(p.relative_to(root)): p.read_bytes() for p in (root / name).rglob('*') if p.is_file()}
            assert after == before, f'{name}: startup changed configuration files'
            print(f'Packaged GUI smoke: {name} PASS', flush=True)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python scripts/smoke_package.py <application.exe|application.app>')
    smoke(Path(sys.argv[1]))
