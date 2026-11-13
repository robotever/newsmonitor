"""Provider adapters are tested only with sanitized fixtures and injected I/O."""
import json
import io
import subprocess
from contextlib import redirect_stdout
import unittest
from pathlib import Path
from tools.market_dashboard import sources
from tools.market_dashboard.concepts import concept_definitions, load_concept_config


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class SourceTests(unittest.TestCase):

    def setUp(self):
        self.collect_wind_concepts = getattr(sources, 'collect_wind_concepts', None)

    @staticmethod
    def concept_envelope(definitions, *, timestamp='2026-11-13T15:00:02.000+08:00',
                         units=None):
        names = ['最新交易日', '交易时间', '中文简称', '涨跌幅', '5日涨跌幅', '20日涨跌幅',
                 '成交额', '换手率', '当日主力净流入额', '近5日主力净流入额',
                 '近20日主力净流入额', '上涨家数', '下跌家数', '平盘家数', 'Wind代码']
        columns = [{'name': name, 'type': 'string'} for name in names]
        rows = []
        for index, (code, name) in enumerate(definitions):
            rows.append(['20261113', timestamp, name, str(index / 10), str(index / 5),
                         str(index / 2), str(1000000000 + index), '2.5', str(index * 1000),
                         str(index * 2000), str(index * 3000), '20', '10', '1', code])
        return {'data': {'columns': columns, 'rows': rows, 'unit': units or {
            '成交额': '元', '当日主力净流入额': '元', '近5日主力净流入额': '元',
            '近20日主力净流入额': '元', '上涨家数': '个', '下跌家数': '个', '平盘家数': '个'}}}

    def test_concepts_use_two_serial_batches_and_preserve_exact_identities_and_units(self):
        self.assertIsNotNone(self.collect_wind_concepts, 'concept collector is missing')
        config = load_concept_config()
        definitions = concept_definitions(config)
        calls = []

        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            requested = json.loads(argv[-1])['windcode'].split(',')
            by_id = dict(definitions)
            return self.concept_envelope([(code, by_id[code]) for code in requested])

        batch = self.collect_wind_concepts(runner, {}, config)

        self.assertTrue(batch.complete)
        self.assertEqual(len(batch.rows), 75)
        self.assertEqual([len(json.loads(call[0][-1])['windcode'].split(',')) for call in calls], [50, 25])
        self.assertTrue(all(call[0][2:5] == ['call', 'index_data', 'get_index_price_indicators'] for call in calls))
        self.assertEqual([row['id'] for row in batch.rows], [code for code, _ in definitions])
        self.assertEqual(batch.rows[0]['_units']['成交额'], '元')
        self.assertEqual(batch.rows[0]['_timestamp'], '2026-11-13T15:00:02+08:00')

    def test_concept_first_batch_failure_stops_and_second_batch_failure_rejects_all(self):
        self.assertIsNotNone(self.collect_wind_concepts, 'concept collector is missing')
        config = load_concept_config()
        definitions = concept_definitions(config)
        calls = []

        def failed_probe(argv, **kwargs):
            calls.append(argv)
            return {'ok': False, 'code': 'AUTH_ERROR', 'message': 'secret'}

        batch = self.collect_wind_concepts(failed_probe, {}, config)
        self.assertEqual(len(calls), 1)
        self.assertEqual(batch.rows, [])
        self.assertEqual(batch.errors[0]['code'], 'AUTH_ERROR')
        self.assertNotIn('secret', str(batch.errors))

        calls.clear()
        by_id = dict(definitions)
        def broken_second(argv, **kwargs):
            calls.append(argv)
            requested = json.loads(argv[-1])['windcode'].split(',')
            values = [(code, by_id[code]) for code in requested]
            if len(calls) == 2:
                values[-1] = values[0]
            return self.concept_envelope(values)

        batch = self.collect_wind_concepts(broken_second, {}, config)
        self.assertEqual(len(calls), 2)
        self.assertEqual(batch.rows, [])
        self.assertEqual(batch.errors[0]['code'], 'IDENTITY_MISMATCH')

    def test_concept_batch_rejects_missing_wrong_or_duplicate_identifiers(self):
        self.assertIsNotNone(self.collect_wind_concepts, 'concept collector is missing')
        config = load_concept_config()
        definitions = concept_definitions(config)
        by_id = dict(definitions)
        for mutation in ('missing', 'wrong', 'duplicate'):
            calls = 0
            def runner(argv, **kwargs):
                nonlocal calls
                calls += 1
                requested = json.loads(argv[-1])['windcode'].split(',')
                values = [(code, by_id[code]) for code in requested]
                if calls == 1:
                    if mutation == 'missing':
                        values.pop()
                    elif mutation == 'wrong':
                        values[-1] = ('8849999.WI', '未知指数')
                    else:
                        values[-1] = values[0]
                return self.concept_envelope(values)
            with self.subTest(mutation=mutation):
                batch = self.collect_wind_concepts(runner, {}, config)
                self.assertEqual(batch.rows, [])
                self.assertEqual(batch.errors[0]['code'], 'IDENTITY_MISMATCH')

    def test_concept_batch_rejects_ambiguous_units_or_missing_timestamps(self):
        self.assertIsNotNone(self.collect_wind_concepts, 'concept collector is missing')
        config = load_concept_config()
        definitions = concept_definitions(config)
        by_id = dict(definitions)
        for problem in ('units', 'timestamp'):
            def runner(argv, **kwargs):
                requested = json.loads(argv[-1])['windcode'].split(',')
                values = [(code, by_id[code]) for code in requested]
                if problem == 'units':
                    return self.concept_envelope(values, units={
                        '成交额': 'unknown', '当日主力净流入额': '元', '近5日主力净流入额': '元',
                        '近20日主力净流入额': '元', '上涨家数': '个', '下跌家数': '个', '平盘家数': '个'})
                return self.concept_envelope(values, timestamp=None)
            with self.subTest(problem=problem):
                batch = self.collect_wind_concepts(runner, {}, config)
                self.assertEqual(batch.rows, [])
                self.assertEqual(batch.errors[0]['code'], 'UNIT_MISMATCH' if problem == 'units' else 'MISSING_FIELDS')

    def test_nested_content_retains_fields_units_and_nulls(self):
        rows = sources.parse_wind_content(fixture("wind-breadth.json"))
        self.assertEqual(rows[0]["Wind代码"], "881001.WI")
        self.assertEqual(rows[0]["成交额"], 123456789000.0)
        self.assertEqual(rows[0]["_units"]["成交额"], "元")
        self.assertEqual(rows[0]["_units"]["上涨家数"], "个")
        self.assertIsNone(rows[0]["平盘家数"])
        self.assertEqual(rows[0]["_timestamp"], "2026-11-13T10:15:00+08:00")

    def test_wind_numeric_missing_markers_preserve_text_but_reduce_completeness(self):
        for marker in (".", ""):
            with self.subTest(marker=marker):
                envelope = fixture("wind-styles.json")
                inner = json.loads(envelope["content"][0]["text"])
                inner["data"]["rows"][0][3] = marker
                envelope["content"][0]["text"] = json.dumps(inner)
                batch = sources.collect_wind_styles(lambda *a, **k: envelope, {})
                self.assertFalse(batch.complete)
                self.assertEqual(batch.rows[0]["涨跌幅"], marker)
                self.assertEqual(batch.errors[0]["code"], "MISSING_FIELDS")
                self.assertIn("涨跌幅", batch.errors[0]["fields"])

    def test_malformed_error_codes_return_an_unavailable_batch(self):
        for response in ({"ok": False, "code": []}, {"isError": True, "code": {}}):
            with self.subTest(response=response):
                batch = sources.collect_wind_styles(lambda *a, **k: response, {})
                self.assertFalse(batch.complete)
                self.assertEqual(batch.rows, [])
                self.assertEqual(batch.errors[0]["code"], "MALFORMED_RESPONSE")

    def test_nonzero_cli_error_preserves_safe_error_code(self):
        response = subprocess.CompletedProcess([], 1, '{"ok":false,"code":"AUTH_ERROR","message":"secret"}', 'secret')
        batch = sources.collect_wind_styles(lambda *a, **k: response, {})
        self.assertEqual(batch.errors[0]["code"], "AUTH_ERROR")

    def test_error_nested_in_data_or_malformed_numeric_field_rejects_group(self):
        for broken in ("backend", "numeric"):
            envelope = fixture("wind-styles.json")
            inner = json.loads(envelope["content"][0]["text"])
            if broken == "backend":
                inner["data"]["error"] = "secret backend failure"
            else:
                inner["data"]["rows"][0][3] = "not-a-number"
            envelope["content"][0]["text"] = json.dumps(inner)
            batch = sources.collect_wind_styles(lambda *a, **k: envelope, {})
            self.assertFalse(batch.complete)
            self.assertEqual(batch.rows, [])

    def test_malformed_error_and_duplicate_columns_fail_closed(self):
        for envelope in ({"ok": False, "code": "AUTH_ERROR"}, {"content": [{"text": "not json"}]},
            {"data": {"columns": ["x", "x"], "rows": [[1, 2]]}},
            {"data": {"columns": ["x", "y"], "rows": [[1]]}},
            {"data": {"columns": ["x"], "rows": [[float("nan")]]}}):
            with self.subTest(envelope=envelope), self.assertRaises(sources.SourceError):
                sources.parse_wind_content(envelope)

    def test_industry_order_is_keyed_by_code_not_return_position(self):
        data = fixture("wind-industries.json")
        inner = json.loads(data["content"][0]["text"])
        inner["data"]["data"][0]["rows"].reverse()
        data["content"][0]["text"] = json.dumps(inner)
        batch = sources.collect_wind_industries(lambda *a, **k: data, {})
        self.assertEqual(len(batch.rows), 35)
        self.assertEqual(batch.rows[0]["id"], "882100.WI")
        self.assertEqual(batch.rows[-1]["id"], "882136.WI")
        self.assertEqual(batch.rows[0]["_units"]["最新成交额(亿元)"], "亿元")
        self.assertFalse(batch.complete)
        self.assertIn("MISSING_FIELDS", [e["code"] for e in batch.errors])

    def test_partial_or_duplicate_industry_set_is_rejected(self):
        for duplicate in (False, True):
            data = fixture("wind-industries.json")
            inner = json.loads(data["content"][0]["text"])
            rows = inner["data"]["data"][0]["rows"]
            if duplicate:
                rows[-1] = rows[0]
            else:
                rows.pop()
            data["content"][0]["text"] = json.dumps(inner)
            batch = sources.collect_wind_industries(lambda *a, **k: data, {})
            self.assertEqual(batch.rows, [])
            self.assertFalse(batch.complete)
            self.assertEqual(batch.errors[0]["code"], "IDENTITY_MISMATCH")

    def test_primary_sector_name_is_not_silently_mapped_by_name(self):
        data = fixture("wind-industries.json")
        inner = json.loads(data["content"][0]["text"])
        inner["data"]["data"][0]["rows"][0][1] = "能源"
        data["content"][0]["text"] = json.dumps(inner)
        batch = sources.collect_wind_industries(lambda *a, **k: data, {})
        self.assertEqual(batch.rows[0]["name"], "石油石化")
        self.assertEqual(batch.rows[0]["证券简称"], "能源")
        inner["data"]["data"][0]["rows"][0][0] = "881001.WI"
        data["content"][0]["text"] = json.dumps(inner)
        self.assertEqual(sources.collect_wind_industries(lambda *a, **k: data, {}).rows, [])

    def test_style_probe_stops_group_on_auth_quota_backend_or_malformed(self):
        for response in ({"ok": False, "code": "AUTH_ERROR", "message": "secret"},
            {"ok": False, "code": "RATE_LIMIT_ERROR"}, {"ok": False, "code": "backend_error"}, "bad json"):
            calls = []
            def runner(*args, **kwargs):
                calls.append(args)
                if len(calls) > 1:
                    self.fail("an unsuccessful probe must stop the parameter group")
                return response
            batch = sources.collect_wind_styles(runner, {})
            self.assertFalse(batch.complete)
            self.assertEqual(batch.rows, [])
            self.assertNotIn("secret", str(batch.errors))

    def test_style_single_batch_keeps_six_verified_identifiers(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append((argv, kwargs))
            return fixture("wind-styles.json")
        batch = sources.collect_wind_styles(runner, {})
        self.assertTrue(batch.complete)
        self.assertEqual(len(batch.rows), 6)
        self.assertEqual(batch.rows[2]["id"], "H30356.CSI")
        self.assertEqual(batch.rows[2]["name"], "价值")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0][1:5], ["scripts/cli.mjs", "call", "index_data", "get_index_price_indicators"])
        self.assertEqual(len(json.loads(calls[0][0][-1])["windcode"].split(",")), 6)

    def test_industries_use_one_specialized_price_batch_and_preserve_returned_units(self):
        data = fixture("wind-industries.json")
        inner = json.loads(data["content"][0]["text"])
        table = inner['data']['data'][0]
        aliases = {'最新涨跌幅(%)': '涨跌幅', '最新换手率(%)': '换手率',
                   '最新成交额(亿元)': '成交额', '最新主力净流入额(亿元)': '当日主力净流入额',
                   '日期': '最新交易日', '证券简称': '中文简称'}
        for column in table['columns']:
            column['name'] = aliases.get(column['name'], column['name'])
        data['content'][0]['text'] = json.dumps({'data': table})
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            return data
        batch = sources.collect_wind_industries(runner, {})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2:5], ['call', 'index_data', 'get_index_price_indicators'])
        params = json.loads(calls[0][-1])
        self.assertEqual(params['windcode'].split(','), [code for code, _ in sources.INDUSTRY_DEFINITIONS])
        self.assertEqual(params['indexes'], '最新交易日,交易时间,中文简称,涨跌幅,成交额,换手率,5日涨跌幅,20日涨跌幅,当日主力净流入额,上涨家数,下跌家数')
        self.assertEqual(len(batch.rows), 35)
        self.assertEqual(batch.rows[0]['最新成交额(亿元)'], table['rows'][0][4])
        self.assertEqual(batch.rows[0]['_units']['最新成交额(亿元)'], '亿元')
        self.assertEqual(batch.rows[0]['_timestamp'], '2026-11-13T10:15:00+08:00')

    def test_legacy_industry_analytics_requires_explicit_configuration(self):
        calls = []
        def runner(argv, **kwargs):
            calls.append(argv)
            return fixture('wind-industries.json')
        sources.collect_wind_industries(runner, {'sources': {'wind': {'industryMode': 'analytics'}}})
        self.assertEqual(calls[0][2:5], ['call', 'analytics_data', 'get_financial_data'])


class GlobalSourceTests(unittest.TestCase):
    def config(self, metrics):
        return {"sources": {"now": "2026-11-13T10:15:00+08:00", "global": {"metrics": metrics}}}

    def test_fred_missing_marker_never_becomes_zero_and_history_has_dates(self):
        text = (FIXTURES / "fred-series.csv").read_text()
        batch = sources.collect_global_inputs(None, lambda url: text, self.config({
            "rates": {"source": "fred", "series": "DGS10", "frequency": "daily", "maxAgeDays": 7, "unit": "%"}}))
        self.assertTrue(batch.complete)
        self.assertEqual(batch.rows[0]["value"], 4.1)
        self.assertEqual(batch.rows[0]["timestamp"], "2026-11-12T00:00:00+00:00")
        self.assertEqual(batch.rows[0]["history"], [
            {"timestamp": "2026-11-10T00:00:00+00:00", "value": 4.0},
            {"timestamp": "2026-11-12T00:00:00+00:00", "value": 4.1}])
        self.assertFalse(batch.rows[0]["stale"])

    def test_daily_and_monthly_freshness_use_distinct_limits(self):
        text = "observation_date,X\n2026-10-01,1.5\n"
        config = self.config({
            "daily": {"source": "fred", "series": "DGS10", "frequency": "daily", "unit": "%"},
            "monthly": {"source": "fred", "series": "IRLTLT01JPM156N", "frequency": "monthly", "unit": "%"}})
        rows = sources.collect_global_inputs(None, lambda url: text.replace(",X", "," + url.split("=")[-1]), config).rows
        self.assertTrue(rows[0]["stale"])
        self.assertFalse(rows[1]["stale"])
        self.assertFalse(rows[0]["available"])
        old = "observation_date,IRLTLT01JPM156N\n2026-08-01,1.5\n"
        batch = sources.collect_global_inputs(None, lambda url: old,
            self.config({"monthly": config["sources"]["global"]["metrics"]["monthly"]}))
        self.assertFalse(batch.complete)
        self.assertTrue(batch.rows[0]["stale"])

    def test_mx_nested_error_envelopes_never_accept_accompanying_data(self):
        for layer in ("data", "inner", "result"):
            for error_fields in ({"error": "backend failure", "code": "AUTH_ERROR"},
                                 {"code": "AUTH_ERROR"}, {"status": 113}):
                with self.subTest(layer=layer, error_fields=error_fields):
                    payload = fixture("mx-global.json")
                    nested = payload["data"]
                    if layer in ("inner", "result"):
                        nested = nested["data"]
                    if layer == "result":
                        nested = nested["searchDataResultDTO"]
                    nested.update(error_fields)
                    batch = sources.collect_global_inputs(lambda *a, **k: payload, None, self.config({
                        "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"}}))
                    self.assertFalse(batch.complete)
                    self.assertFalse(batch.rows[0]["available"])
                    self.assertIsNone(batch.rows[0]["value"])
                    self.assertEqual(batch.rows[0]["history"], [])
                    self.assertNotIn("backend failure", str(batch))

    def test_mx_partial_cross_asset_data_keeps_missing_metric_unavailable(self):
        config = self.config({
            "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"},
            "oil": {"source": "mx", "entityName": "WTI原油", "field": "最新价", "frequency": "daily"}})
        batch = sources.collect_global_inputs(lambda *a, **k: fixture("mx-global.json"), None, config)
        self.assertFalse(batch.complete)
        self.assertEqual(batch.rows[0]["value"], 2500.0)
        self.assertEqual(batch.rows[0]["unit"], "美元/盎司")
        self.assertIsNone(batch.rows[1]["value"])
        self.assertFalse(batch.rows[1]["available"])
        self.assertEqual(batch.rows[0]["sourceMode"], "mx")
        self.assertIn("MISSING_METRIC", [e["code"] for e in batch.errors])

    def test_metric_role_selects_one_source_without_merging_or_fallback(self):
        config = self.config({
            "equity": {"source": "wind", "windcode": "000300.SH", "field": "涨跌幅", "frequency": "intraday"},
            "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"}})
        def runner(argv, **kwargs):
            if argv[0] == "node":
                envelope = fixture("wind-styles.json")
                inner = json.loads(envelope["content"][0]["text"])
                inner["data"]["rows"] = inner["data"]["rows"][:1]
                envelope["content"][0]["text"] = json.dumps(inner)
                return envelope
            return fixture("mx-global.json")
        batch = sources.collect_global_inputs(runner, None, config)
        self.assertEqual(batch.rows[0]["value"], -.3)
        self.assertEqual(batch.rows[0]["sourceMode"], "wind")
        self.assertEqual(batch.rows[1]["sourceMode"], "mx")
        def failed_wind(argv, **kwargs):
            return {"ok": False, "code": "AUTH_ERROR"} if argv[0] == "node" else fixture("mx-global.json")
        failed = sources.collect_global_inputs(failed_wind, None, config)
        self.assertIsNone(failed.rows[0]["value"])
        self.assertEqual(failed.rows[0]["sourceMode"], "wind")

    def test_mx_script_result_is_loaded_from_disposable_output_directory(self):
        directories = []
        def runner(argv, **kwargs):
            directory = Path(argv[-1])
            directories.append(directory)
            (directory / "mx_data_fixture_raw.json").write_text(json.dumps(fixture("mx-global.json")))
            return subprocess.CompletedProcess(argv, 0, "preview: secret", "")
        batch = sources.collect_global_inputs(runner, None, self.config({
            "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"}}))
        self.assertTrue(batch.complete)
        self.assertEqual(batch.rows[0]["value"], 2500)
        self.assertFalse(directories[0].exists())
        self.assertNotIn("secret", str(batch))

    def test_probe_outputs_only_safe_metadata(self):
        def runner(argv, **kwargs):
            if argv[0] != "node":
                return fixture("mx-global.json")
            params = json.loads(argv[-1])
            name = "wind-industries.json" if "question" in params or params.get("windcode", "").startswith("882") else "wind-breadth.json" if params["windcode"] == "881001.WI" else "wind-styles.json"
            return fixture(name)
        config = self.config({"rates": {"source": "fred", "series": "DGS10", "frequency": "daily", "unit": "%"}})
        output = io.StringIO()
        with redirect_stdout(output):
            code = sources.main(["--probe"], runner=runner,
                fetcher=lambda url: (FIXTURES / "fred-series.csv").read_text(), config=config)
        self.assertEqual(code, 1)  # required industry fields remain missing
        summaries = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([row["rowCount"] for row in summaries], [1, 6, 35, 1])
        for row in summaries:
            self.assertEqual(set(row), {"source", "rowCount", "fields", "units", "timestamps"})
        self.assertNotIn("123456789000", output.getvalue())

    def test_malformed_mx_metadata_and_fred_body_fail_closed(self):
        payload = fixture("mx-global.json")
        payload["data"]["data"]["searchDataResultDTO"]["dataTableDTOList"][0]["field"] = ["bad metadata"]
        batch = sources.collect_global_inputs(lambda *a, **k: payload, None, self.config({
            "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"}}))
        self.assertFalse(batch.complete)
        self.assertIsNone(batch.rows[0]["value"])
        batch = sources.collect_global_inputs(None, lambda url: None, self.config({
            "rates": {"source": "fred", "series": "DGS10", "frequency": "daily"}}))
        self.assertFalse(batch.complete)
        self.assertIsNone(batch.rows[0]["value"])

    def test_conflicting_mx_units_and_duplicate_values_are_rejected(self):
        for changed in ("unit", "value"):
            payload = fixture("mx-global.json")
            blocks = payload["data"]["data"]["searchDataResultDTO"]["dataTableDTOList"]
            duplicate = json.loads(json.dumps(blocks[0]))
            if changed == "unit":
                duplicate["field"]["unit"] = "人民币/克"
            else:
                duplicate["table"]["price"][0] = 999
            blocks.append(duplicate)
            batch = sources.collect_global_inputs(lambda *a, **k: payload, None, self.config({
                "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"}}))
            self.assertFalse(batch.complete)
            self.assertIsNone(batch.rows[0]["value"])

    def test_unknown_and_known_mx_units_cannot_be_merged(self):
        payload = fixture("mx-global.json")
        blocks = payload["data"]["data"]["searchDataResultDTO"]["dataTableDTOList"]
        duplicate = json.loads(json.dumps(blocks[0]))
        del blocks[0]["field"]["unit"]
        duplicate["table"]["headName"] = ["2026-11-13"]
        blocks.append(duplicate)
        batch = sources.collect_global_inputs(lambda *a, **k: payload, None, self.config({
            "gold": {"source": "mx", "entityName": "现货黄金", "field": "最新价", "frequency": "daily"}}))
        self.assertFalse(batch.complete)
        self.assertEqual(batch.errors[0]["code"], "UNIT_MISMATCH")
        self.assertIsNone(batch.rows[0]["value"])

    def test_malformed_fred_does_not_leak_text_into_errors(self):
        batch = sources.collect_global_inputs(None, lambda url: "credential-secret",
            self.config({"x": {"source": "fred", "series": "DGS10", "frequency": "daily"}}))
        self.assertFalse(batch.complete)
        self.assertIsNone(batch.rows[0]["value"])
        self.assertNotIn("credential-secret", str(batch))

if __name__ == "__main__":
    unittest.main()
