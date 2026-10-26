#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Create a reproducible Arch recipe and final checksums after collecting native builds."""
import hashlib
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from build import ROOT,DIST,VERSION

source=DIST/f'sweepdesk-{VERSION}.tar.gz'
digest=hashlib.sha256(source.read_bytes()).hexdigest()
recipe=(ROOT/'packaging/arch/PKGBUILD.in').read_text().replace('@VERSION@',VERSION).replace('@SHA256@',digest)
(DIST/'PKGBUILD').write_text(recipe)
artifacts=sorted(p for p in DIST.iterdir() if p.is_file() and (VERSION in p.name and p.name.endswith(('.deb','.rpm','.pkg.tar.zst','.tar.gz')) or p.name=='PKGBUILD'))
(DIST/'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in artifacts))
print('\n'.join(p.name for p in artifacts))
