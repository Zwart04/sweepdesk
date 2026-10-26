from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backend as b
import native_packages as n


class NativeTests(unittest.TestCase):
    def test_distro_families_and_critical_packages(self):
        for info,expected in [({'ID':'ubuntu'},'deb'),({'ID':'linuxmint','ID_LIKE':'ubuntu debian'},'deb'),
                              ({'ID':'fedora'},'rpm'),({'ID':'rocky','ID_LIKE':'rhel fedora'},'rpm'),
                              ({'ID':'opensuse-tumbleweed'},'suse'),({'ID':'manjaro','ID_LIKE':'arch'},'arch'),
                              ({'ID':'alpine'},'alpine'),({'ID':'nixos'},'other')]:
            self.assertEqual(n.family(info),expected)
        for name in ('kernel-core','linux-lts','pacman','rpm','systemd-libs','musl','python3','gnome-shell'):
            self.assertTrue(n.is_critical(name),name)
        self.assertFalse(n.is_critical('tree'))

    def test_native_database_metadata(self):
        with tempfile.TemporaryDirectory() as temp,patch.object(n,'protected_owners',return_value=set()),patch.object(n,'immutable_system',return_value=False):
            root=Path(temp);entry=root/'demo-1';entry.mkdir()
            (entry/'desc').write_text('%NAME%\ndemo\n\n%VERSION%\n1.0-1\n\n%DESC%\nExample app\n\n%ISIZE%\n1234\n\n%ARCH%\nx86_64\n')
            app=n.pacman_inventory(root)[0]
            self.assertEqual((app.package,app.version,app.size),('demo','1.0-1',1234))
            database=root/'installed';database.write_text('P:demo\nV:1.0-r0\nT:Example app\nI:456\nA:x86_64\n\n')
            app=n.apk_inventory(database)[0]
            self.assertEqual((app.package,app.version,app.size),('demo','1.0-r0',456))
        with patch.object(b,'run',return_value='demo\t0:1.0-1\tx86_64\t42\tExample app\tdemo-1.0-1.x86_64\n'),patch.object(n,'protected_owners',return_value=set()),patch.object(n,'immutable_system',return_value=False):
            app=n.rpm_inventory()[0]
            self.assertEqual(app.package,'demo-1.0-1.x86_64')
            self.assertEqual(app.location,'demo')

    def test_pacman_preview_rejects_core_and_never_cascades(self):
        app=b.App('Demo','demo','1','Pacman')
        with patch.object(n,'protected_owners',return_value=set()),patch.object(n,'immutable_system',return_value=False),patch.object(n,'fingerprint',return_value='fixture'),patch.object(b,'run',return_value='demo\nlib-example\n'):
            plan=b.make_plan(app,dependencies=True)
            self.assertEqual(plan.removed,['demo','lib-example'])
            self.assertEqual(plan.extra,['lib-example'])
            self.assertIn('-Rs',plan.commands[0])
            self.assertNotIn('-Rsc',plan.commands[0])
            self.assertNotIn('--nodeps',plan.commands[0])
        with patch.object(n,'protected_owners',return_value=set()),patch.object(n,'immutable_system',return_value=False),patch.object(b,'run',return_value='demo\nglibc\n'):
            with self.assertRaisesRegex(RuntimeError,'Core system'): b.make_plan(app)

    def test_apk_preview_rejects_install_side_effects(self):
        app=b.App('Demo','demo','1','APK')
        with patch.object(n,'protected_owners',return_value=set()),patch.object(n,'immutable_system',return_value=False),patch.object(n,'fingerprint',return_value='fixture'),patch.object(b,'run',return_value='(1/1) Purging demo (1.0-r0)\nOK: 20 MiB in 4 packages\n'):
            plan=b.make_plan(app)
            self.assertEqual(plan.removed,['demo'])
            self.assertIn('--no-network',plan.commands[0])
        with patch.object(n,'immutable_system',return_value=False),patch.object(n,'protected_owners',return_value=set()),patch.object(b,'run',return_value='(1/2) Purging demo (1.0-r0)\n(2/2) Installing replacement (1-r0)'):
            with self.assertRaisesRegex(RuntimeError,'verified'): b.make_plan(app)

    def test_rpm_is_exact_and_does_not_disable_dependencies(self):
        app=b.App('Demo','demo-1.0-1.x86_64','0:1.0-1','RPM',location='demo')
        with patch.object(n,'protected_owners',return_value=set()),patch.object(n,'immutable_system',return_value=False),patch.object(n,'fingerprint',return_value='fixture'),patch.object(n,'rpm_inventory',return_value=[app]):
            plan=b.make_plan(app)
            self.assertEqual(plan.removed,[app.package])
            self.assertIn('--erase',plan.commands[0])
            self.assertNotIn('--allmatches',plan.commands[0])
            self.assertNotIn('--nodeps',plan.commands[0])

    def test_changed_database_and_immutable_system_never_execute(self):
        plan=b.Plan(b.App('Demo','demo','1','Pacman'),commands=[['pkexec','pacman','-R','demo']],fingerprint='old')
        with patch.object(n,'fingerprint',return_value='changed'),patch.object(b.subprocess,'Popen') as process:
            with self.assertRaisesRegex(RuntimeError,'changed'): b.execute(plan,lambda _:None)
            process.assert_not_called()
        with patch.object(n,'immutable_system',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'immutable'): n.preview(plan.app)
