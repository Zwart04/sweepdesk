"""Read Python distribution metadata in the selected interpreter. Never imports applications."""
import importlib.metadata as metadata
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import sysconfig


def normalize(value):
    return re.sub(r'[-_.]+', '-', value).lower()


def probe():
    # Debian's older pip adds its private wheel archives to sys.path on import.
    # Snapshot actual installed distributions before importing its requirement parser.
    installed = list(metadata.distributions())
    try:
        from pip._vendor.packaging.requirements import Requirement
    except ImportError:
        try:
            from packaging.requirements import Requirement
        except ImportError:
            Requirement = None
    packages = []
    for dist in installed:
        name = dist.metadata.get('Name')
        if not name:
            continue
        raw_info = getattr(dist, '_path', dist.locate_file(''))
        try:
            info = Path(raw_info)
        except TypeError:
            # Older Debian pip exposes bundled wheel metadata through zipfile.Path.
            # Keep its dependency edges, but never offer it as an uninstallable directory.
            info = None
        requirements, complete = [], Requirement is not None
        for value in dist.requires or []:
            try:
                if Requirement is None:
                    complete = False
                    continue
                req = Requirement(value)
                # Keep optional edges too: an installed extra may still use the dependency.
                requirements.append(normalize(req.name))
            except Exception:
                complete = False
        packages.append({'name': name, 'key': normalize(name), 'version': dist.version,
                         'location': str(dist.locate_file('')), 'metadata': str(raw_info),
                         'installer': (dist.read_text('INSTALLER') or '').strip(),
                         'requested': bool(info is not None and (info/'REQUESTED').exists()),
                         'recorded': bool(info is not None and (info/'RECORD').is_file()),
                         'archived': info is None,
                         'requirements': requirements, 'complete': complete})
    return {'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
            'venv': sys.prefix != sys.base_prefix,
            'pip': importlib.util.find_spec('pip') is not None,
            'externally_managed': (Path(sysconfig.get_path('stdlib'))/'EXTERNALLY-MANAGED').exists(),
            'packages': sorted(packages, key=lambda p: (p['key'], p['location']))}


if __name__ == '__main__':
    print(json.dumps(probe()))
