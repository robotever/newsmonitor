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

    def copy_ops(self):
        self.assertTrue((OPS / 'run-market-dashboard.sh').exists(), 'wrapper is missing')
        shutil.copytree(OPS, self.repo / 'ops/macos', dirs_exist_ok=True)

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

    def test_installer_renders_idempotently_without_starting_and_recovers_previous_file(self):
        self.copy_ops()
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
        (self.root / 'scripts/rotate_service_logs.py').unlink()
        result = self.execute('install-market-dashboard-service.sh', '--prepare')
        self.assertNotEqual(result.returncode, 0)
        target = Path(self.env['HOME']) / f'Library/LaunchAgents/{LABEL}.plist'
        self.assertFalse(target.exists())


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
