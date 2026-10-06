#!/usr/bin/env bash
# Test entry point used by agents (test_command in projects.yaml). Exit 0 = green, 1 = red.
set -uo pipefail
cd "$(dirname "$0")" || exit 1
python3 -m unittest discover -s tests -p 'test_*.py' -q
rc=$?
if [ "$rc" -ne 0 ]; then exit 1; fi
exit 0
