import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import backend as b


def python_report():
    def package(name, requires=(), requested=False):
        return {'name':name,'key':name,'version':'1.0','location':str(b.HOME/'.venv/lib'),
                'metadata':str(b.HOME/'.venv/lib'/f'{name}.dist-info'), 'installer':'pip',
                'requested':requested,'recorded':True,'requirements':list(requires),'complete':True}
    return {'prefix':str(b.HOME/'.venv'),'base_prefix':'/usr','venv':True,'pip':True,
            'externally_managed':True,'packages':[
                package('demo',['dep'],True),package('dep'),package('pip',requested=True)]}


class SourceTests(unittest.TestCase):
    def test_ubuntu_distro_detection(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'os-release'
            f.write_text('ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04 LTS"\n')
            self.assertEqual(b.distro_info(f),'Ubuntu 24.04 LTS')

    def test_pip_unused_dependencies_and_shared_exclusions(self):
        report=python_report()
        self.assertEqual(b.pip_dependencies(report,'demo'),['dep'])
        other=copy.deepcopy(report['packages'][0])
        other.update(name='other',key='other',requested=True)
        report['packages'].append(other)
        self.assertEqual(b.pip_dependencies(report,'demo'),[])

    def test_pip_keeps_explicit_or_incompletely_recorded_dependencies(self):
        report=python_report()
        report['packages'][1]['requested']=True
        self.assertEqual(b.pip_dependencies(report,'demo'),[])
        report['packages'][1]['requested']=False
        report['packages'][1]['complete']=False
        self.assertEqual(b.pip_dependencies(report,'demo'),[])

    def test_pep668_protection_and_venv_exception(self):
        report=python_report()
        report['venv']=False
        self.assertIn('PEP 668',b.pip_readonly(report,report['packages'][0]))
        report['venv']=True
        self.assertEqual(b.pip_readonly(report,report['packages'][0]),'')

    def test_pip_plan_uses_selected_interpreter_and_recorded_locations(self):
        report=python_report()
        app=b.App('demo','demo','1','pip',manager='/tmp/venv/bin/python',
                  scope=report['prefix'],location=report['packages'][0]['metadata'])
        with patch.object(b,'probe_python',return_value=report):
            plan=b.make_plan(app,dependencies=True)
        self.assertEqual(plan.extra,['dep'])
        self.assertEqual(plan.commands[0],['/tmp/venv/bin/python','-m','pip','uninstall','-y','--','demo','dep'])
        with patch.object(b,'probe_python',return_value={}), patch.object(b.subprocess,'Popen') as popen:
            with self.assertRaisesRegex(RuntimeError,'environment changed'):
                b.execute(plan,lambda _:None)
            popen.assert_not_called()

    def test_homebrew_has_no_force_or_unrelated_global_cleanup(self):
        app=b.App('demo','vendor/tap/demo','1','Homebrew',manager='/brew')
        command=b.make_plan(app).commands[0]
        self.assertEqual(command,['/brew','uninstall','--formula','vendor/tap/demo'])
        self.assertEqual(b.ENV['HOMEBREW_NO_AUTOREMOVE'],'1')

    def test_bun_and_uv_use_their_own_managers(self):
        app=b.App('demo','demo','1','Bun',manager='/bun',scope=str(b.HOME/'.bun/install/global'))
        command=b.make_plan(app).commands[0]
        self.assertIn('--ignore-scripts',command)
        self.assertIn('BUN_INSTALL_GLOBAL_DIR='+app.scope,command)
        app=b.App('demo','demo','1','uv',manager='/uv')
        self.assertEqual(b.make_plan(app).commands[0],['/uv','tool','uninstall','demo'])

    def test_flatpak_scopes_are_separate(self):
        for scope in ('user','system'):
            app=b.App('Demo','org.example.Demo','1','Flatpak',scope=scope)
            with patch.object(b.shutil,'which',return_value='/flatpak'):
                command=b.make_plan(app).commands[0]
            self.assertIn('--'+scope,command)

    def test_cli_brand_icons_are_bundled_and_offline(self):
        for name in ('curl','command-code','opencode','npm'):
            app=b.decorate(b.App(name,name,'1','Manual'),{})
            self.assertTrue(Path(app.icon).is_file(),app.icon)

    def test_brand_files_match_official_download_hashes(self):
        import hashlib
        data=json.loads((b.ROOT/'assets/brands/sources.json').read_text())
        for entry in data:
            path=b.ROOT/'assets/brands'/entry['file']
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),entry['sha256'])


if __name__=='__main__':
    unittest.main()
