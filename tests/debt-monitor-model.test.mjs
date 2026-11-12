import test from 'node:test'
import assert from 'node:assert/strict'
import {
  parseFredCsv,
  summarizeSeries,
  deriveDebtDashboard,
} from '../src/features/debt-monitor/model.mjs'

test('parseFredCsv ignores missing and malformed observations and sorts valid points', () => {
  const csv = [
    'DATE,VALUE',
    '2026-11-10,4.25',
    'bad-date,9.99',
    '2026-02-31,8.88',
    '2026-11-12,.',
    '2026-11-11,4.30',
    '2026-11-09,not-a-number',
  ].join('\n')

  assert.deepEqual(parseFredCsv(csv), [
    { date: '2026-11-10', value: 4.25 },
    { date: '2026-11-11', value: 4.3 },
  ])
})

test('summarizeSeries returns latest value and hand-checked change', () => {
  const summary = summarizeSeries([
    { date: '2026-11-10', value: 3.4 },
    { date: '2026-11-11', value: 3.55 },
  ])

  assert.deepEqual(summary, {
    date: '2026-11-11',
    value: 3.55,
    previousValue: 3.4,
    change: 0.15,
  })
})

test('deriveDebtDashboard calculates European spreads and a warning state', () => {
  const dashboard = deriveDebtDashboard({
    DFII10: [{ date: '2026-11-11', value: 2.2 }],
    BAMLH0A0HYM2: [{ date: '2026-11-11', value: 4.1 }],
    THREEFYTP10: [{ date: '2026-11-11', value: 0.85 }],
    IRLTLT01DEM156N: [{ date: '2026-10-01', value: 2.6 }],
    IRLTLT01FRM156N: [{ date: '2026-10-01', value: 3.45 }],
    IRLTLT01ITM156N: [{ date: '2026-10-01', value: 4.1 }],
  })

  assert.equal(dashboard.europe.franceGermanySpread.value, 85)
  assert.equal(dashboard.europe.italyGermanySpread.value, 150)
  assert.equal(dashboard.status, 'warning')
  assert.equal(dashboard.label, '关注')
})

test('deriveDebtDashboard remains usable when series are partially unavailable', () => {
  const dashboard = deriveDebtDashboard({
    DGS10: [
      { date: '2026-11-10', value: 4.2 },
      { date: '2026-11-11', value: 4.25 },
    ],
  })

  assert.equal(dashboard.us.nominal10y.value, 4.25)
  assert.equal(dashboard.us.real10y, null)
  assert.equal(dashboard.europe.franceGermanySpread, null)
  assert.equal(dashboard.availableCount, 1)
  assert.equal(dashboard.status, 'insufficient')
  assert.equal(dashboard.label, '数据不足')
})

test('deriveDebtDashboard flags severe credit and sovereign stress as alert', () => {
  const dashboard = deriveDebtDashboard({
    DFII10: [{ date: '2026-11-11', value: 2.8 }],
    BAMLH0A0HYM2: [{ date: '2026-11-11', value: 5.2 }],
    THREEFYTP10: [{ date: '2026-11-11', value: 1.3 }],
    IRLTLT01DEM156N: [{ date: '2026-10-01', value: 2.5 }],
    IRLTLT01FRM156N: [{ date: '2026-10-01', value: 4.0 }],
    IRLTLT01ITM156N: [{ date: '2026-10-01', value: 4.8 }],
  })

  assert.equal(dashboard.status, 'alert')
  assert.equal(dashboard.label, '警戒')
})

test('European spreads use the latest common dates and calculate spread change', () => {
  const dashboard = deriveDebtDashboard({
    IRLTLT01DEM156N: [
      { date: '2026-08-01', value: 2.5 },
      { date: '2026-09-01', value: 2.6 },
      { date: '2026-10-01', value: 2.7 },
    ],
    IRLTLT01FRM156N: [
      { date: '2026-08-01', value: 3.1 },
      { date: '2026-09-01', value: 3.4 },
    ],
  })

  assert.deepEqual(dashboard.europe.franceGermanySpread, {
    date: '2026-09-01', value: 80, previousValue: 60, change: 20, stale: false,
  })
})

test('Japanese long-rate jump contributes to the composite warning state', () => {
  const dashboard = deriveDebtDashboard({
    DFII10: [{ date: '2026-11-10', value: 1.8 }],
    BAMLH0A0HYM2: [{ date: '2026-11-10', value: 3.2 }],
    IRLTLT01JPM156N: [
      { date: '2026-08-01', value: 1.8 },
      { date: '2026-09-01', value: 1.96 },
    ],
    IRLTLT01DEM156N: [{ date: '2026-09-01', value: 2.6 }],
    IRLTLT01FRM156N: [{ date: '2026-09-01', value: 3.0 }],
  }, new Date('2026-11-12T00:00:00Z'))

  assert.equal(dashboard.status, 'warning')
  assert.equal(dashboard.score, 2)
})

test('signal thresholds use inclusive boundaries from the model', () => {
  const dashboard = deriveDebtDashboard({
    DFII10: [{ date: '2026-11-10', value: 2.0 }],
    BAMLH0A0HYM2: [{ date: '2026-11-10', value: 4.0 }],
    IRLTLT01JPM156N: [{ date: '2026-09-01', value: 2.0 }],
    IRLTLT01DEM156N: [{ date: '2026-09-01', value: 2.5 }],
    IRLTLT01FRM156N: [{ date: '2026-09-01', value: 3.25 }],
  }, new Date('2026-11-12T00:00:00Z'))

  assert.equal(dashboard.signals.credit.level, 'warning')
  assert.equal(dashboard.signals.europe.level, 'warning')
})

test('freshness is frequency-aware for daily and monthly observations', () => {
  const dashboard = deriveDebtDashboard({
    DFII10: [{ date: '2026-10-20', value: 2.1 }],
    IRLTLT01JPM156N: [{ date: '2026-07-01', value: 2.0 }],
  }, new Date('2026-11-12T00:00:00Z'))

  assert.equal(dashboard.us.real10y.stale, true)
  assert.equal(dashboard.japan.nominal10y.stale, true)
})

test('stale observations do not contribute to coverage, score, or signal levels', () => {
  const dashboard = deriveDebtDashboard({
    DFII10: [{ date: '2026-01-01', value: 3.0 }],
    BAMLH0A0HYM2: [{ date: '2026-01-01', value: 6.0 }],
    IRLTLT01JPM156N: [
      { date: '2025-01-01', value: 1.0 },
      { date: '2025-02-01', value: 1.3 },
    ],
    IRLTLT01DEM156N: [{ date: '2025-01-01', value: 2.0 }],
    IRLTLT01FRM156N: [{ date: '2025-01-01', value: 4.0 }],
  }, new Date('2026-11-12T00:00:00Z'))

  assert.equal(dashboard.status, 'insufficient')
  assert.equal(dashboard.score, 0)
  assert.equal(dashboard.signals.credit.level, 'neutral')
  assert.equal(dashboard.signals.europe.level, 'neutral')
})
