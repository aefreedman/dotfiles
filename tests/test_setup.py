from __future__ import annotations

from contextlib import redirect_stdout
import io
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


class HerdrCoreTests(unittest.TestCase):
    def test_missing_core_installs_and_verifies_on_both_platforms(self):
        for platform in ['darwin', 'win32']:
            with self.subTest(platform=platform), \
                    patch.object(provision, 'herdr_core_path', side_effect=[None, 'installed-core']), \
                    patch.object(provision, 'official_installer') as installer, \
                    patch.object(provision, 'execute') as execute:
                self.assertEqual(provision.ensure_herdr_core(platform), 'installed-core')
                installer.assert_called_once_with(provision.MANIFEST['officialInstallers']['herdrCore'][platform], platform)
                execute.assert_called_once_with(['installed-core', '--version'])

    def test_existing_core_is_verified_without_reinstallation(self):
        with patch.object(provision, 'herdr_core_path', return_value='existing-core'), \
                patch.object(provision, 'official_installer') as installer, \
                patch.object(provision, 'execute') as execute:
            provision.ensure_herdr_core('darwin')
            installer.assert_not_called()
            execute.assert_called_once_with(['existing-core', '--version'])

    def test_core_missing_from_path_is_found_in_default_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            mac = home / '.local/bin/herdr-core'
            windows = home / 'AppData/Local/Programs/herdr-core/herdr-core.exe'
            for path in [mac, windows]:
                path.parent.mkdir(parents=True)
                path.write_text('test executable', encoding='utf-8')
            with patch.object(provision.shutil, 'which', return_value=None), \
                    patch.object(provision.Path, 'home', return_value=home), \
                    patch.dict(provision.os.environ, {'LOCALAPPDATA': str(home / 'AppData/Local')}):
                self.assertEqual(provision.herdr_core_path('darwin'), str(mac))
                self.assertEqual(provision.herdr_core_path('win32'), str(windows))

    def test_failed_install_is_not_reported_as_success(self):
        with patch.object(provision, 'herdr_core_path', return_value=None), \
                patch.object(provision, 'official_installer', side_effect=subprocess.CalledProcessError(1, 'installer')), \
                patch.object(provision, 'execute') as execute:
            with self.assertRaises(subprocess.CalledProcessError):
                provision.ensure_herdr_core('darwin')
            execute.assert_not_called()

    def test_missing_executable_after_install_blocks(self):
        with patch.object(provision, 'herdr_core_path', return_value=None), \
                patch.object(provision, 'official_installer'), \
                patch.object(provision, 'execute') as execute:
            with self.assertRaisesRegex(RuntimeError, 'executable was not found'):
                provision.ensure_herdr_core('darwin')
            execute.assert_not_called()

    def test_version_failure_blocks_without_reinstalling(self):
        with patch.object(provision, 'herdr_core_path', return_value='broken-core'), \
                patch.object(provision, 'official_installer') as installer, \
                patch.object(provision, 'execute', side_effect=subprocess.CalledProcessError(1, 'broken-core')):
            with self.assertRaises(subprocess.CalledProcessError):
                provision.ensure_herdr_core('darwin')
            installer.assert_not_called()

    def test_core_installer_urls_are_allowed(self):
        for platform in ['darwin', 'win32']:
            with self.subTest(platform=platform), \
                    patch.object(provision.urllib.request, 'urlopen') as download, \
                    patch.object(provision, 'execute') as execute:
                url = provision.MANIFEST['officialInstallers']['herdrCore'][platform]
                response = download.return_value.__enter__.return_value
                response.url = url
                response.read.return_value = b'# test installer\n'
                provision.official_installer(url, platform)
                execute.assert_called_once()
                script = Path(execute.call_args.args[0][-1])
                self.assertEqual(script.suffix, '.ps1' if platform == 'win32' else '.sh')

    def test_provisioning_checks_core_on_both_platforms(self):
        for platform in ['darwin', 'win32']:
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as directory, \
                    patch.object(provision.sys, 'argv', ['provision.py', '--install', '--skip-packages', '--platform', platform]), \
                    patch.object(provision.sys, 'platform', platform), \
                    patch.object(provision.Path, 'home', return_value=Path(directory)), \
                    patch.object(provision.shutil, 'which', side_effect=lambda name: 'test-' + name), \
                    patch.object(provision, 'managed_pi', return_value=True), \
                    patch.object(provision, 'ensure_herdr_core') as ensure, \
                    patch.object(provision, 'ensure_unity_cli') as unity, \
                    patch.object(provision, 'execute'), redirect_stdout(io.StringIO()):
                provision.main()
                ensure.assert_called_once_with(platform)
                unity.assert_called_once_with(platform)


class UnityCliTests(unittest.TestCase):
    def test_existing_cli_is_verified_without_reinstallation(self):
        for platform in ['darwin', 'win32']:
            with self.subTest(platform=platform), \
                    patch.object(provision, 'unity_cli_path', return_value='existing-unity'), \
                    patch.object(provision, 'official_installer') as installer, \
                    patch.object(provision, 'execute') as execute:
                self.assertEqual(provision.ensure_unity_cli(platform), 'existing-unity')
                installer.assert_not_called()
                execute.assert_called_once_with(['existing-unity', '--version'])

    def test_windows_install_disables_agent_setup_without_changing_parent_environment(self):
        with patch.object(provision, 'unity_cli_path', side_effect=[None, 'installed-unity']), \
                patch.object(provision, 'official_installer') as installer, \
                patch.object(provision, 'execute') as execute, \
                patch.dict(provision.os.environ, {'UNITY_CLI_SKIP_SETUP': '0'}):
            self.assertEqual(provision.ensure_unity_cli('win32'), 'installed-unity')
            installer.assert_called_once_with(provision.MANIFEST['officialInstallers']['unityWindows'],
                                              'win32', env={**provision.os.environ, 'UNITY_CLI_SKIP_SETUP': '1'})
            self.assertEqual(provision.os.environ['UNITY_CLI_SKIP_SETUP'], '0')
            execute.assert_called_once_with(['installed-unity', '--version'])

    def test_mac_missing_cli_requires_homebrew_instead_of_another_installer(self):
        with patch.object(provision, 'unity_cli_path', return_value=None), \
                patch.object(provision, 'official_installer') as installer:
            with self.assertRaisesRegex(RuntimeError, 'Homebrew cask'):
                provision.ensure_unity_cli('darwin')
            installer.assert_not_called()

    def test_windows_default_and_custom_install_locations_are_found_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for environment, binary in [
                ({'LOCALAPPDATA': str(root / 'Local')}, root / 'Local/Unity/bin/unity.exe'),
                ({'UNITY_CLI_HOME': str(root / 'Custom')}, root / 'Custom/bin/unity.exe'),
            ]:
                binary.parent.mkdir(parents=True)
                binary.write_text('test executable', encoding='utf-8')
                with self.subTest(environment=environment), \
                        patch.dict(provision.os.environ, environment, clear=True), \
                        patch.object(provision.shutil, 'which', return_value=None):
                    self.assertEqual(provision.unity_cli_path('win32'), str(binary))

    def test_mac_homebrew_locations_are_found_without_path(self):
        for binary in ['/opt/homebrew/bin/unity', '/usr/local/bin/unity']:
            with self.subTest(binary=binary), \
                    patch.object(provision.shutil, 'which', return_value=None), \
                    patch.object(provision.Path, 'is_file', autospec=True,
                                 side_effect=lambda path: path.as_posix() == binary):
                self.assertEqual(provision.unity_cli_path('darwin'), str(Path(binary)))

    def test_missing_windows_environment_is_reported(self):
        with patch.dict(provision.os.environ, {}, clear=True), \
                patch.object(provision.shutil, 'which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'LOCALAPPDATA or UNITY_CLI_HOME'):
                provision.unity_cli_path('win32')

    def test_failed_install_propagates_without_verification(self):
        with patch.object(provision, 'unity_cli_path', return_value=None), \
                patch.object(provision, 'official_installer', side_effect=subprocess.CalledProcessError(1, 'installer')), \
                patch.object(provision, 'execute') as execute:
            with self.assertRaises(subprocess.CalledProcessError):
                provision.ensure_unity_cli('win32')
            execute.assert_not_called()

    def test_missing_executable_after_install_blocks(self):
        with patch.object(provision, 'unity_cli_path', return_value=None), \
                patch.object(provision, 'official_installer'), \
                patch.object(provision, 'execute') as execute:
            with self.assertRaisesRegex(RuntimeError, 'executable was not found'):
                provision.ensure_unity_cli('win32')
            execute.assert_not_called()

    def test_version_failure_blocks_without_reinstalling(self):
        with patch.object(provision, 'unity_cli_path', return_value='broken-unity'), \
                patch.object(provision, 'official_installer') as installer, \
                patch.object(provision, 'execute', side_effect=subprocess.CalledProcessError(1, 'broken-unity')):
            with self.assertRaises(subprocess.CalledProcessError):
                provision.ensure_unity_cli('win32')
            installer.assert_not_called()

    def test_installer_is_approved_and_receives_environment(self):
        with patch.object(provision.urllib.request, 'urlopen') as download, \
                patch.object(provision, 'execute') as execute:
            url = provision.MANIFEST['officialInstallers']['unityWindows']
            response = download.return_value.__enter__.return_value
            response.url = url
            response.read.return_value = b'# test installer\n'
            env = {'UNITY_CLI_SKIP_SETUP': '1'}
            provision.official_installer(url, 'win32', env=env)
            execute.assert_called_once()
            self.assertEqual(execute.call_args.kwargs, {'env': env})
            self.assertEqual(Path(execute.call_args.args[0][-1]).suffix, '.ps1')

    def test_execute_passes_environment_to_child(self):
        with patch.object(provision.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            env = {'UNITY_CLI_SKIP_SETUP': '1'}
            provision.execute(['unity', '--version'], env=env)
            run.assert_called_once_with(['unity', '--version'], check=True, env=env)


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
