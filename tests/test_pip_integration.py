# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Uninstall only synthetic distributions in a temporary venv, without network access."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import backend as b


class PipIntegrationTests(unittest.TestCase):
    def test_recorded_package_and_unused_dependency_are_actually_removed(self):
        with tempfile.TemporaryDirectory(prefix='sweepdesk-pip-test-') as temporary:
            home=Path(temporary)
            env=home/'venv'
            result=subprocess.run(['/usr/bin/python3','-m','venv',str(env)],text=True,capture_output=True)
            if result.returncode:
                self.skipTest('python3-venv/ensurepip unavailable: install python3-venv to run the isolated integration test')
            python=env/'bin/python'
            site=Path(subprocess.check_output([str(python),'-c','import sysconfig;print(sysconfig.get_path("purelib"))'],text=True).strip())
            def create(name,requires='',requested=False):
                module=site/(name+'.py')
                module.write_text('VALUE = 1\n')
                info=site/(name+'-1.0.dist-info')
                info.mkdir()
                metadata='Metadata-Version: 2.1\nName: '+name+'\nVersion: 1.0\n'
                if requires:
                    metadata+='Requires-Dist: '+requires+'\n'
                (info/'METADATA').write_text(metadata)
                (info/'INSTALLER').write_text('pip\n')
                if requested:
                    (info/'REQUESTED').touch()
                files=[module,*info.iterdir(),info/'RECORD']
                (info/'RECORD').write_text(''.join(str(f.relative_to(site))+',,\n' for f in files))
                return info
            create('sweepdesk_fixture_dep')
            target=create('sweepdesk_fixture_app','sweepdesk_fixture_dep',True)
            with patch.object(b,'HOME',home):
                report=b.probe_python(str(python))
                app=b.App('Fixture','sweepdesk_fixture_app','1.0','pip',manager=str(python),
                          scope=report['prefix'],location=str(target))
                plan=b.make_plan(app,dependencies=True)
                self.assertEqual(plan.extra,['sweepdesk-fixture-dep'])
                logs=[]
                b.execute(plan,logs.append)
                after=b.probe_python(str(python))
            names={p['key'] for p in after['packages']}
            self.assertNotIn('sweepdesk-fixture-app',names)
            self.assertNotIn('sweepdesk-fixture-dep',names)
            self.assertIn('pip',names)
            self.assertFalse(target.exists())


if __name__=='__main__':
    unittest.main()
