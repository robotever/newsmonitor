import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'

async function model() {
  const path = new URL('../src/features/market-dashboard/model.mjs', import.meta.url)
  assert.ok(existsSync(path), 'market dashboard presentation model must exist')
  return import(path)
}
const observed = '2026-11-13T10:15:00+08:00'
const object = (id, fields = {}) => ({ id, name: id, strength: 60, heat: 60, risk: 60, completeness: 80,
  frequency: 'intraday', missing: [], contributors: [], sourceTimestamps: [{ source: 'Wind', timestamp: observed }],
  change1d: null, change5d: null, ...fields })
const payload = (fields = {}) => ({ schemaVersion: 'market-dashboard-v2', scoringVersion: 'market-score-v0.1',
  observedAt: observed, marketDate: '2026-11-13', session: 'intraday', global: object('global'),
  aShare: object('a-share', { stage: '震荡' }), styles: [], industries: [],
  concepts: { selectionVersion: 'concept-selection-v0.1', scoringVersion: 'concept-score-v0.1',
    selectedAt: observed, core: [], dynamic: [] },
  dataStatus: { completeness: 80, stale: false, missing: [] }, ...fields })
const now = new Date('2026-11-13T02:20:00Z')

// Hand-checked score bands; mutation of either boundary must fail.
test('score labels respect 30/70 boundaries and keep nullable axes unavailable', async () => {
  const { deriveMarketDashboardView } = await model()
  const values = [0, 29, 30, 69, 70, 100, null]
  const view = deriveMarketDashboardView(payload({ industries: values.map((value, i) => object(String(i), { strength: value, heat: value, risk: value })) }), now)
  assert.deepEqual(view.industries.map(o => o.scoreLabels.strength), ['弱', '弱', '中性', '中性', '强', '强', '暂无数据'])
  assert.deepEqual(view.industries.map(o => o.scoreLabels.heat), ['冷', '冷', '正常', '正常', '热', '热', '暂无数据'])
  assert.deepEqual(view.industries.map(o => o.scoreLabels.risk), ['低', '低', '中等', '中等', '高', '高', '暂无数据'])
  assert.equal(view.industries.at(-1).strength, null)
})

test('completeness 49 suppresses stage; 50 retains server stage; 70 clears evidence badge', async () => {
  const { deriveMarketDashboardView } = await model()
  for (const [completeness, stage, label] of [[49, null, '证据不足'], [50, '扩张', '证据不足'], [69, '扩张', '证据不足'], [70, '扩张', '证据充分']]) {
    const view = deriveMarketDashboardView(payload({ aShare: object('a-share', { completeness, stage: '扩张' }) }), now)
    assert.equal(view.aShare.stage, stage)
    assert.equal(view.aShare.stageLabel, stage ?? '证据不足')
    assert.equal(view.aShare.evidenceLabel, label)
  }
  assert.equal(deriveMarketDashboardView(payload({ aShare: object('a-share') }), now).aShare.stage, null)
})

test('Beijing intraday stale boundary is >30 minutes and +08/Z represent the same instant', async () => {
  const { deriveMarketDashboardView } = await model()
  assert.equal(deriveMarketDashboardView(payload(), new Date('2026-11-13T02:45:00Z')).freshness.stale, false)
  const late = deriveMarketDashboardView(payload(), new Date('2026-11-13T02:46:00Z'))
  assert.equal(late.freshness.stale, true)
  assert.equal(late.aShare.freshness.stale, true)
  const utc = payload({ observedAt: '2026-11-13T02:15:00Z' })
  assert.deepEqual(deriveMarketDashboardView(utc, new Date('2026-11-13T02:46:00Z')).freshness, late.freshness)
  assert.equal(deriveMarketDashboardView(payload(), now, { staleAfterMs: { intraday: 4 * 60000 } }).freshness.stale, true)
})

test('confirmed close remains fresh after hours; missing close is explicit after 15:30', async () => {
  const { deriveMarketDashboardView } = await model()
  const atClose = payload({ observedAt: '2026-11-13T07:00:00Z', session: 'close' })
  const evening = new Date('2026-11-13T12:00:00Z')
  assert.equal(deriveMarketDashboardView(atClose, evening).freshness.stale, false)
  assert.equal(deriveMarketDashboardView(atClose, evening).freshness.missingClose, false)
  const unconfirmed = deriveMarketDashboardView(payload(), evening)
  assert.equal(unconfirmed.freshness.missingClose, true)
  assert.equal(unconfirmed.freshness.label, '缺少收盘确认')
  assert.equal(deriveMarketDashboardView(payload(), new Date('2026-11-13T07:30:00Z')).freshness.missingClose, false)
  assert.equal(deriveMarketDashboardView(payload({ observedAt: observed, session: 'close' }), evening).freshness.missingClose, true)
})

test('weekends, lunch and configured holidays do not count as intraday delay', async () => {
  const { deriveMarketDashboardView } = await model()
  for (const time of ['2026-11-14T02:46:00Z', '2026-11-15T12:00:00Z', '2026-11-13T04:00:00Z']) {
    const freshness = deriveMarketDashboardView(payload(), new Date(time)).freshness
    assert.equal(freshness.stale, false)
    assert.equal(freshness.missingClose, false)
  }
  assert.equal(deriveMarketDashboardView(payload(), new Date('2026-11-13T02:46:00Z'), { tradingDates: ['2026-11-12'] }).freshness.stale, false)
  assert.equal(deriveMarketDashboardView(payload({ dataStatus: { completeness: 80, stale: true, missing: [] } }), new Date('2026-11-14T02:00:00Z')).freshness.stale, true)
})

test('daily/monthly observation has configurable age thresholds and preserves oldest evidence date', async () => {
  const { deriveMarketDashboardView } = await model()
  const p = payload({ global: object('global', { frequency: 'daily', observedAt: '2026-10-23T00:00:00Z', sourceTimestamps: [
    { source: 'FRED', timestamp: '2026-10-23T00:00:00Z' }, { source: 'MX', timestamp: observed } ] }) })
  const view = deriveMarketDashboardView(p, now)
  assert.equal(view.global.freshness.stale, true)
  assert.equal(view.global.freshness.oldestSourceAt, '2026-10-23T00:00:00Z')
  assert.equal(deriveMarketDashboardView(p, now, { staleAfterMs: { daily: 30 * 86400000 } }).global.freshness.stale, false)
  p.global.frequency = 'monthly'
  assert.equal(deriveMarketDashboardView(p, now).global.freshness.stale, false)
  p.global.observedAt = '2026-08-01T00:00:00Z'
  assert.equal(deriveMarketDashboardView(p, now).global.freshness.stale, true)
})

test('mixed-frequency provenance stays display-only while object observation and server stale govern freshness', async () => {
  const { deriveMarketDashboardView } = await model()
  const p = payload({ global: object('global', { frequency: 'daily', observedAt: '2026-11-12T00:00:00Z', sourceTimestamps: [
    { source: 'FRED', timestamp: '2026-10-01T00:00:00Z' },
    { source: 'MX', timestamp: '2026-11-12T00:00:00Z' },
  ] }) })
  const fresh = deriveMarketDashboardView(p, now).global.freshness
  assert.equal(fresh.stale, false)
  assert.equal(fresh.oldestSourceAt, '2026-10-01T00:00:00Z')
  assert.equal(fresh.ageMs, 94800000)
  delete p.global.observedAt
  assert.equal(deriveMarketDashboardView(p, now).global.freshness.ageMs, 300000)
  p.dataStatus.stale = true
  assert.equal(deriveMarketDashboardView(p, now).global.freshness.stale, true)
  assert.equal(deriveMarketDashboardView(p, now).global.freshness.oldestSourceAt, '2026-10-01T00:00:00Z')
})

test('comparison badges distinguish close fallback, missing calendar and unavailable comparisons', async () => {
  const { deriveMarketDashboardView } = await model()
  const view = deriveMarketDashboardView(payload({ industries: [object('a', { comparisonFallback: 'close',
    change1d: { strength: 0, heat: null, risk: -2 }, comparisonUnavailable: { change5d: 'missingTradingCalendar' } }), object('b')] }), now)
  assert.deepEqual(view.industries[0].comparisonBadges, { change1d: '至少一项使用收盘回退', change5d: '缺少交易日历' })
  assert.deepEqual(view.industries[1].comparisonBadges, { change1d: '暂无可比快照', change5d: '暂无可比快照' })
})

test('object-wide close fallback never claims either available comparison window definitely fell back', async () => {
  const { deriveMarketDashboardView } = await model()
  const comparison = { strength: 2, heat: null, risk: -1 }
  const view = deriveMarketDashboardView(payload({ industries: [object('a', {
    comparisonFallback: 'close', change1d: comparison, change5d: comparison,
  }), object('b', { change1d: comparison, change5d: comparison })] }), now)
  assert.deepEqual(view.industries[0].comparisonBadges, {
    change1d: '至少一项使用收盘回退', change5d: '至少一项使用收盘回退',
  })
  assert.deepEqual(view.industries[1].comparisonBadges, { change1d: '同口径比较', change5d: '同口径比较' })
})

test('four rankings use supplied scores and change5d/1d; null sorts last and ties use stable IDs', async () => {
  const { rankIndustries } = await model()
  const industries = [object('d', { strength: null, heat: null, risk: null }),
    object('c', { strength: 70, heat: 20, risk: 0, change1d: { strength: 5, heat: null, risk: null } }),
    object('b', { strength: 70, heat: 90, risk: 60, change5d: { strength: 5, heat: 1, risk: 1 } }),
    object('a', { strength: 10, heat: 90, risk: 80, change5d: { strength: 10, heat: 0, risk: 0 } }),
    object('e', { strength: 0, heat: 0, risk: 0, change5d: { strength: 0, heat: null, risk: null } })]
  const before = structuredClone(industries)
  const ranks = rankIndustries(industries)
  assert.deepEqual(ranks.strength.map(o => o.id), ['b', 'c', 'a', 'e', 'd'])
  assert.deepEqual(ranks.heat.map(o => o.id), ['a', 'b', 'c', 'e', 'd'])
  assert.deepEqual(ranks.risk.map(o => o.id), ['a', 'b', 'c', 'e', 'd'])
  assert.deepEqual(ranks.improvement.map(o => o.id), ['a', 'b', 'c', 'e', 'd'])
  assert.equal(ranks.improvement[0].improvementLabel, '5日强度改善')
  assert.equal(ranks.improvement[2].improvementLabel, '1日强度改善（回退）')
  assert.equal(ranks.improvement.at(-1).improvementValue, null)
  assert.deepEqual(rankIndustries([...industries].reverse()), ranks)
  assert.deepEqual(industries, before)
})

test('view preserves input, scores, sourceMode and dataStatus while ordering industries deterministically', async () => {
  const { deriveMarketDashboardView } = await model()
  const p = payload({ industries: [object('b'), object('a')], sourceMode: { breadth: 'wind', styles: 'wind', industries: 'wind', global: { DGS10: 'fred' } } })
  const before = structuredClone(p)
  const freeze = value => { if (value && typeof value === 'object') { Object.freeze(value); Object.values(value).forEach(freeze) } }
  freeze(p)
  const view = deriveMarketDashboardView(p, now)
  assert.deepEqual(p, before)
  assert.deepEqual(view.industries.map(o => o.id), ['a', 'b'])
  assert.deepEqual(view.sourceMode, p.sourceMode)
  assert.deepEqual(view.dataStatus, p.dataStatus)
  assert.equal(view.aShare.stage, '震荡')
  assert.equal(view.aShare.strength, 60)
})

test('concept presentation preserves configured and selected order with separate deterministic rankings', async () => {
  const { deriveMarketDashboardView } = await model()
  const core = [object('8842002.WI', { strength: 20 }), object('8842000.WI', { strength: 80 })]
  const dynamic = [object('8842030.WI', { heat: 90, selectionScore: 88, selectedOn: '2026-11-13', retainedTradingDays: 1 }),
    object('8842029.WI', { heat: 20, selectionScore: 70, selectedOn: '2026-11-12', retainedTradingDays: 2,
      comparisonUnavailable: { change1d: 'missingObservation', change5d: 'missingObservation' } })]
  const before = structuredClone({ core, dynamic })
  const view = deriveMarketDashboardView(payload({ concepts: { selectionVersion: 'concept-selection-v0.1',
    scoringVersion: 'concept-score-v0.1', selectedAt: observed, core, dynamic } }), now)
  assert.deepEqual(view.coreConcepts.map(item => item.id), ['8842002.WI', '8842000.WI'])
  assert.deepEqual(view.dynamicConcepts.map(item => item.id), ['8842030.WI', '8842029.WI'])
  assert.deepEqual(view.conceptRankings.core.strength.map(item => item.id), ['8842000.WI', '8842002.WI'])
  assert.deepEqual(view.conceptRankings.dynamic.heat.map(item => item.id), ['8842030.WI', '8842029.WI'])
  assert.equal(view.dynamicConcepts[1].comparisonBadges.change1d, '暂无可比快照')
  assert.equal(view.dynamicConcepts[0].selectionScore, 88)
  assert.deepEqual({ core, dynamic }, before)
})

test('concept freshness and industry rankings remain independent', async () => {
  const { deriveMarketDashboardView } = await model()
  const industries = [object('b', { strength: 80 }), object('a', { strength: 20 })]
  const core = [object('8842000.WI', { observedAt: '2026-11-13T01:00:00Z', strength: 100 })]
  const view = deriveMarketDashboardView(payload({ industries, concepts: { selectionVersion: 'concept-selection-v0.1',
    scoringVersion: 'concept-score-v0.1', selectedAt: observed, core, dynamic: [] } }), now)
  assert.equal(view.coreConcepts[0].freshness.stale, true)
  assert.deepEqual(view.rankings.strength.map(item => item.id), ['b', 'a'])
  assert.deepEqual(view.conceptRankings.core.strength.map(item => item.id), ['8842000.WI'])
})
