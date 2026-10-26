#!/bin/sh
set -eu
app_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/bin/python3 "$app_root/sweepdesk.py" "$@"
