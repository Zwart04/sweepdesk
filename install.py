#!/usr/bin/python3
"""Install SweepDesk for the current user; never writes into a system prefix."""
import argparse
import os
from pathlib import Path
import shlex
import shutil
import sys

ROOT = Path(__file__).resolve().parent
MARKER = '.sweepdesk-install'


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
    if wrapper.exists() and '# Managed by SweepDesk' not in wrapper.read_text():
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
    try:
        import gi
        gi.require_version('Gtk', '3.0')
    except (ImportError, ValueError):
        raise SystemExit('Install the GUI dependencies first:\n  sudo apt install python3-gi gir1.2-gtk-3.0')
    target.mkdir(parents=True, exist_ok=True)
    for name in ('sweepdesk.py', 'backend.py', 'python_probe.py', 'preferences.py', 'styles.py', 'ui_icons.py','i18n.py', 'README.md', 'README.id.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT/name, target/name)
    shutil.copytree(ROOT/'assets', target/'assets', dirs_exist_ok=True)
    shutil.copytree(ROOT/'docs', target/'docs', dirs_exist_ok=True, ignore=shutil.ignore_patterns('local-preview.png'))
    (target/MARKER).write_text('Managed per-user SweepDesk installation\n')
    wrapper.parent.mkdir(parents=True, exist_ok=True)
    wrapper.write_text('#!/bin/sh\n# Managed by SweepDesk\nexec /usr/bin/python3 '+shlex.quote(str(target/'sweepdesk.py'))+' "$@"\n')
    wrapper.chmod(0o755)
    desktop.parent.mkdir(parents=True, exist_ok=True)
    command = '"'+str(wrapper).replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('`','\\`')+'"'
    desktop.write_text('[Desktop Entry]\nType=Application\nName=SweepDesk\n'
                       'Comment=Software inventory and reviewed uninstall for Debian and Ubuntu\n'
                       'Exec='+command+'\nIcon='+str(target/'assets/sweepdesk.svg')+'\n'
                       'Terminal=false\nCategories=System;PackageManager;\nStartupNotify=true\nStartupWMClass=io.github.Zwart04.SweepDesk\nX-SweepDesk-Managed=true\n')
    print('SweepDesk installed. Open it from your application menu.\nCommand: '+str(wrapper))
    print('Support Zwart04: https://tako.id/Zwart04')


if __name__ == '__main__':
    main()
