#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Run UI checks and native install/remove fixtures inside a disposable CI container only."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import backend
import native_packages as native

if os.environ.get('SWEEPDESK_DISPOSABLE_CI')!='1' or not Path('/.dockerenv').exists():
    raise SystemExit('This fixture runner is restricted to disposable CI containers.')

xvfb=subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','1280x900x24','-nolisten','tcp'],stdout=subprocess.PIPE,text=True)
display=xvfb.stdout.readline().strip()
if not display.isdigit(): raise SystemExit('Xvfb did not start')
os.environ['DISPLAY']=':'+display
system=native.family()
try:
    subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],check=True)
    subprocess.run(['desktop-file-validate','sweepdesk.desktop'],check=True)
    if system in ('rpm','suse'):
        flavor='opensuse' if system=='suse' else 'fedora'
        subprocess.run([sys.executable,'scripts/build.py','--format','rpm','--rpm-flavor',flavor],check=True)
        package=next((ROOT/'dist').glob('*.rpm'))
        subprocess.run(['rpm','-Uvh',str(package)],check=True)
        loader=native.rpm_inventory
        subprocess.run((['zypper','--non-interactive','install','tree'] if system=='suse' else ['dnf','-y','install','tree']),check=True)
    elif system=='arch':
        subprocess.run(['useradd','-m','builder'],check=True)
        (ROOT/'dist').mkdir(exist_ok=True)
        subprocess.run(['chown','-R','builder:builder',str(ROOT/'dist')],check=True)
        subprocess.run(['su','-s','/bin/sh','builder','-c','cd /workspace && python3 scripts/build.py --format arch'],check=True)
        package=next((ROOT/'dist').glob('*.pkg.tar.zst'))
        subprocess.run(['pacman','-U','--noconfirm',str(package)],check=True)
        subprocess.run(['pacman','-S','--noconfirm','tree'],check=True)
        loader=native.pacman_inventory
    elif system=='alpine':
        subprocess.run(['apk','add','tree'],check=True)
        loader=native.apk_inventory
        subprocess.run(['adduser','-D','builder'],check=True)
        subprocess.run(['su','-s','/bin/sh','builder','-c','cd /workspace && python3 install.py'],check=True)
    else: raise SystemExit('Unexpected CI system')
    # Only the deliberately installed tree fixture is removed; never host/user packages.
    installed=loader()
    fixture=next(a for a in installed if (a.location if a.source=='RPM' else a.package)=='tree')
    plan=backend.make_plan(fixture)
    if plan.removed!=[fixture.package] or plan.extra: raise RuntimeError('Fixture preview exceeded its expected single package.')
    native.revalidate(plan)
    subprocess.run(plan.commands[0][1:],check=True)  # CI is already root; no polkit agent in containers.
    assert not any((a.location if a.source=='RPM' else a.package)=='tree' for a in loader())
    if system!='alpine':
        subprocess.run(['/usr/bin/sweepdesk','--version'],check=True)
        print('Native package installed, dependencies satisfied, launcher runnable, removal fixture passed.')
    else: print('Alpine user installation and APK removal fixture passed.')
finally:
    xvfb.terminate();xvfb.wait()
