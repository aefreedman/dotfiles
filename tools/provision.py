"""Preview or install packages."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / 'packages/manifest.json').read_text(encoding='utf-8'))


def execute(argv: list[str], *, env: dict[str, str] | None = None) -> None:
    print('+ ' + subprocess.list2cmdline(argv), flush=True)
    if sys.platform == 'win32' and Path(argv[0]).suffix.lower() in ['.cmd', '.bat']:
        argv = [os.environ.get('COMSPEC', 'cmd.exe'), '/d', '/s', '/c', subprocess.list2cmdline(argv)]
    subprocess.run(argv, check=True, env=env)


def official_installer(url: str, platform: str, *, env: dict[str, str] | None = None) -> None:
    approved = (set(MANIFEST['officialInstallers']['pi'].values())
                | set(MANIFEST['officialInstallers']['herdrCore'].values())
                | {MANIFEST['officialInstallers']['herdrWindows'], MANIFEST['officialInstallers']['unityWindows']})
    if url not in approved or not url.startswith('https://'):
        raise ValueError('Unapproved installer URL')
    with tempfile.TemporaryDirectory(prefix='dotfiles-installer-') as directory:
        script = Path(directory) / ('install.ps1' if platform == 'win32' else 'install.sh')
        request = urllib.request.Request(url, headers={'User-Agent': 'dotfiles-bootstrap'})
        with urllib.request.urlopen(request, timeout=60) as response:
            if urllib.parse.urlparse(response.url).scheme != 'https':
                raise ValueError('Installer redirected away from HTTPS')
            script.write_bytes(response.read())
        if platform == 'win32':
            command = [shutil.which('pwsh') or 'powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)]
        else:
            command = ['/bin/bash', str(script)]
        if env is None:
            execute(command)
        else:
            execute(command, env=env)


def herdr_core_path(platform: str) -> str | None:
    command = shutil.which('herdr-core')
    if command:
        return command
    if platform == 'win32':
        local_appdata = os.environ.get('LOCALAPPDATA')
        if not local_appdata:
            raise RuntimeError('LOCALAPPDATA is not set; cannot locate herdr-core')
        candidate = Path(local_appdata) / 'Programs/herdr-core/herdr-core.exe'
    else:
        candidate = Path.home() / '.local/bin/herdr-core'
    return str(candidate) if candidate.is_file() else None


def ensure_herdr_core(platform: str) -> str:
    core = herdr_core_path(platform)
    if not core:
        official_installer(MANIFEST['officialInstallers']['herdrCore'][platform], platform)
        core = herdr_core_path(platform)
        if not core:
            raise RuntimeError('herdr-core installer finished, but its executable was not found')
    execute([core, '--version'])
    return core


def unity_cli_path(platform: str) -> str | None:
    command = shutil.which('unity')
    if command:
        return command
    if platform == 'win32':
        custom_home = os.environ.get('UNITY_CLI_HOME')
        local_appdata = os.environ.get('LOCALAPPDATA')
        if custom_home:
            candidates = [Path(custom_home) / 'bin/unity.exe']
        elif local_appdata:
            candidates = [Path(local_appdata) / 'Unity/bin/unity.exe']
        else:
            raise RuntimeError('LOCALAPPDATA or UNITY_CLI_HOME must be set to locate Unity CLI')
    else:
        candidates = [Path('/opt/homebrew/bin/unity'), Path('/usr/local/bin/unity')]
    return next((str(path) for path in candidates if path.is_file()), None)


def ensure_unity_cli(platform: str) -> str:
    unity = unity_cli_path(platform)
    if not unity:
        if platform == 'darwin':
            raise RuntimeError('Unity CLI is missing. Run bootstrap.sh --install to install its Homebrew cask.')
        # The CLI installer also installs agent skills unless explicitly disabled.
        official_installer(MANIFEST['officialInstallers']['unityWindows'], platform,
                           env={**os.environ, 'UNITY_CLI_SKIP_SETUP': '1'})
        unity = unity_cli_path(platform)
        if not unity:
            raise RuntimeError('Unity CLI installer finished, but its executable was not found')
    execute([unity, '--version'])
    return unity


def managed_pi(path: str) -> bool:
    candidate = Path(path).absolute()
    if not candidate.is_file():
        return False
    resolved = candidate.resolve(strict=True)
    # Pi may link into Homebrew's bin; check its install marker, not the PATH prefix.
    roots = {candidate.parent, resolved.parent}
    if resolved.parent.name == 'bin':
        roots.add(resolved.parent.parent / 'install')
    for root in roots:
        marker = root / 'managed-install.json'
        if not marker.is_file():
            continue
        metadata = json.loads(marker.read_text(encoding='utf-8-sig'))
        if (metadata.get('kind'), metadata.get('schemaVersion'), metadata.get('layout')) != ('pi-managed-install', 1, 'releases-v1'):
            raise ValueError('Unrecognized Pi install marker; review installation ownership before proceeding')
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install', action='store_true', help='Install/update packages; default is a preview')
    parser.add_argument('--skip-packages', action='store_true', help='Skip packages installed by the bootstrap script')
    parser.add_argument('--platform', choices=['darwin', 'win32'], default=sys.platform)
    args = parser.parse_args()
    if args.install and args.platform != sys.platform:
        parser.error('Cannot install for another operating system')
    platform = args.platform
    if platform not in ['darwin', 'win32']:
        parser.error('Only macOS and Windows are supported')
    group = MANIFEST['macos' if platform == 'darwin' else 'windows']
    print('Packages:')
    if platform == 'darwin':
        print('Homebrew formulae: ' + ', '.join(group['formulae']))
        print('Homebrew casks: ' + ', '.join(group['casks']))
    else:
        print('WinGet packages: ' + ', '.join(group['winget']))
        print('Original JetBrains Mono: per-user install from the official release')
        print('Unity CLI: official installer if missing; verify installed executable')
    print('Herdr core: official installer if missing; verify installed executable')
    print('Pi: latest official release; packages: ' + ', '.join(MANIFEST['piPackages']))
    for item in group.get('manual', []):
        print('Install separately: ' + item['name'] + ' - ' + item['url'])
    if not args.install:
        print('Plan only. No packages installed or settings changed.')
        return
    current_pi = shutil.which('pi')
    if current_pi and not managed_pi(current_pi):
        raise RuntimeError('Pi install ownership is unrecognized. Review it before provisioning.')
    if not args.skip_packages:
        if platform == 'darwin':
            brew = shutil.which('brew')
            if not brew:
                raise RuntimeError('Homebrew is missing. Run bootstrap.sh --install.')
            execute([brew, 'bundle', '--file', str(ROOT / 'packages/Brewfile'), '--no-upgrade'])
        else:
            winget = shutil.which('winget')
            if not winget:
                raise RuntimeError('WinGet is missing. Install/update Microsoft App Installer first.')
            execute([winget, 'import', '--import-file', str(ROOT / 'packages/windows-winget.json'), '--ignore-versions', '--disable-interactivity'])
    if platform == 'win32':
        execute([shutil.which('pwsh') or 'powershell.exe', '-NoProfile', '-File', str(ROOT / 'tools/install-fonts.ps1')])
        if not shutil.which('herdr-app') and not (Path(os.environ['LOCALAPPDATA']) / 'Programs/herdr-app/herdr-app.exe').exists():
            official_installer(MANIFEST['officialInstallers']['herdrWindows'], platform)
    ensure_herdr_core(platform)
    ensure_unity_cli(platform)
    if current_pi:
        execute([current_pi, 'update'])
    else:
        official_installer(MANIFEST['officialInstallers']['pi'][platform], platform)
    # Installer PATH updates are not necessarily inherited by this process.
    candidates = [Path.home() / '.pi/agent/bin/pi.cmd', Path.home() / '.pi/agent/bin/pi', Path.home() / '.local/bin/pi']
    pi = next((str(path) for path in candidates if path.is_file()), None) or shutil.which('pi')
    if not pi or not managed_pi(pi):
        raise RuntimeError('Official Pi launcher not found. Open a fresh terminal and check command resolution.')
    for package in MANIFEST['piPackages']:
        execute([pi, 'install', package])
    execute([pi, '--version'])
    execute([pi, 'list'])
    print('Packages installed. Preview settings with tools/preferences.py.')


if __name__ == '__main__':
    main()
