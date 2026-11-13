"""Local-only provider adapters. Inject runner/fetcher for all offline tests.

Runner contract: ``runner(argv, cwd=...) -> dict | JSON text | CompletedProcess``.
Wind calls are synchronous, one parameter group per collector, with no retry or
fallback on errors. SourceBatch rows retain provider field names and units;
consumers must explicitly derive score inputs, never treat these as scores.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import json
import math
import subprocess


WIND_SKILL = Path.home() / '.agents/skills/wind-mcp-skill'
STYLE_DEFINITIONS = (
    ('000300.SH', '大盘'), ('000852.SH', '小盘'), ('H30356.CSI', '价值'),
    ('399006.SZ', '成长'), ('000922.CSI', '红利'), ('000688.SH', '科技'),
)
_INDUSTRY_CODES = list(range(100, 117)) + list(range(119, 137))
_INDUSTRY_NAMES = ('石油石化 化工 国防军工 企业服务 交通运输 汽车与零配件 耐用消费品 '
                   '消费者服务 传媒 可选消费零售 日常消费零售 食品饮料 家庭用品 医疗设备与服务 '
                   '医药生物 银行 非银金融 软件服务 硬件设备 半导体 电信服务 公用事业Ⅱ 煤炭Ⅱ '
                   '建材Ⅱ 钢铁Ⅱ 有色金属 造纸与包装 建筑 电气设备 机械 工业贸易与综合 环保Ⅱ '
                   '家电Ⅱ 纺织服装Ⅱ 房地产Ⅱ').split()
INDUSTRY_DEFINITIONS = tuple((f'882{code}.WI', name) for code, name in zip(_INDUSTRY_CODES, _INDUSTRY_NAMES))
BREADTH_FIELDS = ('最新交易日', '交易时间', '中文简称', '涨跌幅', '成交额', '换手率', '上涨家数', '下跌家数', '平盘家数')
STYLE_FIELDS = ('最新交易日', '交易时间', '中文简称', '涨跌幅', '成交额', '换手率', '5日涨跌幅', '20日涨跌幅', '当日主力净流入额')
INDUSTRY_FIELDS = ('最新涨跌幅(%)', '最新换手率(%)', '最新成交额(亿元)', '最新主力净流入额(亿元)', '上涨家数', '下跌家数', '5日涨跌幅', '20日涨跌幅')
INDUSTRY_PRICE_FIELDS = ('最新交易日', '交易时间', '中文简称', '涨跌幅', '成交额', '换手率',
                         '5日涨跌幅', '20日涨跌幅', '当日主力净流入额', '上涨家数', '下跌家数')


@dataclass(frozen=True)
class SourceBatch:
    source: str
    rows: list[dict] = field(default_factory=list)
    source_mode: str = ''
    errors: list[dict] = field(default_factory=list)
    complete: bool = False


class SourceError(ValueError):
    """A safe error code; provider messages and raw responses are never retained."""
    def __init__(self, code='MALFORMED_RESPONSE'):
        self.code = code
        super().__init__(code)


def _decode(value):
    if hasattr(value, 'returncode'):
        if value.returncode:
            # Parse structured CLI error envelopes even when the CLI exits nonzero.
            try:
                output = json.loads(value.stdout)
            except (ValueError, TypeError):
                raise SourceError('COMMAND_ERROR') from None
            if isinstance(output, dict) and output.get('ok') is False:
                return _decode(output)
            raise SourceError('COMMAND_ERROR')
        value = value.stdout
    if isinstance(value, (str, bytes)):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            raise SourceError() from None
    if not isinstance(value, dict):
        raise SourceError()
    if value.get('ok') is False or value.get('isError') is True or value.get('error'):
        allowed = {'AUTH_ERROR', 'RATE_LIMIT_ERROR', 'backend_error', 'NETWORK_ERROR', 'TOOL_RUNTIME_ERROR'}
        code = value.get('code')
        if code is not None and not isinstance(code, str):
            raise SourceError()
        raise SourceError(code if code in allowed else 'backend_error')
    return value


def _timestamp(row):
    date = row.get('最新交易日', row.get('日期'))
    time = row.get('交易时间')
    if not isinstance(time, str):
        return None
    try:
        if len(time) <= 8:
            if not isinstance(date, str):
                return None
            date = datetime.strptime(date, '%Y%m%d').date().isoformat() if len(date) == 8 else date
            time = f'{date}T{time}'
        value = datetime.fromisoformat(time)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone(timedelta(hours=8)))
        return value.isoformat()
    except ValueError:
        return None


def parse_wind_content(envelope):
    """Parse verified MCP direct and analytics nested tables, without unit conversion.

    Only table scalars, explicitly returned units, and derived observation time
    survive. CLI metadata, request IDs, credentials, and unrelated fields do not.
    Malformed tables and provider errors raise SourceError, never partial rows.
    """
    envelope = _decode(envelope)
    if 'content' in envelope:
        content = envelope['content']
        if not isinstance(content, list) or not content or not isinstance(content[0], dict):
            raise SourceError()
        envelope = _decode(content[0].get('text'))
    data = envelope.get('data')
    if not isinstance(data, dict):
        raise SourceError()
    _decode(data)  # a nested backend error is never a successful partial table
    tables = data.get('data', [data])
    if not isinstance(tables, list) or not tables:
        raise SourceError()
    result = []
    for table in tables:
        if not isinstance(table, dict):
            raise SourceError()
        _decode(table)
        columns, rows = table.get('columns'), table.get('rows')
        if not isinstance(columns, list) or not columns or not isinstance(rows, list) or not rows:
            raise SourceError()
        names, units = [], {}
        metadata = table.get('unit', {})
        if not isinstance(metadata, dict):
            raise SourceError()
        for column in columns:
            name = column.get('name') if isinstance(column, dict) else column
            if not isinstance(name, str) or not name or name.startswith('_') or name in names:
                raise SourceError()
            names.append(name)
            unit = column.get('unit', metadata.get(name)) if isinstance(column, dict) else metadata.get(name)
            if unit is not None:
                if not isinstance(unit, str):
                    raise SourceError()
                units[name] = unit
        for values in rows:
            if not isinstance(values, list) or len(values) != len(names):
                raise SourceError()
            if any(isinstance(v, (dict, list, bool)) or isinstance(v, float) and not math.isfinite(v) for v in values):
                raise SourceError()
            for column, value in zip(columns, values):
                if isinstance(column, dict) and column.get('type') in ('number', 'float', 'double', 'int', 'integer'):
                    _number(value)  # validate finite numerics without changing units/values
            row = dict(zip(names, values))
            row['_units'] = dict(units)
            row['_timestamp'] = _timestamp(row)
            result.append(row)
    return result


def run_command(argv, *, cwd=None):
    """No shell, no response printing, no disk persistence."""
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=90, check=False)


def _error(source, code, group, **safe_details):
    return {'source': source, 'code': code, 'group': group, **safe_details}


def _wind(runner, config, group, definitions, fields, *, analytics=False):
    settings = config.get('sources', {}).get('wind', {})
    codes = [definition[0] for definition in definitions]
    if analytics:
        params = {'question': '按Wind二级行业分类返回以下固定行业指数的最新涨跌幅、换手率、成交额、主力净流入额、上涨家数、下跌家数、5日涨跌幅、20日涨跌幅、交易时间、日期和Wind代码：' + ','.join(codes)}
        server, tool = 'analytics_data', 'get_financial_data'
    else:
        params = {'windcode': ','.join(codes), 'indexes': ','.join(fields)}
        server, tool = 'index_data', 'get_index_price_indicators'
    argv = ['node', 'scripts/cli.mjs', 'call', server, tool, json.dumps(params, ensure_ascii=False)]
    try:
        # This one call is the group's probe and full batch (<=50 identifiers).
        rows = parse_wind_content(runner(argv, cwd=str(settings.get('skillPath', WIND_SKILL))))
        actual = [row.get('Wind代码') for row in rows]
        if len(actual) != len(codes) or len(set(actual)) != len(actual) or set(actual) != set(codes):
            raise SourceError('IDENTITY_MISMATCH')
    except SourceError as error:
        return SourceBatch('Wind', source_mode='wind', errors=[_error('Wind', error.code, group)])
    except (OSError, subprocess.SubprocessError):
        return SourceBatch('Wind', source_mode='wind', errors=[_error('Wind', 'COMMAND_ERROR', group)])
    by_code = {row['Wind代码']: row for row in rows}
    ordered, errors = [], []
    for code, name in definitions:
        row = dict(by_code[code])
        row.update(id=code, name=name, source='Wind', sourceMode='wind')
        # Missing provider markers retain their original text but never count
        # as observed values in the batch's completeness signal.
        missing = [key for key in fields if row.get(key) in (None, '', '.')]
        if not row['_timestamp']:
            missing.append('timestamp')
        if missing:
            errors.append(_error('Wind', 'MISSING_FIELDS', group, id=code, fields=missing))
        ordered.append(row)
    return SourceBatch('Wind', ordered, 'wind', errors, not errors)


def collect_wind_breadth(runner, config):
    return _wind(runner, config, 'breadth', (('881001.WI', '万得全A'),), BREADTH_FIELDS)


def collect_wind_styles(runner, config):
    return _wind(runner, config, 'styles', STYLE_DEFINITIONS, STYLE_FIELDS)


def collect_wind_industries(runner, config):
    legacy = config.get('sources', {}).get('wind', {}).get('industryMode') == 'analytics'
    batch = _wind(runner, config, 'industries', INDUSTRY_DEFINITIONS,
                  INDUSTRY_FIELDS if legacy else INDUSTRY_PRICE_FIELDS, analytics=legacy)
    # Keep the scorer's established keys without changing returned values or
    # inventing units. _money still checks the copied provider unit explicitly.
    aliases = {'涨跌幅': '最新涨跌幅(%)', '换手率': '最新换手率(%)',
               '成交额': '最新成交额(亿元)', '当日主力净流入额': '最新主力净流入额(亿元)'}
    for row in batch.rows:
        for field, alias in aliases.items():
            if field in row:
                row[alias] = row[field]
                if field in row['_units']:
                    row['_units'][alias] = row['_units'][field]
    return batch


# Reuses all ten series IDs/frequencies in src/features/debt-monitor/api.mjs.
FRED_SERIES = {
    'DGS2': 'daily', 'DGS10': 'daily', 'DFII10': 'daily', 'T10YIE': 'daily',
    'BAMLH0A0HYM2': 'daily', 'THREEFYTP10': 'daily',
    'IRLTLT01JPM156N': 'monthly', 'IRLTLT01DEM156N': 'monthly',
    'IRLTLT01FRM156N': 'monthly', 'IRLTLT01ITM156N': 'monthly',
}
DEFAULT_GLOBAL_METRICS = {
    **{key: {'source': 'fred', 'series': key, 'frequency': frequency, 'unit': '%'}
       for key, frequency in FRED_SERIES.items()},
    'vix': {'source': 'fred', 'series': 'VIXCLS', 'frequency': 'daily', 'unit': 'index'},
    'usEquity': {'source': 'fred', 'series': 'SP500', 'frequency': 'daily', 'unit': 'index'},
    'dollar': {'source': 'fred', 'series': 'DTWEXBGS', 'frequency': 'daily', 'unit': 'index'},
    'gold': {'source': 'mx', 'entityName': '现货黄金', 'field': '最新价', 'frequency': 'daily'},
    'oil': {'source': 'mx', 'entityName': 'WTI原油', 'field': '最新价', 'frequency': 'daily'},
    'usdcnh': {'source': 'mx', 'entityName': '美元离岸人民币', 'field': '最新价', 'frequency': 'daily'},
}


def _now(config):
    value = config.get('sources', {}).get('now')
    now = datetime.fromisoformat(value) if value else datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('sources.now must include a timezone')
    return now


def _number(value):
    if value is None or isinstance(value, bool) or value in ('', '.'):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        raise SourceError() from None
    if not math.isfinite(number):
        raise SourceError()
    return number


def _observation_time(value):
    if not isinstance(value, str):
        raise SourceError()
    try:
        observed = datetime.fromisoformat(value)
    except ValueError:
        raise SourceError() from None
    if observed.tzinfo is None:
        # FRED/MX date-only observations represent a date, not a real-time quote.
        zone = timezone.utc if len(value) == 10 else timezone(timedelta(hours=8))
        observed = observed.replace(tzinfo=zone)
    return observed.isoformat()


def parse_fred_csv(text, series):
    """Strict two-column FRED CSV parser; missing '.' observations stay absent."""
    import csv
    import io
    reader = csv.reader(io.StringIO(text))
    header = next(reader, [])
    if len(header) != 2 or header[0] not in ('observation_date', 'DATE') or header[1] != series:
        raise SourceError()
    points = {}
    for row in reader:
        if not row:
            continue
        if len(row) != 2:
            raise SourceError()
        timestamp = _observation_time(row[0])
        if len(row[0]) != 10:
            raise SourceError()
        value = _number(row[1].strip())
        if value is None:
            continue
        if timestamp in points and points[timestamp] != value:
            raise SourceError()
        points[timestamp] = value
    return [{'timestamp': timestamp, 'value': value} for timestamp, value in sorted(points.items())]


def fetch_csv(url):
    from urllib.request import urlopen
    with urlopen(url, timeout=20) as response:
        return response.read().decode('utf-8-sig')


def _fred(fetcher, definition):
    from urllib.parse import urlencode
    series = definition.get('series')
    if not isinstance(series, str) or not series or not series.replace('_', '').isalnum():
        raise SourceError('INVALID_CONFIG')
    response = fetcher('https://fred.stlouisfed.org/graph/fredgraph.csv?' + urlencode({'id': series}))
    if hasattr(response, 'ok') and not response.ok:
        raise SourceError('FETCH_ERROR')
    if isinstance(response, str):
        text = response
    else:
        text = getattr(response, 'text', None)
        text = text() if callable(text) else text
    if not isinstance(text, str):
        raise SourceError()
    return parse_fred_csv(text, series), definition.get('unit')


def _mx_payload(runner, config, definitions):
    """Run the documented MX script in a disposable directory, never in repo.

    The CLI emits a preview, not JSON; its raw JSON result is read only inside
    TemporaryDirectory and removed immediately. An injected runner can directly
    return the decoded API envelope for offline execution.
    """
    from tempfile import TemporaryDirectory
    settings = config.get('sources', {}).get('mx', {})
    skill = Path(settings.get('skillPath', Path.home() / '.codex/skills/mx-data'))
    query = '查询' + '；'.join(f"{d['entityName']} {d['field']} 以及交易时间、指标单位" for d in definitions)
    with TemporaryDirectory(prefix='market-dashboard-mx-') as directory:
        output = runner(['python3', str(skill / 'mx_data.py'), query, directory], cwd=str(skill))
        if hasattr(output, 'returncode') and output.returncode:
            raise SourceError('COMMAND_ERROR')
        if isinstance(output, dict):
            return output
        try:
            return _decode(output)
        except SourceError:
            files = list(Path(directory).glob('*_raw.json'))
            if len(files) != 1:
                raise SourceError('MALFORMED_RESPONSE') from None
            return _decode(files[0].read_text())


def _mx_envelope(value):
    value = _decode(value)
    if value.get('status') not in (None, 0, '0') or value.get('code') not in (None, 0, '0', 200, '200'):
        raise SourceError('backend_error')
    return value


def _mx_points(payload, definition):
    payload = _mx_envelope(payload)
    data = _mx_envelope(payload.get('data'))
    if isinstance(data.get('data'), dict):
        inner = _mx_envelope(data['data'])
        data = _mx_envelope(inner.get('searchDataResultDTO'))
    blocks = data.get('dataTableDTOList') if isinstance(data, dict) else None
    if not isinstance(blocks, list):
        raise SourceError()
    points, unit, seen_unit = {}, None, False
    for block in blocks:
        if not isinstance(block, dict):
            raise SourceError()
        if block.get('entityName') != definition.get('entityName'):
            continue
        if definition.get('code') and block.get('code') != definition['code']:
            continue
        table, name_map = block.get('table'), block.get('nameMap')
        if not isinstance(table, dict) or not isinstance(name_map, dict):
            raise SourceError()
        dates = table.get('headName')
        if not isinstance(dates, list):
            raise SourceError()
        for key, label in name_map.items():
            if label != definition.get('field') or key == 'headName':
                continue
            values = table.get(key)
            if not isinstance(values, list) or len(values) != len(dates):
                raise SourceError()
            metadata = block.get('field') or {}
            if not isinstance(metadata, dict):
                raise SourceError()
            current_unit = metadata.get('unit')
            if current_unit is not None and not isinstance(current_unit, str):
                raise SourceError()
            if seen_unit and current_unit != unit:
                raise SourceError('UNIT_MISMATCH')
            unit, seen_unit = current_unit, True
            for date, raw in zip(dates, values):
                timestamp = _observation_time(date)
                value = _number(raw)
                if value is None:
                    continue
                if timestamp in points and points[timestamp] != value:
                    raise SourceError('AMBIGUOUS_METRIC')
                points[timestamp] = value
    return [{'timestamp': timestamp, 'value': value} for timestamp, value in sorted(points.items())], unit


def _global_wind(runner, config, definitions):
    codes = list(dict.fromkeys(d['windcode'] for d in definitions))
    fields = list(dict.fromkeys(['最新交易日', '交易时间'] + [d['field'] for d in definitions]))
    # Global index observations use the same documented price-indicator contract.
    if len(codes) > 50:
        raise SourceError('INVALID_CONFIG')
    settings = config.get('sources', {}).get('wind', {})
    params = {'windcode': ','.join(codes), 'indexes': ','.join(fields)}
    rows = parse_wind_content(runner(['node', 'scripts/cli.mjs', 'call', 'index_data',
                                    'get_index_price_indicators', json.dumps(params, ensure_ascii=False)],
                                   cwd=str(settings.get('skillPath', WIND_SKILL))))
    actual = [row.get('Wind代码') for row in rows]
    if len(actual) != len(codes) or len(set(actual)) != len(actual) or set(actual) != set(codes):
        raise SourceError('IDENTITY_MISMATCH')
    return {row['Wind代码']: row for row in rows}


def _global_row(role, definition, points, unit, now):
    latest = points[-1] if points else {}
    timestamp = latest.get('timestamp')
    frequency = definition.get('frequency', 'daily')
    limit = definition.get('maxAgeDays', 75 if frequency == 'monthly' else 7 if frequency == 'daily' else 1 / 24)
    stale = timestamp is None
    if timestamp:
        age = (now - datetime.fromisoformat(timestamp)).total_seconds() / 86400
        stale = age < 0 or age > limit
    return {'id': role, 'value': latest.get('value'), 'unit': unit, 'timestamp': timestamp,
            'frequency': frequency, 'stale': stale, 'available': bool(points) and not stale,
            'source': {'fred': 'FRED', 'mx': 'MX', 'wind': 'Wind'}[definition['source']],
            'sourceMode': definition['source'], 'history': points}


def collect_global_inputs(runner, fetcher, config):
    """Choose exactly one configured provider per role; never auto-fallback/merge.

    Optional config: sources.global.metrics = {role: {source: fred|mx|wind,
    frequency, maxAgeDays, series/unit OR entityName/field/code OR windcode/field}}.
    Missing/stale metrics remain explicit unavailable rows for completeness.
    """
    settings = config.get('sources', {})
    definitions = settings.get('global', {}).get('metrics', DEFAULT_GLOBAL_METRICS)
    now = _now(config)
    rows, errors, grouped = [], [], {}
    runner, fetcher = runner or run_command, fetcher or fetch_csv
    for provider in ('wind', 'mx'):
        group = [d for d in definitions.values() if d.get('source') == provider]
        if not group:
            continue
        try:
            grouped[provider] = _global_wind(runner, config, group) if provider == 'wind' else _mx_payload(runner, config, group)
        except SourceError as error:
            grouped[provider] = error
        except (OSError, subprocess.SubprocessError):
            grouped[provider] = SourceError('COMMAND_ERROR')
    for role, definition in definitions.items():
        provider = definition.get('source')
        if provider not in ('fred', 'mx', 'wind'):
            errors.append(_error('Global', 'INVALID_CONFIG', 'global', id=role))
            continue
        points, unit = [], definition.get('unit')
        try:
            if provider == 'fred':
                points, unit = _fred(fetcher, definition)
            elif isinstance(grouped[provider], SourceError):
                raise grouped[provider]
            elif provider == 'mx':
                points, unit = _mx_points(grouped[provider], definition)
            else:
                row = grouped[provider][definition['windcode']]
                value = _number(row.get(definition['field']))
                unit = row['_units'].get(definition['field'])
                if value is not None and row['_timestamp']:
                    points = [{'timestamp': row['_timestamp'], 'value': value}]
            if not points:
                raise SourceError('MISSING_METRIC')
        except SourceError as error:
            errors.append(_error({'fred': 'FRED', 'mx': 'MX', 'wind': 'Wind'}[provider], error.code, 'global', id=role))
        except (OSError, subprocess.SubprocessError):
            errors.append(_error(provider.upper(), 'FETCH_ERROR', 'global', id=role))
        row = _global_row(role, definition, points, unit, now)
        if row['stale'] and points:
            errors.append(_error(row['source'], 'STALE_OBSERVATION', 'global', id=role))
        rows.append(row)
    modes = '+'.join(sorted({d.get('source', 'invalid') for d in definitions.values()}))
    return SourceBatch('Global', rows, modes, errors, bool(rows) and not errors)



def _summary(batch, group):
    units, timestamps = set(), set()
    for row in batch.rows:
        units.update(row.get('_units', {}).values())
        if isinstance(row.get('unit'), str):
            units.add(row['unit'])
        timestamp = row.get('_timestamp', row.get('timestamp'))
        if timestamp:
            timestamps.add(timestamp)
    return {'source': f'{batch.source}/{group}', 'rowCount': len(batch.rows),
            'fields': sorted({key for row in batch.rows for key in row if not key.startswith('_')}),
            'units': sorted(units), 'timestamps': sorted(timestamps)}


def main(argv=None, *, runner=run_command, fetcher=fetch_csv, config=None):
    """Explicit market-open smoke probe; prints metadata only, never raw payloads."""
    from .scoring import load_config
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', action='store_true', help='Run serial live provider probes; print metadata only')
    args = parser.parse_args(argv)
    if not args.probe:
        parser.print_help()
        return 0
    config = config if config is not None else load_config()
    complete = True
    for group, collector in (('breadth', collect_wind_breadth), ('styles', collect_wind_styles),
                             ('industries', collect_wind_industries)):
        batch = collector(runner, config)
        print(json.dumps(_summary(batch, group), ensure_ascii=False))
        complete &= batch.complete
    batch = collect_global_inputs(runner, fetcher, config)
    print(json.dumps(_summary(batch, 'global'), ensure_ascii=False))
    return 0 if complete and batch.complete else 1


if __name__ == '__main__':
    raise SystemExit(main())
