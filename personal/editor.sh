#!/usr/bin/env bash
set -euo pipefail
editor_personal_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$editor_personal_root/.."
exec "$editor_personal_root/.venv/bin/python" "$editor_personal_root/run.py" start "$@"
