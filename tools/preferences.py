"""Merge app preferences while preserving unrelated JSONC settings."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def tokenize(text: str) -> list[tuple[str, int, int]]:
    """Retain offsets to preserve comments and formatting."""
    tokens = []
    pos = 0
    while pos < len(text):
        char = text[pos]
        if char.isspace() or (pos == 0 and char == '\ufeff'):
            pos += 1
        elif text.startswith('//', pos):
            end = text.find('\n', pos)
            pos = len(text) if end < 0 else end
        elif text.startswith('/*', pos):
            end = text.find('*/', pos + 2)
            if end < 0:
                raise ValueError('Unterminated JSONC block comment')
            pos = end + 2
        elif char == '"':
            start = pos
            pos += 1
            while pos < len(text):
                if text[pos] == '\\':
                    pos += 2
                elif text[pos] == '"':
                    pos += 1
                    break
                else:
                    pos += 1
            else:
                raise ValueError('Unterminated JSON string')
            tokens.append((text[start:pos], start, pos))
        elif char in '{}[]:,':
            tokens.append((char, pos, pos + 1))
            pos += 1
        else:
            start = pos
            while pos < len(text) and not text[pos].isspace() and text[pos] not in '{}[]:,/':
                pos += 1
            if pos == start:
                raise ValueError('Unexpected character in JSONC')
            tokens.append((text[start:pos], start, pos))
    return tokens


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON property; resolve it before applying preferences')
        result[key] = value
    return result


def parse_jsonc(text: str) -> dict:
    tokens = tokenize(text)
    compact = ' '.join(token for i, (token, _, _) in enumerate(tokens)
                       if not (token == ',' and i > 0 and i + 1 < len(tokens)
                               and tokens[i + 1][0] in ['}', ']']
                               and tokens[i - 1][0] not in ['{', '[', ',', ':']))
    def reject_constant(value: str) -> None:
        raise ValueError('Non-JSON numeric constant: ' + value)
    result = json.loads(compact, object_pairs_hook=unique_object, parse_constant=reject_constant)
    if not isinstance(result, dict):
        raise ValueError('Preferences must be a JSON object')
    return result


def merge_jsonc(text: str, updates: dict) -> str:
    current = parse_jsonc(text)
    changes = {key: value for key, value in updates.items()
               if key not in current or json.dumps(current[key], sort_keys=True) != json.dumps(value, sort_keys=True)}
    if not changes:
        return text
    tokens = tokenize(text)
    spans = {}
    i = 1
    last_value_end = None
    trailing_comma = False
    while i < len(tokens) and tokens[i][0] != '}':
        key = json.loads(tokens[i][0])
        if tokens[i + 1][0] != ':':
            raise ValueError('Invalid object property')
        start_index = i + 2
        end_index = start_index
        depth = 0
        while end_index < len(tokens):
            value = tokens[end_index][0]
            if depth == 0 and value in [',', '}']:
                break
            if value in ['{', '[']:
                depth += 1
            elif value in ['}', ']']:
                depth -= 1
            end_index += 1
        start, end = tokens[start_index][1], tokens[end_index - 1][2]
        spans[key] = (start, end)
        last_value_end = end
        trailing_comma = tokens[end_index][0] == ','
        i = end_index + 1 if trailing_comma else end_index
    close = tokens[-1][1]
    newline = '\r\n' if '\r\n' in text else '\n'
    edits = []
    for key, value in changes.items():
        if key in spans:
            start, end = spans[key]
            edits.append((start, end, json.dumps(value, ensure_ascii=True)))
    additions = {key: value for key, value in changes.items() if key not in spans}
    if additions:
        if spans and not trailing_comma and last_value_end != close:
            edits.append((last_value_end, last_value_end, ','))
        body = (',' + newline).join('  ' + json.dumps(k) + ': ' + json.dumps(v, ensure_ascii=True)
                                    for k, v in additions.items())
        prefix = '' if close > 0 and text[close - 1] in '\r\n' else newline
        separator = ',' if spans and not trailing_comma and last_value_end == close else ''
        edits.append((close, close, separator + prefix + body + newline))
    result = text
    for start, end, value in sorted(edits, reverse=True):
        result = result[:start] + value + result[end:]
    expected = dict(current, **updates)
    if parse_jsonc(result) != expected:
        raise ValueError('Preference merge verification failed; no file was written')
    return result


def pi_updates(current: dict, platform: str) -> dict:
    required = json.loads((ROOT / 'packages/manifest.json').read_text(encoding='utf-8'))['piPackages']
    packages = current.get('packages', [])
    if not isinstance(packages, list):
        raise ValueError('Pi packages must be an array')
    packages = list(packages)
    def identity(source: str) -> str:
        if source.startswith('npm:'):
            version = source.find('@', len('npm:') + 1)
            return source if version < 0 else source[:version]
        return source
    sources = set()
    for package in packages:
        source = package if isinstance(package, str) else package.get('source') if isinstance(package, dict) else None
        if not isinstance(source, str):
            raise ValueError('Pi package entries need a string source; resolve malformed entries before migration')
        sources.add(identity(source))
    packages.extend(source for source in required if identity(source) not in sources)
    existing = current.get('defaultTools', [])
    if not isinstance(existing, list) or not all(isinstance(v, str) for v in existing):
        raise ValueError('Pi defaultTools must be an array of strings')
    if any(entry in ['', '+', '-'] for entry in existing):
        raise ValueError('Pi tool entries need a tool name')
    plain = any(not entry.startswith(('+', '-')) for entry in existing)
    names = ['grep', 'find', 'ls', 'codemode', 'tool_search']
    if plain:
        # Resolve mixed settings lists before adding shared tools.
        tools = list(dict.fromkeys(entry for entry in existing if not entry.startswith(('+', '-'))))
        for entry in existing:
            if entry.startswith('+') and entry[1:] not in tools:
                tools.append(entry[1:])
            elif entry.startswith('-'):
                tools = [name for name in tools if name != entry[1:]]
        excluded = 'bash' if platform == 'win32' else 'powershell'
        tools = [entry for entry in tools if entry != excluded]
        for entry in ['read', 'edit', 'write', 'powershell' if platform == 'win32' else 'bash'] + names:
            if entry not in tools:
                tools.append(entry)
    else:
        desired = ['+' + name for name in names]
        if platform == 'win32':
            desired += ['-bash', '+powershell']
        else:
            desired += ['+bash']
        changed_names = {entry[1:] for entry in desired}
        tools = [entry for entry in existing if entry[1:] not in changed_names] + desired
    return {'packages': packages, 'defaultTools': tools, 'theme': 'solarized-dark'}


def read_settings(path: Path) -> str:
    with path.open(encoding='utf-8', newline='') as handle:
        return handle.read()


def preference_targets(home: Path, platform: str, appdata: Path | None = None) -> list[tuple[Path, dict]]:
    if platform == 'win32':
        appdata = appdata or home / 'AppData/Roaming'
        vscode = appdata / 'Code/User/settings.json'
    elif platform == 'darwin':
        vscode = home / 'Library/Application Support/Code/User/settings.json'
    else:
        raise ValueError('Only macOS and Windows are supported')
    pi = home / '.pi/agent/settings.json'
    current = parse_jsonc(read_settings(pi)) if pi.exists() else {}
    return [
        (vscode, json.loads((ROOT / 'config/vscode.json').read_text(encoding='utf-8'))),
        (home / '.config/herdr-app/settings.json', json.loads((ROOT / 'config/herdr.json').read_text(encoding='utf-8'))),
        (pi, pi_updates(current, platform)),
    ]


def atomic_write(path: Path, text: str, backup_root: Path) -> None:
    if path.is_symlink():
        raise ValueError('Refusing to replace a symlinked preference file; review its owner first')
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    if path.exists():
        backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = backup_root / (str(len(list(backup_root.iterdir()))) + '-' + path.name)
        shutil.copy2(path, backup)
        backup.chmod(0o600)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='', dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(mode)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='Write changes; default is a preview')
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--platform', choices=['darwin', 'win32'], default=sys.platform)
    args = parser.parse_args()
    home = args.home.resolve()
    if args.apply and home == Path.home().resolve() and args.platform != sys.platform:
        parser.error('Refusing cross-platform preference application to the real home directory')
    appdata = Path(os.environ['APPDATA']) if args.platform == 'win32' and home == Path.home().resolve() and os.environ.get('APPDATA') else None
    targets = preference_targets(home, args.platform, appdata)
    prepared = []
    for path, updates in targets:
        old = read_settings(path) if path.exists() else '{}\n'
        merged = merge_jsonc(old, updates)
        old_data = parse_jsonc(old)
        changed = [key for key, value in updates.items() if key not in old_data
                   or json.dumps(old_data[key], sort_keys=True) != json.dumps(value, sort_keys=True)]
        print(('MERGE ' if changed else 'OK ') + str(path.relative_to(home)) + (': ' + ', '.join(changed) if changed else ''))
        if old != merged:
            prepared.append((path, merged))
    # Validate all files before writing any.
    if args.apply:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backups = home / '.local/state/dotfiles/backups' / stamp
        for path, merged in prepared:
            atomic_write(path, merged, backups)
        print('Applied ' + str(len(prepared)) + ' preference merges.')
    else:
        print('Plan only. Use --apply to write changes.')


if __name__ == '__main__':
    main()
