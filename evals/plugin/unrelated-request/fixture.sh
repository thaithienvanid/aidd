#!/usr/bin/env bash
set -euo pipefail
# A workspace with a few Python files, so the one-liner the prompt asks for has something to count. The files are ours.
mkdir -p src
printf 'print(1)\n' > src/a.py
printf 'print(2)\nprint(3)\n' > src/b.py
