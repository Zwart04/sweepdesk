#!/usr/bin/python3
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
"""Regenerate rust/src/catalogue.rs from i18n.py after editing a translation."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
table = None
for node in ast.parse((ROOT/'i18n.py').read_text()).body:
    if isinstance(node, ast.Assign) and any(getattr(target, 'id', None) == 'ID' for target in node.targets):
        table = ast.literal_eval(node.value)
if not table:
    raise SystemExit('i18n.py does not define a non-empty ID table')

def quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'

lines = [
    '// SPDX-FileCopyrightText: 2026 Zwart04',
    '// SPDX-License-Identifier: GPL-3.0-or-later',
    '// SweepDesk: see LICENSE for copying terms and warranty disclaimer.',
    '//! Generated from i18n.py; package names and command logs stay intact.',
    '',
    'pub static ID: &[(&str, &str)] = &[',
]
lines += [f'    ({quote(key)}, {quote(value)}),' for key, value in table.items()]
lines.append('];')
(ROOT/'rust/src/catalogue.rs').write_text('\n'.join(lines) + '\n')
print(f'{len(table)} entries written to rust/src/catalogue.rs')
