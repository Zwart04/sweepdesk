#!/bin/sh
# SPDX-FileCopyrightText: 2026 Zwart04
# SPDX-License-Identifier: GPL-3.0-or-later
# SweepDesk: see LICENSE for copying terms and warranty disclaimer.
set -eu
app_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
binary="$app_root/rust/target/release/sweepdesk"
if [ ! -x "$binary" ]; then
  cargo build --release --locked --manifest-path "$app_root/rust/Cargo.toml" >&2
fi
exec "$binary" "$@"
