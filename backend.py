# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Read-only inventory and reviewed uninstall plans. No commands run through a shell."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import configparser
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import uuid
import native_packages
from dataclasses import dataclass, field
from pathlib import Path


ENV = dict(os.environ, LC_ALL="C", LANG="C", NO_COLOR="1", HOMEBREW_NO_AUTO_UPDATE="1",
           HOMEBREW_NO_ANALYTICS="1", HOMEBREW_NO_AUTOREMOVE="1",
           PIP_DISABLE_PIP_VERSION_CHECK="1", npm_config_update_notifier="false")
HOME = Path.home()
ROOT = Path(__file__).resolve().parent
SOURCES = ('APT', 'RPM', 'Pacman', 'APK', 'npm', 'pip', 'Cargo', 'Flatpak', 'Snap', 'pipx', 'uv', 'Bun', 'Homebrew', 'ArtCraft', 'Manual')


def xdg_data_home():
    path = Path(os.environ.get('XDG_DATA_HOME', HOME/'.local/share')).expanduser()
    return path if path.is_absolute() else HOME/'.local/share'


def run(args, timeout=90, check=True):
    p = subprocess.run([str(x) for x in args], text=True, capture_output=True,
                       env=ENV, timeout=timeout, stdin=subprocess.DEVNULL)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout or "Command failed").strip()[-6000:])
    return p.stdout


@dataclass
class App:
    name: str
    package: str
    version: str
    source: str
    description: str = ""
    icon: str = "utilities-terminal"
    size: int = 0
    support: bool = False
    essential: bool = False
    executable: str = ""
    manager: str = ""
    scope: str = ""
    paths: list[str] = field(default_factory=list)
    registry: str = ""
    location: str = ""
    readonly_reason: str = ""

    @property
    def key(self):
        return (self.source, self.scope, self.package, self.manager)


@dataclass
class Plan:
    app: App
    commands: list[list[str]] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    data: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    raw: str = ""
    fingerprint: str = ""
    cleanup_requested: bool = False


def distro_info(path=Path('/etc/os-release')):
    values = {}
    try:
        for line in path.read_text().splitlines():
            if '=' in line and not line.lstrip().startswith('#'):
                key, value = line.split('=', 1)
                tokens = shlex.split(value)
                values[key] = tokens[0] if tokens else ''
    except (OSError, ValueError):
        pass
    return values.get('PRETTY_NAME', 'Linux')


def executable(name, candidates=()):
    found = shutil.which(name)
    if found:
        return found
    return next((str(p) for p in candidates if Path(p).is_file() and os.access(p, os.X_OK)), '')


def desktop_index():
    """Read installed launchers; never run their Exec fields."""
    result = {}
    roots = [Path('/usr/share/applications'), Path('/usr/local/share/applications'),
             xdg_data_home()/'applications']
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob('*.desktop')):
            cfg = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cfg.read(path, encoding='utf-8')
                section = cfg['Desktop Entry']
                if section.get('Type') != 'Application':
                    continue
                if section.get('NoDisplay', '').lower() == 'true':
                    continue
                info = (section.get('Name', path.stem),
                        section.get('Icon', 'application-x-executable'), str(path))
                keys = {path.stem.lower(), path.stem.split('.')[-1].lower()}
                tokens = shlex.split(section.get('Exec', ''))
                if tokens:
                    keys.add(Path(tokens[0]).name.lower())
                for key in keys:
                    result[key] = info
            except (OSError, configparser.Error, ValueError):
                continue
    return result


def decorate(app, desktops):
    aliases = {'@anthropic-ai/claude-code': 'claude', '@openai/codex': 'codex',
               'opencode-ai': 'opencode', 'curl': 'curl'}
    key = app.package.split(':')[0]
    for candidate in [app.location if app.source=='RPM' else '',key, aliases.get(key, ''), Path(app.executable).name.lower()]:
        if candidate and candidate.lower() in desktops:
            title, icon, _ = desktops[candidate.lower()]
            app.icon = icon
            if app.source in ('APT','RPM','Pacman','APK','ArtCraft'):
                app.name = title
                app.support = False
            break
    if app.package.startswith('libreoffice-'):
        part = app.package.removeprefix('libreoffice-')
        if part in ('writer', 'calc', 'impress', 'draw', 'math', 'base'):
            app.name = 'LibreOffice ' + part.capitalize()
            app.icon = 'libreoffice-' + part
    brands = {'opencode': 'opencode.svg', 'opencode-ai': 'opencode.svg',
              'opencode2': 'opencode.svg', 'command-code': 'command-code.png',
              'commandcode': 'command-code.png', 'curl': 'curl.svg',
              'npm': 'npm.svg', 'corepack': 'npm.svg'}
    brand = ROOT/'assets/brands'/brands.get(key, '__missing__')
    if brand.is_file() and app.icon in ('utilities-terminal', 'package-x-generic'):
        app.icon = str(brand)
    if key == 'command-code':
        app.name = 'Command Code'
    return app


def python_locations(extra=()):
    paths = [shutil.which('python3'), '/usr/bin/python3']
    for name in ('VIRTUAL_ENV', 'CONDA_PREFIX'):
        if os.environ.get(name):
            paths.append(str(Path(os.environ[name])/'bin/python'))
    paths += [str(p) for p in (HOME/'.pyenv/versions').glob('*/bin/python')]
    paths += list(extra)
    # Do not resolve venv symlinks: their prefixes are different even if the binary is shared.
    return list(dict.fromkeys(str(Path(p).absolute()) for p in paths if p and Path(p).is_file()))


def probe_python(interpreter):
    return json.loads(run([interpreter, str(ROOT/'python_probe.py')]))


def python_fingerprint(report):
    return hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()


def pip_readonly(report, record):
    location = Path(record['location'])
    if not location.resolve().is_relative_to(HOME.resolve()) or not Path(record['metadata']).resolve().is_relative_to(HOME.resolve()):
        return 'This package is outside your home folder; manage it through its owning package manager.'
    if not report['pip']:
        return 'This Python environment does not provide pip.'
    if report['externally_managed'] and not report['venv']:
        return 'This Python is externally managed (PEP 668). SweepDesk will not override the system protection. Use a virtual environment or the owning package manager.'
    if not record['recorded']:
        return 'The distribution has no RECORD file; its installed files cannot be reliably uninstalled.'
    return ''


def pip_inventory(extra=()):
    apps, seen = [], set()
    for interpreter in python_locations(extra):
        report = probe_python(interpreter)
        for record in report['packages']:
            if record.get('archived'):
                continue
            identity = (record['key'], record['metadata'])
            if identity in seen:
                continue
            # System packages installed by dpkg already appear under APT.
            if record['installer'] not in ('pip', 'uv') and not Path(record['location']).is_relative_to(HOME):
                continue
            if any(part in record['location'] for part in ('/pipx/venvs/', '/uv/tools/')):
                continue
            seen.add(identity)
            apps.append(App(record['name'], record['name'], record['version'], 'pip',
                            'Python distribution · '+interpreter,
                            manager=interpreter, scope=report['prefix'], location=record['metadata'],
                            readonly_reason=pip_readonly(report, record)))
    return apps


def pip_dependencies(report, selected):
    """Only recorded, non-requested, unshared pip dependencies in a writable environment."""
    packages = {p['key']: p for p in report['packages']}
    if len(packages) != len(report['packages']):
        return []
    if not all(p['complete'] for p in packages.values()):
        return []
    protected = {'pip', 'setuptools', 'wheel', 'packaging'}
    closure, pending = set(), list(packages[selected]['requirements'])
    while pending:
        key = pending.pop()
        if key in closure or key == selected or key not in packages:
            continue
        closure.add(key)
        pending.extend(packages[key]['requirements'])
    candidates = {k for k in closure if k not in protected and not packages[k]['requested']
                  and packages[k]['installer'] == 'pip' and not pip_readonly(report, packages[k])}
    while True:
        shared = {k for k in candidates if any(k in p['requirements'] and parent not in candidates | {selected}
                                             for parent, p in packages.items())}
        if not shared:
            return sorted(candidates)
        candidates -= shared


def uv_inventory():
    manager = executable('uv', [HOME/'.local/bin/uv', HOME/'.cargo/bin/uv'])
    apps = []
    for line in run([manager, 'tool', 'list']).splitlines():
        match = re.match(r'^([A-Za-z0-9][A-Za-z0-9_.-]*) v(\S+)', line)
        if match:
            name, version = match.groups()
            apps.append(App(name, name, version, 'uv', 'Isolated Python tool managed by uv', manager=manager))
    return apps


def bun_inventory():
    manager = executable('bun', [HOME/'.bun/bin/bun'])
    base = Path(os.environ.get('BUN_INSTALL', str(HOME/'.bun'))).expanduser()
    folder = Path(os.environ.get('BUN_INSTALL_GLOBAL_DIR', str(base/'install/global'))).expanduser()
    # The manager's output honors custom globalDir settings in bunfig.toml.
    for line in run([manager, 'pm', 'ls', '--global'], check=False).splitlines():
        if ' node_modules' in line:
            candidate = Path(line.rsplit(' node_modules', 1)[0]).expanduser()
            if candidate.is_absolute():
                folder = candidate
                break
    manifest = folder/'package.json'
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text())
    apps = []
    for name in data.get('dependencies', {}):
        if not re.fullmatch(r'(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_][A-Za-z0-9_.-]*', name):
            continue
        meta = folder/'node_modules'/name/'package.json'
        version = json.loads(meta.read_text()).get('version', '') if meta.is_file() else ''
        apps.append(App(name, name, version, 'Bun', 'Global Bun package · '+str(folder),
                        manager=manager, scope=str(folder)))
    return apps


def brew_inventory():
    manager = executable('brew', [Path('/home/linuxbrew/.linuxbrew/bin/brew'), HOME/'.linuxbrew/bin/brew'])
    report = json.loads(run([manager, 'info', '--json=v2', '--installed']))
    apps = []
    for formula in report.get('formulae', []):
        installs = formula.get('installed', [])
        version = ', '.join(i.get('version', '') for i in installs)
        name = formula.get('full_name', formula['name'])
        apps.append(App(formula['name'], name, version, 'Homebrew', formula.get('desc', ''),
                        manager=manager, support=not any(i.get('installed_on_request', True) for i in installs)))
    return apps


def apt_inventory():
    fmt = '${binary:Package}\t${Version}\t${Installed-Size}\t${Essential}\t${Priority}\t${db:Status-Abbrev}\t${binary:Summary}\n'
    lines = run(['/usr/bin/dpkg-query', '-W', '-f=' + fmt]).splitlines()
    automatic = set(run(['/usr/bin/apt-mark', 'showauto']).splitlines())
    apps = []
    for line in lines:
        parts = line.split('\t', 6)
        if len(parts) != 7 or not parts[5].startswith('ii'):
            continue
        pkg, version, size, essential, priority, _, description = parts
        base = pkg.split(':')[0]
        support = (essential == 'yes' or priority in ('required', 'important') or
                   pkg in automatic or base in automatic or
                   base.startswith(('lib', 'fonts-', 'gir1.', 'linux-', 'python3-')))
        apps.append(App(base, pkg, version, 'APT', description,
                        'package-x-generic' if support else 'utilities-terminal',
                        int(size or 0)*1024, support,
                        essential == 'yes' or priority == 'required'))
    return apps


def flatpak_inventory():
    apps = []
    for scope in ('user', 'system'):
        output = run(['flatpak', '--'+scope, 'list', '--app',
                      '--columns=application,name,version,size'], check=False)
        for line in output.splitlines():
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            pkg, name = parts[:2]
            icon = pkg
            for base in [HOME/'.local/share/flatpak/exports/share/icons',
                         Path('/var/lib/flatpak/exports/share/icons')]:
                matches = list(base.glob('hicolor/*/apps/'+pkg+'.*'))
                if matches:
                    icon = str(matches[-1])
                    break
            apps.append(App(name, pkg, parts[2] if len(parts)>2 else '',
                            'Flatpak', 'Flatpak application · '+scope, icon, scope=scope))
    return apps


def npm_locations():
    paths = [shutil.which('npm')]
    paths += [str(p) for p in (HOME/'.nvm/versions/node').glob('*/bin/npm')]
    paths += [str(p) for p in (HOME/'.local/share/fnm/node-versions').glob('*/installation/bin/npm')]
    result = []
    seen = set()
    for path in paths:
        if not path or not Path(path).is_file():
            continue
        real = str(Path(path).resolve())
        if real not in seen:
            seen.add(real)
            result.append(path)
    return result


def npm_run(manager, args, check=True):
    env = dict(ENV)
    env['PATH'] = str(Path(manager).parent) + os.pathsep + env.get('PATH', '')
    p = subprocess.run([manager, *args], text=True, capture_output=True, env=env,
                       stdin=subprocess.DEVNULL, timeout=90)
    if check and p.returncode:
        raise RuntimeError((p.stderr or p.stdout).strip()[-4000:])
    return p.stdout


def npm_inventory():
    apps, seen = [], set()
    for manager in npm_locations():
        data = json.loads(npm_run(manager, ['list', '-g', '--depth=0', '--json'], check=False))
        prefix = npm_run(manager, ['prefix', '-g']).strip()
        if not prefix or not Path(prefix).is_absolute():
            raise RuntimeError('npm did not return a valid global prefix: '+manager)
        for pkg, meta in data.get('dependencies', {}).items():
            identity = (prefix, pkg)
            if identity in seen:
                continue
            seen.add(identity)
            apps.append(App(pkg, pkg, meta.get('version', ''), 'npm',
                            'Global Node.js package · '+prefix, manager=manager, scope=prefix))
    return apps


def pipx_inventory():
    data = json.loads(run(['pipx', 'list', '--json']))
    apps = []
    for key, value in data.get('venvs', {}).items():
        meta = value.get('metadata', {}).get('main_package', {})
        apps.append(App(key, key, meta.get('package_version', ''), 'pipx',
                        'Python application in an isolated pipx environment'))
    return apps


def cargo_inventory():
    manager = executable('cargo', [HOME/'.cargo/bin/cargo'])
    apps = []
    for line in run([manager, 'install', '--list']).splitlines():
        match = re.match(r'^(\S+) v([^:]+):$', line)
        if match:
            pkg, version = match.groups()
            apps.append(App(pkg, pkg, version, 'Cargo', 'Rust application · cargo install', manager=manager))
    return apps


def snap_inventory():
    apps = []
    for line in run(['snap', 'list']).splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 6:
            pkg, version = parts[:2]
            apps.append(App(pkg, pkg, version, 'Snap', 'Snap package · '+parts[-1],
                            'package-x-generic', support='base' in parts[-1]))
    return apps


def owner(path):
    text = run(['/usr/bin/dpkg-query', '-S', str(path)], check=False)
    return text.split(': ', 1)[0] if ': ' in text else ''


def package_owner(path):
    system=native_packages.family()
    if system=='deb' and shutil.which('dpkg-query'): return owner(path)
    source={'rpm':'RPM','suse':'RPM','arch':'Pacman','alpine':'APK'}.get(system)
    return native_packages.owner(path,source) if source else ''


def manual_inventory(registered, extra_dirs=()):
    """Known native installs and unregistered executables in user bin directories."""
    apps, seen = [], set()
    managed_names = {x.package for x in registered if x.source not in ('APT','RPM','Pacman','APK')}
    known = {
        'claude': ('Claude Code', '@anthropic-ai/claude-code'),
        'opencode': ('OpenCode', 'opencode-ai'),
        'codex': ('Codex CLI', '@openai/codex'),
        'commandcode': ('Command Code', 'command-code'),
        'command-code': ('Command Code', 'command-code'),
    }
    candidates = []
    for folder in [HOME/'.local/bin', HOME/'bin', HOME/'.opencode/bin', Path('/usr/local/bin'),
                   *[Path(p).expanduser() for p in extra_dirs]]:
        if folder.is_dir():
            candidates += [p for p in folder.iterdir() if p.is_file() and os.access(p, os.X_OK)]
    for name in known:
        path = shutil.which(name)
        if path:
            candidates.append(Path(path))
    ownership = None
    if native_packages.family()=='deb' and shutil.which('dpkg-query') and candidates:
        paths = list(dict.fromkeys(str(q) for p in candidates for q in (p,p.resolve())))
        # Nonliteral dpkg patterns and line delimiters use the existing conservative path check.
        if all(not any(c in path for c in '*?[]\n\r') for path in paths):
            ownership = set()
            for offset in range(0,len(paths),128):
                output = run(['/usr/bin/dpkg-query','-S','--',*paths[offset:offset+128]],check=False)
                for line in output.splitlines():
                    if ': ' in line:
                        ownership.add(line.split(': ',1)[1])
    def is_owned(path):
        return str(path) in ownership if ownership is not None else bool(package_owner(path))
    for p in candidates:
        resolved = str(p.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        title, package = known.get(p.name, (p.name, p.name))
        if package in managed_names or any(s in resolved for s in ('node_modules/', '/pipx/venvs/', '/.cargo/bin/')):
            continue
        if is_owned(p) or (p.is_symlink() and is_owned(p.resolve())):
            continue
        paths = [str(p)]
        # Known vendor install trees, never a shared bin or package-manager directory.
        if p.name == 'claude' and (HOME/'.local/share/claude').is_dir():
            native = HOME/'.local/share/claude'
            if p.resolve().is_relative_to(native):
                paths.append(str(native))
        if p.name == 'opencode' and p.resolve().is_relative_to(HOME/'.opencode'):
            paths = [str(HOME/'.opencode')]
        apps.append(App(title, p.name, '—', 'Manual',
                        'Unregistered executable. Review its install location before removal.',
                        executable=str(p), paths=paths,
                        scope='User' if p.is_relative_to(HOME) else 'System'))
    return apps


def appimage_inventory(registered):
    """Managed Craft AppImages and user launchers; do not crawl personal documents."""
    apps, seen = [], {str(Path(p).resolve()) for a in registered for p in a.paths}
    manifest = HOME/'.local/share/artcraft-launcher/installed.json'
    if manifest.is_file():
        try:
            entries = json.loads(manifest.read_text()).get('apps', {})
            for key, record in entries.items():
                path = Path(record.get('path', ''))
                if record.get('kind') != 'AppImage' or not path.is_file() or not safe_user_path(path):
                    continue
                files = [str(path)]
                files += [p for p in record.get('files', []) if safe_user_path(p)]
                app = App(key.capitalize(), key, record.get('version', ''), 'ArtCraft',
                          'AppImage registered with ArtCraft Launcher',
                          'ai.storyteller.'+key, executable=str(path), paths=files,
                          registry=str(manifest), scope='User')
                apps.append(app)
                seen.add(str(path.resolve()))
        except (ValueError, OSError, TypeError):
            pass
    for path in (HOME/'.local/share/applications').glob('*.desktop'):
        cfg = configparser.ConfigParser(interpolation=None, strict=False)
        try:
            cfg.read(path, encoding='utf-8')
            section = cfg['Desktop Entry']
            tokens = shlex.split(section.get('Exec', ''))
            if not tokens:
                continue
            exe = Path(tokens[0])
            if exe.suffix.lower() != '.appimage' or not exe.is_file() or not safe_user_path(exe):
                continue
            if str(exe.resolve()) in seen:
                continue
            seen.add(str(exe.resolve()))
            apps.append(App(section.get('Name', exe.stem), exe.name, '—', 'Manual',
                            'AppImage from a user launcher · executable and shortcut tracked',
                            section.get('Icon', 'application-x-executable'), executable=str(exe),
                            paths=[str(exe), str(path)], scope='User'))
        except (KeyError, OSError, configparser.Error, ValueError):
            pass
    return apps


DESKTOP_LAUNCHER_READONLY = (
    'Found from a user desktop shortcut. SweepDesk cannot verify its installation '
    'or remove it safely; use the original installer.'
)


def horizon_launcher_executable(section):
    """Return only a directly installed, user-owned Horizon launcher executable."""
    if section.get('Name', '').strip().casefold() != 'horizon':
        return None
    try:
        tokens = shlex.split(section.get('Exec', ''))
    except (TypeError, ValueError):
        return None
    if not tokens:
        return None
    candidate = Path(tokens[0]).expanduser()
    home = HOME.absolute()
    if (not candidate.is_absolute() or candidate.name != 'horizon-launcher' or
            not candidate.absolute().is_relative_to(home) or candidate.is_symlink() or
            not safe_user_path(candidate)):
        return None
    parent = candidate.parent
    while parent != home:
        if parent.is_symlink():
            return None
        parent = parent.parent
    try:
        return candidate.absolute() if candidate.is_file() and os.access(candidate, os.X_OK) else None
    except OSError:
        return None


def horizon_install_paths(executable):
    """List known Horizon launcher files and user icons, never user worlds."""
    exe = Path(executable).absolute()
    if horizon_launcher_executable({'Name': 'Horizon', 'Exec': shlex.quote(str(exe))}) != exe:
        return []
    paths = []
    install_dir = exe.parent
    # The upstream Linux archive extracts to this dedicated directory. Move the
    # directory only when it contains exactly the verified launcher binary.
    if (re.fullmatch(r'horizon-launcher(?:[-_].+)', install_dir.name, re.IGNORECASE) and
            install_dir.is_dir() and not install_dir.is_symlink() and safe_user_path(install_dir)):
        try:
            entries = list(install_dir.iterdir())
            if len(entries) == 1 and entries[0] == exe and not entries[0].is_symlink():
                paths.append(str(install_dir))
        except OSError:
            pass
    if not paths and safe_user_path(exe):
        paths.append(str(exe))

    desktop_root = xdg_data_home()/'applications'
    # Horizon installs a visible launcher and may also install a hidden game entry.
    for shortcut in sorted(desktop_root.glob('*.desktop')):
        if shortcut.is_symlink() or not safe_user_path(shortcut):
            continue
        try:
            cfg = configparser.ConfigParser(interpolation=None, strict=False)
            cfg.read(shortcut, encoding='utf-8')
            section = cfg['Desktop Entry']
            identity_matches = (
                shortcut.stem.casefold() == 'horizon-launcher' and
                horizon_launcher_executable(section) == exe)
            if shortcut.stem.casefold() == 'horizon':
                try:
                    sidecar = shlex.split(section.get('Exec', ''))
                except (TypeError, ValueError):
                    sidecar = []
                identity_matches = (
                    section.get('NoDisplay', '').strip().lower() == 'true' and
                    bool(sidecar) and Path(sidecar[0]).name.casefold() == 'horizon-client')
            if (section.get('Type') == 'Application' and
                    section.get('Name', '').strip().casefold() == 'horizon' and
                    section.get('Icon', '').strip().casefold() == 'horizon' and
                    identity_matches):
                paths.append(str(shortcut.absolute()))
        except (OSError, configparser.Error, KeyError, TypeError, ValueError):
            continue

    data = xdg_data_home()
    icon_root = data/'icons/hicolor'
    for icon_dir in icon_root.glob('*/apps'):
        for icon in icon_dir.glob('horizon.*'):
            if icon.is_file() and not icon.is_symlink() and safe_user_path(icon):
                paths.append(str(icon.absolute()))
    return list(dict.fromkeys(paths))


def desktop_command_path(command):
    """Resolve a desktop Exec/TryExec command without running it."""
    try:
        tokens = shlex.split(command)
    except (TypeError, ValueError):
        return None
    if not tokens:
        return None
    command = tokens[0]
    candidate = Path(command).expanduser()
    if not candidate.is_absolute():
        # Desktop Exec is not a shell command. Do not interpret relative paths,
        # shell operators, or wrapper arguments as executable paths.
        if '/' in command or '\\' in command:
            return None
        found = shutil.which(command)
        if not found:
            return None
        candidate = Path(found)
    try:
        candidate = candidate.resolve(strict=True)
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    except (OSError, RuntimeError, ValueError):
        return None


def desktop_launcher_inventory(registered):
    """List user launchers with an unmanaged executable as read-only Manual apps."""
    apps, seen_paths = [], set()
    home = HOME.resolve()
    known_ids = {value.casefold() for app in registered
                 for value in (app.name, app.package, app.package.split(':')[0]) if value}
    for app in registered:
        if app.executable:
            try:
                seen_paths.add(str(Path(app.executable).resolve()))
            except (OSError, RuntimeError, ValueError):
                pass
    root = xdg_data_home()/'applications'
    for shortcut in sorted(root.glob('*.desktop')):
        if shortcut.is_symlink():
            continue
        try:
            if not shortcut.resolve().is_relative_to(home) or shortcut.stat().st_uid != os.getuid():
                continue
            cfg = configparser.ConfigParser(interpolation=None, strict=False)
            cfg.read(shortcut, encoding='utf-8')
            section = cfg['Desktop Entry']
            if (section.get('Type') != 'Application' or
                    section.get('Hidden', '').strip().lower() == 'true' or
                    section.get('NoDisplay', '').strip().lower() == 'true'):
                continue
            if section.get('TryExec', '').strip() and not desktop_command_path(section.get('TryExec')):
                continue
            executable = desktop_command_path(section.get('Exec', ''))
            if not executable or not executable.is_relative_to(home):
                continue
            identity = str(executable)
            if identity in seen_paths:
                continue
            horizon_exe = horizon_launcher_executable(section)
            if (horizon_exe and str(horizon_exe) == identity and
                    shortcut.stem.casefold() in {'horizon', 'horizon-launcher'} and
                    section.get('Icon', '').strip().casefold() == 'horizon'):
                icon = section.get('Icon', 'horizon')
                paths = horizon_install_paths(horizon_exe)
                if not paths:
                    continue
                seen_paths.add(identity)
                apps.append(App(
                    'Horizon', 'horizon-launcher', '—', 'Manual',
                    'Horizon launcher · launcher files and user icons tracked', icon,
                    executable=identity, manager='horizon-launcher', scope='User',
                    paths=paths, location=str(horizon_exe.parent)))
                continue
            if shortcut.stem.casefold() in known_ids or executable.name.casefold() in known_ids:
                continue
            seen_paths.add(identity)
            apps.append(App(
                section.get('Name', shortcut.stem), shortcut.stem, '—', 'Manual',
                section.get('Comment', 'Application found through a user desktop shortcut'),
                section.get('Icon', 'application-x-executable'), executable=identity,
                manager='desktop-launcher', scope='User', paths=[identity],
                location=str(executable.parent), readonly_reason=DESKTOP_LAUNCHER_READONLY))
        except (OSError, configparser.Error, KeyError, TypeError, ValueError):
            continue
    return apps


def scan(extra_python=(), extra_manual=(), enabled_sources=None):
    apps, warnings = [], []
    enabled = set(SOURCES if enabled_sources is None else enabled_sources)
    system = native_packages.family()
    loaders = [
        ('APT', lambda: system=='deb' and shutil.which('dpkg-query') and shutil.which('apt-get'), apt_inventory),
        ('RPM', lambda: system in ('rpm','suse') and shutil.which('rpm'), native_packages.rpm_inventory),
        ('Pacman', lambda: system=='arch' and shutil.which('pacman'), native_packages.pacman_inventory),
        ('APK', lambda: system=='alpine' and shutil.which('apk'), native_packages.apk_inventory),
        ('Flatpak', lambda: shutil.which('flatpak'), flatpak_inventory),
        ('npm', npm_locations, npm_inventory),
        ('pipx', lambda: shutil.which('pipx'), pipx_inventory),
        ('pip', lambda: python_locations(extra_python), lambda: pip_inventory(extra_python)),
        ('uv', lambda: executable('uv', [HOME/'.local/bin/uv', HOME/'.cargo/bin/uv']), uv_inventory),
        ('Bun', lambda: executable('bun', [HOME/'.bun/bin/bun']), bun_inventory),
        ('Homebrew', lambda: executable('brew', [Path('/home/linuxbrew/.linuxbrew/bin/brew'), HOME/'.linuxbrew/bin/brew']), brew_inventory),
        ('Cargo', lambda: executable('cargo', [HOME/'.cargo/bin/cargo']), cargo_inventory),
        ('Snap', lambda: shutil.which('snap'), snap_inventory),
    ]
    def read_source(available, loader):
        return loader() if available() else []
    # Only independent read-only inventories overlap; removal remains serial and revalidated.
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix='sweepdesk-scan') as pool:
        desktop_future = pool.submit(desktop_index)
        pending = [(label,pool.submit(read_source,available,loader))
                   for label,available,loader in loaders if label in enabled]
        for label,future in pending:
            try:
                apps.extend(future.result())
            except Exception as error:
                warnings.append(label+': '+str(error))
        desktops = desktop_future.result()
    try:
        if 'Manual' in enabled:
            apps.extend(manual_inventory(apps, extra_manual))
        if 'ArtCraft' in enabled:
            apps.extend(appimage_inventory(apps))
        if 'Manual' in enabled:
            apps.extend(desktop_launcher_inventory(apps))
    except Exception as e:
        warnings.append('Manual: '+str(e))
    for app in apps:
        decorate(app, desktops)
    return sorted(apps, key=lambda a: (a.name.casefold(), a.source, a.scope)), warnings


def profile_key(app):
    s = (app.location if app.source=='RPM' else app.package).lower()
    if s.startswith('libreoffice'):
        return 'libreoffice'
    return {'@anthropic-ai/claude-code': 'claude', 'claude-code': 'claude',
            'opencode-ai': 'opencode', '@openai/codex': 'codex'}.get(s, s)


def data_paths(app):
    config = Path(os.environ.get('XDG_CONFIG_HOME', HOME/'.config'))
    cache = Path(os.environ.get('XDG_CACHE_HOME', HOME/'.cache'))
    data = xdg_data_home()
    state = Path(os.environ.get('XDG_STATE_HOME', HOME/'.local/state'))
    profiles = {
        'libreoffice': [config/'libreoffice', cache/'libreoffice'],
        'opencode': [config/'opencode', cache/'opencode', data/'opencode', state/'opencode'],
        'claude': [HOME/'.claude', HOME/'.claude.json', cache/'claude'],
        'codex': [HOME/'.codex'],
        'curl': [HOME/'.curlrc'],
    }
    if app.source == 'Manual' and app.manager == 'horizon-launcher':
        paths = [data/'horizon-launcher', data/'horizon']
    elif app.source == 'Flatpak' and re.fullmatch(r'[A-Za-z0-9_.-]+', app.package):
        paths = [HOME/'.var/app'/app.package]
    else:
        paths = profiles.get(profile_key(app), [])
    return [str(p) for p in paths if (p.exists() or p.is_symlink()) and safe_user_path(p)
            and not (app.source == 'Manual' and app.manager == 'horizon-launcher' and p.is_symlink())]


def safe_user_path(path, home=None):
    """Reject broad directories, traversal, parent symlinks and non-user-owned trees."""
    home = Path(home or HOME).absolute()
    p = Path(path)
    if not p.is_absolute() or '..' in p.parts or p == home or not p.is_relative_to(home):
        return False
    blocked = {home/x for x in ('bin', '.local', '.local/bin', '.local/share', '.config',
                               '.cache', '.var', '.var/app', 'Documents', 'Downloads',
                               'Desktop', '.local/state', '.nvm', '.npm', '.cargo')}
    if p in blocked:
        return False
    # An exact symlink may be trashed; never walk through a symlink parent.
    parent = p.parent
    while parent != home:
        if parent.is_symlink():
            return False
        parent = parent.parent
    try:
        return p.lstat().st_uid == os.getuid()
    except OSError:
        return False


def horizon_process_running(app):
    """Do not move Horizon executables or data while a Horizon process is live."""
    executable = Path(app.executable).absolute()
    roots = [Path(path).absolute() for path in app.paths if Path(path).is_dir()]
    roots.extend(Path(path).absolute() for path in data_paths(app) if Path(path).is_dir())
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            running = Path(os.readlink(proc/'exe').removesuffix(' (deleted)')).absolute()
            if (running == executable or running.name in {'horizon-launcher', 'horizon-client',
                                                          'horizon-server', 'horizon-prepare'} or
                    any(running.is_relative_to(root) for root in roots)):
                return True
        except (OSError, RuntimeError, ValueError):
            continue
    return False


def horizon_install_fingerprint(paths, executable):
    """Bind a Horizon preview to its exact files and launcher binary contents."""
    records = []
    for path in sorted(set(paths) | {str(Path(executable).absolute())}):
        item = Path(path)
        if not safe_user_path(item):
            raise RuntimeError('A Horizon installation path changed. Refresh the inventory.')
        info = item.lstat()
        records.append((str(item), info.st_dev, info.st_ino, info.st_mode,
                        info.st_uid, info.st_size, info.st_mtime_ns))
    binary = Path(executable)
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(binary, flags)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            current = binary.lstat()
            signature = lambda info: (info.st_dev, info.st_ino, info.st_mode,
                                      info.st_uid, info.st_size, info.st_mtime_ns)
            planned = next(record[1:] for record in records if record[0] == str(binary))
            if signature(opened) != signature(current) or signature(opened) != planned:
                raise RuntimeError('The Horizon launcher changed while preparing the removal plan.')
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024*1024), b''):
                digest.update(chunk)
            if signature(opened) != signature(os.fstat(stream.fileno())):
                raise RuntimeError('The Horizon launcher changed while preparing the removal plan.')
    except OSError:
        raise RuntimeError('The Horizon launcher could not be checked safely. Refresh the inventory.')
    return hashlib.sha256(json.dumps([records, digest.hexdigest()]).encode()).hexdigest()


def sign_out_horizon_accounts(app, emit):
    """Use Horizon's CLI to clear keychain tokens without logging account details."""
    launcher_data = xdg_data_home()/'horizon-launcher'
    accounts_file = launcher_data/'accounts.json'
    if (not accounts_file.exists() or accounts_file.is_symlink() or
            not safe_user_path(accounts_file) or not safe_user_path(launcher_data)):
        return
    try:
        listed = subprocess.run([app.executable, '--json', 'account', 'list'],
                                text=True, capture_output=True, env=ENV,
                                timeout=30, stdin=subprocess.DEVNULL)
        payload = json.loads(listed.stdout) if listed.returncode == 0 else None
        accounts = payload.get('accounts') if isinstance(payload, dict) else None
        if not isinstance(accounts, list):
            raise ValueError
        account_ids = [str(uuid.UUID(item['uuid'])) for item in accounts
                       if isinstance(item, dict) and isinstance(item.get('uuid'), str)]
        if len(account_ids) != len(accounts):
            raise ValueError
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise RuntimeError('Horizon could not safely clear its saved sign-in tokens. No Horizon files were moved; sign out in Horizon and try again.')
    if not account_ids:
        return
    emit('Signing out Horizon accounts from the system keychain…\n')
    for account_id in account_ids:
        try:
            signed_out = subprocess.run([app.executable, 'account', 'sign-out', account_id],
                                        text=True, capture_output=True, env=ENV,
                                        timeout=30, stdin=subprocess.DEVNULL)
        except (OSError, subprocess.SubprocessError):
            raise RuntimeError('Horizon could not finish signing out its saved accounts. No Horizon files were moved; check Horizon account state before retrying.')
        if signed_out.returncode:
            raise RuntimeError('Horizon could not finish signing out its saved accounts. No Horizon files were moved; check Horizon account state before retrying.')
    emit('Horizon accounts signed out.\n')


def removed_packages(output):
    return [line.split()[1] for line in output.splitlines()
            if line.startswith(('Remv ', 'Purg '))]


def check_apt_plan(output):
    if re.search(r'^(Inst|Conf) ', output, re.M):
        raise RuntimeError('APT also plans to install or configure other packages. Resolve this using Synaptic or a terminal.')
    removed = removed_packages(output)
    if not removed:
        raise RuntimeError('No installed packages would be removed. Refresh the inventory.')
    fmt = '${binary:Package}\t${Essential}\t${Priority}\n'
    info = run(['/usr/bin/dpkg-query', '-W', '-f='+fmt, *removed])
    critical = {'apt', 'dpkg', 'sudo', 'polkitd', 'systemd', 'systemd-sysv',
                'gnome-shell', 'gnome-core', 'network-manager', 'python3', 'python3-gi',
                'gir1.2-gtk-3.0', 'libgtk-3-0', 'libgtk-3-0t64', 'pkexec', 'policykit-1',
                'plasma-desktop', 'plasma-workspace', 'kwin-x11', 'kwin-wayland',
                'xfce4-session', 'xfce4-panel', 'xfwm4', 'cinnamon', 'cinnamon-session',
                'mate-session-manager', 'mate-panel', 'lxqt-session', 'lxsession',
                'gdm3', 'sddm', 'lightdm', 'xserver-xorg-core'}
    for line in info.splitlines():
        parts = line.split('\t')
        if len(parts) >= 3 and (parts[1] == 'yes' or parts[2] == 'required' or parts[0].split(':')[0] in critical):
            raise RuntimeError('Removal blocked because the plan includes a core system component: '+parts[0])
    return removed


def make_plan(app, dependencies=False, cleanup=False, family=False):
    plan = Plan(app)
    if app.essential:
        raise RuntimeError('Core system packages cannot be removed through SweepDesk.')
    if app.readonly_reason:
        raise RuntimeError(app.readonly_reason)
    if app.source in native_packages.SOURCES:
        if family: raise RuntimeError('Suite removal is only available for LibreOffice on APT.')
        plan = native_packages.preview(app,dependencies)
    elif app.source == 'APT':
        if not re.fullmatch(r'[a-z0-9][a-z0-9+.:\-]*', app.package):
            raise RuntimeError('Invalid APT package name.')
        targets = [app.package]
        if family:
            if not app.package.startswith('libreoffice'):
                raise RuntimeError('Suite removal is only available for LibreOffice.')
            targets = [a.package for a in apt_inventory() if a.package.startswith('libreoffice')]
        base = run(['/usr/bin/apt-get', '-s', 'purge', '--', *targets])
        plan.removed = check_apt_plan(base)
        if dependencies:
            # Subtract pre-existing garbage: do not clean unrelated applications.
            before = set(removed_packages(run(['/usr/bin/apt-get', '-s', 'autoremove'])))
            after = removed_packages(run(['/usr/bin/apt-get', '-s', '--autoremove', 'purge', '--', *targets]))
            plan.extra = sorted(set(after) - before - set(plan.removed))
            final = run(['/usr/bin/apt-get', '-s', 'purge', '--', *targets, *plan.extra])
            final_removed = check_apt_plan(final)
            if set(final_removed) != set(plan.removed) | set(plan.extra):
                raise RuntimeError('The dependency plan changed. Refresh and try again.')
            plan.raw = final
        else:
            plan.raw = base
        plan.commands = [['/usr/bin/pkexec', '/usr/bin/apt-get', '-y', 'purge', '--', *targets, *plan.extra]]
        if 'gnome' in plan.removed:
            plan.notes.append('The gnome metapackage will also be removed. It groups desktop applications; gnome-shell and the core desktop are not in this plan.')
        if dependencies:
            plan.notes.append('Also clean up support packages used by this app, if no other apps need them.')
    elif app.source == 'Flatpak':
        if app.scope not in ('user', 'system') or not re.fullmatch(r'[A-Za-z0-9_.-]+', app.package):
            raise RuntimeError('Invalid Flatpak identity.')
        # Related runtimes are handled by Flatpak; do not globally remove unrelated runtimes.
        plan.commands = [[shutil.which('flatpak'), '--'+app.scope, 'uninstall', '-y', '--app', app.package]]
        plan.removed = [app.package]
        plan.notes.append('Flatpak calculates related extensions at execution time. Shared runtimes are retained; no global runtime cleanup is performed.')
    elif app.source == 'npm':
        if not re.fullmatch(r'(?:@[a-zA-Z0-9_.-]+/)?[a-zA-Z0-9_][a-zA-Z0-9_.-]*', app.package):
            raise RuntimeError('Invalid npm package name.')
        if not Path(app.scope).is_relative_to(HOME):
            raise RuntimeError('This npm global prefix is outside your home folder. Manage this system-wide installation using its package manager or a terminal.')
        plan.commands = [[shutil.which('env'), 'PATH='+str(Path(app.manager).parent)+os.pathsep+ENV.get('PATH',''),
                          app.manager, 'uninstall', '-g', '--prefix', app.scope,
                          '--ignore-scripts', '--', app.package]]
        plan.removed = [app.package]
        plan.notes.append('npm manages this package and its dependencies. Lifecycle scripts are disabled during removal.')
    elif app.source == 'pip':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', app.package):
            raise RuntimeError('Invalid Python distribution name.')
        report = probe_python(app.manager)
        key = re.sub(r'[-_.]+', '-', app.package).lower()
        records = [p for p in report['packages'] if p['key'] == key and Path(p['metadata']).resolve() == Path(app.location).resolve()]
        if len(records) != 1 or len([p for p in report['packages'] if p['key'] == key]) != 1:
            raise RuntimeError('Python distribution is missing or has overlapping installations. Refresh and resolve it in its environment.')
        record = records[0]
        reason = pip_readonly(report, record)
        if reason:
            raise RuntimeError(reason)
        plan.removed = [app.package]
        if dependencies:
            plan.extra = pip_dependencies(report, key)
            plan.notes.append('Dependency cleanup keeps explicitly requested packages, shared dependencies, packaging tools, and incomplete metadata. Optional dependency relationships are kept conservatively.')
        plan.commands = [[app.manager, '-m', 'pip', 'uninstall', '-y', '--', app.package, *plan.extra]]
        plan.fingerprint = python_fingerprint(report)
        plan.notes.append('pip removes files recorded by the distribution. Legacy/unrecorded files and shared download caches may remain.')
    elif app.source == 'Bun':
        if not re.fullmatch(r'(?:@[A-Za-z0-9_.-]+/)?[A-Za-z0-9_][A-Za-z0-9_.-]*', app.package):
            raise RuntimeError('Invalid Bun package name.')
        if not Path(app.scope).is_relative_to(HOME):
            raise RuntimeError('This Bun global installation is outside your home folder.')
        plan.removed = [app.package]
        plan.commands = [[shutil.which('env'), 'BUN_INSTALL_GLOBAL_DIR='+app.scope,
                          app.manager, 'remove', '--global', '--ignore-scripts', '--', app.package]]
        plan.notes.append('Bun manages its dependency graph. Shared package caches are retained.')
    elif app.source == 'Homebrew':
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_+./@-]*', app.package) or '..' in app.package:
            raise RuntimeError('Invalid Homebrew formula name.')
        plan.removed = [app.package]
        plan.commands = [[app.manager, 'uninstall', '--formula', app.package]]
        plan.notes.append('Homebrew refuses removal if other formulae still depend on this package. No --ignore-dependencies or global cache cleanup is used.')
    elif app.source in ('pipx', 'Cargo', 'Snap', 'uv'):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.+-]*', app.package):
            raise RuntimeError('Invalid package name.')
        if app.source == 'pipx':
            command = [shutil.which('pipx'), 'uninstall', app.package]
        elif app.source == 'uv':
            command = [app.manager, 'tool', 'uninstall', app.package]
        elif app.source == 'Cargo':
            command = [app.manager or executable('cargo', [HOME/'.cargo/bin/cargo']), 'uninstall', app.package]
        else:
            command = ['/usr/bin/pkexec', '/usr/bin/snap', 'remove', app.package]
            plan.notes.append('Snap manages package data and automatic snapshots according to its policy. --purge is not used; existing snapshots are retained.')
        plan.commands = [command]
        plan.removed = [app.package]
    elif app.source == 'Manual' and app.manager == 'horizon-launcher':
        expected = horizon_install_paths(app.executable)
        if (not expected or set(expected) != set(app.paths) or
                not all(safe_user_path(path) for path in expected)):
            raise RuntimeError('Horizon launcher files changed or are outside a safe user folder. Refresh the inventory and try again.')
        plan.files = expected
        plan.fingerprint = horizon_install_fingerprint(plan.files, app.executable)
        plan.removed = ['Horizon launcher']
        plan.notes.append('Only the detected Horizon launcher, its menu shortcuts and user icons will be moved to Trash. Original Minecraft folders are kept.')
        install_dir = Path(app.executable).parent
        if (install_dir.name.casefold().startswith('horizon-launcher-') and
                str(install_dir) not in plan.files and install_dir.is_dir()):
            plan.notes.append('The launcher folder contains other files, so only the launcher executable will be moved. Review that folder after removal.')
    elif app.source in ('Manual', 'ArtCraft'):
        if not app.paths or not all(safe_user_path(p) for p in app.paths):
            raise RuntimeError('This manual executable is in a system location or a location that cannot be cleaned automatically. It is inventory-only; use the official uninstaller.')
        plan.files = list(app.paths)
        plan.removed = [app.name]
        plan.notes.append('Manual installation: only the listed paths will be moved to Trash. PATH edits, services and other installer-created files may not be detected.')
        if app.source == 'ArtCraft':
            plan.notes.append('The ArtCraft installation record will also be updated after its files are moved to Trash.')
    else:
        raise RuntimeError('Removal is not supported for this source yet.')
    if cleanup:
        if profile_key(app) == 'libreoffice' and not family:
            raise RuntimeError('LibreOffice settings are shared. Select the entire suite before cleaning its user data.')
        plan.data = data_paths(app)
        plan.cleanup_requested = True
        if app.manager == 'horizon-launcher' and plan.data:
            plan.notes.append('The listed Horizon folders include downloaded game files, versions, settings, worlds, servers and logs. Horizon accounts are signed out from the system keychain first; original Minecraft folders and custom data homes outside this list are kept.')
        elif plan.data:
            plan.notes.append('Selected data will be moved to Trash, including any history, sign-ins, profiles and settings inside the listed folders.')
        else:
            plan.notes.append('No known user-data locations were found for this package. Complete cleanup cannot be guaranteed.')
    return plan


def execute(plan, emit):
    """Called only after the GUI shows the complete plan and the user confirms."""
    if plan.app.source == 'Manual' and plan.app.manager == 'horizon-launcher':
        expected_files = horizon_install_paths(plan.app.executable)
        expected_data = data_paths(plan.app) if plan.cleanup_requested else []
        if (plan.commands or set(plan.files) != set(expected_files) or
                plan.data != expected_data or
                not all(safe_user_path(path) for path in plan.files + plan.data)):
            raise RuntimeError('Horizon files changed after the preview. Create a new removal plan.')
        if horizon_install_fingerprint(plan.files, plan.app.executable) != plan.fingerprint:
            raise RuntimeError('Horizon files changed after the preview. Create a new removal plan.')
        if horizon_process_running(plan.app):
            raise RuntimeError('Close Horizon, the Horizon game and Horizon servers before removing their files.')
    if plan.app.source in native_packages.SOURCES:
        native_packages.revalidate(plan)
    if plan.app.source == 'APT':
        # Recheck after confirmation: don't apply a broader stale plan.
        args = plan.commands[0]
        targets = args[args.index('--')+1:]
        fresh = run(['/usr/bin/apt-get', '-s', 'purge', '--', *targets])
        actual = check_apt_plan(fresh)
        if set(actual) != set(plan.removed) | set(plan.extra):
            raise RuntimeError('Package state changed after the preview. Create a new plan before removal.')
    if plan.app.source == 'pip':
        if python_fingerprint(probe_python(plan.app.manager)) != plan.fingerprint:
            raise RuntimeError('The Python environment changed after the preview. Create a new removal plan.')
    registry_before = None
    if plan.app.registry:
        expected = HOME/'.local/share/artcraft-launcher/installed.json'
        if Path(plan.app.registry) != expected or expected.is_symlink():
            raise RuntimeError('Invalid ArtCraft registry location.')
        registry_before = expected.read_bytes()
        record = json.loads(registry_before).get('apps', {}).get(plan.app.package)
        if not record or record.get('path') != plan.app.executable:
            raise RuntimeError('The ArtCraft registry changed. Create a new preview.')
        # Launcher can rewrite the manifest, so require it to be closed.
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                if (proc/'exe').resolve().name == 'artcraft-launcher':
                    raise RuntimeError('Close ArtCraft Launcher before removing an AppImage it manages.')
            except OSError:
                pass
    for command in plan.commands:
        emit('$ '+shlex.join(command)+'\n')
        env = dict(ENV, DEBIAN_FRONTEND='noninteractive')
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, env=env, stdin=subprocess.DEVNULL)
        for line in process.stdout:
            emit(line)
        if process.wait():
            raise RuntimeError('Uninstall failed or authentication was canceled. User data has not been moved. Check the log; package changes may be partially applied.')
    if plan.cleanup_requested and plan.app.manager == 'horizon-launcher':
        sign_out_horizon_accounts(plan.app, emit)
        if horizon_install_fingerprint(plan.files, plan.app.executable) != plan.fingerprint:
            raise RuntimeError('The Horizon launcher changed during account sign-out. Horizon files were not moved; create a new preview.')
        if horizon_process_running(plan.app):
            raise RuntimeError('A Horizon process started during removal. Horizon files were not moved; close it and create a new preview.')
    # Never fall back to recursive deletion when the desktop Trash is unavailable.
    import gi
    from gi.repository import Gio
    for path in dict.fromkeys(plan.files + plan.data):
        if not safe_user_path(path):
            raise RuntimeError('Path changed or is not safe to clean: '+path)
        Gio.File.new_for_path(path).trash(None)
        emit('Moved to Trash: '+path+'\n')
    if registry_before is not None:
        registry = Path(plan.app.registry)
        if registry.read_bytes() != registry_before:
            raise RuntimeError('Files were moved, but the ArtCraft registry changed and was not overwritten. Review it in the launcher.')
        data = json.loads(registry_before)
        data['apps'].pop(plan.app.package)
        # Keep a recovery copy next to the registry; no credentials in this manifest.
        backup = registry.with_name('installed.json.sweepdesk-backup')
        backup.write_bytes(registry_before)
        temporary = registry.with_name('installed.json.sweepdesk-tmp')
        with temporary.open('x') as f:
            json.dump(data, f, indent=2)
            f.write('\n')
        os.chmod(temporary, registry.stat().st_mode & 0o777)
        os.replace(temporary, registry)
        emit('ArtCraft registry updated. Backup: '+str(backup)+'\n')


def describe_plan(plan):
    lines = ['WILL BE REMOVED ('+str(len(plan.removed))+')', *plan.removed]
    if plan.extra:
        lines += ['', 'NEWLY UNUSED DEPENDENCIES ('+str(len(plan.extra))+')', *plan.extra]
    if plan.files:
        lines += ['', 'INSTALLATION FILES → TRASH', *plan.files]
    if plan.data:
        lines += ['', 'USER DATA → TRASH', *plan.data]
    if plan.notes:
        lines += ['', 'NOTES', *plan.notes]
    lines += ['', 'COMMANDS', *[shlex.join(c) for c in plan.commands]]
    return '\n'.join(lines)
