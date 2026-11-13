"""Local collection and publication of derived market dashboard snapshots."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener
from zoneinfo import ZoneInfo
import argparse
import fcntl
import json
import math
import os
import re
import time

from . import sources
from .scoring import load_config, build_dashboard_payload, score_family
from .sources import STYLE_DEFINITIONS, INDUSTRY_DEFINITIONS


SHANGHAI = ZoneInfo('Asia/Shanghai')


def _local(now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError('Clock requires a timezone')
    return now.astimezone(SHANGHAI)


def _bucket(now):
    local = _local(now)
    minute = local.hour * 60 + local.minute
    if minute >= 15 * 60:
        return f'{local.date()}:close'
    return f'{local.date()}:intraday:{local.hour:02d}:{local.minute // 15 * 15:02d}'


def should_collect(now, state, config):
    """Weekday session gate, optionally restricted by an explicit trading calendar.

    Default weekdays are a scheduling approximation, never a comparison calendar.
    The close catch-up window is 15:00–15:30, producing a single final snapshot.
    """
    local = _local(now)
    dates = config.get('schedule', {}).get('tradingDates')
    if local.weekday() >= 5 or dates is not None and str(local.date()) not in dates:
        return False
    minute = local.hour * 60 + local.minute
    scheduled = 570 <= minute < 690 or 780 <= minute < 900 or 900 <= minute <= 930
    return scheduled and state.get('bucket') != _bucket(now)



@dataclass(frozen=True)
class PublishResult:
    success: bool
    status_code: int | None = None
    attempts: int = 0
    error_code: str | None = None


class ValidationError(ValueError):
    """Deliberately carries no payload, credential or upstream message."""


def _require(condition):
    if not condition:
        raise ValidationError('INVALID_PAYLOAD')


def _numeric(value, low=0, high=100):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and low <= value <= high)


def _timestamp(value):
    _require(isinstance(value, str))
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError('INVALID_PAYLOAD') from None
    _require(parsed.tzinfo is not None and parsed.utcoffset() is not None)
    return parsed


def _strings(value):
    return isinstance(value, list) and all(isinstance(s, str) and len(s) <= 200 for s in value)


def validate_payload(payload, config=None):
    """Validate derived-only v1 shape, identity coverage and evidence before I/O.

    70/50 are evidence/stage thresholds, not publication minimums. A configurable
    publication.minimumCompleteness defaults to >0; nullable scores stay missing.
    """
    config = config or load_config()
    _require(isinstance(payload, dict))
    required = {'schemaVersion', 'scoringVersion', 'observedAt', 'marketDate', 'session',
                'global', 'aShare', 'styles', 'industries', 'dataStatus'}
    _require(required <= payload.keys() and payload.keys() <= required | {'sourceMode'})
    _require(payload['schemaVersion'] == config['schemaVersion']
             and payload['scoringVersion'] == config['scoringVersion'])
    observed = _timestamp(payload['observedAt'])
    _require(payload['marketDate'] == str(observed.astimezone(SHANGHAI).date()))
    _require(payload['session'] in ('intraday', 'close'))
    objects = []
    for key, expected in [('global', 'global'), ('aShare', 'a-share')]:
        obj = payload[key]
        _require(isinstance(obj, dict) and obj.get('id') == expected)
        objects.append(obj)
    for key, definitions in [('styles', STYLE_DEFINITIONS), ('industries', INDUSTRY_DEFINITIONS)]:
        items = payload[key]
        _require(isinstance(items, list) and len(items) == len(definitions)
                 and all(isinstance(obj, dict) for obj in items))
        ids = [obj.get('id') for obj in items]
        _require(all(isinstance(id, str) for id in ids) and len(set(ids)) == len(ids)
                 and set(ids) == {id for id, _ in definitions})
        objects.extend(items)
    required_obj = {'id', 'strength', 'heat', 'risk', 'completeness', 'missing',
                    'contributors', 'sourceTimestamps', 'change1d', 'change5d'}
    allowed_obj = required_obj | {'name', 'frequency', 'observedAt', 'stage',
                                  'comparisonFallback', 'comparisonUnavailable'}
    for obj in objects:
        _require(required_obj <= obj.keys() and obj.keys() <= allowed_obj)
        _require(_numeric(obj['completeness']) and _strings(obj['missing']))
        scores = [obj[axis] for axis in ('strength', 'heat', 'risk')]
        _require(all(v is None or isinstance(v, int) and _numeric(v) for v in scores))
        _require(any(v is not None for v in scores) and obj['completeness'] > 0)
        if 'observedAt' in obj:
            _timestamp(obj['observedAt'])
        if 'frequency' in obj:
            _require(obj['frequency'] in ('intraday', 'daily', 'monthly'))
        if 'name' in obj:
            _require(isinstance(obj['name'], str) and len(obj['name']) <= 100)
        if obj['completeness'] < config['completeness']['stageThreshold']:
            _require(obj.get('stage') is None)
        if obj.get('stage') is not None:
            _require(obj['stage'] in [stage['label'] for stage in config['stages']] + [config['defaultStage']])
        for change in ('change1d', 'change5d'):
            value = obj[change]
            _require(value is None or isinstance(value, dict) and set(value) == {'strength', 'heat', 'risk'}
                     and all(v is None or _numeric(v, -100, 100) for v in value.values()))
        timestamps = obj['sourceTimestamps']
        _require(isinstance(timestamps, list) and bool(timestamps))
        for provenance in timestamps:
            _require(isinstance(provenance, dict) and set(provenance) == {'source', 'timestamp'}
                     and provenance['source'] in ('Wind', 'FRED', 'MX', 'Derived'))
            _timestamp(provenance['timestamp'])
        contributors = obj['contributors']
        _require(isinstance(contributors, list) and len(contributors) <= 3)
        for contributor in contributors:
            _require(isinstance(contributor, dict) and {'label', 'impact'} <= contributor.keys()
                     and contributor.keys() <= {'label', 'impact', 'evidence'}
                     and isinstance(contributor['label'], str) and len(contributor['label']) <= 200
                     and _numeric(contributor['impact'], -100, 100))
            if 'evidence' in contributor:
                _require(isinstance(contributor['evidence'], str) and len(contributor['evidence']) <= 200)
        if 'comparisonFallback' in obj:
            _require(obj['comparisonFallback'] == 'close')
        if 'comparisonUnavailable' in obj:
            unavailable = obj['comparisonUnavailable']
            _require(isinstance(unavailable, dict) and unavailable.keys() <= {'change1d', 'change5d'}
                     and all(reason in ('missingObservation', 'missingCurrentScores', 'missingTradingCalendar',
                                        'missingTargetTradingDate') for reason in unavailable.values()))
    status = payload['dataStatus']
    _require(isinstance(status, dict) and set(status) == {'completeness', 'stale', 'missing'}
             and _numeric(status['completeness']) and isinstance(status['stale'], bool)
             and _strings(status['missing']))
    expected_completeness = math.floor(sum(obj['completeness'] for obj in objects) / len(objects) + .5)
    _require(status['completeness'] == expected_completeness)
    minimum = config.get('publication', {}).get('minimumCompleteness', 0)
    _require(_numeric(minimum) and status['completeness'] > 0 and status['completeness'] >= minimum)
    if 'sourceMode' in payload:
        modes = payload['sourceMode']
        _require(isinstance(modes, dict) and set(modes) == {'breadth', 'styles', 'industries', 'global'})
        for group, mode in modes.items():
            if group == 'global':
                _require(isinstance(mode, dict) and all(isinstance(key, str) and key.isalnum()
                         and value in ('fred', 'wind', 'mx') for key, value in mode.items()))
            else:
                _require(mode == 'wind')
    # Catch NaN, unserializable objects and excessive derived bodies before transport.
    try:
        _require(len(json.dumps(payload, allow_nan=False).encode()) <= 256 * 1024)
    except (TypeError, ValueError):
        raise ValidationError('INVALID_PAYLOAD') from None
    return payload


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # Never forward the Bearer credential to a redirect target.


# Keep the transport patchable while disabling urllib's cross-host auth redirects.
urlopen = build_opener(_NoRedirect()).open


def publish_payload(payload, url, token, timeout=20, *, config=None):
    """Three bounded attempts only for network errors/5xx; never logs secrets."""
    try:
        validate_payload(payload, config)
    except (ValidationError, TypeError, KeyError):
        return PublishResult(False, error_code='INVALID_PAYLOAD')
    try:
        target = urlsplit(url)
        valid_target = target.scheme == 'https' and bool(target.hostname) and not target.username and not target.password
        valid_auth = isinstance(token, str) and bool(token.strip()) and '\n' not in token and '\r' not in token
        if not valid_target or not valid_auth or not _numeric(timeout, .001, 300):
            return PublishResult(False, error_code='INVALID_PUBLISH_CONFIG')
        request = Request(url, data=json.dumps(payload, allow_nan=False, separators=(',', ':')).encode(),
                          headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}, method='POST')
    except (TypeError, ValueError):
        return PublishResult(False, error_code='INVALID_PUBLISH_CONFIG')
    for attempt in range(1, 4):
        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.status
            if 200 <= status < 300:
                return PublishResult(True, status, attempt)
            transient = 500 <= status < 600
            error_code = f'HTTP_{status}'
        except HTTPError as error:
            status = error.code
            transient = 500 <= status < 600
            error_code = f'HTTP_{status}'
            error.close()
        except (URLError, OSError, TimeoutError):
            status, transient, error_code = None, True, 'NETWORK_ERROR'
        except Exception:
            return PublishResult(False, attempts=attempt, error_code='TRANSPORT_ERROR')
        if not transient or attempt == 3:
            return PublishResult(False, status, attempt, error_code)
        time.sleep(.25 * 2 ** (attempt - 1))



FIXTURES = Path(__file__).with_name('fixtures')
FIXTURE_NOW = datetime.fromisoformat('2026-11-13T10:15:00+08:00')


def collect_batches(config, *, fixture=False, runner=None, fetcher=None):
    """Serial adapter calls; fixture mode replaces I/O, never production failures."""
    config = deepcopy(config)
    if fixture:
        config.setdefault('sources', {}).update(now=config.get('sources', {}).get('now', FIXTURE_NOW.isoformat()))
        config['sources']['global'] = {'metrics': {
            'DGS10': {'source': 'fred', 'series': 'DGS10', 'frequency': 'daily', 'unit': '%'},
            'gold': {'source': 'mx', 'entityName': '现货黄金', 'field': '最新价', 'frequency': 'daily'},
        }}
        def runner(argv, *, cwd=None):
            if argv[0] == 'python3':
                name = 'mx-global.json'
            else:
                params = json.loads(argv[-1])
                name = ('wind-industries.json' if 'question' in params else
                        'wind-breadth.json' if params['windcode'] == '881001.WI' else 'wind-styles.json')
            return json.loads((FIXTURES / name).read_text())
        def fetcher(url):
            return (FIXTURES / 'fred-series.csv').read_text()
    runner = runner or sources.run_command
    fetcher = fetcher or sources.fetch_csv
    return {'breadth': sources.collect_wind_breadth(runner, config),
            'styles': sources.collect_wind_styles(runner, config),
            'industries': sources.collect_wind_industries(runner, config),
            'global': sources.collect_global_inputs(runner, fetcher, config)}


def _value(row, field, *, units=None):
    value = row.get(field)
    if units is not None and row.get('_units', {}).get(field) not in units:
        return None
    if isinstance(value, bool) or value is None:
        return None
    try:
        value = float(value)
    except (ValueError, TypeError):
        return None
    return value if math.isfinite(value) else None


def _money(row, field):
    units = row.get('_units', {}).get(field)
    value = _value(row, field)
    if value is None or units not in ('元', '亿元'):
        return None
    return value * (100000000 if units == '亿元' else 1)


def _fresh(row, now):
    try:
        timestamp = _timestamp(row.get('_timestamp'))
    except ValidationError:
        return False
    age = now - timestamp
    if _local(now).hour >= 15 and (_local(timestamp).date() != _local(now).date() or _local(timestamp).hour < 15):
        return False
    return timedelta(0) <= age <= timedelta(minutes=30)


def _component(row, value, now, **normalization):
    timestamp = row.get('_timestamp', row.get('timestamp'))
    fresh = row.get('available', False) and not row.get('stale', False) if 'timestamp' in row else _fresh(row, now)
    return {'value': value, 'available': fresh and value is not None,
            'stale': not fresh, 'timestamp': timestamp, 'source': row.get('source', 'Wind'), **normalization}


def _cross(row, value, history, now):
    return _component(row, value, now, mode='cross_sectional', history=history)


def _ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None


def _breadth(row):
    values = [_value(row, field, units=('个', '家')) for field in ('上涨家数', '下跌家数', '平盘家数')]
    if any(v is None or v < 0 for v in values) or sum(values) <= 0:
        return None, None
    return values[0] / sum(values) * 100, values[1] / sum(values) * 100


def _global_components(rows, now, config):
    """Use only supported observations; no guessed bounds or synthetic histories.

    Source-role fixed bounds live in versioned config. Other rolling indicators
    remain unavailable until 20 observations. Composite/unsupported evidence is
    explicitly absent from the scoring builder's expected denominator.
    """
    by_id = {row['id']: row for row in rows}
    expected_units = {'DGS10': ('%',), 'BAMLH0A0HYM2': ('%',), 'DFII10': ('%',),
                      'IRLTLT01JPM156N': ('%',), 'vix': ('index', '点'),
                      'dollar': ('index', '点'), 'usEquity': ('index', '点')}
    by_id = {role: row if row.get('unit') in expected_units.get(role, ()) else {**row, 'available': False}
             for role, row in by_id.items()}
    indicators = {}
    mapping = {'ratesLiquidity': ('DGS10', True), 'creditConditions': ('BAMLH0A0HYM2', True),
               'highYieldSpread': ('BAMLH0A0HYM2', False), 'realRates': ('DFII10', False),
               'vixPressure': ('vix', False), 'vixPercentile': ('vix', False),
               'currencyEnvironment': ('dollar', True), 'currencyPressure': ('dollar', False),
               'sovereignPressure': ('IRLTLT01JPM156N', False)}
    for component, (role, reverse) in mapping.items():
        row = by_id.get(role)
        if not row:
            continue
        history = [point['value'] for point in row.get('history', []) if _numeric(point.get('value'), -1e15, 1e15)]
        bounds = config['normalization'].get('fixedBounds', {}).get(role)
        normalization = {'mode': 'rolling', 'history': history, 'reverse': reverse}
        if bounds:
            normalization['fixedBounds'] = [bounds['min'], bounds['max']]
        indicators[component] = _component(row, row.get('value'), now, **normalization)
    # Actual changes are derived only from dated history with at least two points.
    for component, role, absolute, percentage in [('equityTrend', 'usEquity', False, True),
                                                    ('rateMoves', 'DGS10', True, False)]:
        row = by_id.get(role)
        if not row:
            continue
        points = row.get('history', [])
        changes = []
        for previous, current in zip(points, points[1:]):
            a, b = previous.get('value'), current.get('value')
            if not _numeric(a, -1e15, 1e15) or not _numeric(b, -1e15, 1e15) or percentage and a <= 0:
                continue
            value = (b / a - 1) * 100 if percentage else b - a
            changes.append(abs(value) if absolute else value)
        indicators[component] = _component(row, changes[-1] if changes else None, now,
                                           mode='rolling', history=changes)
    return indicators


def derive_inputs(batches, now, config):
    """Derive interpretable component inputs from unit-checked adapter rows.

    Return/flow/turnover ranks compare fresh peers in the same source batch.
    Market amount shares use the all-A denominator, never overlapping style sums.
    Unknown flat counts and unavailable industry 5d/20d returns stay missing.
    """
    local = _local(now)
    broad = batches['breadth'].rows[0] if batches['breadth'].rows else {}
    market_amount = _money(broad, '成交额') if _fresh(broad, now) else None
    global_rows = batches['global'].rows
    global_obj = {'id': 'global', 'name': '全球环境', 'indicators': _global_components(global_rows, now, config)}
    global_score = score_family('global', global_obj, config)
    used = {(p['source'], p['timestamp']) for p in global_score['sourceTimestamps']}
    observed_rows = [row for row in global_rows if (row.get('source'), row.get('timestamp')) in used]
    frequencies = {row.get('frequency') for row in observed_rows}
    if frequencies and frequencies <= {'daily', 'monthly'}:
        global_obj['frequency'] = 'daily' if 'daily' in frequencies else 'monthly'
        global_obj['observedAt'] = max((row['timestamp'] for row in observed_rows), key=_timestamp)
    global_risk = global_score['risk']
    advancing, declining = _breadth(broad)
    style_returns = [_value(row, '涨跌幅', units=('%',)) for row in batches['styles'].rows if _fresh(row, now)]
    broad_return = _value(broad, '涨跌幅', units=('%',))
    amount_rows = batches['industries'].rows
    industry_amounts = [_money(row, '最新成交额(亿元)') for row in amount_rows if _fresh(row, now)]
    industry_amounts = [value for value in industry_amounts if value is not None and value >= 0]
    # Top-five industry amount share is observable concentration, already 0–100.
    concentration = (sum(sorted(industry_amounts, reverse=True)[:5]) / sum(industry_amounts) * 100
                     if len(industry_amounts) == len(INDUSTRY_DEFINITIONS) and sum(industry_amounts) > 0 else None)
    a_indicators = {'breadth': _component(broad, advancing, now),
                    'indexTrend': _cross(broad, broad_return, [v for v in style_returns if v is not None], now),
                    'downsideDiffusion': _component(broad, declining, now),
                    'industryConcentration': _component(broad, concentration, now)}
    if global_risk is not None:
        a_indicators['globalPressure'] = {'value': global_risk, 'source': 'Derived', 'timestamp': now.isoformat()}
    a_obj = {'id': 'a-share', 'name': 'A股整体', 'frequency': 'intraday', 'indicators': a_indicators}
    market_risk = score_family('aShare', a_obj, config)['risk']
    output = {'observedAt': now.isoformat(), 'marketDate': str(local.date()),
              'session': 'close' if local.hour >= 15 else 'intraday',
              'global': global_obj, 'aShare': a_obj}
    if 'tradingDates' in config.get('schedule', {}):
        output['tradingDates'] = list(config['schedule']['tradingDates'])
    for group, definitions in [('styles', STYLE_DEFINITIONS), ('industries', INDUSTRY_DEFINITIONS)]:
        industry = group == 'industries'
        rows = batches[group].rows
        by_id = {row['id']: row for row in rows}
        ret_field = '最新涨跌幅(%)' if industry else '涨跌幅'
        turnover_field = '最新换手率(%)' if industry else '换手率'
        amount_field = '最新成交额(亿元)' if industry else '成交额'
        flow_field = '最新主力净流入额(亿元)' if industry else '当日主力净流入额'
        def metrics(row):
            amount, flow = _money(row, amount_field), _money(row, flow_field)
            up, down = _breadth(row)
            return {'relativeReturn1d': _value(row, ret_field, units=('%',)),
                    'relativeReturn5d': _value(row, '5日涨跌幅', units=('%',)),
                    'relativeReturn20d': _value(row, '20日涨跌幅', units=('%',)),
                    'advancingShare': up, 'decliningShare': down,
                    'turnoverCrossSection': _value(row, turnover_field, units=('%',)),
                    'amountCrossSection': amount, 'marketAmountShare': _ratio(amount, market_amount),
                    'mainFlowDirection': _ratio(flow, amount)}
        values = {row['id']: metrics(row) for row in rows}
        histories = {key: [m[key] for id, m in values.items() if _fresh(by_id[id], now) and m[key] is not None]
                     for key in ('relativeReturn1d', 'relativeReturn5d', 'relativeReturn20d',
                                 'turnoverCrossSection', 'amountCrossSection', 'marketAmountShare', 'mainFlowDirection')}
        objects = []
        for id, name in definitions:
            row = by_id.get(id, {})
            metric = values.get(id, {})
            indicators = {key: _cross(row, metric.get(key), history, now) for key, history in histories.items()}
            indicators['advancingShare'] = _component(row, metric.get('advancingShare'), now)
            indicators['decliningShare' if industry else 'negativeBreadth'] = _component(row, metric.get('decliningShare'), now)
            flow = metric.get('mainFlowDirection')
            indicators['mainOutflow'] = _cross(row, flow, histories['mainFlowDirection'], now)
            indicators['mainOutflow']['reverse'] = True
            indicators['mainFlowConcentration'] = _cross(row, abs(flow) if flow is not None else None,
                [abs(v) for v in histories['mainFlowDirection']], now)
            trend = metric.get('relativeReturn20d')
            indicators['mediumTrendDeterioration' if industry else 'trendDeterioration20d'] = _cross(
                row, trend, histories['relativeReturn20d'], now)
            indicators['mediumTrendDeterioration' if industry else 'trendDeterioration20d']['reverse'] = True
            risk = market_risk if industry else global_risk
            if risk is not None:
                indicators['marketRiskTransmission' if industry else 'globalRiskTransmission'] = {
                    'value': risk, 'available': _fresh(row, now), 'stale': not _fresh(row, now),
                    'source': 'Derived', 'timestamp': now.isoformat()}
            objects.append({'id': id, 'name': name, 'frequency': 'intraday', 'indicators': indicators})
        output[group] = objects
    return output



@dataclass(frozen=True)
class JobResult:
    success: bool
    status: str
    payload: dict | None = None
    error_code: str | None = None
    publish_result: PublishResult | None = None


def _read_json(path):
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError('INVALID_STATE')
    return data


def _write_json(path, value):
    """Same-directory atomic replace; runtime derived state only, private mode."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(mode='w', dir=path.parent, prefix='.dashboard-', delete=False) as file:
            temporary = Path(file.name)
            json.dump(value, file, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _source_modes(batches):
    return {'breadth': 'wind', 'styles': 'wind', 'industries': 'wind',
            'global': {row['id']: row['sourceMode'] for row in batches['global'].rows
                       if isinstance(row.get('id'), str) and row['id'].isalnum()
                       and row.get('sourceMode') in ('fred', 'wind', 'mx')}}


def _safe_error(code, fallback):
    return code if isinstance(code, str) and re.fullmatch(r'(HTTP_[1-5][0-9]{2}|NETWORK_ERROR|INVALID_PAYLOAD|TRANSPORT_ERROR|INVALID_PUBLISH_CONFIG)', code) else fallback


def run_job(args, deps=None):
    """Collect → score → validate → publish under a nonblocking process lock.

    deps is an optional dict: now, config, state_root, collector(config),
    builder(inputs, previous, config), publisher(payload, url, token, timeout,
    config=...). All tests inject external I/O. Dry runs write no state at all;
    skip-publish writes health only. Only a successful publish advances buckets
    and the derived comparison history in last-success.json.
    """
    deps = deps or {}
    arg = (lambda key, default=None: args.get(key, default)) if isinstance(args, dict) else (lambda key, default=None: getattr(args, key, default))
    fixture, dry_run, skip_publish = arg('fixture', False), arg('dry_run', False), arg('skip_publish', False)
    if fixture and not (dry_run or skip_publish):
        return JobResult(False, 'configuration', error_code='FIXTURE_PUBLISH_DISABLED')
    now = deps.get('now') or (FIXTURE_NOW if fixture else datetime.now(timezone.utc))
    if callable(now):
        now = now()
    try:
        _local(now)
        config = deepcopy(deps.get('config') or load_config(arg('config')))
        config.setdefault('sources', {})['now'] = now.isoformat()
    except (ValueError, TypeError, OSError, KeyError):
        return JobResult(False, 'configuration', error_code='INVALID_CONFIG')
    state_root = Path(deps.get('state_root') or Path(__file__).resolve().parents[2].parent / 'state')
    state_path = state_root / 'market-dashboard/last-success.json'
    health_path = state_root / 'service-health/market-dashboard.json'
    lock = None
    stage, counts, completeness = 'state', {}, None
    last_status = 'never'
    payload = None
    try:
        if not dry_run:
            state_path.parent.mkdir(parents=True, exist_ok=True)
            lock = (state_path.parent / 'job.lock').open('a')
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return JobResult(True, 'locked')
        state = {} if fixture else _read_json(state_path)
        old_health = {} if fixture else _read_json(health_path)
        last_status = old_health.get('lastPublishStatus', 'published' if state else 'never')
        if last_status not in ('published', 'failed', 'never', 'skipped'):
            last_status = 'never'
        counts = old_health.get('sourceCounts', {})
        counts = {key: value for key, value in counts.items() if key in ('breadth', 'global', 'styles', 'industries')
                  and isinstance(value, int) and 0 <= value <= 1000} if isinstance(counts, dict) else {}
        prior_payload = state.get('payload', {})
        completeness = prior_payload.get('dataStatus', {}).get('completeness') if isinstance(prior_payload, dict) else None
        # Force never overrides duplicate-bucket idempotency.
        if state.get('bucket') == _bucket(now):
            return JobResult(True, 'duplicate')
        if not arg('force', False) and not should_collect(now, state, config):
            return JobResult(True, 'outside_schedule')
        stage = 'collect'
        batches = deps['collector'](config) if 'collector' in deps else collect_batches(config, fixture=fixture)
        counts = {group: len(batch.rows) for group, batch in batches.items()}
        # Evaluate freshness at completion, so observations arriving during the
        # serial provider calls are not incorrectly classified as future data.
        if callable(deps.get('now')):
            now = deps['now']()
        elif 'now' not in deps and not fixture:
            now = datetime.now(timezone.utc)
        _local(now)
        stage = 'score'
        inputs = derive_inputs(batches, now, config)
        previous = state.get('history', [])
        previous = previous if isinstance(previous, list) else []
        payload = deps.get('builder', build_dashboard_payload)(inputs, previous, config)
        # Only explicit safe provenance survives Task 1's derived-field whitelist.
        payload['sourceMode'] = _source_modes(batches)
        stage = 'validate'
        validate_payload(payload, config)
        completeness = payload['dataStatus']['completeness']
        if dry_run:
            return JobResult(True, 'dry_run', payload)
        if skip_publish:
            _write_json(health_path, {'stage': 'complete', 'observedAt': now.isoformat(),
                        'sourceCounts': counts, 'completeness': completeness,
                        'lastPublishStatus': last_status, 'publishStatus': 'skipped', 'errorCode': None})
            return JobResult(True, 'skip_publish', payload)
        stage = 'publish'
        result = deps.get('publisher', publish_payload)(payload,
            arg('url') or os.environ.get('MARKET_DASHBOARD_PUBLISH_URL', ''),
            arg('token') or os.environ.get('MARKET_DASHBOARD_PUBLISH_TOKEN', ''),
            arg('timeout', 20), config=config)
        if not result.success:
            code = _safe_error(result.error_code, 'PUBLISH_FAILED')
            _write_json(health_path, {'stage': stage, 'observedAt': now.isoformat(), 'sourceCounts': counts,
                        'completeness': completeness, 'lastPublishStatus': 'failed', 'errorCode': code})
            return JobResult(False, stage, error_code=code,
                             publish_result=PublishResult(False, result.status_code, result.attempts, code))
        stage = 'persist'
        # Store only validated derived snapshots, retaining at least 90 calendar days.
        history = []
        for snapshot in previous:
            try:
                validate_payload(snapshot, config)
                if _timestamp(snapshot['observedAt']) >= now - timedelta(days=90):
                    history.append(snapshot)
            except (ValidationError, TypeError, KeyError):
                continue
        history.append(payload)
        _write_json(state_path, {'bucket': _bucket(now), 'mode': 'published',
                    'observedAt': now.isoformat(), 'payload': payload, 'history': history})
        _write_json(health_path, {'stage': 'complete', 'observedAt': now.isoformat(), 'sourceCounts': counts,
                    'completeness': completeness, 'lastPublishStatus': 'published', 'errorCode': None})
        return JobResult(True, 'published', payload, publish_result=PublishResult(True, result.status_code, result.attempts))
    except Exception as error:
        code = 'INVALID_PAYLOAD' if isinstance(error, ValidationError) else {
            'state': 'INVALID_STATE', 'collect': 'COLLECTION_FAILED', 'score': 'SCORING_FAILED',
            'validate': 'INVALID_PAYLOAD', 'publish': 'PUBLISH_FAILED', 'persist': 'STATE_WRITE_FAILED',
        }.get(stage, 'JOB_FAILED')
        if not dry_run:
            try:
                _write_json(health_path, {'stage': stage, 'observedAt': now.isoformat(), 'sourceCounts': counts,
                            'completeness': completeness if _numeric(completeness) else None,
                            'lastPublishStatus': 'failed' if stage == 'publish' else last_status, 'errorCode': code})
            except (OSError, ValueError, TypeError):
                pass
        return JobResult(False, stage, error_code=code)
    finally:
        if lock is not None:
            lock.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true', help='Validate and summarize; no publication or state writes')
    parser.add_argument('--fixture', action='store_true', help='Use sanitized synthetic fixtures and their fixed observation clock')
    parser.add_argument('--force', action='store_true', help='Bypass session gate only; validation/idempotency still apply')
    parser.add_argument('--skip-publish', action='store_true', help='Collect/validate and write health, without advancing last-success')
    parser.add_argument('--config', help='Versioned config JSON path')
    parser.add_argument('--url', help='HTTPS publication URL (or MARKET_DASHBOARD_PUBLISH_URL)')
    parser.add_argument('--token', help='Publication Bearer token (prefer MARKET_DASHBOARD_PUBLISH_TOKEN)')
    parser.add_argument('--timeout', type=float, default=20)
    args = parser.parse_args(argv)
    result = run_job(args)
    summary = {'status': result.status, 'success': result.success}
    if result.payload:
        summary.update(observedAt=result.payload['observedAt'], session=result.payload['session'],
                       completeness=result.payload['dataStatus']['completeness'],
                       objectCounts={'global': 1, 'aShare': 1, 'styles': len(result.payload['styles']),
                                     'industries': len(result.payload['industries'])},
                       synthetic=bool(args.fixture))
    if result.error_code:
        summary['errorCode'] = result.error_code
    print(json.dumps(summary, ensure_ascii=False, separators=(',', ':')))
    return 0 if result.success else 1


if __name__ == '__main__':
    raise SystemExit(main())
