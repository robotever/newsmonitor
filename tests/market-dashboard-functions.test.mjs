import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'

const migrationPath = new URL('../migrations/0001_market_dashboard.sql', import.meta.url)

// Exercise handler SQL against real SQLite, with only the external D1 transport adapted.
function database(t) {
  const directory = mkdtempSync(join(tmpdir(), 'market-d1-'))
  t.after(() => rmSync(directory, { recursive: true, force: true }))
  const file = join(directory, 'db.sqlite')
  const execute = (sql, params = [], script = false) => JSON.parse(execFileSync('python3', ['-c', `
import json, sqlite3, sys
request = json.load(sys.stdin)
with sqlite3.connect(sys.argv[1]) as connection:
    connection.row_factory = sqlite3.Row
    if request['script']:
        connection.executescript(request['sql'])
        result = {'results': [], 'meta': {'changes': connection.total_changes}}
    else:
        cursor = connection.execute(request['sql'], request['params'])
        result = {'results': [dict(row) for row in cursor.fetchall()], 'meta': {'changes': max(cursor.rowcount, 0)}}
print(json.dumps(result))
`, file], { input: JSON.stringify({ sql, params, script }), encoding: 'utf8' }))
  execute(readFileSync(migrationPath, 'utf8'), [], true)
  return {
    execute,
    prepare(sql) {
      const statement = params => ({
        bind: (...values) => statement(values),
        run: async () => execute(sql, params),
        first: async () => execute(sql, params).results[0] ?? null,
        all: async () => execute(sql, params),
      })
      return statement([])
    },
  }
}

test('migration creates all snapshot columns, unique observations and latest index', t => {
  assert.ok(existsSync(migrationPath), 'market dashboard migration must exist')
  const db = database(t)
  assert.deepEqual(db.execute('PRAGMA table_info(market_dashboard_snapshots)').results.map(row => row.name), [
    'id', 'observed_at', 'market_date', 'session', 'schema_version', 'scoring_version', 'completeness', 'payload_json', 'created_at',
  ])
  const indexes = db.execute('PRAGMA index_list(market_dashboard_snapshots)').results
  assert.ok(indexes.some(index => index.name === 'idx_market_dashboard_latest'))
  assert.ok(indexes.some(index => index.unique &&
    db.execute(`PRAGMA index_info('${index.name}')`).results.map(row => row.name).join(',') === 'observed_at,scoring_version'))
  const configuration = readFileSync(new URL('../wrangler.toml', import.meta.url), 'utf8')
  assert.match(configuration, /^pages_build_output_dir\s*=\s*"dist"/m)
  assert.match(configuration, /^\[\[d1_databases\]\]/m)
  assert.match(configuration, /^binding\s*=\s*"MARKET_DB"/m)
  assert.match(configuration, /^database_name\s*=\s*"newsmonitor-market-dashboard"/m)
  assert.match(configuration, /^database_id\s*=\s*"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"\s*$/m)
  assert.doesNotMatch(configuration, /^\s*(?:account_id|[\w-]*(?:token|secret|api[_-]?key)[\w-]*)\s*=/im)
  assert.doesNotMatch(configuration, /<provisioned-database-id>|database_id\s*=\s*"(?:0{8}-0{4}-0{4}-0{4}-0{12}|[^"\n]*(?:placeholder|replace|example)[^"\n]*)"/i)
})

const TOKEN = 'synthetic-publish-sentinel'
const OBSERVED = '2026-11-12T02:15:00Z'
const styleIds = ['000300.SH', '000852.SH', 'H30356.CSI', '399006.SZ', '000922.CSI', '000688.SH']
const industryIds = [
  '882100.WI', '882101.WI', '882102.WI', '882103.WI', '882104.WI', '882105.WI', '882106.WI',
  '882107.WI', '882108.WI', '882109.WI', '882110.WI', '882111.WI', '882112.WI', '882113.WI',
  '882114.WI', '882115.WI', '882116.WI', '882119.WI', '882120.WI', '882121.WI', '882122.WI',
  '882123.WI', '882124.WI', '882125.WI', '882126.WI', '882127.WI', '882128.WI', '882129.WI',
  '882130.WI', '882131.WI', '882132.WI', '882133.WI', '882134.WI', '882135.WI', '882136.WI',
]
function payload() {
  const object = id => ({ id, name: id, strength: 60, heat: null, risk: 40,
    completeness: 60, missing: ['heat'], contributors: [{ label: 'Derived evidence', impact: 10 }],
    sourceTimestamps: [{ source: 'Wind', timestamp: OBSERVED }], change1d: null, change5d: null })
  return {
    schemaVersion: 'market-dashboard-v1', scoringVersion: 'market-score-v0.1',
    observedAt: OBSERVED, marketDate: '2026-11-12', session: 'intraday',
    global: object('global'), aShare: { ...object('a-share'), stage: '震荡' },
    styles: styleIds.map(object), industries: industryIds.map(object),
    dataStatus: { completeness: 60, stale: false, missing: [] },
    sourceMode: { breadth: 'wind', styles: 'wind', industries: 'wind', global: { DGS10: 'fred', gold: 'mx' } },
  }
}
async function handler(name) {
  const path = new URL(`../functions/api/market-dashboard/${name}.js`, import.meta.url)
  assert.ok(existsSync(path), `${name} handler must exist`)
  const module = await import(path)
  const method = name === 'publish' ? module.onRequestPost : module.onRequestGet
  assert.equal(typeof method, 'function')
  return method
}
function publishRequest(body, authorization = `Bearer ${TOKEN}`, headers = {}) {
  return new Request('https://example.test/api/market-dashboard/publish', {
    method: 'POST', headers: { ...(authorization === null ? {} : { Authorization: authorization }), ...headers },
    body: typeof body === 'string' || body instanceof ReadableStream ? body : JSON.stringify(body),
    ...(body instanceof ReadableStream ? { duplex: 'half' } : {}),
  })
}
function context(request, db, token = TOKEN) {
  return { request, env: { MARKET_DB: db, MARKET_DASHBOARD_PUBLISH_TOKEN: token } }
}
async function errorResponse(response, status, code) {
  assert.equal(response.status, status)
  assert.equal(response.headers.get('Cache-Control'), 'no-store')
  assert.equal(response.headers.get('Content-Type'), 'application/json; charset=utf-8')
  assert.deepEqual(await response.json(), { error: code })
}

test('publish denies missing, malformed, wrong and differently sized tokens before database access', async () => {
  const publish = await handler('publish')
  for (const authorization of [null, 'Basic synthetic', 'Bearer wrong', `Bearer ${TOKEN}x`, `Bearer ${TOKEN.toUpperCase()}`]) {
    await errorResponse(await publish(context(publishRequest(payload(), authorization), null)), 401, 'UNAUTHORIZED')
  }
  await errorResponse(await publish(context(publishRequest(payload()), null, '')), 503, 'SERVICE_UNAVAILABLE')
})

test('publish handles invalid JSON and enforces the actual UTF-8 stream limit even with false Content-Length', async () => {
  const publish = await handler('publish')
  await errorResponse(await publish(context(publishRequest('{ broken'), null)), 400, 'INVALID_JSON')
  const tooLarge = new TextEncoder().encode('汉'.repeat(90000))
  let cancelled = false
  const stream = new ReadableStream({ start(controller) { controller.enqueue(tooLarge) }, cancel() { cancelled = true } })
  await errorResponse(await publish(context(publishRequest(stream, `Bearer ${TOKEN}`, { 'Content-Length': '1' }), null)), 413, 'PAYLOAD_TOO_LARGE')
  assert.equal(cancelled, true)
  const exactLimit = ' '.repeat(256 * 1024)
  await errorResponse(await publish(context(publishRequest(exactLimit), null)), 400, 'INVALID_JSON')
  await errorResponse(await publish(context(publishRequest(exactLimit + ' '), null)), 413, 'PAYLOAD_TOO_LARGE')
})

test('publish validates exact schema, 43 identities, evidence, missingness and derived field allowlists', async () => {
  const publish = await handler('publish')
  const invalid = [
    p => { p.schemaVersion = 'market-dashboard-v2' }, p => { p.scoringVersion = 'unknown' },
    p => { p.aShare.strength = 101 }, p => { p.aShare.risk = -1 }, p => { p.aShare.heat = 1.5 },
    p => { p.global.strength = true }, p => { p.aShare.completeness = 101 },
    p => { p.global.completeness = 0 }, p => { p.global.sourceTimestamps = [] },
    p => { p.global.strength = p.global.heat = p.global.risk = null },
    p => { p.aShare.completeness = 49; p.aShare.stage = '扩张' },
    p => { p.styles.pop() }, p => { p.industries[1].id = p.industries[0].id },
    p => { p.industries[0].id = 'fake.WI' }, p => { p.global.id = 'fake' },
    p => { p.aShare.missing = null }, p => { p.aShare.frequency = 'realtime' },
    p => { p.global.sourceTimestamps[0].source = 'provider-secret-detail' },
    p => { p.aShare.contributors = Array(4).fill({ label: 'x', impact: 1 }) },
    p => { p.aShare.contributors[0].rawRows = [] }, p => { p.aShare.change1d = { strength: 101, heat: 0, risk: 0 } },
    p => { p.aShare.comparisonUnavailable = { change1d: 'unsafe-detail' } },
    p => { p.aShare.stage = 'made-up' }, p => { p.dataStatus.completeness = 61 },
    p => { p.dataStatus.stale = 1 }, p => { p.sourceMode.breadth = 'mx' },
    p => { p.sourceMode.global.DGS10 = 'unknown' }, p => { p.sourceMode.global['raw.rows'] = 'fred' },
    p => { p.sourceMode.global.DGS10 = { token: 'unsafe' } },
    ...['rows', '_units', 'history', 'raw', 'indicators', 'authorization'].flatMap(key => [
      p => { p[key] = [] }, p => { p.aShare[key] = [] },
    ]),
    p => { p.observedAt = '2026-11-12T02:15:00' },
    p => { p.observedAt = '2026-02-30T02:15:00Z'; p.marketDate = '2026-02-30' },
    p => { p.marketDate = '2026-11-11' }, p => { p.session = 'pre-market' },
    p => { p.observedAt = '0000-01-01T00:00:00Z'; p.marketDate = '0000-01-01' },
    p => { p.global.sourceTimestamps[0].timestamp = 'invalid' },
    p => { p.global.observedAt = '2026-01-01' },
    p => { p.observedAt = '2099-01-01T00:00:00Z'; p.marketDate = '2099-01-01' },
  ]
  for (const mutate of invalid) {
    const candidate = payload(); mutate(candidate)
    await errorResponse(await publish(context(publishRequest(candidate), null)), 400, 'INVALID_PAYLOAD')
  }
})

test('publish accepts nullable axes and low positive evidence, stores only processed payload and returns no secrets', async t => {
  const publish = await handler('publish')
  const db = database(t)
  const candidate = payload()
  for (const object of [candidate.global, candidate.aShare, ...candidate.styles, ...candidate.industries]) {
    object.completeness = 1
    object.stage = null
  }
  candidate.dataStatus.completeness = 1
  const response = await publish(context(publishRequest(candidate), db))
  assert.equal(response.status, 201)
  assert.equal(response.headers.get('Cache-Control'), 'no-store')
  assert.deepEqual(await response.json(), { ok: true, duplicate: false, observedAt: OBSERVED })
  const rows = db.execute('SELECT * FROM market_dashboard_snapshots').results
  assert.equal(rows.length, 1)
  assert.equal(rows[0].observed_at, '2026-11-12T02:15:00.000000Z')
  assert.deepEqual(JSON.parse(rows[0].payload_json), candidate)
  assert.ok(!JSON.stringify(rows).includes(TOKEN))
})

test('publish is idempotent across equivalent timezone strings and never overwrites the first snapshot', async t => {
  const publish = await handler('publish')
  const db = database(t)
  const candidate = payload()
  assert.equal((await publish(context(publishRequest(candidate), db))).status, 201)
  candidate.observedAt = '2026-11-12T10:15:00+08:00'
  candidate.aShare.strength = 70
  const response = await publish(context(publishRequest(candidate), db))
  assert.equal(response.status, 200)
  assert.deepEqual(await response.json(), { ok: true, duplicate: true, observedAt: candidate.observedAt })
  const rows = db.execute('SELECT payload_json FROM market_dashboard_snapshots').results
  assert.equal(rows.length, 1)
  assert.equal(JSON.parse(rows[0].payload_json).aShare.strength, 60)
})

test('publish returns safe database failures without token, SQL or provider details', async () => {
  const publish = await handler('publish')
  const failingDb = { prepare() { throw new Error(`${TOKEN} raw provider response SELECT secret`) } }
  await errorResponse(await publish(context(publishRequest(payload()), failingDb)), 503, 'STORAGE_UNAVAILABLE')
})

test('publish accepts the five-minute future boundary and rejects one millisecond beyond it', async t => {
  const publish = await handler('publish')
  const db = database(t)
  const now = Date.now
  Date.now = () => Date.parse('2026-11-12T02:10:00Z')
  t.after(() => { Date.now = now })
  assert.equal((await publish(context(publishRequest(payload()), db))).status, 201)
  const candidate = payload()
  candidate.observedAt = '2026-11-12T02:15:00.001Z'
  await errorResponse(await publish(context(publishRequest(candidate), db)), 400, 'INVALID_PAYLOAD')
})

test('publish preserves distinct microsecond observations instead of colliding at millisecond precision', async t => {
  const publish = await handler('publish')
  const db = database(t)
  for (const observedAt of ['2026-11-12T02:15:00.000001Z', '2026-11-12T10:15:00.000002+08:00']) {
    const candidate = payload(); candidate.observedAt = observedAt
    assert.equal((await publish(context(publishRequest(candidate), db))).status, 201)
  }
  assert.deepEqual(db.execute('SELECT observed_at FROM market_dashboard_snapshots ORDER BY observed_at').results, [
    { observed_at: '2026-11-12T02:15:00.000001Z' }, { observed_at: '2026-11-12T02:15:00.000002Z' },
  ])
})

test('publish accepts the actual Task 3 fixture payload without forwarding provider rows', async t => {
  const publish = await handler('publish')
  const db = database(t)
  const candidate = JSON.parse(execFileSync('python3', ['-B', '-c', `
import json
from tools.market_dashboard.job import run_job
result = run_job({'fixture': True, 'dry_run': True})
assert result.success
print(json.dumps(result.payload))
`], { cwd: new URL('..', import.meta.url), encoding: 'utf8' }))
  const response = await publish(context(publishRequest(candidate), db))
  assert.equal(response.status, 201)
  assert.equal(db.execute('SELECT completeness FROM market_dashboard_snapshots').results[0].completeness, 54)
})

function readContext(name, db, search = '') {
  return context(new Request(`https://example.test/api/market-dashboard/${name}${search}`), db)
}
async function publishAt(publish, db, observedAt, score = 60) {
  const candidate = payload()
  candidate.observedAt = observedAt
  candidate.marketDate = new Date(Date.parse(observedAt) + 8 * 3600000).toISOString().slice(0, 10)
  candidate.aShare.strength = score
  const response = await publish(context(publishRequest(candidate), db))
  assert.equal(response.status, 201)
  return candidate
}

test('read handlers return stable noncached empty snapshots and database failures', async t => {
  const db = database(t)
  for (const name of ['latest', 'history']) {
    const read = await handler(name)
    await errorResponse(await read(readContext(name, db)), 404, 'NO_SNAPSHOT')
    await errorResponse(await read(readContext(name, { prepare() { throw new Error(`${TOKEN} provider private`) } })), 503, 'STORAGE_UNAVAILABLE')
  }
})

test('latest selects by observation time after older backfills and preserves original timestamp strings and nullable scores', async t => {
  const publish = await handler('publish'), latest = await handler('latest')
  const db = database(t)
  const expected = await publishAt(publish, db, '2026-11-12T10:15:00+08:00', 80)
  await publishAt(publish, db, '2026-11-12T01:00:00Z', 20)
  // Lexicographic sorting of original offsets would place this older record first.
  await publishAt(publish, db, '2026-11-12T10:30:00+09:00', 30)
  const response = await latest(readContext('latest', db))
  assert.equal(response.status, 200)
  assert.equal(response.headers.get('Cache-Control'), 'public, max-age=30, s-maxage=60')
  assert.equal(response.headers.get('Content-Type'), 'application/json; charset=utf-8')
  assert.deepEqual(await response.json(), expected)
  assert.equal(db.execute('SELECT COUNT(*) AS count FROM market_dashboard_snapshots').results[0].count, 3)
})

test('history defaults to 5d and accepts only the four bounded windows', async t => {
  const publish = await handler('publish'), history = await handler('history')
  const db = database(t)
  await publishAt(publish, db, OBSERVED)
  for (const window of ['1d', '5d', '20d', '90d']) {
    const response = await history(readContext('history', db, `?window=${window}`))
    assert.equal(response.status, 200)
    assert.equal(response.headers.get('Cache-Control'), 'public, max-age=300, s-maxage=600')
    assert.equal((await response.json()).window, window)
  }
  assert.equal((await (await history(readContext('history', db))).json()).window, '5d')
  for (const query of ['?window=2d', '?window=', '?window=1D', '?window=5d%27%20OR%201=1', '?window=5d&window=90d']) {
    await errorResponse(await history(readContext('history', null, query)), 400, 'INVALID_WINDOW')
  }
})

test('history includes its exact UTC lower boundary and sorts compact observations chronologically', async t => {
  const publish = await handler('publish'), history = await handler('history')
  const db = database(t)
  await publishAt(publish, db, '2026-11-12T10:15:00+08:00', 80)
  await publishAt(publish, db, '2026-11-07T10:14:59.999999+08:00', 10)
  await publishAt(publish, db, '2026-11-07T10:15:00+08:00', 20)
  await publishAt(publish, db, '2026-11-09T01:00:00Z', 50)
  const response = await history(readContext('history', db, '?window=5d'))
  assert.equal(response.status, 200)
  const result = await response.json()
  assert.deepEqual(Object.keys(result).sort(), ['snapshots', 'window'])
  assert.deepEqual(result.snapshots.map(item => item.observedAt), [
    '2026-11-07T02:15:00.000000Z', '2026-11-09T01:00:00.000000Z', '2026-11-12T02:15:00.000000Z',
  ])
  assert.deepEqual(result.snapshots.map(item => item.aShare.strength), [20, 50, 80])
  const last = result.snapshots[2]
  assert.deepEqual(Object.keys(last).sort(), ['aShare', 'global', 'industries', 'marketDate', 'observedAt', 'scoringVersion', 'session', 'styles'])
  assert.equal(last.marketDate, '2026-11-12')
  assert.equal(last.scoringVersion, 'market-score-v0.1')
  assert.equal(last.session, 'intraday')
  assert.deepEqual(last.aShare, { id: 'a-share', strength: 80, heat: null, risk: 40, completeness: 60 })
  assert.equal(last.styles.length, 6)
  assert.equal(last.industries.length, 35)
  assert.ok(!JSON.stringify(result).includes('contributors'))
  assert.ok(!JSON.stringify(result).includes('sourceTimestamps'))
  assert.ok(!JSON.stringify(result).includes('sourceMode'))
})

test('history keeps the anchor microseconds at the lower window boundary', async t => {
  const publish = await handler('publish'), history = await handler('history')
  const db = database(t)
  await publishAt(publish, db, '2026-11-12T02:15:00.000002Z')
  await publishAt(publish, db, '2026-11-11T02:15:00.000001Z')
  await publishAt(publish, db, '2026-11-11T02:15:00.000002Z')
  const response = await history(readContext('history', db, '?window=1d'))
  assert.deepEqual((await response.json()).snapshots.map(item => item.observedAt), [
    '2026-11-11T02:15:00.000002Z', '2026-11-12T02:15:00.000002Z',
  ])
})

test('read handlers redact corrupt stored payloads instead of publishing internal text', async t => {
  const db = database(t), publish = await handler('publish')
  await publishAt(publish, db, OBSERVED)
  db.execute('UPDATE market_dashboard_snapshots SET payload_json = ?', [`{"token":"${TOKEN}"}`])
  for (const name of ['latest', 'history']) {
    await errorResponse(await (await handler(name))(readContext(name, db)), 503, 'STORAGE_UNAVAILABLE')
  }
})

test('publish rejects even one microsecond beyond the allowed future skew', async t => {
  const publish = await handler('publish')
  const db = database(t)
  const now = Date.now
  Date.now = () => Date.parse('2026-11-12T02:10:00Z')
  t.after(() => { Date.now = now })
  const candidate = payload(); candidate.observedAt = '2026-11-12T02:15:00.000001Z'
  await errorResponse(await publish(context(publishRequest(candidate), db)), 400, 'INVALID_PAYLOAD')
})

test('publish accepts a valid body at exactly 256 KiB while rejecting one extra byte', async t => {
  const publish = await handler('publish')
  const db = database(t)
  const encoded = JSON.stringify(payload())
  const body = encoded + ' '.repeat(256 * 1024 - new TextEncoder().encode(encoded).byteLength)
  assert.equal((await publish(context(publishRequest(body), db))).status, 201)
  await errorResponse(await publish(context(publishRequest(body + ' '), db)), 413, 'PAYLOAD_TOO_LARGE')
})

for (const [label, observedAt, marketDate] of [
  ['upper', '9999-12-31T23:59:59-23:59', '+010000-01'],
  ['lower', '0001-01-01T00:00:00+23:59', '0000-12-31'],
]) {
  test(`publish rejects ${label} UTC year overflow before accessing D1`, async () => {
    const publish = await handler('publish')
    let databaseCalls = 0
    const db = { prepare() { databaseCalls++; throw new Error('database must not be reached') } }
    const candidate = payload(); candidate.observedAt = observedAt; candidate.marketDate = marketDate
    await errorResponse(await publish(context(publishRequest(candidate), db)), 400, 'INVALID_PAYLOAD')
    assert.equal(databaseCalls, 0)
  })
}

test('timestamp rejects UTC year overflow even when the input has a legal four-digit year', async () => {
  const { timestamp } = await import('../functions/_lib/market-dashboard.js')
  for (const input of ['9999-12-31T23:59:59-23:59', '0001-01-01T00:00:00+23:59']) {
    assert.throws(() => timestamp(input), /INVALID_PAYLOAD/)
  }
})

test('legal year 0001 and 9999 timestamps retain four-digit UTC years and the publication skew gate', async t => {
  const { timestamp, validatePayload } = await import('../functions/_lib/market-dashboard.js')
  const publish = await handler('publish'), db = database(t)
  for (const [observedAt, utc, marketDate] of [
    ['0001-01-01T23:59:00+23:59', '0001-01-01T00:00:00.000000Z', '0001-01-01'],
    ['9999-12-30T00:01:00-23:59', '9999-12-31T00:00:00.000000Z', '9999-12-31'],
  ]) {
    assert.equal(timestamp(observedAt).utc, utc)
    const candidate = payload(); candidate.observedAt = observedAt; candidate.marketDate = marketDate
    assert.equal(validatePayload(candidate).utc, utc)
    if (marketDate.startsWith('0001')) {
      assert.equal((await publish(context(publishRequest(candidate), db))).status, 201)
    } else {
      await errorResponse(await publish(context(publishRequest(candidate), db)), 400, 'INVALID_PAYLOAD')
      const now = Date.now
      Date.now = () => Date.parse('9999-12-30T23:55:00Z')
      try { assert.equal((await publish(context(publishRequest(candidate), db))).status, 201) }
      finally { Date.now = now }
    }
  }
})

test('publish rejects a Shanghai market date overflowing year 9999 before accessing D1', async t => {
  const now = Date.now
  Date.now = () => Date.parse('9999-12-31T23:00:00Z')
  t.after(() => { Date.now = now })
  const publish = await handler('publish')
  let databaseCalls = 0
  const db = { prepare() { databaseCalls++; throw new Error('database must not be reached') } }
  const candidate = payload()
  candidate.observedAt = '9999-12-31T23:00:00Z'
  candidate.marketDate = '+010000-01'
  await errorResponse(await publish(context(publishRequest(candidate), db)), 400, 'INVALID_PAYLOAD')
  assert.equal(databaseCalls, 0)
})

test('publish accepts a valid year 9999 observation when the future limit crosses year 10000', async t => {
  const publish = await handler('publish'), db = database(t)
  const now = Date.now
  Date.now = () => Date.parse('9999-12-31T23:58:00Z')
  t.after(() => { Date.now = now })
  const candidate = payload()
  candidate.observedAt = '9999-12-31T15:59:59.999999Z'
  candidate.marketDate = '9999-12-31'
  assert.equal((await publish(context(publishRequest(candidate), db))).status, 201)
})
