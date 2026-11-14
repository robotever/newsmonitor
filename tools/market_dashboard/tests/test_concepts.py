import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

try:
    from tools.market_dashboard.concepts import (
        ConceptConfigError,
        concept_definitions,
        core_concept_ids,
        load_concept_config,
    )
except ModuleNotFoundError:
    ConceptConfigError = None
    concept_definitions = None
    core_concept_ids = None
    load_concept_config = None

from tools.market_dashboard.scoring import load_config
from tools.market_dashboard.sources import SourceBatch

try:
    from tools.market_dashboard.concepts import build_concept_payload, select_dynamic_concepts
except ImportError:
    build_concept_payload = None
    select_dynamic_concepts = None

try:
    from tools.market_dashboard.job import derive_concept_candidates
except ImportError:
    derive_concept_candidates = None


class ConceptConfigTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(load_concept_config, 'concept configuration module is missing')

    def test_default_config_has_verified_universe_and_exact_core_membership(self):
        config = load_concept_config()
        definitions = concept_definitions(config)
        core = core_concept_ids(config)

        self.assertEqual(config['selectionVersion'], 'concept-selection-v0.1')
        self.assertGreaterEqual(len(definitions), 60)
        self.assertLessEqual(len(definitions), 100)
        self.assertEqual(len(definitions), len(set(code for code, _ in definitions)))
        self.assertEqual(len(core), 25)
        self.assertEqual(len(core), len(set(core)))
        self.assertTrue(set(core) <= {code for code, _ in definitions})
        self.assertTrue(all(code.endswith('.WI') for code, _ in definitions))

    def test_config_rejects_unknown_core_duplicate_or_non_wind_id(self):
        config = load_concept_config()
        invalid = []

        duplicate = copy.deepcopy(config)
        duplicate['universe'].append(copy.deepcopy(duplicate['universe'][0]))
        invalid.append(duplicate)

        unknown_core = copy.deepcopy(config)
        unknown_core['coreIds'][0] = '8849999.WI'
        invalid.append(unknown_core)

        non_wind = copy.deepcopy(config)
        non_wind['universe'][0]['id'] = 'BK1184'
        invalid.append(non_wind)

        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ConceptConfigError):
                    load_concept_config(self._write(value))

    def test_config_rejects_non_a_share_or_non_concept_names(self):
        base = load_concept_config()
        rejected = [
            ('8877015.WI', '[HK]AI安全指数'),
            ('8884055.WI', '[US]云计算指数'),
            ('8841454.WI', '申万宏源金股指数'),
            ('8841923.WI', '深圳国资改革指数'),
            ('8841695.WI', '地方国企综合指数'),
            ('8841947.WI', '成交额TOP20指数'),
        ]
        for code, name in rejected:
            candidate = copy.deepcopy(base)
            candidate['universe'][0].update(id=code, name=name)
            candidate['coreIds'] = [code if item == base['universe'][0]['id'] else item
                                    for item in candidate['coreIds']]
            with self.subTest(name=name):
                with self.assertRaises(ConceptConfigError):
                    load_concept_config(self._write(candidate))

    def test_config_rejects_wrong_versions_counts_and_unsafe_names(self):
        base = load_concept_config()
        cases = []

        version = copy.deepcopy(base)
        version['selectionVersion'] = 'unknown'
        cases.append(version)

        too_small = copy.deepcopy(base)
        too_small['universe'] = too_small['universe'][:59]
        cases.append(too_small)

        wrong_core_count = copy.deepcopy(base)
        wrong_core_count['coreIds'] = wrong_core_count['coreIds'][:-1]
        cases.append(wrong_core_count)

        unsafe = copy.deepcopy(base)
        unsafe['universe'][0]['name'] = '<script>alert(1)</script>'
        cases.append(unsafe)

        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(ConceptConfigError):
                    load_concept_config(self._write(value))

    def _write(self, value):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'concepts.json'
        path.write_text(json.dumps(value, ensure_ascii=False))
        return path


class ConceptDerivationTests(unittest.TestCase):
    @staticmethod
    def batch(count=20, missing=None, source='Wind'):
        rows = []
        for index in range(count):
            row = {
                'id': f'884{2000 + index}.WI', 'name': f'概念{index}', 'source': source,
                '_timestamp': '2026-11-13T15:00:02+08:00',
                '_units': {'成交额': '元', '当日主力净流入额': '元', '近5日主力净流入额': '元',
                           '近20日主力净流入额': '元', '上涨家数': '个', '下跌家数': '个', '平盘家数': '个'},
                '涨跌幅': index - 10, '5日涨跌幅': index - 8, '20日涨跌幅': index - 5,
                '成交额': 1_000_000_000 + index * 10_000_000, '换手率': 1 + index / 10,
                '当日主力净流入额': (index - 10) * 1_000_000,
                '近5日主力净流入额': (index - 8) * 5_000_000,
                '近20日主力净流入额': (index - 5) * 20_000_000,
                '上涨家数': 10 + index, '下跌家数': 30 - index, '平盘家数': 2,
            }
            if missing is not None and index == 0:
                row[missing] = '.'
            rows.append(row)
        return SourceBatch('Wind', rows, 'wind', [], True)

    def test_derivation_uses_full_wind_universe_without_mx_or_natural_language_fields(self):
        self.assertIsNotNone(derive_concept_candidates, 'concept derivation is missing')
        candidates = derive_concept_candidates(
            self.batch(), 200_000_000_000, 60,
            datetime.fromisoformat('2026-11-13T15:05:00+08:00'), load_config())

        self.assertEqual(len(candidates), 20)
        for candidate in candidates:
            self.assertEqual(candidate['frequency'], 'intraday')
            self.assertNotIn('technicalIndicators', candidate)
            self.assertNotIn('fundamentals', candidate)
            for component in candidate['indicators'].values():
                self.assertNotEqual(component.get('source'), 'MX')
            for key in ('relativeReturn1d', 'relativeReturn5d', 'relativeReturn20d',
                        'turnoverCrossSection', 'amountCrossSection', 'mainFlowDirection'):
                self.assertEqual(len(candidate['indicators'][key]['history']), 20)

    def test_derivation_keeps_missing_inputs_unavailable_instead_of_zero(self):
        self.assertIsNotNone(derive_concept_candidates, 'concept derivation is missing')
        candidates = derive_concept_candidates(
            self.batch(missing='5日涨跌幅'), 200_000_000_000, 60,
            datetime.fromisoformat('2026-11-13T15:05:00+08:00'), load_config())
        component = candidates[0]['indicators']['relativeReturn5d']
        self.assertIsNone(component['value'])
        self.assertFalse(component['available'])
        self.assertNotEqual(component['value'], 0)


class ConceptSelectionTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(select_dynamic_concepts, 'concept selector is missing')
        self.config = load_config()

    @staticmethod
    def candidate(index, *, score=None, complete=100, core=False):
        value = 90 - index if score is None else score
        return {
            'id': f'884{3000 + index}.WI', 'name': f'候选{index}', 'core': core,
            'strength': 60, 'heat': 50, 'risk': 40, 'completeness': complete,
            'missing': [], 'contributors': [], 'sourceTimestamps': [],
            'selectionComponents': {'momentum': value, 'flow': value, 'breadth': value, 'activity': value},
            'selectionCompleteness': complete, 'relativeReturn5dRaw': value,
        }

    def test_first_day_excludes_core_returns_ten_unique_and_breaks_ties_by_code(self):
        candidates = [self.candidate(i, score=50, core=i < 2) for i in range(14)]
        result = select_dynamic_concepts(candidates, [], '2026-11-13', self.config)
        self.assertEqual(len(result), 10)
        self.assertEqual(len({item['id'] for item in result}), 10)
        self.assertTrue(all(not item['core'] for item in result))
        self.assertEqual([item['id'] for item in result], sorted(item['id'] for item in result))
        self.assertTrue(all(item['selectedOn'] == '2026-11-13' and item['retainedTradingDays'] == 1
                            for item in result))

    def test_same_day_reuses_identity_and_two_day_hold_exits_invalid_immediately(self):
        candidates = [self.candidate(i) for i in range(20)]
        first = select_dynamic_concepts(candidates, [], '2026-11-13', self.config)
        reordered = list(reversed(candidates))
        same_day = select_dynamic_concepts(reordered, first, '2026-11-13', self.config)
        self.assertEqual([item['id'] for item in same_day], [item['id'] for item in first])
        self.assertEqual([item['retainedTradingDays'] for item in same_day], [1] * 10)

        next_day_candidates = [dict(item) for item in candidates]
        for item in next_day_candidates[:10]:
            item['selectionComponents'] = {key: 0 for key in item['selectionComponents']}
        next_day_candidates[0]['selectionCompleteness'] = 0
        second = select_dynamic_concepts(next_day_candidates, first, '2026-11-14', self.config)
        self.assertNotIn(first[0]['id'], [item['id'] for item in second])
        self.assertTrue(set(item['id'] for item in first[1:]) <= set(item['id'] for item in second))

    def test_after_hold_only_rank_fifteen_buffer_is_retained(self):
        candidates = [self.candidate(i) for i in range(25)]
        previous = []
        for rank in (14, 15):
            item = self.candidate(rank)
            item.update(selectedOn='2026-11-10', retainedTradingDays=2, selectionScore=100 - rank)
            previous.append(item)
        result = select_dynamic_concepts(candidates, previous, '2026-11-13', self.config)
        ids = {item['id'] for item in result}
        self.assertIn(self.candidate(14)['id'], ids)
        self.assertNotIn(self.candidate(15)['id'], ids)

    def test_fewer_than_ten_eligible_candidates_fails_explicitly(self):
        candidates = [self.candidate(i, complete=100 if i < 9 else 0) for i in range(12)]
        with self.assertRaises(ValueError):
            select_dynamic_concepts(candidates, [], '2026-11-13', self.config)

    def test_payload_scores_core_and_emits_selection_metadata_only_for_dynamic(self):
        self.assertIsNotNone(build_concept_payload, 'concept payload builder is missing')
        config = self.config
        keys = {key for weights in config.get('families', {}).get('concept', {}).values() for key in weights}
        candidates = []
        for index in range(40):
            candidate = self.candidate(index, core=index < 25)
            candidate['coreOrder'] = index if index < 25 else None
            candidate['indicators'] = {key: {'value': 60, 'source': 'Wind',
                'timestamp': '2026-11-13T15:00:02+08:00'} for key in keys}
            candidates.append(candidate)
        payload = build_concept_payload(candidates, [], '2026-11-13',
                                        '2026-11-13T15:05:00+08:00', config)
        self.assertEqual(payload['selectionVersion'], 'concept-selection-v0.1')
        self.assertEqual(payload['scoringVersion'], 'concept-score-v0.1')
        self.assertEqual(len(payload['core']), 25)
        self.assertEqual(len(payload['dynamic']), 10)
        self.assertTrue(all('selectionScore' not in item for item in payload['core']))
        self.assertTrue(all({'selectionScore', 'selectedOn', 'retainedTradingDays'} <= item.keys()
                            for item in payload['dynamic']))


if __name__ == '__main__':
    unittest.main()
