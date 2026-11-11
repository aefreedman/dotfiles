from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import preferences
import integrate
import provision


class JsoncTests(unittest.TestCase):
    def test_preserves_comments_and_unrelated_values(self):
        source = '{\n  // Keep this explanation\n  "unrelated": {"path": "https://example.invalid/a//b"},\n  "size": 20, // Keep this too\n}\n'
        result = preferences.merge_jsonc(source, {'size': 13, 'ligatures': True})
        self.assertIn('// Keep this explanation', result)
        self.assertIn('// Keep this too', result)
        self.assertEqual(preferences.parse_jsonc(result), {'unrelated': {'path': 'https://example.invalid/a//b'}, 'size': 13, 'ligatures': True})

    def test_nested_trailing_commas(self):
        result = preferences.merge_jsonc('{"old": [1, {"x": true,},],}', {'new': [1, 2]})
        self.assertEqual(preferences.parse_jsonc(result), {'old': [1, {'x': True}], 'new': [1, 2]})

    def test_append_before_last_line_comment(self):
        result = preferences.merge_jsonc('{"old": 1 // final comment\n}', {'new': 2})
        self.assertEqual(preferences.parse_jsonc(result), {'old': 1, 'new': 2})
        self.assertIn('// final comment', result)

    def test_empty_object_with_comment(self):
        result = preferences.merge_jsonc('{/* keep */}', {'new': True})
        self.assertIn('/* keep */', result)
        self.assertEqual(preferences.parse_jsonc(result), {'new': True})

    def test_idempotent(self):
        source = '{ "size": 13 }\n'
        self.assertEqual(preferences.merge_jsonc(source, {'size': 13}), source)

    def test_bom_and_crlf(self):
        result = preferences.merge_jsonc('\ufeff{\r\n  "x": 1\r\n}\r\n', {'y': False})
        self.assertEqual(preferences.parse_jsonc(result), {'x': 1, 'y': False})
        self.assertTrue(result.startswith('\ufeff'))

    def test_escaped_strings(self):
        source = json.dumps({'path': 'C:\\work\\quoted"name', 'text': '/* not a comment */'})
        self.assertEqual(preferences.parse_jsonc(preferences.merge_jsonc(source, {'new': 3}))['text'], '/* not a comment */')

    def test_boolean_and_numeric_values_are_distinct(self):
        value = preferences.parse_jsonc(preferences.merge_jsonc('{"x": true}', {'x': 1}))
        self.assertIs(type(value['x']), int)

    def test_duplicate_properties_rejected(self):
        with self.assertRaises(ValueError):
            preferences.parse_jsonc('{"x": 1, "x": 2}')

    def test_duplicate_nested_properties_rejected(self):
        with self.assertRaises(ValueError):
            preferences.parse_jsonc('{"outer": {"x": 1, "x": 2}}')

    def test_malformed_input_rejected(self):
        for source in ['[]', '{"x": }', '{/* never closed', '{"x": "never closed}', '{"x": /}']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                preferences.merge_jsonc(source, {'new': True})

    def test_malformed_json_is_not_repaired_accidentally(self):
        for source in ['{"x": 1 2}', '{"x": t rue}', '{,}', '{"x": [,]}', '{"x": NaN}']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                preferences.merge_jsonc(source, {'new': True})

    def test_various_replacements(self):
        for value in [None, True, 13, 'text', [], {}, [1, {'nested': 'value'}]]:
            with self.subTest(value=value):
                result = preferences.merge_jsonc('{"keep": [1,2], "replace": false}', {'replace': value, 'added': value})
                self.assertEqual(preferences.parse_jsonc(result), {'keep': [1, 2], 'replace': value, 'added': value})

    def test_backup_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            path = base / 'app/settings.json'
            path.parent.mkdir()
            path.write_text('{"keep": true}')
            preferences.atomic_write(path, '{"keep": true, "added": 1}', base / 'backups')
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['added'], 1)
            backups = list((base / 'backups').iterdir())
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(encoding='utf-8'), '{"keep": true}')


class PiTests(unittest.TestCase):
    def test_four_core_packages_on_new_machine(self):
        value = preferences.pi_updates({}, 'darwin')
        self.assertEqual(len(value['packages']), 4)
        self.assertTrue(all(p.startswith('npm:') for p in value['packages']))

    def test_preserve_optional_packages_and_resource_filters(self):
        optional = {'source': 'npm:optional-package', 'skills': []}
        value = preferences.pi_updates({'packages': [optional]}, 'darwin')
        self.assertIn(optional, value['packages'])

    def test_versioned_core_package_keeps_filters_without_duplicate(self):
        package = {'source': 'npm:pi-subagents@0.87.0', 'skills': []}
        value = preferences.pi_updates({'packages': [package]}, 'darwin')
        self.assertEqual(len(value['packages']), 4)
        self.assertIn(package, value['packages'])

    def test_no_duplicate_core_packages(self):
        first = preferences.pi_updates({}, 'darwin')
        self.assertEqual(preferences.pi_updates(first, 'darwin'), first)

    def test_windows_additive_tools(self):
        value = preferences.pi_updates({'defaultTools': ['+bash', '-grep']}, 'win32')
        self.assertIn('-bash', value['defaultTools'])
        self.assertIn('+powershell', value['defaultTools'])
        self.assertIn('+grep', value['defaultTools'])
        self.assertNotIn('+bash', value['defaultTools'])

    def test_windows_existing_allowlist_remains_allowlist(self):
        value = preferences.pi_updates({'defaultTools': ['read', 'bash', 'custom']}, 'win32')
        self.assertIn('custom', value['defaultTools'])
        self.assertIn('powershell', value['defaultTools'])
        self.assertNotIn('bash', value['defaultTools'])
        self.assertTrue(all(not t.startswith(('+', '-')) for t in value['defaultTools']))

    def test_mixed_settings_tool_modes_preserve_adjustments(self):
        value = preferences.pi_updates({'defaultTools': ['read', 'custom', 'obsolete', '+extra', '-obsolete']}, 'darwin')
        self.assertIn('custom', value['defaultTools'])
        self.assertIn('extra', value['defaultTools'])
        self.assertNotIn('obsolete', value['defaultTools'])
        self.assertTrue(all(not tool.startswith(('+', '-')) for tool in value['defaultTools']))

    def test_target_locations(self):
        home = Path('/synthetic-home')
        mac = preferences.preference_targets(home, 'darwin')
        windows = preferences.preference_targets(home, 'win32')
        self.assertIn('Library/Application Support/Code', mac[0][0].as_posix())
        self.assertIn('AppData/Roaming/Code', windows[0][0].as_posix())
        self.assertEqual(mac[1][1]['font_ligatures'], True)
        self.assertEqual(mac[0][1]['editor.fontSize'], 13)

    def test_installer_owner_detection(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            launcher = home / '.pi/agent/bin/pi'
            launcher.parent.mkdir(parents=True)
            launcher.write_text('launcher', encoding='utf-8')
            self.assertFalse(provision.managed_pi(str(launcher)))
            marker = home / '.pi/agent/install/managed-install.json'
            marker.parent.mkdir(parents=True)
            marker.write_text(json.dumps({'kind': 'pi-managed-install', 'schemaVersion': 1, 'layout': 'releases-v1'}), encoding='utf-8')
            self.assertTrue(provision.managed_pi(str(launcher)))
            other = home / 'npm/bin/pi'
            other.parent.mkdir(parents=True)
            other.write_text('unrelated npm launcher', encoding='utf-8')
            self.assertFalse(provision.managed_pi(str(other)))

    def test_invalid_installer_marker_blocks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = root / 'pi'
            launcher.write_text('launcher', encoding='utf-8')
            (root / 'managed-install.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError):
                provision.managed_pi(str(launcher))


class IntegrationTests(unittest.TestCase):
    def test_git_include_is_idempotent(self):
        home = Path('/synthetic-home')
        old = '[credential]\n    helper = private-helper\n'
        first = integrate.git_text(old, home)
        self.assertIn('helper = private-helper', first)
        self.assertEqual(integrate.git_text(first, home), first)

    def test_invalid_git_config_is_rejected(self):
        with self.assertRaises(ValueError):
            integrate.git_text('[invalid', Path('/synthetic-home'))

    def test_profile_preserves_existing_helpers(self):
        old = 'function Useful { "hello" }\n'
        result = integrate.powershell_text(old)
        self.assertIn(old.strip(), result)
        self.assertEqual(integrate.powershell_text(result), result)

    def test_competing_prompt_requires_review(self):
        with self.assertRaises(ValueError):
            integrate.powershell_text('oh-my-posh init pwsh | Invoke-Expression')

    def test_malformed_profile_markers_rejected(self):
        with self.assertRaises(ValueError):
            integrate.powershell_text(integrate.START)


class RepositoryTests(unittest.TestCase):
    def test_manifest_and_platform_files_agree(self):
        manifest = json.loads((ROOT / 'packages/manifest.json').read_text(encoding='utf-8'))
        winget = json.loads((ROOT / 'packages/windows-winget.json').read_text(encoding='utf-8'))
        ids = [p['PackageIdentifier'] for s in winget['Sources'] for p in s['Packages']]
        self.assertEqual(ids, manifest['windows']['winget'])
        brewfile = (ROOT / 'packages/Brewfile').read_text(encoding='utf-8')
        for name in manifest['macos']['formulae']:
            self.assertIn('brew "' + name + '"', brewfile)
        for name in manifest['macos']['casks']:
            self.assertIn('cask "' + name + '"', brewfile)
        self.assertTrue(any(item['name'] == 'Xcode' for item in manifest['macos']['manual']))

    def test_no_bun_opencode_or_local_pi_sources(self):
        manifest = json.loads((ROOT / 'packages/manifest.json').read_text(encoding='utf-8'))
        self.assertNotIn('bun', manifest['macos']['formulae'])
        self.assertNotIn('opencode', manifest['macos']['formulae'])
        self.assertEqual(len(manifest['piPackages']), 4)
        self.assertTrue(all(p.startswith('npm:') for p in manifest['piPackages']))

    def test_herdr_theme_defaults_reference_managed_palettes(self):
        settings = json.loads((ROOT / 'config/herdr.json').read_text(encoding='utf-8'))
        self.assertTrue(settings['font_ligatures'])
        for name in settings['theme'].values():
            self.assertTrue((ROOT / 'home/dot_config/herdr-app/themes' / (name + '.json')).is_file())

    def test_prompt_themes_no_obsolete_plastic_property(self):
        for path in (ROOT / 'home/dot_config/oh-my-posh').glob('*.json'):
            theme = json.loads(path.read_text(encoding='utf-8'))
            segments = [s for b in theme['blocks'] for s in b.get('segments', [])]
            self.assertTrue(any(s['type'] == 'plastic' for s in segments))
            for segment in segments:
                if segment['type'] == 'plastic':
                    self.assertNotIn('fetch_status', segment.get('properties', {}))

    def test_default_commands_are_plans(self):
        for script in ['provision.py', 'preferences.py', 'integrate.py']:
            with self.subTest(script=script), tempfile.TemporaryDirectory() as directory:
                argv = [sys.executable, str(ROOT / 'tools' / script), '--platform', 'darwin']
                if script != 'provision.py':
                    argv += ['--home', directory]
                result = subprocess.run(argv, text=True, capture_output=True, check=True)
                self.assertIn('Plan only', result.stdout)
                self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
