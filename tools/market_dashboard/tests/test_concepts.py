import copy
import json
import tempfile
import unittest
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


if __name__ == '__main__':
    unittest.main()
