"""Public, pinned GitHub release checks and checksum-verified native updates."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlparse
from urllib.request import Request,build_opener,HTTPRedirectHandler

import native_packages

REPOSITORY='Zwart04/sweepdesk'
API='https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
RELEASES='https://github.com/'+REPOSITORY+'/releases/latest'
PREFIX='https://github.com/'+REPOSITORY+'/releases/download/'
HOSTS={'api.github.com','github.com','objects.githubusercontent.com','release-assets.githubusercontent.com'}


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,url):
        validate_url(url)
        return super().redirect_request(request,fp,code,msg,headers,url)


def validate_url(url):
    parsed=urlparse(url)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.port not in (None,443):
        raise RuntimeError('Unexpected update download destination.')


def read_url(url,limit=2*1024*1024):
    validate_url(url)
    request=Request(url,headers={'User-Agent':'SweepDesk-Updater','Accept':'application/vnd.github+json' if url==API else 'application/octet-stream'})
    with build_opener(SafeRedirect()).open(request,timeout=30) as response:
        validate_url(response.geturl())
        content=response.read(limit+1)
    if len(content)>limit: raise RuntimeError('Update response is too large.')
    return content


def version_tuple(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d+\.\d+\.\d+',value): raise RuntimeError('Unsupported release version.')
    return tuple(map(int,value.split('.')))


@dataclass(frozen=True)
class Release:
    version: str
    assets: tuple
    notes: str = ''

    @property
    def url(self): return 'https://github.com/'+REPOSITORY+'/releases/tag/v'+self.version


def check(current):
    current_version=version_tuple(current)
    data=json.loads(read_url(API))
    if not isinstance(data,dict) or data.get('draft') or data.get('prerelease'): return None
    version=str(data.get('tag_name','')).removeprefix('v')
    if version_tuple(version)<=current_version: return None
    assets=[]
    for asset in data.get('assets',[]):
        if not isinstance(asset,dict): continue
        name=asset.get('name','');url=asset.get('browser_download_url','');size=asset.get('size',0)
        if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.+-]+',name) and url==PREFIX+'v'+version+'/'+name and isinstance(size,int) and 0<size<=128*1024*1024:
            assets.append({'name':name,'url':url,'size':size,'digest':asset.get('digest','')})
    return Release(version,tuple(assets),str(data.get('body',''))[:12000])


def package_name(version,system=None):
    system=system or native_packages.family()
    names={'deb':f'sweepdesk_{version}_all.deb','rpm':f'sweepdesk-{version}-1.fedora.noarch.rpm',
           'suse':f'sweepdesk-{version}-1.opensuse.noarch.rpm','arch':f'sweepdesk-{version}-1-any.pkg.tar.zst'}
    return names.get(system,'')


def install_command(path,system=None):
    system=system or native_packages.family()
    if native_packages.immutable_system(): raise RuntimeError('System packages on immutable desktops are inventory-only. Use the distribution system updater.')
    manager={'deb':'apt-get','rpm':'dnf','suse':'zypper','arch':'pacman'}.get(system)
    binary=shutil.which(manager) if manager else None
    pkexec=shutil.which('pkexec')
    if not binary or not pkexec: raise RuntimeError('No supported native updater is available. Download the release manually.')
    path=str(Path(path).absolute())
    args={'deb':['-y','install',path],'rpm':['-y','install',path],
          'suse':['--non-interactive','install',path],'arch':['-U','--noconfirm','--',path]}[system]
    return [pkexec,binary,*args]


def packaged_install(root):
    # A checkout or managed per-user source installation must not silently become a system install.
    return Path(root).resolve()==Path('/usr/share/sweepdesk').resolve()


def download(release,system=None):
    name=package_name(release.version,system)
    asset=next((a for a in release.assets if a['name']==name),None)
    if not asset: raise RuntimeError('This release has no compatible native package. Open the release page.')
    checksum=next((a for a in release.assets if a['name']=='SHA256SUMS'),None)
    if not checksum: raise RuntimeError('The release has no SHA256SUMS file.')
    entries={}
    for line in read_url(checksum['url'],65536).decode('utf-8').splitlines():
        match=re.fullmatch(r'([a-fA-F0-9]{64})  ([A-Za-z0-9_.+-]+)',line)
        if match:
            digest,filename=match.groups()
            if filename in entries: raise RuntimeError('Duplicate update checksum entry.')
            entries[filename]=digest.lower()
    expected=entries.get(name)
    if not expected: raise RuntimeError('The update checksum is missing.')
    if asset['digest'] and asset['digest']!='sha256:'+expected: raise RuntimeError('GitHub asset digest does not match SHA256SUMS.')
    content=read_url(asset['url'],128*1024*1024)
    if len(content)!=asset['size'] or hashlib.sha256(content).hexdigest()!=expected: raise RuntimeError('Update checksum verification failed. Nothing was installed.')
    directory=tempfile.TemporaryDirectory(prefix='sweepdesk-update-')
    path=Path(directory.name)/name
    path.write_bytes(content)
    path.chmod(0o600)
    return directory,path
