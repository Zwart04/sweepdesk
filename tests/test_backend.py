# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Safety checks run without removing packages or touching real application data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backend as b


class SafetyTests(unittest.TestCase):
    def test_user_paths_reject_parent_links_broad_dirs_and_traversal(self):
        with tempfile.TemporaryDirectory() as d:
            home = Path(d)
            (home/'.config/demo').mkdir(parents=True)
            (home/'outside').mkdir()
            (home/'link').symlink_to(home/'outside', target_is_directory=True)
            (home/'outside/file').touch()
            self.assertTrue(b.safe_user_path(home/'.config/demo', home))
            self.assertFalse(b.safe_user_path(home/'.config', home))
            self.assertFalse(b.safe_user_path(home, home))
            self.assertFalse(b.safe_user_path(home/'link/file', home))
            self.assertFalse(b.safe_user_path(home/'outside/../.config/demo', home))
            self.assertFalse(b.safe_user_path('/usr/bin/curl', home))
            self.assertTrue(b.safe_user_path(home/'link', home))

    def test_dependencies_exclude_old_unrelated_garbage(self):
        def fake_run(args, **kwargs):
            if args[0] == '/usr/bin/dpkg-query':
                return 'demo\tno\toptional\nlibnew\tno\toptional\n'
            if 'autoremove' in args:
                return 'Remv old-unrelated [1]\n'
            if '--autoremove' in args:
                return 'Purg demo [1]\nPurg libnew [1]\nPurg old-unrelated [1]\n'
            if 'libnew' in args:
                return 'Purg demo [1]\nPurg libnew [1]\n'
            return 'Purg demo [1]\n'
        with patch.object(b, 'run', side_effect=fake_run):
            plan = b.make_plan(b.App('Demo', 'demo', '1', 'APT'), dependencies=True)
        self.assertEqual(plan.extra, ['libnew'])
        self.assertNotIn('old-unrelated', plan.commands[0])

    def test_core_package_or_apt_install_side_effect_blocks_plan(self):
        with patch.object(b, 'run', return_value='gnome-shell\tno\toptional\n'):
            with self.assertRaises(RuntimeError):
                b.check_apt_plan('Purg gnome-shell [1]\n')
        with self.assertRaises(RuntimeError):
            b.check_apt_plan('Purg demo [1]\nInst replacement [1]\n')

    def test_changed_apt_plan_never_executes(self):
        app = b.App('Demo', 'demo', '1', 'APT')
        plan = b.Plan(app, commands=[['pkexec', 'apt-get', 'purge', '--', 'demo']], removed=['demo'])
        with patch.object(b, 'run', return_value='Purg demo [1]\nPurg surprise [1]\n'), \
             patch.object(b, 'check_apt_plan', return_value=['demo','surprise']), \
             patch.object(b.subprocess, 'Popen') as process:
            with self.assertRaises(RuntimeError):
                b.execute(plan, lambda _: None)
            process.assert_not_called()

    def test_shared_libreoffice_data_requires_family_removal(self):
        app = b.App('Writer', 'libreoffice-writer', '1', 'APT')
        with patch.object(b, 'run', return_value='Purg libreoffice-writer [1]\n'), \
             patch.object(b, 'check_apt_plan', return_value=['libreoffice-writer']):
            with self.assertRaisesRegex(RuntimeError, 'settings are shared'):
                b.make_plan(app, cleanup=True)

    def test_failed_uninstaller_cannot_clean_user_data(self):
        app = b.App('Demo', 'demo', '1', 'pipx')
        plan = b.Plan(app, commands=[['false']], data=['/unreachable/example'])
        class Process:
            stdout = ['Failed\n']
            def wait(self):
                return 1
        with patch.object(b.subprocess, 'Popen', return_value=Process()), \
             patch.object(b, 'safe_user_path') as safe:
            with self.assertRaisesRegex(RuntimeError, 'User data has not'):
                b.execute(plan, lambda _: None)
            safe.assert_not_called()

    def test_manual_system_file_is_inventory_only(self):
        app = b.App('Demo','demo','1','Manual',paths=['/usr/local/bin/demo'])
        with self.assertRaises(RuntimeError):
            b.make_plan(app)

    def test_vendor_data_are_opt_in(self):
        app = b.App('Claude','@anthropic-ai/claude-code','1','npm',
                    manager='/usr/bin/npm',scope=str(b.HOME/'.npm-global'))
        plan = b.make_plan(app)
        self.assertEqual(plan.data, [])
        self.assertIn('--ignore-scripts', plan.commands[0])

    def test_json_inventory_works_with_scoped_npm_packages(self):
        payload={'path': str(b.HOME/'.nvm/versions/node/v24/lib'),
                 'dependencies': {'@anthropic-ai/claude-code': {'version':'2.1'}}}
        def fake_npm(manager, args, **kwargs):
            return str(b.HOME/'.nvm/versions/node/v24') if args[0] == 'prefix' else json.dumps(payload)
        with patch.object(b, 'npm_locations', return_value=['/fake/npm']), \
             patch.object(b, 'npm_run', side_effect=fake_npm):
            apps=b.npm_inventory()
        self.assertEqual(apps[0].package,'@anthropic-ai/claude-code')
        self.assertEqual(apps[0].scope,str(b.HOME/'.nvm/versions/node/v24'))

    def test_npm_prefix_is_not_guessed_from_json(self):
        app=b.App('command-code','command-code','1','npm',manager='/fake/npm',
                  scope=str(b.HOME/'.nvm/versions/node/v24'))
        plan=b.make_plan(app)
        command=plan.commands[0]
        self.assertEqual(command[command.index('--prefix')+1],app.scope)

    def test_artcraft_missing_file_is_not_an_installed_app(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            folder=home/'.local/share/artcraft-launcher'
            folder.mkdir(parents=True)
            binary=home/'GridCraft.AppImage'
            binary.touch()
            manifest={'apps': {
                'gridcraft': {'path':str(binary),'kind':'AppImage','version':'1','files':[]},
                'wordcraft': {'path':str(home/'missing.AppImage'),'kind':'AppImage','files':[]}}}
            (folder/'installed.json').write_text(json.dumps(manifest))
            with patch.object(b,'HOME',home):
                apps=b.appimage_inventory([])
            self.assertEqual([a.package for a in apps],['gridcraft'])

    def test_user_desktop_launcher_is_listed_readonly(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            applications=home/'.local/share/applications'
            applications.mkdir(parents=True)
            executable=home/'Unduhan'/'Horizon Client'
            executable.parent.mkdir()
            executable.write_text('not executed by inventory')
            executable.chmod(0o755)
            (applications/'horizon-launcher.desktop').write_text(
                '[Desktop Entry]\nType=Application\nName=Horizon\n'
                'Comment=Minecraft launcher\n'
                f'Exec="{executable}" %U\nTryExec="{executable}"\nIcon=horizon\n')
            (applications/'hidden.desktop').write_text(
                '[Desktop Entry]\nType=Application\nName=Hidden\nNoDisplay=true\n'
                f'Exec="{executable}"\n')
            (applications/'missing.desktop').write_text(
                '[Desktop Entry]\nType=Application\nName=Missing\n'
                f'Exec="{home}/missing-app"\n')
            (applications/'system.desktop').write_text(
                '[Desktop Entry]\nType=Application\nName=System\nExec=/usr/bin/true\n')
            with patch.object(b, 'HOME', home):
                apps=b.desktop_launcher_inventory([])
                self.assertEqual([app.name for app in apps], ['Horizon'])
                app=apps[0]
                self.assertEqual(app.source, 'Manual')
                self.assertEqual(app.manager, 'desktop-launcher')
                self.assertEqual(app.executable, str(executable))
                self.assertTrue(app.readonly_reason)
                with self.assertRaisesRegex(RuntimeError, 'cannot verify'):
                    b.make_plan(app)
                self.assertEqual(b.desktop_launcher_inventory([app]), [])


if __name__ == '__main__':
    unittest.main()
