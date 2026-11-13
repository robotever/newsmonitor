"""Versioned, fail-closed concept-universe configuration."""
from pathlib import Path
import json
import re


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
