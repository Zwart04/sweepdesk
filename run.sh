#!/bin/sh
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
set -eu
app_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec python3 "$app_root/sweepdesk.py" "$@"
