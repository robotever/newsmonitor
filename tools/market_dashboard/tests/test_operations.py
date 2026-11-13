"""Exercise installers and wrappers in disposable roots; never load real jobs."""
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
OPS = REPO / 'ops/macos'
LABEL = 'com.robot-ever.newsmonitor.market-dashboard'


def health_module():
    common = subprocess.check_output(['git', 'rev-parse', '--git-common-dir'], cwd=REPO, text=True).strip()
    project = Path(common).resolve().parent.parent
    path = Path(os.environ.get('MARKET_DASHBOARD_TEST_PROJECT_ROOT', project)) / 'scripts/intake_health_check.py'
    if not path.exists():
        raise unittest.SkipTest('Financial Knowledge Repository health script is not available')
    spec = importlib.util.spec_from_file_location('dashboard_health_operations', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='dashboard ops ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / 'Financial Project'
        self.repo = self.root / 'newsmonitor'
        (self.repo / 'ops/macos').mkdir(parents=True)
        (self.root / 'scripts').mkdir()
        (self.root / 'scripts/rotate_service_logs.py').touch()
        self.env = {**os.environ, 'HOME': str(Path(self.tmp.name) / 'user home'),
                    'MARKET_DASHBOARD_PROJECT_ROOT': str(self.root),
                    'MARKET_DASHBOARD_PYTHON': sys.executable}
        self.env.pop('MARKET_DASHBOARD_PUBLISH_TOKEN', None)
        self.env.pop('MARKET_DASHBOARD_PUBLISH_URL', None)
        self.env.pop('MX_APIKEY', None)
        Path(self.env['HOME']).mkdir()

    def copy_ops(self):
        self.assertTrue((OPS / 'run-market-dashboard.sh').exists(), 'wrapper is missing')
        shutil.copytree(OPS, self.repo / 'ops/macos', dirs_exist_ok=True)

    def make_checkout(self):
        subprocess.run(['git', 'init', '-q', str(self.repo)], check=True, capture_output=True)
        (self.repo / 'tools/market_dashboard').mkdir(parents=True, exist_ok=True)
        (self.repo / 'tools/market_dashboard/job.py').touch()
        (self.repo / 'config').mkdir(exist_ok=True)
        (self.repo / 'config/market-dashboard.json').write_text('{}')

    def trap_launchctl(self):
        binary = self.root / 'bin'
        binary.mkdir(exist_ok=True)
        launchctl = binary / 'launchctl'
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/launchctl-calls"\n'
                             'if [ "$1" = print ]; then exit 1; fi\nexit 0\n')
        launchctl.chmod(0o755)
        self.env['PATH'] = f'{binary}:{os.environ["PATH"]}'

    def execute(self, script, *args):
        return subprocess.run(['/bin/bash', str(self.repo / 'ops/macos' / script), *args],
                              env=self.env, capture_output=True, text=True, timeout=15)

    def test_wrapper_loads_literal_dotenv_executes_cli_and_rotates_private_logs(self):
        self.copy_ops()
        package = self.repo / 'tools/market_dashboard'
        package.mkdir(parents=True)
        (self.repo / 'tools/__init__.py').touch()
        (package / '__init__.py').touch()
        (package / 'job.py').write_text(
            'import json, os, sys\nfrom pathlib import Path\n'
            'Path(os.environ["TEST_CAPTURE"]).write_text(json.dumps({'
            '"key":os.environ["MX_APIKEY"], "token":os.environ["MARKET_DASHBOARD_PUBLISH_TOKEN"],'
            '"state":os.environ["MARKET_DASHBOARD_STATE_ROOT"],"args":sys.argv[1:],"pid":os.getpid()}))\n')
        (self.root / '.env').write_text('export MX_APIKEY="synthetic $(touch should-not-exist)"\n'
                                      'MARKET_DASHBOARD_PUBLISH_TOKEN=synthetic-private\n')
        self.env['TEST_CAPTURE'] = str(self.root / 'capture.json')
        scripts = self.root / 'scripts'
        # Use the real existing rotation policy, never execute its CLI on live logs.
        health = health_module()
        shutil.copy(health.ROOT / 'scripts/rotate_service_logs.py', scripts)
        logs = self.root / 'logs/market-dashboard'
        logs.mkdir(parents=True)
        (logs / 'job.log').write_text('x' * 2_000_001)
        result = self.execute('run-market-dashboard.sh', '--dry-run')
        self.assertEqual(result.returncode, 0, result.stderr)
        captured = json.loads((self.root / 'capture.json').read_text())
        self.assertEqual(captured['key'], 'synthetic $(touch should-not-exist)')
        self.assertEqual(captured['token'], 'synthetic-private')
        self.assertEqual(captured['state'], str(self.root / 'state'))
        self.assertEqual(captured['args'], ['--dry-run'])
        self.assertFalse((self.repo / 'should-not-exist').exists())
        self.assertNotIn('synthetic-private', result.stdout + result.stderr)
        self.assertTrue((logs / 'job.log.1').exists())
        self.assertEqual(logs.stat().st_mode & 0o777, 0o700)
        self.assertEqual((logs / 'job.log').stat().st_mode & 0o777, 0o600)

    def test_log_directory_symlinks_fail_before_writes_or_launchctl(self):
        self.copy_ops()
        self.make_checkout()
        self.trap_launchctl()
        (self.root / 'scripts/rotate_service_logs.py').write_text('def rotate(path): pass\n')
        outside = Path(self.tmp.name) / 'outside logs'
        outside.mkdir(mode=0o755)
        sentinel = outside / 'sentinel.log'
        sentinel.write_text('retained')
        sentinel.chmod(0o644)
        for relative in ('logs', 'logs/market-dashboard'):
            link = self.root / relative
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside, target_is_directory=True)
            for script, args in (('run-market-dashboard.sh', ('--dry-run',)),
                                 ('install-market-dashboard-service.sh', ('--prepare',)),
                                 ('install-market-dashboard-service.sh', ('--enable',))):
                with self.subTest(relative=relative, script=script, args=args):
                    result = self.execute(script, *args)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(sentinel.read_text(), 'retained')
                    self.assertEqual(sentinel.stat().st_mode & 0o777, 0o644)
                    self.assertEqual(outside.stat().st_mode & 0o777, 0o755)
                    self.assertEqual(sorted(p.name for p in outside.iterdir()), ['sentinel.log'])
                    self.assertFalse((Path(self.env['HOME']) / 'Library/LaunchAgents').exists())
                    self.assertFalse((Path(self.env['HOME']) / 'launchctl-calls').exists())
            link.unlink()

    def test_direct_job_test_module_includes_close_freshness_tests(self):
        result = subprocess.run([sys.executable, '-m', 'tools.market_dashboard.tests.test_job', '-v'],
                                cwd=REPO, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CloseFreshnessTests.test_final_close_remains_fresh', result.stderr)

    def test_installer_renders_idempotently_without_starting_and_recovers_previous_file(self):
        self.copy_ops()
        self.make_checkout()
        agents = Path(self.env['HOME']) / 'Library/LaunchAgents'
        agents.mkdir(parents=True)
        target = agents / f'{LABEL}.plist'
        target.write_bytes(b'previous installation')
        # A trap records even an accidental launchctl command during prepare.
        binary = self.root / 'bin'
        binary.mkdir()
        launchctl = binary / 'launchctl'
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/launchctl-calls"\nexit 1\n')
        launchctl.chmod(0o755)
        self.env['PATH'] = f'{binary}:{os.environ["PATH"]}'
        first = self.execute('install-market-dashboard-service.sh', '--prepare')
        self.assertEqual(first.returncode, 0, first.stderr)
        data = target.read_bytes()
        plist = plistlib.loads(data)
        self.assertEqual(plist['StartInterval'], 300)
        self.assertEqual(plist['ProgramArguments'], ['/bin/bash', str(self.repo / 'ops/macos/run-market-dashboard.sh')])
        self.assertEqual(plist['EnvironmentVariables']['MARKET_DASHBOARD_PROJECT_ROOT'], str(self.root))
        self.assertFalse(plist.get('RunAtLoad', False))
        self.assertFalse(plist.get('KeepAlive', False))
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.with_suffix('.plist.bak').read_bytes(), b'previous installation')
        second = self.execute('install-market-dashboard-service.sh', '--prepare')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(target.read_bytes(), data)
        self.assertEqual(target.with_suffix('.plist.bak').read_bytes(), b'previous installation')
        self.assertFalse((Path(self.env['HOME']) / 'launchctl-calls').exists())
        self.assertIn('--disable', first.stdout)
        self.assertIn('--uninstall', first.stdout)

    def test_disable_uninstall_and_restore_preserve_configuration_without_bootstrap(self):
        self.copy_ops()
        self.make_checkout()
        agents = Path(self.env['HOME']) / 'Library/LaunchAgents'
        agents.mkdir(parents=True)
        target = agents / f'{LABEL}.plist'
        target.write_bytes(b'previous installation')
        binary = self.root / 'bin'
        binary.mkdir()
        launchctl = binary / 'launchctl'
        launchctl.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$HOME/launchctl-calls"\nexit 0\n')
        launchctl.chmod(0o755)
        self.env['PATH'] = f'{binary}:{os.environ["PATH"]}'
        self.assertEqual(self.execute('install-market-dashboard-service.sh', '--prepare').returncode, 0)
        prepared = target.read_bytes()
        for action in ('--disable', '--uninstall', '--restore'):
            result = self.execute('install-market-dashboard-service.sh', action)
            self.assertEqual(result.returncode, 0, result.stderr)
            if action == '--disable':
                self.assertEqual(target.read_bytes(), prepared)
            if action == '--uninstall':
                self.assertFalse(target.exists())
                self.assertEqual(target.with_suffix('.plist.disabled').read_bytes(), prepared)
        self.assertEqual(target.read_bytes(), b'previous installation')
        calls = (Path(self.env['HOME']) / 'launchctl-calls').read_text()
        self.assertIn('disable gui/', calls)
        self.assertIn('bootout gui/', calls)
        self.assertNotIn('bootstrap', calls)
        self.assertNotIn('kickstart', calls)

    def test_prepare_requires_real_project_rotation_policy_before_writing_agent(self):
        self.copy_ops()
        self.make_checkout()
        (self.root / 'scripts/rotate_service_logs.py').unlink()
        result = self.execute('install-market-dashboard-service.sh', '--prepare')
        self.assertNotEqual(result.returncode, 0)
        target = Path(self.env['HOME']) / f'Library/LaunchAgents/{LABEL}.plist'
        self.assertFalse(target.exists())

    def test_dotenv_preserves_hashes_backslashes_quotes_spaces_comments_and_environment(self):
        self.copy_ops()
        package = self.repo / 'tools/market_dashboard'
        package.mkdir(parents=True)
        (package / 'job.py').write_text('import json, os\nfrom pathlib import Path\n'
            'Path(os.environ["TEST_CAPTURE"]).write_text(json.dumps({key:value for key,value in os.environ.items() if key.startswith("SYNTH_")}))\n')
        (self.root / 'scripts/rotate_service_logs.py').write_text('def rotate(path): pass\n')
        (self.root / '.env').write_text(
            '# comment\nSYNTH_HASH=synthetic#suffix\n'
            'SYNTH_BACKSLASH=C:\\synthetic\\path\n'
            'SYNTH_SINGLE=\'single # value \\literal\' # trailing comment\n'
            'SYNTH_DOUBLE="double # value \\literal"  # trailing comment\n'
            'SYNTH_SPACES=  two  internal spaces  # ignored\n'
            'SYNTH_QUOTE=unquoted"quote\n'
            'SYNTH_OVERRIDE=dotenv-value\n'
            'SYNTH_COMMAND=$(touch synthetic-sentinel)\n')
        self.env['SYNTH_OVERRIDE'] = 'existing-environment'
        self.env['TEST_CAPTURE'] = str(self.root / 'capture.json')
        result = self.execute('run-market-dashboard.sh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'capture.json').read_text()), {
            'SYNTH_HASH': 'synthetic#suffix', 'SYNTH_BACKSLASH': 'C:\\synthetic\\path',
            'SYNTH_SINGLE': 'single # value \\literal', 'SYNTH_DOUBLE': 'double # value \\literal',
            'SYNTH_SPACES': 'two  internal spaces', 'SYNTH_QUOTE': 'unquoted"quote',
            'SYNTH_OVERRIDE': 'existing-environment', 'SYNTH_COMMAND': '$(touch synthetic-sentinel)'})
        self.assertFalse((self.repo / 'synthetic-sentinel').exists())
        self.assertNotIn('dotenv-value', result.stdout + result.stderr)

    def test_invalid_checkout_and_missing_cli_or_config_fail_before_writes_or_launchctl(self):
        self.copy_ops()
        self.trap_launchctl()
        for missing in ('.git', 'tools/market_dashboard/job.py', 'config/market-dashboard.json',
                        'ops/macos/run-market-dashboard.sh', f'ops/macos/{LABEL}.plist'):
            self.copy_ops()
            self.make_checkout()
            path = self.repo / missing
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            for action in ('--prepare', '--enable'):
                with self.subTest(missing=missing, action=action):
                    result = self.execute('install-market-dashboard-service.sh', action)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((Path(self.env['HOME']) / 'Library/LaunchAgents').exists())
                    self.assertFalse((Path(self.env['HOME']) / 'launchctl-calls').exists())
                    self.assertFalse((self.root / 'logs').exists())

    def test_worktree_requires_explicit_override_and_stable_checkout_can_enable(self):
        self.copy_ops()
        self.make_checkout()
        self.trap_launchctl()
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Synthetic',
                        '-c', 'user.email=synthetic@example.invalid', 'commit', '-qm', 'fixture'],
                       check=True, capture_output=True)
        stable_repo = self.repo
        worktree = self.root / 'isolated worktree'
        subprocess.run(['git', '-C', str(stable_repo), 'worktree', 'add', '--detach', str(worktree)],
                       check=True, capture_output=True)
        self.repo = worktree
        for action in ('--prepare', '--enable'):
            result = self.execute('install-market-dashboard-service.sh', action)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('--allow-worktree', result.stderr)
            self.assertFalse((Path(self.env['HOME']) / 'Library/LaunchAgents').exists())
            self.assertFalse((Path(self.env['HOME']) / 'launchctl-calls').exists())
            self.assertFalse((self.root / 'logs').exists())
        allowed = self.execute('install-market-dashboard-service.sh', '--prepare', '--allow-worktree')
        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertFalse((Path(self.env['HOME']) / 'launchctl-calls').exists())
        self.repo = stable_repo
        enabled = self.execute('install-market-dashboard-service.sh', '--enable')
        self.assertEqual(enabled.returncode, 0, enabled.stderr)
        calls = (Path(self.env['HOME']) / 'launchctl-calls').read_text()
        self.assertIn('enable gui/', calls)
        self.assertIn('bootstrap gui/', calls)
        self.assertNotIn('bootout', calls)
        self.assertNotIn('kickstart', calls)


class DashboardHealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.health = health_module()

    def check(self, clock, state=None, enabled=True, trading_dates=None):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            if state is not None:
                (root / 'market-dashboard').mkdir()
                (root / 'market-dashboard/last-success.json').write_text(json.dumps(state))
            errors, warnings = [], []
            self.health.check_market_dashboard_health(errors, warnings, state_root=root,
                now=datetime.fromisoformat(clock), enabled=enabled, trading_dates=trading_dates)
            return errors, warnings

    def test_uninstalled_is_informational_even_during_trading(self):
        errors, warnings = self.check('2026-11-13T10:20:00+08:00', enabled=False)
        self.assertEqual(errors, [])
        self.assertTrue(any('not yet enabled' in warning for warning in warnings))

    def test_installed_branch_rejects_invalid_config_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            repo = home / 'checkout'
            (repo / 'config').mkdir(parents=True)
            agents = home / 'Library/LaunchAgents'
            agents.mkdir(parents=True)
            (agents / f'{LABEL}.plist').write_bytes(plistlib.dumps({'WorkingDirectory': str(repo)}))
            bad_configs = [None, [], 7, {'schedule': None}, {'schedule': []},
                           {'schedule': {'tradingDates': None}},
                           {'schedule': {'tradingDates': '2026-11-13'}},
                           {'schedule': {'tradingDates': {}}},
                           {'schedule': {'tradingDates': [1]}},
                           {'schedule': {'tradingDates': ['not-a-date']}}]
            for config in bad_configs:
                with self.subTest(config=config):
                    (repo / 'config/market-dashboard.json').write_text(json.dumps(config))
                    errors, warnings = [], []
                    with patch.object(self.health.Path, 'home', return_value=home), patch.object(
                            self.health, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')) as launch:
                        self.health.check_market_dashboard_health(errors, warnings, state_root=home / 'state',
                            now=datetime.fromisoformat('2026-11-13T10:25:00+08:00'))
                    self.assertEqual(launch.call_args.args[0], ['launchctl', 'print', f'gui/{os.getuid()}/{LABEL}'])
                    self.assertTrue(any('configuration invalid' in item for item in errors + warnings))

    def test_expected_completed_bucket_is_required_after_ten_minute_grace(self):
        stale = {'bucket': '2026-11-13:intraday:09:45', 'mode': 'published',
                 'observedAt': '2026-11-13T09:46:00+08:00'}
        errors, _ = self.check('2026-11-13T10:25:00+08:00', stale)
        self.assertTrue(any('market dashboard' in error for error in errors))
        fresh = {'bucket': '2026-11-13:intraday:10:15', 'mode': 'published',
                 'observedAt': '2026-11-13T10:16:00+08:00'}
        self.assertEqual(self.check('2026-11-13T02:25:00+00:00', fresh)[0], [])
        self.assertEqual(self.check('2026-11-13T09:39:00+08:00')[0], [])

    def test_lunch_weekends_and_explicit_holidays_do_not_alert(self):
        for clock in ['2026-11-13T09:00:00+08:00', '2026-11-13T11:30:00+08:00',
                      '2026-11-13T12:00:00+08:00',
                      '2026-11-14T10:25:00+08:00']:
            with self.subTest(clock=clock):
                self.assertEqual(self.check(clock)[0], [])
        self.assertEqual(self.check('2026-11-13T10:25:00+08:00', trading_dates=['2026-11-12'])[0], [])

    def test_close_is_required_only_at_close_deadline_and_has_to_be_published(self):
        self.assertEqual(self.check('2026-11-13T15:29:00+08:00')[0], [])
        self.assertTrue(self.check('2026-11-13T15:30:00+08:00')[0])
        self.assertTrue(self.check('2026-11-13T15:31:00+08:00')[0])
        self.assertTrue(self.check('2026-11-13T17:00:00+08:00')[0])
        close = {'bucket': '2026-11-13:close', 'mode': 'published',
                 'observedAt': '2026-11-13T15:05:00+08:00'}
        self.assertEqual(self.check('2026-11-13T15:30:00+08:00', close)[0], [])
        self.assertEqual(self.check('2026-11-13T17:00:00+08:00', close)[0], [])
        close['mode'] = 'fixture'
        self.assertTrue(self.check('2026-11-13T15:30:00+08:00', close)[0])


if __name__ == '__main__':
    unittest.main()
