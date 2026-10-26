# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
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
    def test_disabled_sources_do_not_run_package_managers(self):
        with patch.object(b,'run') as run, patch.object(b,'desktop_index',return_value={}):
            apps,warnings=b.scan(enabled_sources=[])
        self.assertEqual(apps,[])
        self.assertEqual(warnings,[])
        run.assert_not_called()
    def test_independent_sources_overlap_and_failures_are_isolated(self):
        import threading
        barrier=threading.Barrier(2,timeout=5)
        def loader(name):
            barrier.wait()
            return [b.App(name,name,'1',name)]
        with patch.object(b.native_packages,'family',return_value='deb'), \
             patch.object(b.shutil,'which',return_value='/manager'),patch.object(b,'npm_locations',return_value=['/npm']), \
             patch.object(b,'apt_inventory',side_effect=lambda:loader('APT')), \
             patch.object(b,'npm_inventory',side_effect=lambda:loader('npm')), \
             patch.object(b,'cargo_inventory',side_effect=RuntimeError('fixture failure')), \
             patch.object(b,'executable',return_value='/cargo'),patch.object(b,'desktop_index',return_value={}):
            apps,warnings=b.scan(enabled_sources=['APT','npm','Cargo'])
        self.assertEqual({a.source for a in apps},{'APT','npm'})
        self.assertEqual(warnings,['Cargo: fixture failure'])

    def test_disabled_source_discovery_is_skipped(self):
        with patch.object(b,'npm_locations',side_effect=AssertionError('disabled npm discovery')), \
             patch.object(b,'python_locations',side_effect=AssertionError('disabled Python discovery')), \
             patch.object(b,'desktop_index',return_value={}):
            self.assertEqual(b.scan(enabled_sources=[]),([],[]))

    def test_manual_batch_ownership_keeps_native_packages_out(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            home=Path(directory);folder=home/'.local/bin';folder.mkdir(parents=True)
            owned=folder/'owned';free=folder/'free';target=home/'owned-target';link=folder/'linked'
            for p in [owned,free,target]: p.write_text('fixture');p.chmod(0o700)
            link.symlink_to(target)
            def query(args,**kwargs):
                self.assertEqual(args[:3],['/usr/bin/dpkg-query','-S','--'])
                return 'native-package: '+str(owned)+'\nnative-package: '+str(target)+'\n'
            with patch.object(b,'HOME',home),patch.object(b.native_packages,'family',return_value='deb'), \
                 patch.object(b.shutil,'which',side_effect=lambda name:'/usr/bin/dpkg-query' if name=='dpkg-query' else None), \
                 patch.object(b.os,'access',side_effect=lambda p,mode:Path(p).is_relative_to(home)), \
                 patch.object(b,'run',side_effect=query) as run, \
                 patch.object(b,'package_owner',side_effect=AssertionError('unexpected individual lookup')):
                apps=b.manual_inventory([])
            self.assertEqual([a.package for a in apps],['free'])
            self.assertEqual(run.call_count,1)

    def test_python_probe_accepts_legacy_zip_metadata(self):
        import python_probe
        class ArchivePath:
            def __str__(self): return '/venv/share/vendor.whl/vendor.dist-info'
        class Distribution:
            metadata={'Name':'vendor'}
            version='1'
            requires=[]
            _path=ArchivePath()
            def locate_file(self,path): return ArchivePath()
            def read_text(self,name): return None
        with patch.object(python_probe.metadata,'distributions',return_value=[Distribution()]):
            report=python_probe.probe()
        self.assertTrue(report['packages'][0]['archived'])
        self.assertFalse(report['packages'][0]['recorded'])

    def test_apt_metadata_uses_real_version_field(self):
        def query(args, **kwargs):
            if 'dpkg-query' in args[0]:
                self.assertIn('${Version}',args[-1])
                return 'curl\t8.0\t20\tno\toptional\tii \tTransfer tool\n'
            return ''
        with patch.object(b,'run',side_effect=query):
            apps=b.apt_inventory()
        self.assertEqual(apps[0].version,'8.0')

    def test_bun_detects_custom_global_directory(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'Custom global'
            folder.mkdir()
            (folder/'package.json').write_text(json.dumps({'dependencies':{'demo':'1'}}))
            with patch.object(b,'executable',return_value='/bun'), \
                 patch.object(b,'run',return_value=str(folder)+' node_modules (1 installed)\n'):
                apps=b.bun_inventory()
            self.assertEqual(apps[0].scope,str(folder))

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

    def test_python_probe_deduplicates_lib64_aliases_but_keeps_real_overlaps(self):
        import python_probe
        import tempfile
        from pathlib import Path
        class Distribution:
            metadata={'Name':'fixture'}
            version='1.0'
            requires=[]
            def __init__(self,path): self._path=path
            def locate_file(self,value): return self._path.parent
            def read_text(self,value): return 'pip' if value=='INSTALLER' else ''
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);real=root/'lib/fixture-1.0.dist-info';real.mkdir(parents=True)
            (root/'lib64').symlink_to(root/'lib',target_is_directory=True)
            entries=[Distribution(real),Distribution(root/'lib64/fixture-1.0.dist-info')]
            with patch.object(python_probe.metadata,'distributions',return_value=entries):
                self.assertEqual(len(python_probe.probe()['packages']),1)
            other=root/'other/fixture-1.0.dist-info';other.mkdir(parents=True)
            with patch.object(python_probe.metadata,'distributions',return_value=[Distribution(real),Distribution(other)]):
                self.assertEqual(len(python_probe.probe()['packages']),2)


if __name__=='__main__':
    unittest.main()
