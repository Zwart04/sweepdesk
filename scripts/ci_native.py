#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Build, install, and smoke-run the native package inside a disposable CI container only."""
from pathlib import Path
import os
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
FAMILY=os.environ.get('FAMILY','')

if os.environ.get('SWEEPDESK_DISPOSABLE_CI')!='1' or not Path('/.dockerenv').exists():
    raise SystemExit('This fixture runner is restricted to disposable CI containers.')
if FAMILY not in ('fedora','suse','arch'):
    raise SystemExit('Unexpected CI system: '+FAMILY)

if FAMILY in ('fedora','suse'):
    flavor='opensuse' if FAMILY=='suse' else 'fedora'
    subprocess.run([sys.executable,'scripts/build.py','--format','rpm','--rpm-flavor',flavor],check=True)
    package=next((ROOT/'dist').glob('*.rpm'))
    # Built seconds earlier in this disposable container, so it carries no signature.
    subprocess.run(['rpm','-Uvh','--nosignature',str(package)],check=True)
else:
    subprocess.run(['useradd','-m','builder'],check=True)
    (ROOT/'dist').mkdir(exist_ok=True)
    subprocess.run(['chown','-R','builder:builder',str(ROOT/'dist')],check=True)
    subprocess.run(['su','-s','/bin/sh','builder','-c','cd /workspace && python3 scripts/build.py --format arch'],check=True)
    package=next((ROOT/'dist').glob('*.pkg.tar.zst'))
    subprocess.run(['pacman','-U','--noconfirm',str(package)],check=True)

if not Path('/usr/bin/sweepdesk').is_file():
    raise SystemExit('The package did not install /usr/bin/sweepdesk')
subprocess.run(['useradd','-m','runner'],check=True)
report=subprocess.run(['su','-s','/bin/sh','runner','-c','/usr/bin/sweepdesk --scan'],check=True,capture_output=True,text=True).stdout
line=report.splitlines()[0] if report else ''
count=int(line.split()[0]) if line and line.split()[0].isdigit() else 0
if count<1:
    raise SystemExit('Inventory scan returned no applications: '+report)
print('Installed package scan:',line)
