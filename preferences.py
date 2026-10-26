"""Small, validated per-user preferences. Inventories and operation logs are not persisted."""
import json
import os
from pathlib import Path
import tempfile

from backend import SOURCES


def defaults():
    return {'theme': 'dark', 'density': 'compact', 'show_system': False,
            'show_details': True, 'show_empty_sources': False, 'scan_on_start': True,
            'remember_folders': True, 'python_folders': [], 'manual_folders': [],
            'enabled_sources': list(SOURCES)}


def config_path():
    base = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config')))
    if not base.is_absolute():
        base = Path.home()/'.config'
    return base/'sweepdesk/preferences.json'


def validate(data):
    result = defaults()
    if not isinstance(data, dict):
        return result
    for key in ('theme', 'density'):
        allowed = ('dark', 'light', 'system') if key == 'theme' else ('compact', 'comfortable')
        if data.get(key) in allowed:
            result[key] = data[key]
    for key in ('show_system', 'show_details', 'show_empty_sources', 'scan_on_start', 'remember_folders'):
        if isinstance(data.get(key), bool):
            result[key] = data[key]
    for key in ('python_folders', 'manual_folders'):
        if isinstance(data.get(key), list):
            result[key] = list(dict.fromkeys(p for p in data[key] if isinstance(p, str) and Path(p).is_absolute()))
    if isinstance(data.get('enabled_sources'), list):
        result['enabled_sources'] = [s for s in SOURCES if s in data['enabled_sources']]
    return result


def load(path=None):
    try:
        return validate(json.loads(Path(path or config_path()).read_text()))
    except (OSError, ValueError):
        return defaults()


def save(data, path=None):
    destination = Path(path or config_path())
    if destination.is_symlink():
        raise OSError('The preferences file is a symbolic link; it was not overwritten.')
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(prefix='.preferences-', dir=destination.parent)
    try:
        with os.fdopen(descriptor, 'w') as stream:
            json.dump(validate(data), stream, indent=2)
            stream.write('\n')
        os.replace(temporary, destination)
    finally:
        if Path(temporary).exists():
            Path(temporary).unlink()
