"""Pure deterministic scoring of normalized source components.

A component without ``mode`` contains an already normalized 0–100 ``value``.
Raw components use ``mode`` rolling/cross_sectional/fixed, optional ``history``
and ``fixedBounds``. Missing and stale components remain in completeness's
expected denominator but never in the score denominator. Source dictionaries
may also carry timestamp, unit, source, label and evidence metadata.
"""
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import json
import math
from datetime import datetime, timedelta, timezone


def load_config(path=None):
    """Explicit local config loader; no provider access or mutable global state."""
    return json.loads(Path(path or Path(__file__).resolve().parents[2] / 'config/market-dashboard.json').read_text())


_DEFAULT_CONFIG = load_config()


@dataclass(frozen=True)
class ScoreResult:
    score: int | None
    raw: float | None
    completeness: int
    used_weight: float
    total_weight: float
    cold_start: bool


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _round(value):
    return int(math.floor(value + .5))


def _quantile(values, fraction):
    index = (len(values) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def percentile_rank(values, value, config=None):
    """Midpoint empirical percentile after 5/95 winsorization; ties share rank."""
    config = config or _DEFAULT_CONFIG
    valid = sorted(float(v) for v in values if _number(v))
    if not valid or not _number(value):
        return None
    lower = _quantile(valid, config['normalization']['winsorLower'])
    upper = _quantile(valid, config['normalization']['winsorUpper'])
    clipped = [min(upper, max(lower, v)) for v in valid]
    target = min(upper, max(lower, value))
    below = sum(v < target for v in clipped)
    equal = sum(v == target for v in clipped)
    return (below + .5 * equal) / len(clipped) * 100


def _components(components):
    return list(components.values()) if isinstance(components, Mapping) else list(components)


def _normalized(component, config):
    value = component.get('value')
    if not component.get('available', True) or component.get('stale', False) or not _number(value):
        return None, False
    mode = component.get('mode')
    cold = False
    if mode in ('rolling', 'cross_sectional'):
        history = [v for v in component.get('history', []) if _number(v)]
        if mode == 'rolling':
            history = history[-config['history']['rollingObservations']:]
        if mode == 'cross_sectional' or len(history) >= config['history']['minimumObservations']:
            value = percentile_rank(history, value, config)
        else:
            mode, cold = 'fixed', True
    if mode == 'fixed':
        bounds = component.get('fixedBounds')
        if not bounds or len(bounds) != 2 or not all(_number(v) for v in bounds) or bounds[0] >= bounds[1]:
            return None, False
        value = (value - bounds[0]) / (bounds[1] - bounds[0]) * 100
    elif mode not in (None, 'rolling', 'cross_sectional'):
        raise ValueError(f'Unsupported normalization mode: {mode}')
    if value is None:
        return None, False
    value = min(100., max(0., value))
    return (100 - value if component.get('reverse', False) else value), cold


def weighted_score(components, config=None):
    """Renormalize observed weights, round only final score and completeness."""
    config = config or _DEFAULT_CONFIG
    total = used = effective = numerator = 0.
    any_cold = False
    for component in _components(components):
        weight = component.get('weight', 0)
        if not _number(weight) or weight < 0:
            raise ValueError('Component weight must be finite and nonnegative')
        total += weight
        value, cold = _normalized(component, config)
        if value is not None and weight:
            numerator += weight * value
            used += weight
            effective += weight * (config['history']['coldStartCompletenessMultiplier'] if cold else 1)
            any_cold |= cold
    raw = numerator / used if used else None
    return ScoreResult(_round(raw) if raw is not None else None, raw,
                       _round(effective / total * 100) if total else 0,
                       used, total, any_cold)


def compute_completeness(components, config=None):
    return weighted_score(components, config).completeness


def score_family(family, inputs, config=None):
    """Score one object using configured component IDs and authoritative weights.

    ``inputs`` contains id/name and ``indicators`` keyed by config component ID.
    Provider-supplied weights and unknown fields never override versioned config.
    Missing expected component IDs are explicitly reported.
    """
    config = config or _DEFAULT_CONFIG
    indicators = inputs.get('indicators', {})
    result = {k: inputs[k] for k in ('id', 'name', 'frequency', 'observedAt') if k in inputs}
    all_components, missing, contributors, timestamps = [], [], [], []
    for score_name, weights in config['families'][family].items():
        components = []
        for key, weight in weights.items():
            component = dict(indicators.get(key) or {})
            component['weight'] = weight
            components.append(component)
            all_components.append(component)
            value, _ = _normalized(component, config)
            if value is None:
                if key not in missing:
                    missing.append(key)
                continue
            source, timestamp = component.get('source'), component.get('timestamp')
            if isinstance(source, str) and isinstance(timestamp, str):
                provenance = {'source':source, 'timestamp':timestamp}
                if provenance not in timestamps:
                    timestamps.append(provenance)
        scored = weighted_score(components, config)
        result[score_name] = scored.score
        for key, component in zip(weights, components):
            value, _ = _normalized(component, config)
            if value is None:
                continue
            contribution = {'label': str(component.get('label',key)),
                            'impact': (value - 50) * component['weight'] / scored.used_weight}
            if isinstance(component.get('evidence'), str):
                contribution['evidence'] = component['evidence']
            contributors.append(contribution)
    result['completeness'] = compute_completeness(all_components, config)
    result['contributors'] = [{**c, 'impact':_round(abs(c['impact'])) * (-1 if c['impact'] < 0 else 1)}
                              for c in sorted(contributors, key=lambda c:abs(c['impact']), reverse=True)[:3]]
    result['sourceTimestamps'] = timestamps
    result['missing'] = missing
    return result


def build_dashboard_payload(inputs, previous, config):
    """Build only derived scores/provenance; never forward raw provider payloads.

    ``previous`` is a list of earlier dashboard payload snapshots. Comparison
    selection uses their explicit marketDate/session and never invents weekdays.
    """
    result = {key:inputs[key] for key in ('observedAt','marketDate','session')}
    result.update(schemaVersion=config['schemaVersion'], scoringVersion=config['scoringVersion'])
    result['global'] = score_family('global', inputs.get('global', {}), config)
    result['aShare'] = score_family('aShare', inputs.get('aShare', {}), config)
    result['global'].setdefault('id', 'global')
    result['aShare'].setdefault('id', 'a-share')
    for collection, family in (('styles','style'),('industries','industry')):
        result[collection] = [score_family(family, obj, config) for obj in inputs.get(collection, [])]
    objects = [result['global'],result['aShare'],*result['styles'],*result['industries']]
    for section in ('global','aShare'):
        _add_comparisons(result[section], section, inputs, previous or [], config)
    for collection in ('styles','industries'):
        for obj in result[collection]:
            _add_comparisons(obj, collection, inputs, previous or [], config)
    slopes = inputs.get('aShare', {}).get('slopes', result['aShare']['change1d'] or {})
    result['aShare']['stage'] = classify_market_stage(result['aShare'], slopes, result['aShare']['completeness'], config)
    result['dataStatus'] = {
        'completeness':_round(sum(obj['completeness'] for obj in objects) / len(objects)),
        'stale':any(c.get('stale',False) for section in (inputs.get('global',{}),inputs.get('aShare',{}),
                    *inputs.get('styles',[]),*inputs.get('industries',[])) for c in section.get('indicators',{}).values() if c),
        'missing':[f"{obj.get('id','unknown')}:{key}" for obj in objects for key in obj['missing']],
    }
    return result



def classify_market_stage(scores, slopes, completeness, config=None):
    """Apply ordered, versioned stage rules; insufficient evidence has no label."""
    config = config or _DEFAULT_CONFIG
    if completeness < config['completeness']['stageThreshold']:
        return None
    if not all(_number(scores.get(key)) for key in ('strength','heat','risk')):
        return None
    values = {**scores, **{key + 'Slope':value for key,value in slopes.items()}}
    for stage in config['stages']:
        matched = True
        for key, bounds in stage['conditions'].items():
            value = values.get(key)
            if not _number(value):
                matched = False
                break
            if ('min' in bounds and value < bounds['min'] or
                'max' in bounds and value > bounds['max'] or
                'lt' in bounds and value >= bounds['lt']):
                matched = False
                break
        if matched:
            return stage['label']
    return config['defaultStage']


def _time(value):
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError('Observation timestamps must include a timezone')
    return parsed


def _previous_object(snapshot, section, object_id):
    value = snapshot.get(section)
    if section in ('styles','industries'):
        return next((obj for obj in value or [] if obj.get('id') == object_id), None)
    return value


def _valid_scores(obj):
    return obj and any(_number(obj.get(key)) for key in ('strength','heat','risk'))


def _add_comparisons(obj, section, inputs, previous, config):
    candidates = []
    for snapshot in previous:
        if snapshot.get('scoringVersion') != config['scoringVersion']:
            continue
        old = _previous_object(snapshot, section, obj.get('id'))
        if _valid_scores(old):
            candidates.append((snapshot, old))
    unavailable = {}
    for lookback in config['comparison']['lookbacks']:
        key = f'change{lookback}d'
        selected = None
        reason = 'missingObservation'
        if not _valid_scores(obj):
            reason = 'missingCurrentScores'
        elif obj.get('frequency') in ('daily','monthly'):
            current_time = _time(obj.get('observedAt',inputs['observedAt']))
            observations = {}
            for snapshot, old in candidates:
                observed = _time(old.get('observedAt',snapshot['observedAt']))
                if observed < current_time:
                    # Deduplicate repeated publications of the same source observation.
                    observations[observed] = (snapshot,old)
            times = sorted(observations,reverse=True)
            if len(times) >= lookback:
                selected = observations[times[lookback-1]][1]
        else:
            dates = sorted(set(inputs.get('tradingDates',[])))
            current_date = inputs['marketDate']
            if not dates or current_date not in dates:
                reason = 'missingTradingCalendar'
            elif dates.index(current_date) < lookback:
                reason = 'missingTargetTradingDate'
            else:
                target = dates[dates.index(current_date)-lookback]
                day_candidates = [(snap,old) for snap,old in candidates if snap['marketDate'] == target]
                closes = [(snap,old) for snap,old in day_candidates if snap['session'] == 'close']
                if inputs['session'] == 'close':
                    if closes:
                        selected = max(closes,key=lambda pair:_time(pair[0]['observedAt']))[1]
                else:
                    beijing = timezone(timedelta(hours=8))
                    now = _time(inputs['observedAt']).astimezone(beijing)
                    def distance(pair):
                        then = _time(pair[0]['observedAt']).astimezone(beijing)
                        return abs((then.hour-now.hour)*3600+(then.minute-now.minute)*60+then.second-now.second)
                    same_clock = [pair for pair in day_candidates if pair[0]['session'] != 'close'
                                  and distance(pair) <= config['comparison']['toleranceMinutes']*60]
                    if same_clock:
                        selected = min(same_clock,key=lambda pair:(distance(pair),pair[0]['observedAt']))[1]
                    elif closes:
                        selected = max(closes,key=lambda pair:_time(pair[0]['observedAt']))[1]
                        obj['comparisonFallback'] = 'close'
        if selected is None:
            obj[key] = None
            unavailable[key] = reason
        else:
            obj[key] = {axis:obj[axis]-selected[axis] if _number(obj.get(axis)) and _number(selected.get(axis)) else None
                        for axis in ('strength','heat','risk')}
    if unavailable:
        obj['comparisonUnavailable'] = unavailable
