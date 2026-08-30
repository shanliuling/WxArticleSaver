#!/bin/zsh
set -e
cd "${0:A:h}"

if [[ -x .venv/bin/python ]]; then
  exec .venv/bin/python -u launcher_macos.py "$@"
fi

exec python3 -u launcher_macos.py "$@"
