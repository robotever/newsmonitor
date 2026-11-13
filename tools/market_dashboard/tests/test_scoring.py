"""Deterministic tests for the public scoring contract."""
import unittest
from copy import deepcopy

from tools.market_dashboard.scoring import (
    compute_completeness, percentile_rank, weighted_score,
    build_dashboard_payload, load_config, score_family, classify_market_stage,
)


class PrimitiveTests(unittest.TestCase):
    def test_percentile_winsorizes_extremes(self):
        values = list(range(100))
        self.assertEqual(percentile_rank(values, -10000), 2.5)
        self.assertEqual(percentile_rank(values, 10000), 97.5)
        self.assertEqual(percentile_rank([5], 5), 50)
        self.assertEqual(percentile_rank([2, 2, 2], 2), 50)
        self.assertIsNone(percentile_rank([], 1))

    def test_reverse_indicator_changes_direction(self):
        result = weighted_score([{'value': 80, 'weight': 1, 'reverse': True}])
        self.assertEqual(result.score, 20)
        self.assertEqual(result.raw, 20)
        self.assertEqual(result.completeness, 100)
        for value, want in [(-50, 0), (150, 100)]:
            self.assertEqual(weighted_score([{'value': value, 'weight': 1}]).score, want)

    def test_missing_component_reduces_completeness_without_zero_score(self):
        components = [{'value': 80, 'weight': .35}, {'value': None, 'weight': .65}]
        result = weighted_score(components)
        self.assertEqual(result.score, 80)
        self.assertEqual(result.used_weight, .35)
        self.assertEqual(result.total_weight, 1)
        self.assertEqual(compute_completeness(components), 35)
        result = weighted_score([{'value': None, 'weight': 1}])
        self.assertIsNone(result.score)
        self.assertIsNone(result.raw)
        self.assertEqual(result.completeness, 0)


class FormulaTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()

    def test_all_four_families_apply_exact_design_weights(self):
        # One-hot inputs independently expose every configured weight in output.
        expected = {
            'aShare': [[35,25,20,20], [30,25,25,20], [30,25,20,15,10]],
            'global': [[25,30,20,15,10], [30,25,20,15,10], [25,25,20,15,15]],
            'style': [[25,25,20,15,15], [35,25,20,20], [25,25,20,20,10]],
            'industry': [[20,20,15,30,15], [30,30,20,20], [30,25,20,15,10]],
        }
        for family, score_weights in expected.items():
            for score_name, want_weights in zip(('strength','heat','risk'), score_weights):
                weights = self.config['families'][family][score_name]
                self.assertEqual(sum(weights.values()), 100)
                keys = list(weights)
                for key, expected_score in zip(keys, want_weights):
                    indicators = {k: {'value': 0} for k in keys}
                    indicators[key]['value'] = 100
                    with self.subTest(family=family, score=score_name, component=key):
                        self.assertEqual(score_family(family, {'indicators':indicators}, self.config)[score_name], expected_score)

    def test_cold_start_discount_stale_and_rolling_window(self):
        component = {'value': 8, 'weight': 1, 'mode':'rolling', 'history':[1,2], 'fixedBounds':[0,10]}
        result = weighted_score([component], self.config)
        self.assertEqual((result.score, result.completeness, result.cold_start), (80,85,True))
        self.assertIsNone(weighted_score([{**component, 'fixedBounds':None}]).score)
        self.assertIsNone(weighted_score([{**component, 'stale':True}]).score)
        self.assertEqual(compute_completeness([{**component,'available':False}]), 0)
        rolling = {**component, 'value':30, 'history': [-1000]*60 + list(range(60))}
        self.assertAlmostEqual(weighted_score([rolling]).raw, 50.83333333333333)
        cross = {'value':2, 'weight':1, 'mode':'cross_sectional','history':[1,2,3]}
        self.assertEqual(weighted_score([cross]).score, 50)

    def test_public_rounding_retains_raw_precision_and_rejects_invalid_weights(self):
        result = weighted_score([{'value':33.25,'weight':1},{'value':33.75,'weight':1}])
        self.assertEqual((result.score,result.raw), (34,33.5))
        for weight in (-1, float('nan'), True):
            with self.assertRaises(ValueError):
                weighted_score([{'value':50,'weight':weight}])
        self.assertIsNone(percentile_rank([None,float('inf')], 10))

    def test_payload_is_deterministic_keeps_provenance_and_ignores_news(self):
        indicators = {k: {'value':80, 'timestamp':'2026-11-13T10:15:00+08:00', 'source':'fixture', 'unit':'score'}
                      for weights in self.config['families']['aShare'].values() for k in weights}
        inputs = {'observedAt':'2026-11-13T10:15:00+08:00','marketDate':'2026-11-13','session':'intraday',
                  'aShare':{'indicators':indicators}, 'news':[{'title':'ignored','sentiment':0}]}
        original = deepcopy(inputs)
        result = build_dashboard_payload(inputs, [], self.config)
        self.assertEqual(result['schemaVersion'], 'market-dashboard-v1')
        self.assertEqual(result['scoringVersion'], 'market-score-v0.1')
        self.assertEqual([result['aShare'][k] for k in ('strength','heat','risk')], [80,80,80])
        self.assertEqual(result['aShare']['completeness'],100)
        self.assertEqual(result['global']['completeness'],0)
        self.assertIsNone(result['global']['strength'])
        self.assertEqual(result['aShare']['sourceTimestamps'],[{'source':'fixture','timestamp':'2026-11-13T10:15:00+08:00'}])
        self.assertLessEqual(len(result['aShare']['contributors']),3)
        self.assertNotIn('news', result)
        self.assertEqual(build_dashboard_payload(inputs, [], self.config), result)
        self.assertEqual(inputs, original)
        inputs['news'] = []
        self.assertEqual(build_dashboard_payload(inputs, [], self.config), result)

    def test_config_controls_weights_without_python_constants(self):
        config = deepcopy(self.config)
        config['families']['aShare']['strength'] = {'custom':100}
        self.assertEqual(score_family('aShare', {'indicators':{'custom':{'value':73}}},config)['strength'],73)


class StageAndComparisonTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.inputs = {'observedAt':'2026-11-13T10:15:00+08:00','marketDate':'2026-11-13','session':'intraday',
                       'tradingDates':['2026-11-06','2026-11-09','2026-11-10','2026-11-11','2026-11-12','2026-11-13']}
        self.inputs['aShare'] = {'indicators':{k:{'value':60} for ws in self.config['families']['aShare'].values() for k in ws}}

    def snapshot(self, day, clock, values=(20,30,40), session='intraday'):
        return {'observedAt':f'{day}T{clock}:00+08:00','marketDate':day,'session':session,
                'scoringVersion':'market-score-v0.1',
                'aShare':dict(zip(('strength','heat','risk'),values),id='a-share',completeness=100)}

    def test_all_six_stages_and_low_completeness(self):
        fixtures = [
            ((70,80,60),(0,0),'过热'),
            ((39,50,70),(-5,5),'退潮'),
            ((29,39,70),(0,0),'冰点'),
            ((70,50,59),(0,0),'扩张'),
            ((30,69,50),(5,-5),'修复'),
            ((55,50,50),(0,0),'震荡'),
        ]
        for values, slopes, want in fixtures:
            scores = dict(zip(('strength','heat','risk'),values))
            directions = dict(zip(('strength','risk'),slopes))
            with self.subTest(want=want):
                self.assertEqual(classify_market_stage(scores,directions,50,self.config),want)
                self.assertIsNone(classify_market_stage(scores,directions,49,self.config))
        self.assertIsNone(classify_market_stage({'strength':None,'heat':80,'risk':80},{},100,self.config))
        config = deepcopy(self.config)
        config['stages'][0]['conditions']['heat']['min'] = 90
        self.assertEqual(classify_market_stage({'strength':70,'heat':80,'risk':60},{},100,config),'震荡')

    def test_stage_boundaries_and_priority(self):
        cases = [((29,39,70),(-5,0),'退潮'), ((29,39,70),(0,1),'震荡'),
                 ((29,40,70),(0,0),'震荡'), ((70,79,60),(0,0),'震荡'),
                 ((70,80,59),(0,0),'扩张'), ((54,69,50),(5,-5),'修复'),
                 ((55,69,50),(5,-5),'震荡'), ((30,70,50),(5,-5),'震荡')]
        for scores,slopes,want in cases:
            self.assertEqual(classify_market_stage(dict(zip(('strength','heat','risk'),scores)),
                             dict(zip(('strength','risk'),slopes)),100,self.config),want)

    def test_same_clock_comparisons_select_nearest_and_fifth_trading_day(self):
        previous = [self.snapshot('2026-11-12','10:35'), self.snapshot('2026-11-12','10:16'),
                    self.snapshot('2026-11-12','15:00',(90,90,90),'close'),
                    self.snapshot('2026-11-06','10:15',(10,20,30))]
        result = build_dashboard_payload(self.inputs,previous,self.config)['aShare']
        self.assertEqual(result['change1d'],{'strength':40,'heat':30,'risk':20})
        self.assertEqual(result['change5d'],{'strength':50,'heat':40,'risk':30})
        self.assertNotIn('comparisonFallback',result)

    def test_twenty_minute_boundary_and_close_fallback(self):
        exact = self.snapshot('2026-11-12','10:35')
        result = build_dashboard_payload(self.inputs,[exact],self.config)['aShare']
        self.assertEqual(result['change1d']['strength'],40)
        outside = self.snapshot('2026-11-12','10:36')
        close = self.snapshot('2026-11-12','15:00',(50,50,50),'close')
        result = build_dashboard_payload(self.inputs,[outside,close],self.config)['aShare']
        self.assertEqual(result['change1d']['strength'],10)
        self.assertEqual(result['comparisonFallback'],'close')
        self.assertIsNone(result['change5d'])

    def test_close_final_only_compares_with_close_final(self):
        self.inputs.update(session='close',observedAt='2026-11-13T15:00:00+08:00')
        previous = [self.snapshot('2026-11-12','14:59',(0,0,0)),
                    self.snapshot('2026-11-12','15:05',(50,50,50),'close')]
        result = build_dashboard_payload(self.inputs,previous,self.config)['aShare']
        self.assertEqual(result['change1d']['strength'],10)
        self.assertNotIn('comparisonFallback',result)

    def test_sparse_snapshots_without_calendar_do_not_invent_trading_days(self):
        self.inputs.pop('tradingDates')
        result = build_dashboard_payload(self.inputs,[self.snapshot('2026-11-12','10:15')],self.config)['aShare']
        self.assertIsNone(result['change1d'])
        self.assertIsNone(result['change5d'])
        self.assertEqual(result['comparisonUnavailable']['change1d'],'missingTradingCalendar')
        self.inputs['tradingDates'] = ['2026-11-13']
        result = build_dashboard_payload(self.inputs,[],self.config)['aShare']
        self.assertIsNone(result['change1d'])

    def test_daily_objects_use_distinct_valid_observations_and_not_intraday_duplicates(self):
        self.inputs.pop('tradingDates')
        self.inputs['global'] = {'frequency':'daily','observedAt':'2026-11-12T00:00:00Z',
            'indicators':{k:{'value':60} for ws in self.config['families']['global'].values() for k in ws}}
        previous = []
        for day in (5,6,7,8,9,10,11,11,12):
            snap = self.snapshot(f'2026-11-{day:02d}','10:15')
            snap['global'] = {'id':'global','frequency':'daily','observedAt':f'2026-11-{day:02d}T00:00:00Z',
                              'strength':day,'heat':day,'risk':day,'completeness':100}
            previous.append(snap)
        result = build_dashboard_payload(self.inputs,previous,self.config)['global']
        self.assertEqual(result['change1d']['strength'],49)
        self.assertEqual(result['change5d']['strength'],53)
        self.assertNotIn('comparisonFallback',result)

    def test_comparisons_never_cross_scoring_versions(self):
        previous = self.snapshot('2026-11-12','10:15')
        previous['scoringVersion'] = 'old-score'
        result = build_dashboard_payload(self.inputs,[previous],self.config)['aShare']
        self.assertIsNone(result['change1d'])


class PayloadIsolationTests(unittest.TestCase):
    def test_style_and_industry_comparisons_match_ids_and_never_copy_raw_data(self):
        config = load_config()
        inputs = {'observedAt':'2026-11-13T10:15:00+08:00','marketDate':'2026-11-13','session':'intraday',
                  'tradingDates':['2026-11-12','2026-11-13']}
        previous = {'observedAt':'2026-11-12T10:15:00+08:00','marketDate':'2026-11-12','session':'intraday',
                    'scoringVersion':'market-score-v0.1'}
        for section,family in (('styles','style'),('industries','industry')):
            inputs[section] = [{'id':'wanted','name':'fixture','rawResponse':{'private':'excluded'},
                'indicators':{k:{'value':80,'weight':9999} for ws in config['families'][family].values() for k in ws}}]
            previous[section] = [{'id':'other','strength':0,'heat':0,'risk':0},
                                 {'id':'wanted','strength':50,'heat':50,'risk':50}]
        result = build_dashboard_payload(inputs,[previous],config)
        for section in ('styles','industries'):
            obj = result[section][0]
            self.assertEqual(obj['change1d'],{'strength':30,'heat':30,'risk':30})
            self.assertNotIn('rawResponse',obj)
            self.assertNotIn('indicators',obj)
        self.assertEqual(result['styles'][0]['completeness'],100)

    def test_same_clock_comparison_uses_beijing_time_across_offsets(self):
        config = load_config()
        inputs = {'observedAt':'2026-11-13T02:15:00Z','marketDate':'2026-11-13','session':'intraday',
                  'tradingDates':['2026-11-12','2026-11-13'],
                  'aShare':{'indicators':{k:{'value':60} for ws in config['families']['aShare'].values() for k in ws}}}
        previous = [{'observedAt':'2026-11-12T10:15:00+08:00','marketDate':'2026-11-12','session':'intraday',
                     'scoringVersion':'market-score-v0.1','aShare':{'strength':50,'heat':50,'risk':50}}]
        self.assertEqual(build_dashboard_payload(inputs,previous,config)['aShare']['change1d']['strength'],10)


if __name__ == '__main__':
    unittest.main()
