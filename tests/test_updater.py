import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import updater as u


class UpdateTests(unittest.TestCase):
    def fixture(self):
        content=b'fixture package, never executed'
        name='sweepdesk_0.6.0_all.deb';digest=hashlib.sha256(content).hexdigest()
        assets=[{'name':name,'browser_download_url':u.PREFIX+'v0.6.0/'+name,'size':len(content),'digest':'sha256:'+digest},
                {'name':'SHA256SUMS','browser_download_url':u.PREFIX+'v0.6.0/SHA256SUMS','size':100}]
        return {'tag_name':'v0.6.0','draft':False,'prerelease':False,'assets':assets,'body':'Fixture release'},content,digest,name

    def test_stable_newer_release_only_and_pinned_repository(self):
        metadata,_,_,_=self.fixture()
        metadata['assets'].append({'name':'evil.deb','browser_download_url':'https://example.com/evil.deb','size':100})
        with patch.object(u,'read_url',return_value=json.dumps(metadata).encode()):
            release=u.check('0.5.0')
            self.assertEqual(release.version,'0.6.0')
            self.assertEqual(len(release.assets),2)
            self.assertIsNone(u.check('0.6.0'))
            self.assertIsNone(u.check('0.7.0'))
        metadata['prerelease']=True
        with patch.object(u,'read_url',return_value=json.dumps(metadata).encode()): self.assertIsNone(u.check('0.5.0'))

    def test_platform_package_and_native_install_commands(self):
        for system,suffix,manager in [('deb','_all.deb','apt-get'),('rpm','.fedora.noarch.rpm','dnf'),('suse','.opensuse.noarch.rpm','zypper'),('arch','-any.pkg.tar.zst','pacman')]:
            self.assertTrue(u.package_name('0.6.0',system).endswith(suffix))
            with patch.object(u.Path,'is_file',return_value=True),patch.object(u.native_packages,'immutable_system',return_value=False):
                command=u.install_command('/tmp/fixture-package',system)
                self.assertEqual(command[:2],['/usr/bin/pkexec','/usr/bin/'+manager])
                self.assertNotIn('--nodeps',command)
                self.assertNotIn('--nogpgcheck',command)
        self.assertEqual(u.package_name('0.6.0','other'),'')

    def test_download_requires_matching_size_checksum_and_digest(self):
        metadata,content,digest,name=self.fixture()
        with patch.object(u,'read_url',return_value=json.dumps(metadata).encode()): release=u.check('0.5.0')
        def read(url,limit=0): return (digest+'  '+name+'\n').encode() if url.endswith('SHA256SUMS') else content
        with patch.object(u,'read_url',side_effect=read):
            directory,path=u.download(release,'deb')
            try: self.assertEqual(path.read_bytes(),content)
            finally: directory.cleanup()
            self.assertFalse(path.exists())
        def corrupt(url,limit=0): return (digest+'  '+name+'\n').encode() if url.endswith('SHA256SUMS') else b'corrupt'
        with patch.object(u,'read_url',side_effect=corrupt):
            with self.assertRaisesRegex(RuntimeError,'verification failed'): u.download(release,'deb')
        bad=u.Release('0.6.0',tuple(a for a in release.assets if a['name']!='SHA256SUMS'))
        with self.assertRaisesRegex(RuntimeError,'SHA256SUMS'): u.download(bad,'deb')

    def test_download_never_accepts_plain_http_or_unexpected_hosts(self):
        for url in ('http://github.com/file','https://evil.example/file','https://github.com.evil.example/file','https://user:password@github.com/file'):
            with self.assertRaises(RuntimeError): u.validate_url(url)
        with patch.object(u.native_packages,'immutable_system',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'immutable'): u.install_command('/tmp/fixture','rpm')

    def test_privileged_updater_ignores_user_path_overrides(self):
        with patch.object(u.shutil,'which',return_value='/home/untrusted/fake-manager'),patch.object(u.Path,'is_file',return_value=True),patch.object(u.native_packages,'immutable_system',return_value=False):
            command=u.install_command('/tmp/fixture','deb')
            self.assertEqual(command[:2],['/usr/bin/pkexec','/usr/bin/apt-get'])
