#!/usr/bin/python3
"""Build portable, Debian, Fedora/openSUSE RPM, and Arch packages with native tools."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
VERSION=re.search(r"VERSION = '([^']+)'",(ROOT/'sweepdesk.py').read_text()).group(1)
DIST=ROOT/'dist'
PAYLOAD=['sweepdesk.py','backend.py','native_packages.py','updater.py','python_probe.py','preferences.py','styles.py','ui_icons.py','i18n.py','README.md','README.id.md','LICENSE','THIRD_PARTY_NOTICES.md','assets','docs']


def stage_payload(stage):
    app=stage/'usr/share/sweepdesk';app.mkdir(parents=True)
    for name in PAYLOAD:
        source=ROOT/name
        if source.is_dir(): shutil.copytree(source,app/name,ignore=shutil.ignore_patterns('local-preview.png'))
        else: shutil.copy2(source,app/name)
    binary=stage/'usr/bin/sweepdesk';binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/share/sweepdesk/sweepdesk.py "$@"\n');binary.chmod(0o755)
    desktop=stage/'usr/share/applications';desktop.mkdir(parents=True)
    shutil.copy2(ROOT/'sweepdesk.desktop',desktop/'io.github.Zwart04.SweepDesk.desktop')
    icons=stage/'usr/share/icons/hicolor/scalable/apps';icons.mkdir(parents=True)
    shutil.copy2(ROOT/'assets/sweepdesk.svg',icons/'io.github.Zwart04.SweepDesk.svg')
    shutil.copytree(ROOT/'assets/icons/hicolor',stage/'usr/share/icons/hicolor',dirs_exist_ok=True)
    docs=stage/'usr/share/licenses/sweepdesk';docs.mkdir(parents=True)
    shutil.copy2(ROOT/'LICENSE',docs/'LICENSE')


def portable():
    output=DIST/f'sweepdesk-{VERSION}.tar.gz'
    ignored={'.git','.work','dist','__pycache__','.venv'}
    with tarfile.open(output,'w:gz') as archive:
        for path in sorted(ROOT.rglob('*')):
            relative=path.relative_to(ROOT)
            if not path.is_file() or any(part in ignored for part in relative.parts): continue
            if path.name.endswith(('.pyc','.log','.pid')) or path.name in ('local-preview.png','SweepDesk.desktop'): continue
            archive.add(path,arcname=str(Path(f'sweepdesk-{VERSION}')/relative),recursive=False)
    return output


def deb():
    with tempfile.TemporaryDirectory(prefix='deb-',dir=DIST) as directory:
        stage=Path(directory);stage_payload(stage)
        docs=stage/'usr/share/doc/sweepdesk';docs.mkdir(parents=True)
        shutil.copy2(ROOT/'LICENSE',docs/'copyright')
        control=stage/'DEBIAN';control.mkdir()
        size=sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())//1024+1
        (control/'control').write_text(
            f'Package: sweepdesk\nVersion: {VERSION}\nArchitecture: all\nSection: admin\nPriority: optional\n'
            'Maintainer: Zwart04 <48742395+Zwart04@users.noreply.github.com>\n'
            f'Installed-Size: {size}\nDepends: python3 (>= 3.9), python3-gi, gir1.2-gtk-3.0, librsvg2-common, pkexec | policykit-1\n'
            'Homepage: https://zwart04.github.io/sweepdesk/\n'
            'Description: Native Linux software inventory and reviewed uninstall\n'
            ' Browse system packages, desktop apps, and CLI tools. Review removal plans\n'
            ' and optionally move known user data to Trash. Includes GitHub update checks.\n')
        (control/'md5sums').write_text(''.join(hashlib.md5(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(stage))+'\n' for p in sorted((stage/'usr').rglob('*')) if p.is_file()))
        output=DIST/f'sweepdesk_{VERSION}_all.deb'
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(output)],check=True)
        return output


def rpm(flavor):
    with tempfile.TemporaryDirectory(prefix='rpm-',dir=DIST) as directory:
        top=Path(directory).resolve()
        for name in ('BUILD','BUILDROOT','RPMS','SOURCES','SPECS','SRPMS'): (top/name).mkdir()
        payload=top/'payload';stage_payload(payload)
        requirements='python3 >= 3.9, python3-gobject, gtk3, '+('librsvg2, polkit' if flavor=='fedora' else 'typelib-1_0-Gtk-3_0, librsvg-2-2, polkit')
        spec=top/'SPECS/sweepdesk.spec'
        spec.write_text(f'''Name: sweepdesk
Version: {VERSION}
Release: 1.{flavor}
Summary: Native Linux software inventory and reviewed uninstall
License: MIT
URL: https://zwart04.github.io/sweepdesk/
BuildArch: noarch
Requires: {requirements}
AutoReqProv: no
%global debug_package %{{nil}}
%global __brp_python_bytecompile %{{nil}}
%description
Browse system packages, desktop apps, and CLI tools. Review removal plans,
optionally move known data to Trash, and check for new GitHub releases.
%prep
%build
%install
mkdir -p "%{{buildroot}}"
cp -a "{payload}/usr" "%{{buildroot}}/"
%files
/usr/bin/sweepdesk
/usr/share/sweepdesk
/usr/share/applications/io.github.Zwart04.SweepDesk.desktop
/usr/share/icons/hicolor/*/apps/io.github.Zwart04.SweepDesk.*
%license /usr/share/licenses/sweepdesk/LICENSE
''')
        subprocess.run(['rpmbuild','--define','_topdir '+str(top),'-bb',str(spec)],check=True)
        generated=next((top/'RPMS/noarch').glob('sweepdesk-*.rpm'))
        output=DIST/generated.name;shutil.copy2(generated,output)
        return output


def arch():
    with tempfile.TemporaryDirectory(prefix='arch-',dir=DIST) as directory:
        work=Path(directory).resolve();payload=work/'payload';stage_payload(payload)
        (work/'PKGBUILD').write_text(f'''pkgname=sweepdesk
pkgver={VERSION}
pkgrel=1
pkgdesc='Native Linux software inventory and reviewed uninstall'
arch=('any')
url='https://zwart04.github.io/sweepdesk/'
license=('MIT')
depends=('python' 'python-gobject' 'gtk3' 'librsvg' 'polkit')
options=('!strip' '!debug')
package() {{
  cp -a "$startdir/payload/usr" "$pkgdir/"
}}
''')
        subprocess.run(['makepkg','--nodeps','--noconfirm','--cleanbuild'],cwd=work,check=True)
        generated=next(work.glob('sweepdesk-*.pkg.tar.zst'))
        output=DIST/generated.name;shutil.copy2(generated,output)
        return output


def checksums():
    artifacts=sorted(p for p in DIST.iterdir() if p.is_file() and VERSION in p.name and p.name.endswith(('.deb','.rpm','.pkg.tar.zst','.tar.gz')))
    (DIST/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--format',choices=('auto','portable','deb','rpm','arch'),default='auto')
    parser.add_argument('--stage',type=Path,help='Stage the common payload for a native package build')
    parser.add_argument('--rpm-flavor',choices=('fedora','opensuse'),default='fedora')
    args=parser.parse_args()
    if args.stage:
        stage_payload(args.stage);return
    DIST.mkdir(exist_ok=True)
    outputs=[]
    if args.format in ('auto','portable'): outputs.append(portable())
    if args.format=='deb' or args.format=='auto' and shutil.which('dpkg-deb'): outputs.append(deb())
    if args.format=='rpm': outputs.append(rpm(args.rpm_flavor))
    if args.format=='arch': outputs.append(arch())
    checksums()
    for path in outputs: print(path)


if __name__=='__main__': main()
