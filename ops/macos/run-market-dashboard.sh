#!/bin/bash
# Do not source .env: credentials are literal data, never shell code.
set +x
set -euo pipefail
umask 077
OPS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$OPS_DIR/../.." && pwd -P)"
PROJECT_ROOT="${MARKET_DASHBOARD_PROJECT_ROOT:-$(dirname -- "$REPO_DIR")}"
PYTHON="${MARKET_DASHBOARD_PYTHON:-python3}"
exec "$PYTHON" - "$REPO_DIR" "$PROJECT_ROOT" "$@" <<'PY'
import importlib.util
import os
from pathlib import Path
import re
import shlex
import sys

repo, root = (Path(value).resolve() for value in sys.argv[1:3])
try:
    env = root / '.env'
    if env.exists():
        for raw in env.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            if line.startswith('export '):
                line = line[7:].lstrip()
            key, separator, value = line.partition('=')
            key = key.strip()
            if not separator or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
                raise ValueError('invalid dotenv assignment')
            parts = shlex.split(value, comments=True, posix=True)
            os.environ.setdefault(key, ' '.join(parts))
    os.environ['MARKET_DASHBOARD_STATE_ROOT'] = str(root / 'state')
    logs = root / 'logs/market-dashboard'
    logs.mkdir(parents=True, exist_ok=True, mode=0o700)
    logs.chmod(0o700)
    # Reuse the parent project's copy-truncate policy (2 MB, three backups).
    policy = root / 'scripts/rotate_service_logs.py'
    spec = importlib.util.spec_from_file_location('dashboard_log_rotation', policy)
    rotation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rotation)
    for path in logs.glob('*.log'):
        if path.is_symlink():
            raise ValueError('log symlinks are not supported')
        rotation.rotate(path)
    for path in logs.iterdir():
        if path.is_file() and not path.is_symlink():
            path.chmod(0o600)
    log = logs / 'job.log'
    fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    os.fchmod(fd, 0o600)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    os.chdir(repo)
    python = os.environ.get('MARKET_DASHBOARD_PYTHON') or os.environ.get('PYTHON_BIN') or sys.executable
    os.execvpe(python, [python, '-u', '-m', 'tools.market_dashboard.job', *sys.argv[3:]], os.environ)
except Exception:
    # Never print a dotenv line, credential, provider exception or exec arguments.
    print('market dashboard wrapper failed: check local paths and configuration', file=sys.stderr)
    raise SystemExit(1)
PY
