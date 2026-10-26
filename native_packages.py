"""Conservative native inventory/removal for RPM, libalpm, and APK systems.

RPM removes exactly the selected NEVRA, retaining dependency checks and config backups.
Pacman/APK use native read-only transaction previews and recheck before execution.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil

SOURCES = ('RPM', 'Pacman', 'APK')
CRITICAL = {
    'rpm','rpm-libs','dnf','dnf5','libdnf','libdnf5','yum','zypper','libzypp',
    'pacman','apk-tools','alpine-base','alpine-baselayout','alpine-keys','base','filesystem',
    'glibc','musl','busybox','bash','coreutils','systemd','systemd-libs','systemd-sysv',
    'openrc','udev','eudev','elogind','dbus','dbus-broker','sudo','polkit','polkit-gnome',
    'python3','python','python3-gobject','python-gobject','py3-gobject3','gtk3','gtk+3.0',
    'NetworkManager','networkmanager','network-manager','network-manager-applet',
    'gnome-shell','gnome-session','plasma-desktop','plasma-workspace','kwin',
    'xfce4-session','xfce4-panel','xfwm4','cinnamon','cinnamon-session','mate-session-manager',
    'mate-panel','lxqt-session','lxsession','gdm','sddm','lightdm','xorg-server','xorg-x11-server-Xorg',
    'grub','grub2','grub2-common','grub2-tools','dracut','mkinitcpio','sweepdesk',
}
CORE_FILES = ('/usr/bin/python3','/usr/bin/pkexec','/usr/bin/sh','/usr/bin/bash',
              '/usr/lib/systemd/systemd','/sbin/init','/lib/ld-musl-x86_64.so.1')


def family(info=None):
    if info is None:
        info={}
        try:
            import shlex
            for line in Path('/etc/os-release').read_text().splitlines():
                if '=' in line:
                    key,value=line.split('=',1);tokens=shlex.split(value)
                    info[key]=tokens[0] if tokens else ''
        except (OSError,ValueError):
            pass
    ids={info.get('ID',''),*info.get('ID_LIKE','').split()}
    if ids & {'debian','ubuntu','linuxmint','pop','kali','raspbian'}: return 'deb'
    if ids & {'arch','manjaro','endeavouros','garuda','cachyos'}: return 'arch'
    if ids & {'opensuse','opensuse-tumbleweed','opensuse-leap','suse','sles','sled'}: return 'suse'
    if ids & {'fedora','rhel','centos','rocky','almalinux','ol','nobara'}: return 'rpm'
    if 'alpine' in ids: return 'alpine'
    return 'other'


def immutable_system():
    return Path('/run/ostree-booted').exists() or Path('/run/current-system/nixos-version').exists() or Path('/etc/steamos-release').exists() or bool(shutil.which('transactional-update'))


def is_critical(name):
    return name in CRITICAL or bool(re.match(r'^(kernel(?:-|$)|linux(?:-|$)|glibc(?:-|$)|musl(?:-|$)|systemd(?:-|$)|grub2?(?:-|$))',name))


def owner(path, source):
    from backend import run
    manager={'RPM':'rpm','Pacman':'pacman','APK':'apk'}[source]
    if not shutil.which(manager): return ''
    args={'RPM':['rpm','-qf','--qf','%{NAME}\n',str(path)],
          'Pacman':['pacman','-Qoq','--',str(path)],'APK':['apk','info','--who-owns',str(path)]}[source]
    output=run(args,check=False).strip()
    if source=='APK':
        match=re.search(r' is owned by (.+)-[^-]+-r\d+$',output)
        return match.group(1) if match else ''
    return output.splitlines()[0] if output and not re.search(r'not owned|No package|error:',output,re.I) else ''


def protected_owners(source):
    return {name for path in CORE_FILES if Path(path).exists() for name in [owner(path,source)] if name}


def finish(apps, source):
    protected=protected_owners(source)
    frozen=immutable_system()
    for app in apps:
        app.essential=is_critical(app.name) or app.name in protected
        if frozen: app.readonly_reason='System packages on immutable desktops are inventory-only. Use the distribution system updater.'
    return apps


RPM_FORMAT='%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\t%{SIZE}\t%{SUMMARY}\t%{NAME}-%{VERSION}-%{RELEASE}.%{ARCH}\n'


def looks_like_support(name):
    return is_critical(name) or name.startswith(('lib','python3-','python-','perl-','ruby-','typelib-','fonts-','font-','gstreamer-')) or name.endswith(('-libs','-common','-data','-devel','-doc','-lang','-debuginfo'))


def rpm_inventory():
    from backend import App,run
    apps=[]
    for line in run(['rpm','-qa','--qf',RPM_FORMAT]).splitlines():
        parts=line.split('\t',5)
        if len(parts)!=6: continue
        name,version,arch,size,description,identity=parts
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.~-]*',identity): continue
        apps.append(App(name,identity,version,'RPM',description,'package-x-generic',
                        size=int(size) if size.isdigit() else 0,support=looks_like_support(name),manager=shutil.which('rpm') or '/usr/bin/rpm',scope=arch,location=name))
    return finish(apps,'RPM')


def parse_desc(text):
    fields={};current=None
    for line in text.splitlines():
        if line.startswith('%') and line.endswith('%'):
            current=line.strip('%');fields[current]=[]
        elif line and current: fields[current].append(line)
    return fields


def pacman_inventory(database=Path('/var/lib/pacman/local')):
    from backend import App
    apps=[]
    for path in sorted(database.glob('*/desc')):
        fields=parse_desc(path.read_text())
        if not fields.get('NAME') or not fields.get('VERSION'): continue
        get=lambda key,default='':fields.get(key,[default])[0]
        name=get('NAME');size=get('ISIZE','0')
        apps.append(App(name,name,get('VERSION'),'Pacman',get('DESC'),'package-x-generic',
                        size=int(size) if size.isdigit() else 0,support=get('REASON','0')=='1' or is_critical(name),manager=shutil.which('pacman') or '/usr/bin/pacman',scope=get('ARCH'),location=str(path)))
    return finish(apps,'Pacman')


def apk_inventory(database=Path('/lib/apk/db/installed')):
    from backend import App
    apps=[]
    try: explicit={re.split(r'[<>=~@]',line)[0] for line in Path('/etc/apk/world').read_text().splitlines() if line and not line.startswith('#')}
    except OSError: explicit=set()
    for block in database.read_text().split('\n\n'):
        fields={}
        for line in block.splitlines():
            if len(line)>2 and line[1]==':' and line[0] in 'PVTIA': fields[line[0]]=line[2:]
        if 'P' not in fields or 'V' not in fields: continue
        name=fields['P'];size=fields.get('I','0')
        apps.append(App(name,name,fields['V'],'APK',fields.get('T',''),'package-x-generic',
                        size=int(size) if size.isdigit() else 0,support=name not in explicit or is_critical(name),manager=shutil.which('apk') or '/sbin/apk',scope=fields.get('A','')))
    return finish(apps,'APK')


def fingerprint(source):
    from backend import run
    if source=='RPM': text=run(['rpm','-qa','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n'])
    elif source=='Pacman': text=run(['pacman','-Q'])
    else: text=run(['apk','info','-v'])
    return hashlib.sha256('\n'.join(sorted(text.splitlines())).encode()).hexdigest()


def preview(app, dependencies=False):
    from backend import Plan,run
    if immutable_system(): raise RuntimeError('System packages on immutable desktops are inventory-only. Use the distribution system updater.')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9+_.~-]*',app.package): raise RuntimeError('Invalid native package identity.')
    name=app.location if app.source=='RPM' else app.package
    if app.essential or is_critical(name) or name in protected_owners(app.source): raise RuntimeError('Core system packages cannot be removed through SweepDesk.')
    plan=Plan(app)
    pkexec='/usr/bin/pkexec'
    if app.source=='RPM':
        # Exact installed NEVRA: never allow rpm to remove multiple matching versions.
        records=rpm_inventory()
        matches=[entry for entry in records if entry.package==app.package and entry.version==app.version]
        if len(matches)!=1 or matches[0].essential: raise RuntimeError('Package state changed after the preview. Create a new plan before removal.')
        plan.removed=[app.package]
        plan.commands=[[pkexec,'/usr/bin/rpm','--erase','--',app.package]]
        plan.notes.append('RPM removes only the selected package and checks reverse dependencies at execution. Required packages are refused. Shared dependencies and .rpmsave configuration backups are retained; DNF/Zypper history is not updated.')
    elif app.source=='Pacman':
        flags='-Rs' if dependencies else '-R'
        output=run(['pacman',flags,'--print-format','%n','--',app.package])
        removed=[line.strip() for line in output.splitlines() if line.strip()]
        if not removed or app.package not in removed or any(not re.fullmatch(r'[a-zA-Z0-9@_+.-]+',p) for p in removed): raise RuntimeError('Native removal preview could not be verified.')
        protected=protected_owners('Pacman')
        if any(is_critical(p) or p in protected for p in removed): raise RuntimeError('Core system packages cannot be removed through SweepDesk.')
        plan.removed=[app.package];plan.extra=[p for p in removed if p!=app.package]
        plan.commands=[[pkexec,'/usr/bin/pacman',flags,'--noconfirm','--',app.package]]
        plan.notes.append('Pacman dependency checks stay enabled. No cascading removal, forced dependency bypass, global orphan cleanup, or --nosave is used. Modified configuration may remain as .pacsave.')
    elif app.source=='APK':
        output=run(['apk','--no-network','--simulate','del','--',app.package])
        removed=[]
        for line in output.splitlines():
            match=re.match(r'^\(\d+/\d+\) Purging (\S+) \(',line)
            if match: removed.append(match.group(1))
            elif re.search(r'\b(Installing|Upgrading|Downgrading|Reinstalling)\b',line): raise RuntimeError('Native removal preview could not be verified.')
        if app.package not in removed: raise RuntimeError('Native removal preview could not be verified.')
        protected=protected_owners('APK')
        if any(is_critical(p) or p in protected for p in removed): raise RuntimeError('Core system packages cannot be removed through SweepDesk.')
        plan.removed=[app.package];plan.extra=[p for p in removed if p!=app.package]
        plan.commands=[[pkexec,'/sbin/apk','--no-network','--no-interactive','del','--',app.package]]
        plan.notes.append('APK removes the package from world and may remove its newly unused dependencies, as listed in this preview. No recursive reverse-dependency removal or purge of modified configuration is requested.')
    else: raise RuntimeError('Removal is not supported for this source yet.')
    plan.fingerprint=fingerprint(app.source)
    return plan


def revalidate(plan):
    if fingerprint(plan.app.source)!=plan.fingerprint: raise RuntimeError('Package state changed after the preview. Create a new plan before removal.')
    fresh=preview(plan.app, plan.app.source=='Pacman' and '-Rs' in plan.commands[0])
    if fresh.commands!=plan.commands or set(fresh.removed+fresh.extra)!=set(plan.removed+plan.extra): raise RuntimeError('Package state changed after the preview. Create a new plan before removal.')


def files(app):
    from backend import run
    args={'RPM':['rpm','-ql','--',app.package], 'Pacman':['pacman','-Qlq','--',app.package], 'APK':['apk','info','-L',app.package]}
    return run(args[app.source])
