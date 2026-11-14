import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { execFileSync } from 'node:child_process'

// Actual Task 3 derived fixture; only transport is replaced by offline Response objects.
const fixture = JSON.parse(execFileSync('python3', ['-c', `
import json
from tools.market_dashboard.job import run_job
print(json.dumps(run_job({'fixture': True, 'dry_run': True}).payload))
`], { encoding: 'utf8', env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } }))
const payload = () => structuredClone(fixture)
async function api() {
  const path = new URL('../src/features/market-dashboard/api.mjs', import.meta.url)
  assert.ok(existsSync(path), 'market dashboard loader must exist')
  return import(path)
}
const response = body => new Response(JSON.stringify(body), { headers: { 'Content-Type': 'application/json' } })
function history() {
  const compact = object => Object.fromEntries(['id', 'strength', 'heat', 'risk', 'completeness'].map(key => [key, object[key]]))
  return { window: '5d', snapshots: [{ observedAt: fixture.observedAt, marketDate: fixture.marketDate,
    session: fixture.session, scoringVersion: fixture.scoringVersion, global: compact(fixture.global),
    aShare: compact(fixture.aShare), styles: fixture.styles.map(compact), industries: fixture.industries.map(compact),
    concepts: { selectionVersion: fixture.concepts.selectionVersion,
      scoringVersion: fixture.concepts.scoringVersion, selectedAt: fixture.concepts.selectedAt,
      core: fixture.concepts.core.map(compact), dynamic: fixture.concepts.dynamic.map(compact) } }] }
}

test('latest loads real Task 3 nullable 78-object payload without changing its metadata', async () => {
  const { loadMarketDashboard } = await api()
  const result = await loadMarketDashboard(async (url, init) => {
    assert.equal(url, '/api/market-dashboard/latest')
    assert.ok(init.signal instanceof AbortSignal)
    return response(payload())
  })
  assert.equal(result.error, null)
  assert.deepEqual(result.data, fixture)
  assert.equal(result.data.global.heat, null)
  assert.equal(result.data.styles.length + result.data.industries.length
    + result.data.concepts.core.length + result.data.concepts.dynamic.length + 2, 78)
})

test('404 NO_SNAPSHOT is distinct from generic HTTP errors and redacts server text', async () => {
  const { loadMarketDashboard } = await api()
  const empty = await loadMarketDashboard(async () => new Response('{"error":"NO_SNAPSHOT"}', { status: 404 }))
  assert.equal(empty.data, null)
  assert.equal(empty.error.code, 'NO_SNAPSHOT')
  const unavailable = await loadMarketDashboard(async () => new Response('private upstream detail', { status: 503 }))
  assert.equal(unavailable.error.code, 'HTTP_ERROR')
  assert.equal(unavailable.error.status, 503)
  assert.doesNotMatch(JSON.stringify(unavailable), /private upstream/)
  const other404 = await loadMarketDashboard(async () => new Response('{"error":"OTHER"}', { status: 404 }))
  assert.equal(other404.error.code, 'HTTP_ERROR')
})

test('invalid JSON, empty success and malformed latest schema remain distinct safe failures', async () => {
  const { loadMarketDashboard } = await api()
  assert.equal((await loadMarketDashboard(async () => new Response('{broken'))).error.code, 'INVALID_JSON')
  assert.equal((await loadMarketDashboard(async () => response(null))).error.code, 'INVALID_SCHEMA')
  const mutations = [
    p => { p.industries.pop() }, p => { p.styles[0].id = p.styles[1].id },
    p => { p.schemaVersion = 'market-dashboard-v1' },
    p => { p.concepts.core.pop() }, p => { p.concepts.dynamic.pop() },
    p => { p.concepts.dynamic[0].id = p.concepts.core[0].id },
    p => { p.concepts.selectionVersion = 'unknown' }, p => { p.concepts.scoringVersion = 'unknown' },
    p => { p.concepts.selectedAt = 'invalid' }, p => { p.concepts.core[0].selectionScore = 50 },
    p => { p.concepts.dynamic[0].selectionScore = 101 },
    p => { p.concepts.dynamic[0].selectedOn = '2026-02-30' },
    p => { p.concepts.dynamic[0].retainedTradingDays = 0 },
    p => { p.aShare.selectionScore = 50 },
    p => { p.global.strength = '59' }, p => { p.aShare.risk = 101 },
    p => { p.aShare.completeness = null }, p => { p.global.sourceTimestamps = [] },
    p => { p.sourceMode.global.gold = 'unknown' }, p => { p.sourceMode.concepts = 'mx' },
    p => { p.sourceMode.conceptDiscovery = 'wind' }, p => { p.dataStatus.stale = 'false' },
    p => { p.global.change5d = { strength: 1 } }, p => { p.observedAt = '2026-02-30T10:15:00+08:00' },
    p => { p.scoringVersion = 'next-version' }, p => { p.aShare.stage = '扩张' },
  ]
  for (const mutate of mutations) {
    const candidate = payload(); mutate(candidate)
    assert.equal((await loadMarketDashboard(async () => response(candidate))).error.code, 'INVALID_SCHEMA')
  }
})

test('timeout aborts transport and also bounds a hung response body', async () => {
  const { loadMarketDashboard } = await api()
  let signal
  const stalledFetch = await loadMarketDashboard(async (_url, init) => {
    signal = init.signal
    return new Promise(() => {})
  }, { timeoutMs: 5 })
  assert.equal(stalledFetch.error.code, 'TIMEOUT')
  assert.equal(signal.aborted, true)
  const stalledBody = await loadMarketDashboard(async () => ({ ok: true, status: 200, json: () => new Promise(() => {}) }), { timeoutMs: 5 })
  assert.equal(stalledBody.error.code, 'TIMEOUT')
})

test('caller cancellation is propagated and remains distinct from timeout and network failure', async () => {
  const { loadMarketDashboard } = await api()
  const controller = new AbortController()
  const pending = loadMarketDashboard(async () => new Promise(() => {}), { signal: controller.signal, timeoutMs: 100 })
  controller.abort()
  assert.equal((await pending).error.code, 'ABORTED')
  assert.equal((await loadMarketDashboard(async () => { throw new Error('private provider exception') })).error.code, 'NETWORK_ERROR')
  const alreadyAborted = await loadMarketDashboard(async () => { throw new Error('should not fetch') }, { signal: controller.signal })
  assert.equal(alreadyAborted.error.code, 'ABORTED')
})

test('history validates requested window and compact snapshots including nullable score axes', async () => {
  const { loadMarketHistory } = await api()
  const result = await loadMarketHistory('5d', async url => {
    assert.equal(url, '/api/market-dashboard/history?window=5d')
    return response(history())
  })
  assert.deepEqual(result.data, history())
  assert.equal(result.error, null)
  assert.equal((await loadMarketHistory('all', async () => { throw new Error('must not fetch') })).error.code, 'INVALID_WINDOW')
  for (const body of [{ window: '1d', snapshots: [] }, { window: '5d', snapshots: [] },
    { window: '5d', snapshots: [{ observedAt: 'invalid' }] }]) {
    assert.equal((await loadMarketHistory('5d', async () => response(body))).error.code, 'INVALID_SCHEMA')
  }
  const bad = history(); bad.snapshots[0].industries[0].risk = 101
  assert.equal((await loadMarketHistory('5d', async () => response(bad))).error.code, 'INVALID_SCHEMA')
})

test('partial history failure composes with latest success without discarding valid latest', async () => {
  const { loadMarketDashboard, loadMarketHistory } = await api()
  const fetcher = async url => url.endsWith('/latest') ? response(payload()) : new Response('unavailable', { status: 503 })
  const [latest, past] = await Promise.all([loadMarketDashboard(fetcher), loadMarketHistory('5d', fetcher)])
  assert.equal(latest.data.aShare.strength, 75)
  assert.equal(latest.error, null)
  assert.equal(past.data, null)
  assert.equal(past.error.code, 'HTTP_ERROR')
})
