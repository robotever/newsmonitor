#!/bin/bash
# Prepare by default. Enabling is a separate explicit operator action.
set +x
set -euo pipefail
umask 077
OPS_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_DIR="$(cd -- "$OPS_DIR/../.." && pwd -P)"
PROJECT_ROOT="${MARKET_DASHBOARD_PROJECT_ROOT:-$(dirname -- "$REPO_DIR")}"
PYTHON="${MARKET_DASHBOARD_PYTHON:-python3}"
exec "$PYTHON" - "$REPO_DIR" "$PROJECT_ROOT" "$@" <<'PY'
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile

repo_value, root_value, *arguments = sys.argv[1:]
allow_worktree = '--allow-worktree' in arguments
actions = [argument for argument in arguments if argument != '--allow-worktree']
action = actions[0] if actions else '--prepare'
repo, root = Path(repo_value).resolve(), Path(root_value).resolve()
label = 'com.robot-ever.newsmonitor.market-dashboard'
domain = f'gui/{os.getuid()}'
job = f'{domain}/{label}'
agents = Path.home() / 'Library/LaunchAgents'
target = agents / f'{label}.plist'
backup = target.with_suffix('.plist.bak')

def launch(*args):
    return subprocess.run(['launchctl', *args], capture_output=True, text=True, check=False)

def validate_checkout():
    # Run before any filesystem mutation or launchctl call, including disable.
    def git(*args):
        result = subprocess.run(['git', '-C', str(repo), 'rev-parse', *args],
                                capture_output=True, text=True, check=False)
        if result.returncode:
            raise ValueError('a real Git checkout is required')
        return result.stdout.strip()

    if git('--is-inside-work-tree') != 'true' or Path(git('--show-toplevel')).resolve() != repo:
        raise ValueError('installer must be run from its Git checkout')
    git_dir = Path(git('--path-format=absolute', '--git-dir')).resolve()
    common_dir = Path(git('--path-format=absolute', '--git-common-dir')).resolve()
    codex_worktree = any(a == '.codex' and b == 'worktrees' for a, b in zip(repo.parts, repo.parts[1:]))
    if ((repo / '.git').is_file() or git_dir != common_dir or codex_worktree) and not allow_worktree:
        raise ValueError('temporary worktree refused; use a stable checkout or explicitly --allow-worktree')
    required = [repo / 'tools/market_dashboard/job.py', repo / 'config/market-dashboard.json',
                repo / 'ops/macos/run-market-dashboard.sh',
                repo / 'ops/macos' / f'{label}.plist', root / 'scripts/rotate_service_logs.py']
    for path in required:
        if not path.is_file() or not os.access(path, os.R_OK):
            raise ValueError('required CLI, config, wrapper or rotation policy is unreadable')
        with path.open('rb') as file:
            file.read(1)

def atomic_write(path, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.market-dashboard-', delete=False) as file:
            temporary = Path(file.name)
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)

def disable():
    result = launch('disable', job)
    if result.returncode:
        raise RuntimeError('could not disable job')
    if launch('print', job).returncode == 0 and launch('bootout', job).returncode:
        raise RuntimeError('could not unload job')

try:
    if (len(actions) > 1 or arguments.count('--allow-worktree') > 1
            or action not in ('--prepare', '--enable', '--disable', '--uninstall', '--restore')):
        raise ValueError('unknown action')
    validate_checkout()
    if action in ('--disable', '--uninstall', '--restore'):
        disable()
        if action == '--uninstall' and target.exists():
            # Keep both configuration and any pre-install backup recoverable.
            target.replace(target.with_suffix('.plist.disabled'))
        if action == '--restore':
            if not backup.exists():
                raise ValueError('no previous plist backup exists')
            atomic_write(target, backup.read_bytes())
        print('Job disabled. Snapshot state and logs retained; no job started.')
    else:
        agents.mkdir(parents=True, exist_ok=True, mode=0o700)
        logs = root / 'logs/market-dashboard'
        logs.mkdir(parents=True, exist_ok=True, mode=0o700)
        logs.chmod(0o700)
        for name in ('job.log', 'launchd.log'):
            fd = os.open(logs / name, os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
            os.fchmod(fd, 0o600)
            os.close(fd)
        template = repo / 'ops/macos' / f'{label}.plist'
        data = plistlib.loads(template.read_bytes())
        data['ProgramArguments'][1] = str(repo / 'ops/macos/run-market-dashboard.sh')
        data['WorkingDirectory'] = str(repo)
        data['EnvironmentVariables']['MARKET_DASHBOARD_PROJECT_ROOT'] = str(root)
        data['EnvironmentVariables']['MARKET_DASHBOARD_PYTHON'] = sys.executable
        data['StandardOutPath'] = data['StandardErrorPath'] = str(logs / 'launchd.log')
        rendered = plistlib.dumps(data, sort_keys=False)
        if not target.exists() or target.read_bytes() != rendered:
            if target.exists() and not backup.exists():
                shutil.copyfile(target, backup)
                backup.chmod(0o600)
            atomic_write(target, rendered)
        target.chmod(0o600)
        if action == '--enable':
            if launch('enable', job).returncode:
                raise RuntimeError('could not enable job')
            if launch('print', job).returncode:
                if launch('bootstrap', domain, str(target)).returncode:
                    raise RuntimeError('could not bootstrap job')
            print('Job enabled; five-minute timer uses the CLI 15-minute session gate.')
            print('If a loaded job used an older plist: --disable, then --enable to apply it.')
        else:
            print('Plist prepared only; no service loaded or started. Use --enable to opt in.')
        print('Disable: --disable. Uninstall (retains .plist.disabled, state and logs): --uninstall.')
        print('Restore pre-install .plist.bak without starting: --restore.')
except ValueError as error:
    # These messages are local validation constants; never include file contents.
    print(f'market dashboard service validation failed: {error}', file=sys.stderr)
    raise SystemExit(1)
except Exception:
    print('market dashboard service operation failed; inspect local files before retrying', file=sys.stderr)
    raise SystemExit(1)
PY
