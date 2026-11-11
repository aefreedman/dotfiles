"""Connect the shared Git config and PowerShell profile."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil
import subprocess
import sys

from preferences import atomic_write

GIT_INCLUDE = '~/.config/git/shared.gitconfig'
START = '# BEGIN managed dotfiles profile'
END = '# END managed dotfiles profile'


def git_text(old: str, home: Path) -> str:
    # Let Git parse quoted paths and repeated include sections.
    import tempfile
    with tempfile.TemporaryDirectory(prefix='dotfiles-git-check-') as directory:
        path = Path(directory) / 'gitconfig'
        path.write_text(old, encoding='utf-8')
        result = subprocess.run(['git', 'config', '--file', str(path), '--get-all', 'include.path'],
                                text=True, capture_output=True, check=False)
        if result.returncode not in [0, 1]:
            raise ValueError('Existing Git configuration is invalid; no integration was written')
        equivalent = {GIT_INCLUDE, str(home / '.config/git/shared.gitconfig'), (home / '.config/git/shared.gitconfig').as_posix()}
        if any(value in equivalent for value in result.stdout.splitlines()):
            return old
    return old.rstrip() + '\n\n[include]\n    path = ' + GIT_INCLUDE + '\n'


def powershell_text(old: str) -> str:
    block = START + '\n. (Join-Path $HOME \'.config/powershell/profile.ps1\')\n' + END
    if START in old or END in old:
        if old.count(START) != 1 or old.count(END) != 1:
            raise ValueError('Malformed managed PowerShell block; resolve it before integration')
        begin, end = old.index(START), old.index(END) + len(END)
        if begin >= end - len(END):
            raise ValueError('Managed PowerShell block markers are out of order')
        return old[:begin] + block + old[end:]
    if re.search(r'oh-my-posh\s+init', old, re.IGNORECASE):
        raise ValueError('Existing Oh My Posh initialization needs review before profile integration')
    return old.rstrip() + ('\n\n' if old.strip() else '') + block + '\n'


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--platform', choices=['darwin', 'win32'], default=sys.platform)
    args = parser.parse_args()
    if not shutil.which('git'):
        parser.error('Git must be installed before integration')
    home = args.home.resolve()
    if args.apply and home == Path.home().resolve() and args.platform != sys.platform:
        parser.error('Refusing cross-platform integration into the real home directory')
    git = home / '.gitconfig'
    targets = [(git, git_text(git.read_text(encoding='utf-8') if git.exists() else '', home))]
    requirements = [home / '.config/git/shared.gitconfig']
    if args.platform == 'win32':
        if home == Path.home().resolve() and sys.platform == 'win32':
            pwsh = shutil.which('pwsh')
            if not pwsh:
                parser.error('PowerShell 7 must be installed before profile integration')
            result = subprocess.run([pwsh, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', '$PROFILE.CurrentUserAllHosts'],
                                    text=True, capture_output=True, check=True)
            profile = Path(result.stdout.strip())
        else:
            profile = home / 'Documents/PowerShell/profile.ps1'
        old = profile.read_text(encoding='utf-8') if profile.exists() else ''
        targets.append((profile, powershell_text(old)))
        requirements.append(home / '.config/powershell/profile.ps1')
    if args.apply and any(not path.is_file() for path in requirements):
        parser.error('Managed files are missing. Preview and apply the chezmoi source before integration.')
    backups = home / '.local/state/dotfiles/backups' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    for path, text in targets:
        old = path.read_text(encoding='utf-8') if path.exists() else ''
        print(('CONNECT ' if old != text else 'OK ') + str(path))
        if args.apply and old != text:
            atomic_write(path, text, backups)
    if not args.apply:
        print('Plan only. Use --apply to write changes.')


if __name__ == '__main__':
    main()
