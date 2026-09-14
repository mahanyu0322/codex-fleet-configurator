"""Build a native, self-contained release archive on Windows or macOS."""

from __future__ import annotations

import hashlib
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import zipfile

from fleet_configurator import __version__

ROOT = Path(__file__).resolve().parent
APP_NAME = 'Codex Fleet Configurator'


def main():
    # Windows service/automation environments may omit PROCESSOR_ARCHITECTURE.
    machine = {'win-amd64': 'x86_64', 'win-arm64': 'arm64'}.get(sysconfig.get_platform(), platform.machine().lower())
    arch = {'amd64': 'x64', 'x86_64': 'x64', 'arm64': 'arm64', 'aarch64': 'arm64'}.get(machine)
    if sys.platform == 'win32' and arch == 'x64':
        target = 'windows-x64'
        options = ['--onefile']
    elif sys.platform == 'darwin' and arch in ('arm64', 'x64'):
        target = f'macos-{arch}'
        options = ['--onedir', '--osx-bundle-identifier', 'io.github.mahanyu0322.codex-fleet-configurator',
                   '--target-architecture', 'x86_64' if arch == 'x64' else 'arm64']
    else:
        raise SystemExit(f'Build on a supported native host: Windows x64 or macOS arm64/x64 (got {sys.platform}/{machine}).')

    native = ROOT / 'dist' / 'native' / target
    work = ROOT / 'build' / target
    release = ROOT / 'dist' / 'release'
    work.mkdir(parents=True, exist_ok=True)
    release.mkdir(parents=True, exist_ok=True)
    license_files = list((ROOT / 'licenses').iterdir())
    extra_data = []
    if sys.platform == 'win32':
        # Python's Windows distribution adds notices for its bundled DLLs.
        source_license = Path(sys.base_prefix) / 'LICENSE.txt'
        content = source_license.read_text(encoding='utf-8')
        if not all(name in content for name in ('Microsoft', 'bzip2', 'OpenSSL')):
            raise SystemExit('Python LICENSE.txt must contain its bundled runtime notices.')
        runtime_license = work / 'Python-Windows-runtime.txt'
        shutil.copy2(source_license, runtime_license)
        license_files.append(runtime_license)
        extra_data = ['--add-data', f'{runtime_license}:licenses']
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--windowed', '--noupx',
               '--name', APP_NAME, '--distpath', str(native), '--workpath', str(work),
               '--specpath', str(work), '--add-data', f'{ROOT / "licenses"}:licenses',
               '--add-data', f'{ROOT / "LICENSE"}:licenses',
               '--add-data', f'{ROOT / "THIRD_PARTY_NOTICES.md"}:.', *extra_data, *options, str(ROOT / 'main.py')]
    subprocess.run(command, cwd=ROOT, check=True)
    application = native / (APP_NAME + ('.exe' if sys.platform == 'win32' else '.app'))
    subprocess.run([sys.executable, str(ROOT / 'scripts' / 'smoke_package.py'), str(application)],
                   cwd=ROOT, check=True)
    if sys.platform == 'darwin':
        subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(application)], check=True)

    archive = release / f'Codex-Fleet-Configurator-{target}.zip'
    with tempfile.TemporaryDirectory(prefix='package-', dir=work) as folder:
        staging = Path(folder) / APP_NAME
        staging.mkdir()
        if application.is_dir():
            shutil.copytree(application, staging / application.name, symlinks=True)
        else:
            shutil.copy2(application, staging / application.name)
        for name in ('README.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
            shutil.copy2(ROOT / name, staging / name)
        shutil.copy2(ROOT / '桌面使用说明.txt', staging / 'START_HERE.txt')
        shutil.copytree(ROOT / 'licenses', staging / 'licenses')
        if sys.platform == 'win32':
            shutil.copy2(runtime_license, staging / 'licenses' / runtime_license.name)
        (staging / 'VERSION.txt').write_text(__version__ + '\n', encoding='utf-8')
        if sys.platform == 'darwin':
            # ditto preserves the .app's symlinks, signatures and executable modes.
            subprocess.run(['/usr/bin/ditto', '-c', '-k', '--sequesterRsrc', '--keepParent',
                            str(staging), str(archive)], check=True)
        else:
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as output:
                for path in sorted(staging.rglob('*')):
                    if path.is_file():
                        output.write(path, path.relative_to(staging.parent))
    with zipfile.ZipFile(archive) as output:
        for license_file in license_files:
            name = f'{APP_NAME}/licenses/{license_file.name}'
            if output.read(name) != license_file.read_bytes():
                raise RuntimeError(f'Missing or altered packaged license: {license_file.name}')
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='utf-8')
    print(f'Built {archive.name} ({archive.stat().st_size} bytes), version {__version__}', flush=True)


if __name__ == '__main__':
    main()
