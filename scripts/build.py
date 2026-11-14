#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Build the portable tarball plus Debian, RPM, and Arch packages from the Rust binary."""
import argparse
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT=Path(__file__).resolve().parents[1]
VERSION=re.search(r'^version = "([^"]+)"',(ROOT/'rust/Cargo.toml').read_text(),re.M).group(1)
DIST=ROOT/'dist'
TARGET=ROOT/'rust/target/release'
DESKTOP='io.github.Zwart04.SweepDesk.desktop'


def build_binary():
    subprocess.run(['cargo','build','--release','--locked'],cwd=ROOT/'rust',check=True)
    binary=TARGET/'sweepdesk'
    if not binary.is_file():
        raise SystemExit('cargo did not produce '+str(binary))
    return binary


def stage_payload(stage):
    for name in ('usr/bin','usr/share/applications','usr/share/licenses/sweepdesk'):
        (stage/name).mkdir(parents=True,exist_ok=True)
    binary=build_binary()
    shutil.copy2(binary,stage/'usr/bin/sweepdesk')
    (stage/'usr/bin/sweepdesk').chmod(0o755)
    shutil.copy2(ROOT/'sweepdesk.desktop',stage/'usr/share/applications'/DESKTOP)
    shutil.copytree(ROOT/'assets/icons/hicolor',stage/'usr/share/icons/hicolor',dirs_exist_ok=True)
    shutil.copy2(ROOT/'LICENSE',stage/'usr/share/licenses/sweepdesk/LICENSE')


def portable():
    output=DIST/f'sweepdesk-{VERSION}-x86_64.tar.gz'
    binary=build_binary()
    top=f'sweepdesk-{VERSION}'
    with tempfile.TemporaryDirectory(prefix='portable-',dir=DIST) as directory:
        stage=Path(directory)/top
        stage.mkdir(parents=True)
        shutil.copy2(binary,stage/'sweepdesk')
        (stage/'sweepdesk').chmod(0o755)
        for name in ('sweepdesk.desktop','LICENSE','README.md','README.id.md','THIRD_PARTY_NOTICES.md'):
            if (ROOT/name).is_file(): shutil.copy2(ROOT/name,stage/name)
        for name in ('assets','docs'):
            shutil.copytree(ROOT/name,stage/name,ignore=shutil.ignore_patterns('local-preview.png'))
        with tarfile.open(output,'w:gz') as archive:
            archive.add(stage,arcname=top)
    return output


def deb():
    with tempfile.TemporaryDirectory(prefix='deb-',dir=DIST) as directory:
        stage=Path(directory);stage.chmod(0o755);stage_payload(stage)
        docs=stage/'usr/share/doc/sweepdesk';docs.mkdir(parents=True)
        shutil.copy2(ROOT/'LICENSE',docs/'copyright')
        control=stage/'DEBIAN';control.mkdir()
        size=sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())//1024+1
        (control/'control').write_text(
            f'Package: sweepdesk\nVersion: {VERSION}\nArchitecture: amd64\nSection: admin\nPriority: optional\n'
            'Maintainer: Zwart04 <48742395+Zwart04@users.noreply.github.com>\n'
            f'Installed-Size: {size}\nDepends: libc6 (>= 2.28), pkexec | policykit-1\n'
            'Homepage: https://zwart04.github.io/sweepdesk/\n'
            'Description: Native Linux software inventory and reviewed uninstall\n'
            ' Browse system packages, desktop apps, and CLI tools. Review removal plans\n'
            ' and optionally move known user data to Trash. Includes GitHub update checks.\n')
        (control/'md5sums').write_text(''.join(hashlib.md5(p.read_bytes()).hexdigest()+'  '+str(p.relative_to(stage))+'\n' for p in sorted((stage/'usr').rglob('*')) if p.is_file()))
        output=DIST/f'sweepdesk_{VERSION}_amd64.deb'
        subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(output)],check=True)
        return output


def rpm(flavor):
    with tempfile.TemporaryDirectory(prefix='rpm-',dir=DIST) as directory:
        top=Path(directory).resolve()
        for name in ('BUILD','BUILDROOT','RPMS','SOURCES','SPECS','SRPMS'): (top/name).mkdir()
        payload=top/'payload';stage_payload(payload)
        spec=top/'SPECS/sweepdesk.spec'
        spec.write_text(f'''Name: sweepdesk
Version: {VERSION}
Release: 1.{flavor}
Summary: Native Linux software inventory and reviewed uninstall
License: GPL-3.0-or-later
URL: https://zwart04.github.io/sweepdesk/
BuildArch: x86_64
Requires: glibc, polkit
AutoReqProv: no
%global debug_package %{{nil}}
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
/usr/share/applications/{DESKTOP}
/usr/share/icons/hicolor/*/apps/io.github.Zwart04.SweepDesk.png
%license /usr/share/licenses/sweepdesk/LICENSE
''')
        subprocess.run(['rpmbuild','--define','_topdir '+str(top),'-bb',str(spec)],check=True)
        generated=next((top/'RPMS/x86_64').glob('sweepdesk-*.rpm'))
        output=DIST/generated.name;shutil.copy2(generated,output)
        return output


def arch():
    with tempfile.TemporaryDirectory(prefix='arch-',dir=DIST) as directory:
        work=Path(directory).resolve();payload=work/'payload';stage_payload(payload)
        (work/'PKGBUILD').write_text(f'''pkgname=sweepdesk
pkgver={VERSION}
pkgrel=1
pkgdesc='Native Linux software inventory and reviewed uninstall'
arch=('x86_64')
url='https://zwart04.github.io/sweepdesk/'
license=('GPL-3.0-or-later')
depends=('glibc' 'polkit')
options=('strip' '!debug')
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
