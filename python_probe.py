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
    try:
        from pip._vendor.packaging.requirements import Requirement
    except ImportError:
        try:
            from packaging.requirements import Requirement
        except ImportError:
            Requirement = None
    packages = []
    for dist in metadata.distributions():
        name = dist.metadata.get('Name')
        if not name:
            continue
        info = Path(getattr(dist, '_path', dist.locate_file('')))
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
                         'location': str(dist.locate_file('')), 'metadata': str(info),
                         'installer': (dist.read_text('INSTALLER') or '').strip(),
                         'requested': (info/'REQUESTED').exists(),
                         'recorded': (info/'RECORD').is_file(),
                         'requirements': requirements, 'complete': complete})
    return {'prefix': sys.prefix, 'base_prefix': sys.base_prefix,
            'venv': sys.prefix != sys.base_prefix,
            'pip': importlib.util.find_spec('pip') is not None,
            'externally_managed': (Path(sysconfig.get_path('stdlib'))/'EXTERNALLY-MANAGED').exists(),
            'packages': sorted(packages, key=lambda p: (p['key'], p['location']))}


if __name__ == '__main__':
    print(json.dumps(probe()))
