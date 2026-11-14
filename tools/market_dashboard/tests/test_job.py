"""Offline job contracts: scheduling, validation, publication and fixture flow."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
import json
import io
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from tools.market_dashboard import job
from tools.market_dashboard.concepts import load_concept_config
from tools.market_dashboard.scoring import load_config


NOW = datetime.fromisoformat('2026-11-13T10:15:00+08:00')


class ScheduleTests(unittest.TestCase):
    def test_state_root_override_and_precedence_without_logging_paths(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fake_module = root / 'project/newsmonitor/tools/market_dashboard/job.py'
            for explicit, override, expected in [
                (None, None, root / 'project/state'),
                (None, str(root / 'env state'), root / 'env state'),
                (root / 'explicit state', str(root / 'ignored state'), root / 'explicit state'),
            ]:
                deps = {'now': NOW.replace(day=14)}
                if explicit:
                    deps['state_root'] = explicit
                with self.subTest(expected=expected), patch.object(job, '__file__', str(fake_module)), patch.dict(job.os.environ, {}, clear=True):
                    if override:
                        job.os.environ['MARKET_DASHBOARD_STATE_ROOT'] = override
                    output = io.StringIO()
                    with redirect_stdout(output):
                        result = job.run_job({}, deps)
                    self.assertEqual(result.status, 'outside_schedule')
                    self.assertTrue((expected / 'market-dashboard/job.lock').exists())
                    self.assertNotIn(str(root), output.getvalue())

    def test_shanghai_sessions_lunch_weekends_and_close(self):
        for clock, expected in [('09:29', False), ('09:30', True), ('11:29', True),
                                ('11:30', False), ('12:00', False), ('13:00', True),
                                ('14:59', True), ('15:00', True), ('15:15', True),
                                ('15:31', False)]:
            with self.subTest(clock=clock):
                now = datetime.fromisoformat(f'2026-11-13T{clock}:00+08:00')
                self.assertEqual(job.should_collect(now, {}, {}), expected)
        self.assertFalse(job.should_collect(datetime.fromisoformat('2026-11-14T10:00:00+08:00'), {}, {}))
        # Equivalent UTC time must land in the same session.
        self.assertTrue(job.should_collect(datetime.fromisoformat('2026-11-13T02:15:00+00:00'), {}, {}))

    def test_bucket_is_idempotent_and_final_close_only_once(self):
        state = {'bucket': '2026-11-13:intraday:10:15'}
        self.assertFalse(job.should_collect(NOW.replace(minute=29), state, {}))
        self.assertTrue(job.should_collect(NOW.replace(minute=30), state, {}))
        close = {'bucket': '2026-11-13:close'}
        self.assertFalse(job.should_collect(NOW.replace(hour=15, minute=20), close, {}))
        self.assertTrue(job.should_collect(NOW.replace(day=16, hour=15, minute=0), close, {}))

    def test_explicit_calendar_excludes_weekday_holidays(self):
        config = {'schedule': {'tradingDates': ['2026-11-12']}}
        self.assertFalse(job.should_collect(NOW, {}, config))
        with self.assertRaises(ValueError):
            job.should_collect(NOW.replace(tzinfo=None), {}, {})


def valid_payload():
    def obj(id):
        return {'id': id, 'strength': 50, 'heat': None, 'risk': None,
                'completeness': 10, 'missing': ['unavailable'], 'contributors': [],
                'sourceTimestamps': [{'source': 'Wind', 'timestamp': NOW.isoformat()}],
                'change1d': None, 'change5d': None}
    def concept(index, dynamic=False):
        item = obj(f'884{2000 + index}.WI')
        item['name'] = f'概念{index}'
        if dynamic:
            item.update(selectionScore=60, selectedOn='2026-11-13', retainedTradingDays=1)
        return item
    return {'schemaVersion': 'market-dashboard-v2', 'scoringVersion': 'market-score-v0.1',
            'observedAt': NOW.isoformat(), 'marketDate': '2026-11-13', 'session': 'intraday',
            'global': obj('global'), 'aShare': {**obj('a-share'), 'stage': None},
            'styles': [obj(code) for code, _ in job.STYLE_DEFINITIONS],
            'industries': [obj(code) for code, _ in job.INDUSTRY_DEFINITIONS],
            'concepts': {'selectionVersion': 'concept-selection-v0.1',
                         'scoringVersion': 'concept-score-v0.1', 'selectedAt': NOW.isoformat(),
                         'core': [concept(index) for index in range(25)],
                         'dynamic': [concept(index, True) for index in range(25, 35)]},
            'dataStatus': {'completeness': 10, 'stale': False, 'missing': ['unavailable']}}


def v2_payload():
    payload = valid_payload()
    payload['sourceMode'] = {'breadth': 'wind', 'styles': 'wind', 'industries': 'wind',
                             'concepts': 'wind', 'conceptDiscovery': 'mx', 'global': {}}
    return payload


class Response:
    def __init__(self, status=201):
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class PublishTests(unittest.TestCase):
    def test_bearer_json_timeout_and_no_secret_in_result(self):
        requests = []
        def transport(request, timeout):
            requests.append((request, timeout))
            return Response()
        with patch.object(job, 'urlopen', transport):
            result = job.publish_payload(valid_payload(), 'https://example.test/publish', 'private-token', 8)
        self.assertTrue(result.success)
        self.assertEqual(requests[0][0].get_header('Authorization'), 'Bearer private-token')
        self.assertEqual(requests[0][0].get_header('Content-type'), 'application/json')
        self.assertEqual(requests[0][0].get_header('User-agent'), 'NewsmonitorMarketDashboard/1.0')
        self.assertEqual(requests[0][1], 8)
        self.assertEqual(json.loads(requests[0][0].data)['styles'][0]['id'], '000300.SH')
        self.assertNotIn('private-token', repr(result))

    def test_network_and_5xx_retry_but_4xx_never_retry(self):
        for status, expected_calls in [(503, 3), (429, 1), (401, 1), (400, 1), (None, 3)]:
            calls = []
            def transport(request, timeout):
                calls.append(request)
                if status is None:
                    raise URLError('private-token provider detail')
                raise HTTPError(request.full_url, status, 'private-token', None, None)
            with self.subTest(status=status), patch.object(job, 'urlopen', transport), patch.object(job.time, 'sleep'):
                result = job.publish_payload(valid_payload(), 'https://example.test/publish', 'private-token', 8)
                self.assertFalse(result.success)
                self.assertEqual(len(calls), expected_calls)
                self.assertEqual(result.attempts, expected_calls)
                self.assertNotIn('private-token', repr(result))

    def test_transient_failure_can_recover(self):
        calls = []
        def transport(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise TimeoutError('private-token')
            return Response(200)
        with patch.object(job, 'urlopen', transport), patch.object(job.time, 'sleep'):
            result = job.publish_payload(valid_payload(), 'https://example.test/publish', 'private-token', 8)
        self.assertTrue(result.success)
        self.assertEqual(result.attempts, 2)

    def test_invalid_payloads_are_rejected_before_network(self):
        mutations = [lambda p: p.update(schemaVersion='old'),
                     lambda p: p.update(scoringVersion='old'),
                     lambda p: p.pop('observedAt'),
                     lambda p: p.update(observedAt='2026-11-13T10:15:00'),
                     lambda p: p['global'].update(strength=101),
                     lambda p: p['global'].update(strength=42.2),
                     lambda p: p['dataStatus'].update(completeness=100),
                     lambda p: p['global'].update(completeness=0),
                     lambda p: p['global'].update(strength=float('nan')),
                     lambda p: p['dataStatus'].update(completeness=-1),
                     lambda p: p['dataStatus'].update(completeness=0),
                     lambda p: p['industries'].pop(),
                     lambda p: p['styles'][-1].update(id=p['styles'][0]['id']),
                     lambda p: p['global'].update(rawRows=[]),
                     lambda p: p['aShare'].update(stage='扩张'),
                     lambda p: p['global'].pop('missing'),
                     lambda p: p['global'].update(sourceTimestamps=[])]
        for mutate in mutations:
            payload = valid_payload()
            mutate(payload)
            with self.subTest(mutation=mutate), patch.object(job, 'urlopen') as network:
                result = job.publish_payload(payload, 'https://example.test/publish', 'private-token', 8)
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, 'INVALID_PAYLOAD')
                network.assert_not_called()

    def test_low_completeness_permitted_and_configurable_minimum_enforced(self):
        job.validate_payload(valid_payload(), load_config())
        config = load_config()
        config['publication'] = {'minimumCompleteness': 20}
        with self.assertRaises(job.ValidationError):
            job.validate_payload(valid_payload(), config)

    def test_cold_start_discount_does_not_require_invented_missing_inputs(self):
        payload = valid_payload()
        for obj in [payload['global'], payload['aShare'], *payload['styles'], *payload['industries'],
                    *payload['concepts']['core'], *payload['concepts']['dynamic']]:
            obj.update(strength=50, heat=60, risk=40, completeness=85, missing=[])
        payload['dataStatus'].update(completeness=85, missing=[])
        job.validate_payload(payload)

    def test_missing_token_and_insecure_target_are_rejected(self):
        for url, token in [('https://example.test', ''), ('http://example.test', 'private-token'),
                           ('https://user:private-token@example.test', 'private-token')]:
            with self.subTest(url=url), patch.object(job, 'urlopen') as network:
                self.assertFalse(job.publish_payload(valid_payload(), url, token, 8).success)
                network.assert_not_called()


class JobTests(unittest.TestCase):
    def args(self, **overrides):
        return SimpleNamespace(**({'dry_run': False, 'fixture': False, 'force': False,
                                   'skip_publish': False, 'url': 'https://example.test/publish',
                                   'token': 'private-token', 'timeout': 8} | overrides))

    def deps(self, directory, **overrides):
        return {'now': NOW, 'state_root': Path(directory),
                'collector': lambda config: job.collect_batches(config, fixture=True),
                'publisher': lambda *args, **kwargs: job.PublishResult(True, 201, 1)} | overrides

    def test_fixture_end_to_end_missing_fields_safe_metadata_no_writes(self):
        with TemporaryDirectory() as directory:
            result = job.run_job(self.args(fixture=True, dry_run=True),
                                 {'state_root': Path(directory)})
            self.assertTrue(result.success, result.error_code)
            payload = result.payload
            self.assertIsInstance(payload['global'], dict)
            self.assertIsInstance(payload['aShare'], dict)
            self.assertEqual(len(payload['styles']), 6)
            self.assertEqual(len(payload['industries']), 35)
            job.validate_payload(payload)
            for industry in payload['industries']:
                for missing in ('advancingShare', 'decliningShare', 'relativeReturn5d',
                                'relativeReturn20d', 'mediumTrendDeterioration'):
                    self.assertIn(missing, industry['missing'])
                self.assertLess(industry['completeness'], 100)
            self.assertEqual(payload['sourceMode']['global'], {'DGS10': 'fred', 'gold': 'mx'})
            self.assertEqual(payload['sourceMode']['industries'], 'wind')
            self.assertEqual(list(Path(directory).rglob('*')), [])
            public = json.dumps(payload, ensure_ascii=False)
            for raw_key in ('rawRows', '_units', '最新成交额', 'SYNTHETIC_GOLD', 'private-token', 'indicators'):
                self.assertNotIn(raw_key, public)

    def test_v2_fixture_contains_strict_core_and_dynamic_concepts(self):
        with TemporaryDirectory() as directory:
            result = job.run_job(self.args(fixture=True, dry_run=True),
                                 {'state_root': Path(directory)})
        self.assertTrue(result.success, result.error_code)
        payload = result.payload
        self.assertEqual(payload['schemaVersion'], 'market-dashboard-v2')
        self.assertEqual(len(payload['concepts']['core']), 25)
        self.assertEqual(len(payload['concepts']['dynamic']), 10)
        core = {item['id'] for item in payload['concepts']['core']}
        dynamic = {item['id'] for item in payload['concepts']['dynamic']}
        self.assertEqual(len(core), 25)
        self.assertEqual(len(dynamic), 10)
        self.assertFalse(core & dynamic)
        self.assertEqual(payload['sourceMode']['concepts'], 'wind')
        self.assertEqual(payload['sourceMode']['conceptDiscovery'], 'mx')
        self.assertLessEqual(len(json.dumps(payload, ensure_ascii=False).encode()), 256 * 1024)
        job.validate_payload(payload)

    def test_v2_validation_rejects_concept_count_overlap_and_metadata_mutations(self):
        mutations = [
            lambda p: p['concepts']['core'].pop(),
            lambda p: p['concepts']['dynamic'].pop(),
            lambda p: p['concepts']['dynamic'][0].update(id=p['concepts']['core'][0]['id']),
            lambda p: p['concepts']['dynamic'][0].update(retainedTradingDays=0),
            lambda p: p['concepts']['dynamic'][0].update(selectionScore=101),
            lambda p: p['sourceMode'].update(concepts='mx'),
        ]
        for mutate in mutations:
            payload = v2_payload()
            mutate(payload)
            with self.subTest(mutation=mutate), self.assertRaises(job.ValidationError):
                job.validate_payload(payload, load_config())

    def test_concept_collection_failure_preserves_last_selection_or_fails_closed(self):
        from tools.market_dashboard.sources import SourceBatch
        with TemporaryDirectory() as directory:
            deps = self.deps(directory)
            first = job.run_job(self.args(), deps)
            self.assertTrue(first.success, first.error_code)
            previous = first.payload['concepts']
            def failed_concepts(config):
                batches = job.collect_batches(config, fixture=True)
                batches['concepts'] = SourceBatch('Wind', source_mode='wind',
                    errors=[{'source': 'Wind', 'code': 'backend_error', 'group': 'concepts'}])
                return batches
            second = job.run_job(self.args(), deps | {'now': NOW.replace(minute=30),
                                                       'collector': failed_concepts})
            self.assertTrue(second.success, second.error_code)
            self.assertEqual(second.payload['concepts'], previous)
            self.assertTrue(second.payload['dataStatus']['stale'])

        with TemporaryDirectory() as directory:
            result = job.run_job(self.args(), self.deps(directory, collector=failed_concepts))
            self.assertFalse(result.success)
            self.assertEqual(result.error_code, 'COLLECTION_FAILED')

    def test_close_selection_advances_once_and_duplicate_does_not_collect(self):
        close = NOW.replace(hour=15, minute=5)
        def close_batches(config):
            batches = job.collect_batches(config, fixture=True)
            for group in ('breadth', 'styles', 'industries', 'concepts'):
                for row in batches[group].rows:
                    row['_timestamp'] = '2026-11-13T15:00:02+08:00'
            return batches
        with TemporaryDirectory() as directory:
            deps = self.deps(directory, now=close, collector=close_batches)
            first = job.run_job(self.args(), deps)
            self.assertTrue(first.success, first.error_code)
            retained = [item['retainedTradingDays'] for item in first.payload['concepts']['dynamic']]
            duplicate = job.run_job(self.args(force=True), deps | {
                'now': close.replace(minute=20),
                'collector': lambda config: self.fail('duplicate close collected again'),
            })
            self.assertEqual(duplicate.status, 'duplicate')
            state = json.loads((Path(directory) / 'market-dashboard/last-success.json').read_text())
            self.assertEqual([item['retainedTradingDays'] for item in state['payload']['concepts']['dynamic']], retained)

    def test_next_day_intraday_reuses_roster_without_advancing_hold_days(self):
        with TemporaryDirectory() as directory:
            first = job.run_job(self.args(), self.deps(directory))
            self.assertTrue(first.success, first.error_code)
            previous = first.payload['concepts']
            next_day = NOW.replace(day=16)
            def next_day_batches(config):
                batches = job.collect_batches(config, fixture=True)
                for group in ('breadth', 'styles', 'industries', 'concepts'):
                    for row in batches[group].rows:
                        row['_timestamp'] = next_day.isoformat()
                return batches
            second = job.run_job(self.args(), self.deps(
                directory, now=next_day, collector=next_day_batches))
            self.assertTrue(second.success, second.error_code)
            self.assertEqual([item['id'] for item in second.payload['concepts']['dynamic']],
                             [item['id'] for item in previous['dynamic']])
            self.assertEqual([item['retainedTradingDays'] for item in second.payload['concepts']['dynamic']],
                             [item['retainedTradingDays'] for item in previous['dynamic']])
            self.assertEqual(second.payload['concepts']['selectedAt'], previous['selectedAt'])

    def test_cold_start_uses_config_and_never_hardcoded_bounds(self):
        config = load_config()
        batches = job.collect_batches(config, fixture=True)
        inputs = job.derive_inputs(batches, NOW, config)
        scored = job.build_dashboard_payload(inputs, [], config)
        self.assertEqual(scored['global']['strength'], 59)
        self.assertEqual(scored['global']['completeness'], 9)
        config['normalization']['fixedBounds']['DGS10'] = {'min': 0, 'max': 20}
        inputs = job.derive_inputs(batches, NOW, config)
        self.assertEqual(job.build_dashboard_payload(inputs, [], config)['global']['strength'], 80)
        del config['normalization']['fixedBounds']['DGS10']
        inputs = job.derive_inputs(batches, NOW, config)
        scored = job.build_dashboard_payload(inputs, [], config)
        self.assertIsNone(scored['global']['strength'])
        self.assertIn('ratesLiquidity', scored['global']['missing'])
        # Once sufficient observations exist, removing cold bounds must not lose evidence.
        row = batches['global'].rows[0]
        row['history'] = [{'value': v, 'timestamp': NOW.isoformat()} for v in range(20)]
        inputs = job.derive_inputs(batches, NOW, config)
        self.assertIsNotNone(job.build_dashboard_payload(inputs, [], config)['global']['strength'])

    def test_success_duplicate_and_close_state_and_health(self):
        with TemporaryDirectory() as directory:
            deps = self.deps(directory)
            first = job.run_job(self.args(), deps)
            self.assertTrue(first.success, first.error_code)
            state_path = Path(directory) / 'market-dashboard/last-success.json'
            state = json.loads(state_path.read_text())
            self.assertEqual(state['bucket'], '2026-11-13:intraday:10:15')
            self.assertEqual(state['mode'], 'published')
            self.assertEqual(state['payload']['sourceMode']['global']['DGS10'], 'fred')
            def unexpected_collection(config):
                self.fail('Repeated bucket collected again')
            duplicate = job.run_job(self.args(force=True), deps | {'collector': unexpected_collection})
            self.assertTrue(duplicate.success)
            self.assertEqual(duplicate.status, 'duplicate')
            health = json.loads((Path(directory) / 'service-health/market-dashboard.json').read_text())
            self.assertEqual(health['lastPublishStatus'], 'published')
            self.assertIn('sourceCounts', health)
            self.assertIn('completeness', health)
            self.assertNotIn('private-token', json.dumps(health))

    def test_publication_failure_preserves_success_and_redacts_health(self):
        with TemporaryDirectory() as directory:
            deps = self.deps(directory)
            self.assertTrue(job.run_job(self.args(), deps).success)
            state_path = Path(directory) / 'market-dashboard/last-success.json'
            previous = state_path.read_bytes()
            deps.update(now=NOW.replace(minute=30),
                        publisher=lambda *a, **k: job.PublishResult(False, 401, 1, 'HTTP_401'))
            failed = job.run_job(self.args(), deps)
            self.assertFalse(failed.success)
            self.assertEqual(state_path.read_bytes(), previous)
            health = json.loads((Path(directory) / 'service-health/market-dashboard.json').read_text())
            self.assertEqual(health['stage'], 'publish')
            self.assertEqual(health['lastPublishStatus'], 'failed')
            self.assertEqual(health['errorCode'], 'HTTP_401')

    def test_force_bypasses_only_schedule_and_validation_still_runs(self):
        with TemporaryDirectory() as directory:
            deps = self.deps(directory, now=NOW.replace(hour=12))
            self.assertEqual(job.run_job(self.args(), deps).status, 'outside_schedule')
            deps['builder'] = lambda inputs, previous, config: valid_payload() | {'schemaVersion': 'old'}
            with patch.object(job, 'urlopen') as network:
                result = job.run_job(self.args(force=True), deps)
                self.assertFalse(result.success)
                self.assertEqual(result.error_code, 'INVALID_PAYLOAD')
                network.assert_not_called()
            self.assertFalse((Path(directory) / 'market-dashboard/last-success.json').exists())

    def test_skip_publish_and_dry_run_do_not_replace_last_success(self):
        with TemporaryDirectory() as directory:
            deps = self.deps(directory)
            self.assertTrue(job.run_job(self.args(), deps).success)
            state_path = Path(directory) / 'market-dashboard/last-success.json'
            previous = state_path.read_bytes()
            deps['now'] = NOW.replace(minute=30)
            for flag in ('skip_publish', 'dry_run'):
                result = job.run_job(self.args(**{flag: True}), deps)
                self.assertTrue(result.success)
                self.assertEqual(state_path.read_bytes(), previous)

    def test_lock_prevents_concurrent_collection_and_releases_on_error(self):
        import fcntl
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'market-dashboard'
            path.mkdir()
            with (path / 'job.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = job.run_job(self.args(), self.deps(directory))
                self.assertEqual(result.status, 'locked')
            def broken(config):
                raise RuntimeError('private-token upstream raw response')
            result = job.run_job(self.args(), self.deps(directory, collector=broken))
            self.assertFalse(result.success)
            self.assertNotIn('private-token', repr(result))
            health = (Path(directory) / 'service-health/market-dashboard.json').read_text()
            self.assertNotIn('private-token', health)
            self.assertTrue(job.run_job(self.args(), self.deps(directory)).success)

    def test_live_dry_run_skips_collector_when_production_lock_is_held(self):
        import fcntl
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'market-dashboard'
            path.mkdir()
            calls = []
            def collector(config):
                calls.append('collected')
                return job.collect_batches(config, fixture=True)
            with (path / 'job.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                result = job.run_job(self.args(dry_run=True), self.deps(directory, collector=collector))
            self.assertTrue(result.success)
            self.assertEqual(result.status, 'locked')
            self.assertEqual(calls, [])
            self.assertEqual(list(Path(directory).rglob('*.json')), [])

    def test_live_dry_run_holds_shared_lock_but_writes_no_snapshot_or_health(self):
        import fcntl
        with TemporaryDirectory() as directory:
            lock_path = Path(directory) / 'market-dashboard/job.lock'
            lock_path.parent.mkdir()
            calls, held_during_collection = [], []
            def collector(config):
                calls.append('collected')
                with lock_path.open('a') as contender:
                    try:
                        fcntl.flock(contender, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        held_during_collection.append(True)
                    else:
                        held_during_collection.append(False)
                return job.collect_batches(config, fixture=True)
            result = job.run_job(self.args(dry_run=True), self.deps(directory, collector=collector))
            self.assertTrue(result.success, result.error_code)
            self.assertEqual(result.status, 'dry_run')
            self.assertEqual(calls, ['collected'])
            self.assertEqual(held_during_collection, [True])
            self.assertEqual(list(Path(directory).rglob('*.json')), [])
            self.assertEqual(lock_path.read_bytes(), b'')
            with lock_path.open('a') as released:
                fcntl.flock(released, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_source_observations_during_collection_use_completion_clock(self):
        clocks = iter([NOW, NOW.replace(minute=16)])
        def collector(config):
            batches = job.collect_batches(config, fixture=True)
            for group in ('breadth', 'styles', 'industries'):
                for row in batches[group].rows:
                    row['_timestamp'] = '2026-11-13T10:15:30+08:00'
            return batches
        with TemporaryDirectory() as directory:
            result = job.run_job(self.args(), self.deps(directory, now=lambda: next(clocks), collector=collector))
            self.assertTrue(result.success, result.error_code)
            self.assertEqual(result.payload['observedAt'], '2026-11-13T10:16:00+08:00')

    def test_unused_global_rows_do_not_advance_scored_observation_clock(self):
        config = load_config()
        batches = job.collect_batches(config, fixture=True)
        batches['global'].rows[1]['timestamp'] = NOW.isoformat()
        inputs = job.derive_inputs(batches, NOW, config)
        self.assertEqual(inputs['global']['observedAt'], '2026-11-12T00:00:00+00:00')

    def test_wrong_global_units_remain_unavailable(self):
        config = load_config()
        batches = job.collect_batches(config, fixture=True)
        batches['global'].rows[0]['unit'] = 'USD'
        inputs = job.derive_inputs(batches, NOW, config)
        scored = job.build_dashboard_payload(inputs, [], config)
        self.assertIsNone(scored['global']['strength'])
        self.assertIn('ratesLiquidity', scored['global']['missing'])

    def test_stale_or_incompatible_units_never_enter_scores(self):
        config = load_config()
        batches = job.collect_batches(config, fixture=True)
        industry = batches['industries'].rows[0]
        industry['_timestamp'] = '2026-11-12T10:15:00+08:00'
        industry['_units']['最新成交额(亿元)'] = 'USD'
        inputs = job.derive_inputs(batches, NOW, config)
        scored = job.build_dashboard_payload(inputs, [], config)
        self.assertEqual(scored['industries'][0]['completeness'], 0)
        self.assertIsNone(scored['industries'][0]['strength'])
        self.assertTrue(scored['dataStatus']['stale'])
        batches = job.collect_batches(config, fixture=True)
        industry = batches['industries'].rows[0]
        industry['_units']['最新主力净流入额(亿元)'] = 'USD'
        inputs = job.derive_inputs(batches, NOW, config)
        self.assertFalse(inputs['industries'][0]['indicators']['mainFlowDirection']['available'])

    def test_fixture_dry_run_ignores_live_state_and_prints_compact_summary(self):
        with TemporaryDirectory() as directory:
            deps = self.deps(directory)
            self.assertTrue(job.run_job(self.args(), deps).success)
            result = job.run_job(self.args(fixture=True, dry_run=True), {'state_root': Path(directory)})
            self.assertEqual(result.status, 'dry_run')
            self.assertEqual(result.payload['global']['change1d'], None)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(job.main(['--fixture', '--dry-run']), 0)
        summary = json.loads(output.getvalue())
        self.assertEqual(summary['objectCounts'], {'global': 1, 'aShare': 1, 'styles': 6,
                                                   'industries': 35, 'coreConcepts': 25,
                                                   'dynamicConcepts': 10})
        self.assertTrue(summary['synthetic'])
        self.assertLess(len(output.getvalue()), 500)

    def test_final_close_rejects_intraday_observations_then_is_idempotent(self):
        def close_batches(config, clock):
            batches = job.collect_batches(config, fixture=True)
            for group in ('breadth', 'styles', 'industries', 'concepts'):
                for row in batches[group].rows:
                    row['_timestamp'] = f'2026-11-13T{clock}:00+08:00'
            return batches
        with TemporaryDirectory() as directory:
            deps = self.deps(directory, now=NOW.replace(hour=15, minute=5),
                             collector=lambda config: close_batches(config, '14:55'))
            premature = job.run_job(self.args(), deps)
            self.assertFalse(premature.success)
            deps['collector'] = lambda config: close_batches(config, '15:00')
            final = job.run_job(self.args(), deps)
            self.assertTrue(final.success, final.error_code)
            self.assertEqual(final.payload['session'], 'close')
            self.assertEqual(job.run_job(self.args(), deps | {'now': NOW.replace(hour=15, minute=25)}).status, 'duplicate')

    def test_yuan_and_hundred_million_yuan_are_equivalent_for_ratios(self):
        config = load_config()
        original = job.collect_batches(config, fixture=True)
        changed = deepcopy(original)
        for row in changed['industries'].rows:
            for field in ('最新成交额(亿元)', '最新主力净流入额(亿元)'):
                row[field] *= 100000000
                row['_units'][field] = '元'
        first = job.build_dashboard_payload(job.derive_inputs(original, NOW, config), [], config)
        second = job.build_dashboard_payload(job.derive_inputs(changed, NOW, config), [], config)
        self.assertEqual(first['industries'], second['industries'])

    def test_fixture_mode_cannot_publish_to_live_target(self):
        with TemporaryDirectory() as directory:
            result = job.run_job(self.args(fixture=True), self.deps(directory))
            self.assertFalse(result.success)
            self.assertEqual(result.error_code, 'FIXTURE_PUBLISH_DISABLED')
            self.assertFalse((Path(directory) / 'market-dashboard/last-success.json').exists())


class CloseFreshnessTests(unittest.TestCase):
    def test_final_close_remains_fresh_during_afternoon_and_evening(self):
        row = {'_timestamp': '2026-11-13T15:00:03+08:00'}
        for clock in ('2026-11-13T15:30:04+08:00', '2026-11-13T17:45:00+08:00',
                      '2026-11-13T23:59:59+08:00', '2026-11-13T15:59:59Z'):
            with self.subTest(clock=clock):
                self.assertTrue(job._fresh(row, datetime.fromisoformat(clock)))

    def test_final_close_expires_at_next_shanghai_date_and_rejects_future(self):
        row = {'_timestamp': '2026-11-13T15:00:03+08:00'}
        for clock in ('2026-11-14T00:00:00+08:00', '2026-11-13T16:00:00Z',
                      '2026-11-13T15:00:02+08:00'):
            with self.subTest(clock=clock):
                self.assertFalse(job._fresh(row, datetime.fromisoformat(clock)))

    def test_close_does_not_promote_preclose_or_previous_day_quotes(self):
        now = datetime.fromisoformat('2026-11-13T16:00:00+08:00')
        for clock in ('2026-11-13T14:59:59+08:00', '2026-11-12T15:00:03+08:00'):
            with self.subTest(clock=clock):
                self.assertFalse(job._fresh({'_timestamp': clock}, now))
        intraday = datetime.fromisoformat('2026-11-13T14:59:00+08:00')
        self.assertTrue(job._fresh({'_timestamp': '2026-11-13T14:29:00+08:00'}, intraday))
        self.assertFalse(job._fresh({'_timestamp': '2026-11-13T14:28:59+08:00'}, intraday))


if __name__ == '__main__':
    unittest.main()
