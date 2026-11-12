import test from 'node:test'
import assert from 'node:assert/strict'
import { loadDebtSeries, SERIES } from '../src/features/debt-monitor/api.mjs'

test('loadDebtSeries keeps successful observations when another series fails', async () => {
  const fetcher = async url => {
    const seriesId = new URL(url, 'https://example.test').searchParams.get('id')
    if (seriesId === 'DFII10') return new Response('DATE,VALUE\n2026-11-10,2.10\n2026-11-11,2.15')
    return new Response('upstream unavailable', { status: 503 })
  }

  const result = await loadDebtSeries(fetcher, [SERIES.DFII10, SERIES.DGS10])

  assert.deepEqual(result.series.DFII10, [
    { date: '2026-11-10', value: 2.1 },
    { date: '2026-11-11', value: 2.15 },
  ])
  assert.deepEqual(result.series.DGS10, [])
  assert.deepEqual(result.errors, { DGS10: 'HTTP 503' })
})

test('loadDebtSeries rejects an empty successful response as unavailable', async () => {
  const fetcher = async () => new Response('DATE,VALUE\n2026-11-11,.')

  const result = await loadDebtSeries(fetcher, [SERIES.DGS10])

  assert.deepEqual(result.series.DGS10, [])
  assert.equal(result.errors.DGS10, '暂无有效数据')
})

test('loadDebtSeries settles partial results when one upstream request hangs', async () => {
  const fetcher = async url => {
    const seriesId = new URL(url, 'https://example.test').searchParams.get('id')
    if (seriesId === 'DGS10') return new Response('DATE,VALUE\n2026-11-11,4.25')
    return new Promise(() => {})
  }

  const startedAt = Date.now()
  const result = await loadDebtSeries(fetcher, [SERIES.DGS10, SERIES.DFII10], { timeoutMs: 10 })

  assert.equal(result.series.DGS10[0].value, 4.25)
  assert.equal(result.errors.DFII10, '请求超时')
  assert.ok(Date.now() - startedAt < 250)
})
