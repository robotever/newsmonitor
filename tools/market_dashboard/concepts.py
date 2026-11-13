"""Versioned, fail-closed concept-universe configuration."""
from pathlib import Path
import json
import math
import re

from .scoring import score_family


DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / 'config/market-concepts.json'
_CODE = re.compile(r'^884\d{2,4}\.WI$')
_EXCLUDED_NAME = re.compile(
    r'(?:\[HK\]|\[US\]|金股|国资改革|地方国企|央企|TOP\d+|前二十|增仓|减仓|'
    r'最小市值|成交主力|领涨龙头|近端次新股)'
)
_UNSAFE_NAME = re.compile(r'[<>\x00-\x1f]')


class ConceptConfigError(ValueError):
    """Raised when the checked-in concept universe is unsafe or inconsistent."""


def _require(condition):
    if not condition:
        raise ConceptConfigError('INVALID_CONCEPT_CONFIG')


def load_concept_config(path=None):
    try:
        value = json.loads(Path(path or DEFAULT_CONFIG).read_text())
    except (OSError, ValueError, TypeError):
        raise ConceptConfigError('INVALID_CONCEPT_CONFIG') from None
    _require(isinstance(value, dict))
    _require(value.get('selectionVersion') == 'concept-selection-v0.1')
    _require(isinstance(value.get('candidateVersion'), str) and 1 <= len(value['candidateVersion']) <= 100)
    universe, core = value.get('universe'), value.get('coreIds')
    _require(isinstance(universe, list) and 60 <= len(universe) <= 100)
    _require(isinstance(core, list) and len(core) == 25 and len(set(core)) == 25)
    codes = []
    for entry in universe:
        _require(isinstance(entry, dict) and set(entry) <= {'id', 'name', 'group', 'intent'})
        _require({'id', 'name', 'group'} <= set(entry))
        code, name, group = entry['id'], entry['name'], entry['group']
        _require(isinstance(code, str) and _CODE.fullmatch(code))
        _require(isinstance(name, str) and 1 <= len(name) <= 100
                 and not _UNSAFE_NAME.search(name) and not _EXCLUDED_NAME.search(name))
        _require(isinstance(group, str) and re.fullmatch(r'[a-z][a-z-]{1,39}', group))
        if 'intent' in entry:
            _require(isinstance(entry['intent'], str) and 1 <= len(entry['intent']) <= 100
                     and not _UNSAFE_NAME.search(entry['intent']))
        codes.append(code)
    _require(len(codes) == len(set(codes)))
    _require(all(isinstance(code, str) and code in set(codes) for code in core))
    return value


def concept_definitions(config):
    _require(isinstance(config, dict) and isinstance(config.get('universe'), list))
    return tuple((entry['id'], entry['name']) for entry in config['universe'])


def core_concept_ids(config):
    _require(isinstance(config, dict) and isinstance(config.get('coreIds'), list))
    return tuple(config['coreIds'])


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _selection_score(candidate, config):
    weights = config['conceptSelection']['weights']
    components = candidate.get('selectionComponents', {})
    observed = [(components.get(key), weight) for key, weight in weights.items()
                if _number(components.get(key))]
    used = sum(weight for _, weight in observed)
    return sum(value * weight for value, weight in observed) / used if used else None


def _eligible(candidate, config):
    minimum = config['conceptSelection']['minimumCompleteness']
    return (not candidate.get('core') and _number(candidate.get('completeness'))
            and candidate['completeness'] >= minimum
            and _number(candidate.get('selectionCompleteness'))
            and candidate['selectionCompleteness'] >= minimum
            and _selection_score(candidate, config) is not None)


def _ranked(candidates, config):
    eligible = []
    for candidate in candidates:
        if not _eligible(candidate, config):
            continue
        item = dict(candidate)
        item['selectionScore'] = round(_selection_score(item, config), 2)
        eligible.append(item)
    return sorted(eligible, key=lambda item: (
        -item['selectionScore'],
        -(item.get('selectionComponents', {}).get('flow')
          if _number(item.get('selectionComponents', {}).get('flow')) else -1),
        -(item.get('relativeReturn5dRaw') if _number(item.get('relativeReturn5dRaw')) else -math.inf),
        item['id'],
    ))


def select_dynamic_concepts(candidates, previous, market_date, config):
    """Select a deterministic, low-churn ten-concept dynamic roster."""
    settings = config['conceptSelection']
    slots = settings['dynamicSlots']
    ranked = _ranked(candidates, config)
    if len(ranked) < slots:
        raise ValueError('INSUFFICIENT_ELIGIBLE_CONCEPTS')
    by_id = {item['id']: item for item in ranked}
    rank_by_id = {item['id']: index + 1 for index, item in enumerate(ranked)}
    prior = [item for item in previous if isinstance(item, dict)
             and isinstance(item.get('id'), str)]

    same_day = bool(prior) and all(item.get('selectedOn') == market_date for item in prior)
    retained = []
    for old in prior:
        current = by_id.get(old['id'])
        if current is None:
            continue
        days = old.get('retainedTradingDays', 0)
        if not isinstance(days, int) or isinstance(days, bool) or days < 1:
            continue
        keep = (same_day or days < settings['minimumHoldTradingDays']
                or rank_by_id[old['id']] <= settings['exitBufferRank'])
        if not keep:
            continue
        item = dict(current)
        item['selectedOn'] = old.get('selectedOn', market_date)
        item['retainedTradingDays'] = days if same_day else days + 1
        retained.append(item)

    # Preserve the published order within a day and for retained names; fill
    # vacancies in the deterministic ranking order.
    selected_ids = {item['id'] for item in retained}
    result = retained[:slots]
    for item in ranked:
        if len(result) == slots:
            break
        if item['id'] in selected_ids:
            continue
        new_item = dict(item)
        new_item['selectedOn'] = market_date
        new_item['retainedTradingDays'] = 1
        result.append(new_item)
        selected_ids.add(item['id'])
    if len(result) != slots:
        raise ValueError('INSUFFICIENT_ELIGIBLE_CONCEPTS')
    return result


def _public(candidate, *, dynamic=False):
    internal = {'core', 'coreOrder', 'selectionComponents',
                'selectionCompleteness', 'relativeReturn5dRaw', 'indicators'}
    if not dynamic:
        internal |= {'selectionScore', 'selectedOn', 'retainedTradingDays'}
    return {key: value for key, value in candidate.items() if key not in internal}


def build_concept_payload(candidates, previous_dynamic, market_date, selected_at, config):
    """Score candidates and build the derived-only core/dynamic payload."""
    scored = []
    for candidate in candidates:
        item = score_family('concept', candidate, config)
        for key in ('core', 'coreOrder', 'selectionComponents',
                    'selectionCompleteness', 'relativeReturn5dRaw'):
            if key in candidate:
                item[key] = candidate[key]
        scored.append(item)
    core = sorted((item for item in scored if item.get('core')),
                  key=lambda item: item.get('coreOrder', math.inf))
    if len(core) != 25:
        raise ValueError('INVALID_CORE_CONCEPTS')
    dynamic = select_dynamic_concepts(scored, previous_dynamic, market_date, config)
    return {
        'selectionVersion': config['conceptSelection']['version'],
        'scoringVersion': config['conceptSelection']['scoringVersion'],
        'selectedAt': selected_at,
        'core': [_public(item) for item in core],
        'dynamic': [_public(item, dynamic=True) for item in dynamic],
    }
