#!/usr/bin/python3
"""Build a portable source archive and an architecture-independent Debian package."""
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.search(r"VERSION = '([^']+)'", (ROOT/'sweepdesk.py').read_text()).group(1)
DIST = ROOT/'dist'
PAYLOAD = ['sweepdesk.py','backend.py','python_probe.py','preferences.py','styles.py','ui_icons.py','README.md','README.id.md','LICENSE','THIRD_PARTY_NOTICES.md','assets','docs']


def main():
    DIST.mkdir(exist_ok=True)
    archive = DIST/f'sweepdesk-{VERSION}.tar.gz'
    ignored = {'.git','.work','dist','__pycache__','.venv'}
    with tarfile.open(archive, 'w:gz') as out:
        for path in sorted(ROOT.rglob('*')):
            relative = path.relative_to(ROOT)
            if not path.is_file() or any(part in ignored for part in relative.parts):
                continue
            if path.name.endswith(('.pyc','.log','.pid')) or path.name in ('local-preview.png','SweepDesk.desktop'):
                continue
            out.add(path, arcname=str(Path(f'sweepdesk-{VERSION}')/relative), recursive=False)
    artifacts = [archive]
    if shutil.which('dpkg-deb'):
        with tempfile.TemporaryDirectory(prefix='build-', dir=DIST) as temporary:
            stage = Path(temporary)
            app = stage/'usr/share/sweepdesk'
            app.mkdir(parents=True)
            for name in PAYLOAD:
                source = ROOT/name
                if source.is_dir():
                    shutil.copytree(source, app/name, ignore=shutil.ignore_patterns('local-preview.png'))
                else:
                    shutil.copy2(source, app/name)
            binary = stage/'usr/bin/sweepdesk'
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/share/sweepdesk/sweepdesk.py "$@"\n')
            binary.chmod(0o755)
            desktop = stage/'usr/share/applications'
            desktop.mkdir(parents=True)
            shutil.copy2(ROOT/'sweepdesk.desktop',desktop/'io.github.Zwart04.SweepDesk.desktop')
            icons = stage/'usr/share/icons/hicolor/scalable/apps'
            icons.mkdir(parents=True)
            shutil.copy2(ROOT/'assets/sweepdesk.svg',icons/'io.github.Zwart04.SweepDesk.svg')
            raster = ROOT/'assets/icons/hicolor'
            if raster.is_dir():
                shutil.copytree(raster,stage/'usr/share/icons/hicolor',dirs_exist_ok=True)
            docs = stage/'usr/share/doc/sweepdesk'
            docs.mkdir(parents=True)
            shutil.copy2(ROOT/'LICENSE',docs/'copyright')
            control = stage/'DEBIAN'
            control.mkdir()
            size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())//1024+1
            (control/'control').write_text(
                f'Package: sweepdesk\nVersion: {VERSION}\nArchitecture: all\nSection: admin\nPriority: optional\n'
                'Maintainer: Zwart04 <48742395+Zwart04@users.noreply.github.com>\n'
                f'Installed-Size: {size}\nDepends: python3 (>= 3.9), python3-gi, gir1.2-gtk-3.0, librsvg2-common, pkexec | policykit-1\n'
                'Homepage: https://github.com/Zwart04/sweepdesk\n'
                'Description: Native software inventory and reviewed uninstall for Debian and Ubuntu\n'
                ' View APT, npm, pip, Cargo, Flatpak and other software sources in a dark GTK interface.\n'
                ' Review removal plans and optionally clean known user data while keeping shared dependencies.\n')
            checks = []
            for path in sorted((stage/'usr').rglob('*')):
                if path.is_file():
                    checks.append(hashlib.md5(path.read_bytes()).hexdigest()+'  '+str(path.relative_to(stage)))
            (control/'md5sums').write_text('\n'.join(checks)+'\n')
            deb = DIST/f'sweepdesk_{VERSION}_all.deb'
            subprocess.run(['dpkg-deb','--root-owner-group','--build',str(stage),str(deb)],check=True)
            artifacts.append(deb)
    (DIST/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts))
    for p in artifacts:
        print(p)


if __name__ == '__main__':
    main()
