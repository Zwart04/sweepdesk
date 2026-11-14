#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Install the Rust SweepDesk binary for the current user; never writes into a system prefix."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import shutil

ROOT = Path(__file__).resolve().parent
MARKER = '.sweepdesk-install'
BINARY = ROOT/'rust/target/release/sweepdesk'

def paths(prefix=None):
    base = Path(prefix).expanduser().absolute() if prefix else Path.home()/'.local'
    data = base/'share' if prefix else Path(os.environ.get('XDG_DATA_HOME', str(base/'share')))
    return data/'sweepdesk', base/'bin/sweepdesk', data/'applications/io.github.Zwart04.SweepDesk.desktop'

def main():
    parser = argparse.ArgumentParser(description='Install or remove the per-user SweepDesk launcher')
    parser.add_argument('--prefix', help='Install under this user-owned prefix (default: ~/.local)')
    parser.add_argument('--uninstall', action='store_true', help='Remove this per-user installation; keep the source folder')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit('Run this installer without sudo. For system-wide installation, install the .deb package instead.')
    target, wrapper, desktop = paths(args.prefix)
    if target.is_symlink() or wrapper.is_symlink() or desktop.is_symlink():
        raise SystemExit('An install destination is a symbolic link. Nothing was changed.')
    if target.exists() and not (target/MARKER).is_file():
        raise SystemExit('Destination exists and is not marked as a SweepDesk installation: '+str(target))
    if wrapper.exists() and str(target) not in wrapper.read_text() and '# Managed by SweepDesk' not in wrapper.read_text():
        raise SystemExit('A different command already exists at '+str(wrapper))
    if desktop.exists() and 'X-SweepDesk-Managed=true' not in desktop.read_text():
        raise SystemExit('A different launcher already exists at '+str(desktop))
    if args.uninstall:
        if not target.exists():
            print('No managed per-user installation found.')
            return
        shutil.rmtree(target)
        wrapper.unlink(missing_ok=True)
        desktop.unlink(missing_ok=True)
        print('SweepDesk uninstalled. The source folder and other applications were kept.')
        return
    if shutil.which('cargo') is None:
        raise SystemExit('Install Rust (cargo) to build SweepDesk, or use the packaged build from the releases page.')
    subprocess.run(['cargo', 'build', '--release', '--locked'], cwd=ROOT/'rust', check=True)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BINARY, target/'sweepdesk')
    (target/'sweepdesk').chmod(0o755)
    for name in ('README.md', 'README.id.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name, target/name)
    shutil.copytree(ROOT/'assets', target/'assets', dirs_exist_ok=True)
    (target/MARKER).write_text('Managed per-user SweepDesk installation\n')
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\n# Managed by SweepDesk\nexec '+str(target/'sweepdesk')+' "$@"\n')
    wrapper.chmod(0o755)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text('[Desktop Entry]\nType=Application\nName=SweepDesk\n'
                       'Comment=Software inventory and reviewed uninstall for Linux desktops\n'
                       'Exec='+str(wrapper)+'\nIcon='+str(target/'assets/sweepdesk.png')+'\n'
                       'Terminal=false\nCategories=System;PackageManager;\nStartupNotify=true\nStartupWMClass=io.github.Zwart04.SweepDesk\nX-SweepDesk-Managed=true\n')
    print('SweepDesk installed. Open it from your application menu.\nCommand: '+str(wrapper))
    print('Support Zwart04: https://tako.id/Zwart04')

if __name__ == '__main__':
    main()
