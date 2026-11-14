// Public, derived-only contract. Keep identity/version changes paired with the local scorer.
export const SCHEMA_VERSION = 'market-dashboard-v2'
export const SCORING_VERSION = 'market-score-v0.1'
export const CONCEPT_SELECTION_VERSION = 'concept-selection-v0.1'
export const CONCEPT_SCORING_VERSION = 'concept-score-v0.1'
const MAX_BODY_BYTES = 256 * 1024
const AXES = ['strength', 'heat', 'risk']
const STYLE_IDS = ['000300.SH', '000852.SH', 'H30356.CSI', '399006.SZ', '000922.CSI', '000688.SH']
const INDUSTRY_IDS = Array.from({ length: 37 }, (_, i) => 100 + i)
  .filter(code => code !== 117 && code !== 118).map(code => `882${code}.WI`)
const STAGES = ['冰点', '修复', '震荡', '扩张', '过热', '退潮']
const UNAVAILABLE = ['missingObservation', 'missingCurrentScores', 'missingTradingCalendar', 'missingTargetTradingDate']

export function jsonResponse(value, status = 200, cache = 'no-store') {
  return new Response(JSON.stringify(value), { status, headers: {
    'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': cache,
  } })
}
export function errorResponse(code, status) { return jsonResponse({ error: code }, status) }
function requireValid(condition) { if (!condition) throw new Error('INVALID_PAYLOAD') }
function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value) }
function shape(value, required, optional = []) {
  return record(value) && required.every(key => Object.hasOwn(value, key)) &&
    Object.keys(value).every(key => required.includes(key) || optional.includes(key))
}
function numeric(value, min = 0, max = 100) {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
}
function strings(value) { return Array.isArray(value) && value.every(s => typeof s === 'string' && s.length <= 200) }

// Validate calendar dates too: Date.parse alone silently accepts February 30.
export function timestamp(value) {
  requireValid(typeof value === 'string')
  const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(value)
  requireValid(match)
  const [, year, month, day, hour, minute, second, fraction = '', offset] = match
  const days = new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate()
  requireValid(Number(year) >= 1 && Number(month) >= 1 && Number(month) <= 12 && Number(day) >= 1 && Number(day) <= days &&
    Number(hour) < 24 && Number(minute) < 60 && Number(second) < 60 &&
    (offset === 'Z' || Number(offset.slice(1, 3)) < 24 && Number(offset.slice(4)) < 60))
  const millis = Date.parse(value.replace(' ', 'T'))
  requireValid(Number.isFinite(millis))
  const normalized = new Date(millis)
  // Offsets can move a four-digit input year outside the canonical UTC domain.
  requireValid(normalized.getUTCFullYear() >= 1 && normalized.getUTCFullYear() <= 9999)
  const utc = normalized.toISOString().replace(/\.(\d{3})Z$/, `.$1${fraction.slice(3).padEnd(3, '0')}Z`)
  return { millis, utc }
}

export function validatePayload(payload) {
  requireValid(shape(payload, ['schemaVersion', 'scoringVersion', 'observedAt', 'marketDate', 'session',
    'global', 'aShare', 'styles', 'industries', 'concepts', 'dataStatus'], ['sourceMode']))
  requireValid(payload.schemaVersion === SCHEMA_VERSION && payload.scoringVersion === SCORING_VERSION)
  const observed = timestamp(payload.observedAt)
  requireValid(typeof payload.marketDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(payload.marketDate) &&
    payload.marketDate === new Date(observed.millis + 8 * 3600000).toISOString().slice(0, 10))
  requireValid(['intraday', 'close'].includes(payload.session))
  requireValid(record(payload.global) && payload.global.id === 'global')
  requireValid(record(payload.aShare) && payload.aShare.id === 'a-share')
  for (const [key, ids] of [['styles', STYLE_IDS], ['industries', INDUSTRY_IDS]]) {
    const items = payload[key]
    requireValid(Array.isArray(items) && items.length === ids.length && items.every(record))
    requireValid(new Set(items.map(obj => obj.id)).size === ids.length && items.every(obj => ids.includes(obj.id)))
  }
  const concepts = payload.concepts
  requireValid(shape(concepts, ['selectionVersion', 'scoringVersion', 'selectedAt', 'core', 'dynamic']) &&
    concepts.selectionVersion === CONCEPT_SELECTION_VERSION && concepts.scoringVersion === CONCEPT_SCORING_VERSION)
  timestamp(concepts.selectedAt)
  requireValid(Array.isArray(concepts.core) && concepts.core.length === 25 && concepts.core.every(record) &&
    Array.isArray(concepts.dynamic) && concepts.dynamic.length === 10 && concepts.dynamic.every(record))
  const coreIds = concepts.core.map(obj => obj.id), dynamicIds = concepts.dynamic.map(obj => obj.id)
  requireValid([...coreIds, ...dynamicIds].every(id => typeof id === 'string' && /^884\d{2,4}\.WI$/.test(id)) &&
    new Set(coreIds).size === 25 && new Set(dynamicIds).size === 10 && !coreIds.some(id => dynamicIds.includes(id)))
  for (const obj of concepts.core) {
    requireValid(!['selectionScore', 'selectedOn', 'retainedTradingDays'].some(key => Object.hasOwn(obj, key)))
  }
  for (const obj of concepts.dynamic) {
    requireValid(numeric(obj.selectionScore) && typeof obj.selectedOn === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(obj.selectedOn) &&
      Number.isInteger(obj.retainedTradingDays) && obj.retainedTradingDays >= 1)
    const [year, month, day] = obj.selectedOn.split('-').map(Number)
    requireValid(year >= 1 && month >= 1 && month <= 12 && day >= 1 &&
      day <= new Date(Date.UTC(year, month, 0)).getUTCDate())
  }
  const objects = [payload.global, payload.aShare, ...payload.styles, ...payload.industries,
    ...concepts.core, ...concepts.dynamic]
  for (const obj of objects) {
    if (!concepts.dynamic.includes(obj)) {
      requireValid(!['selectionScore', 'selectedOn', 'retainedTradingDays'].some(key => Object.hasOwn(obj, key)))
    }
    requireValid(shape(obj, ['id', ...AXES, 'completeness', 'missing', 'contributors', 'sourceTimestamps', 'change1d', 'change5d'],
      ['name', 'frequency', 'observedAt', 'stage', 'comparisonFallback', 'comparisonUnavailable',
        'selectionScore', 'selectedOn', 'retainedTradingDays']))
    requireValid(numeric(obj.completeness) && obj.completeness > 0 && strings(obj.missing))
    requireValid(AXES.every(axis => obj[axis] === null || Number.isInteger(obj[axis]) && numeric(obj[axis])))
    requireValid(AXES.some(axis => obj[axis] !== null))
    if (Object.hasOwn(obj, 'observedAt')) timestamp(obj.observedAt)
    if (Object.hasOwn(obj, 'frequency')) requireValid(['intraday', 'daily', 'monthly'].includes(obj.frequency))
    if (Object.hasOwn(obj, 'name')) requireValid(typeof obj.name === 'string' && obj.name.length <= 100)
    requireValid(obj.stage == null || obj.completeness >= 50 && STAGES.includes(obj.stage))
    for (const key of ['change1d', 'change5d']) {
      const change = obj[key]
      requireValid(change === null || shape(change, AXES) && AXES.every(axis => change[axis] === null || numeric(change[axis], -100, 100)))
    }
    requireValid(Array.isArray(obj.sourceTimestamps) && obj.sourceTimestamps.length > 0)
    for (const source of obj.sourceTimestamps) {
      requireValid(shape(source, ['source', 'timestamp']) && ['Wind', 'FRED', 'MX', 'Derived'].includes(source.source))
      timestamp(source.timestamp)
    }
    requireValid(Array.isArray(obj.contributors) && obj.contributors.length <= 3)
    for (const contributor of obj.contributors) {
      requireValid(shape(contributor, ['label', 'impact'], ['evidence']) && typeof contributor.label === 'string' &&
        contributor.label.length <= 200 && numeric(contributor.impact, -100, 100))
      if (Object.hasOwn(contributor, 'evidence')) requireValid(typeof contributor.evidence === 'string' && contributor.evidence.length <= 200)
    }
    if (Object.hasOwn(obj, 'comparisonFallback')) requireValid(obj.comparisonFallback === 'close')
    if (Object.hasOwn(obj, 'comparisonUnavailable')) {
      requireValid(shape(obj.comparisonUnavailable, [], ['change1d', 'change5d']) &&
        Object.values(obj.comparisonUnavailable).every(value => UNAVAILABLE.includes(value)))
    }
  }
  const status = payload.dataStatus
  requireValid(shape(status, ['completeness', 'stale', 'missing']) && numeric(status.completeness) &&
    typeof status.stale === 'boolean' && strings(status.missing))
  requireValid(status.completeness > 0 && status.completeness === Math.floor(objects.reduce((sum, obj) => sum + obj.completeness, 0) / objects.length + 0.5))
  if (Object.hasOwn(payload, 'sourceMode')) {
    const modes = payload.sourceMode
    requireValid(shape(modes, ['breadth', 'styles', 'industries', 'concepts', 'conceptDiscovery', 'global']) &&
      ['breadth', 'styles', 'industries', 'concepts'].every(key => modes[key] === 'wind') &&
      modes.conceptDiscovery === 'mx' && record(modes.global))
    requireValid(Object.entries(modes.global).every(([key, value]) => /^[\p{L}\p{N}]+$/u.test(key) && ['fred', 'wind', 'mx'].includes(value)))
  }
  requireValid(new TextEncoder().encode(JSON.stringify(payload)).byteLength <= MAX_BODY_BYTES)
  return observed
}

export async function authorized(request, token) {
  const authorization = request.headers.get('Authorization') || ''
  const match = /^Bearer ([^\s]+)$/i.exec(authorization)
  if (!match) return false
  // Compare fixed-length SHA-256 digests. Workers supports timingSafeEqual;
  // other Web Crypto runtimes use the same fixed 32-iteration comparison.
  const encoder = new TextEncoder()
  const [supplied, expected] = await Promise.all([match[1], token].map(value => crypto.subtle.digest('SHA-256', encoder.encode(value))))
  if (typeof crypto.subtle.timingSafeEqual === 'function') return crypto.subtle.timingSafeEqual(supplied, expected)
  const left = new Uint8Array(supplied), right = new Uint8Array(expected)
  let difference = 0
  for (let i = 0; i < 32; i++) difference |= left[i] ^ right[i]
  return difference === 0
}

export async function readBoundedJson(request) {
  const reader = request.body?.getReader()
  if (!reader) throw new Error('INVALID_JSON')
  let length = 0
  const chunks = []
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      length += value.byteLength
      if (length > MAX_BODY_BYTES) {
        await reader.cancel().catch(() => {})
        throw new Error('PAYLOAD_TOO_LARGE')
      }
      chunks.push(value)
    }
  } finally { reader.releaseLock() }
  const bytes = new Uint8Array(length)
  let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) }
  catch { throw new Error('INVALID_JSON') }
}

export function storedPayload(row) {
  const payload = JSON.parse(row.payload_json)
  validatePayload(payload)
  return payload
}
export function compactSnapshot(row) {
  const payload = storedPayload(row)
  const compact = obj => ({ id: obj.id, strength: obj.strength, heat: obj.heat, risk: obj.risk, completeness: obj.completeness })
  return {
    observedAt: row.observed_at, marketDate: payload.marketDate, session: payload.session,
    scoringVersion: payload.scoringVersion, global: compact(payload.global), aShare: compact(payload.aShare),
    styles: payload.styles.map(compact), industries: payload.industries.map(compact),
    concepts: { selectionVersion: payload.concepts.selectionVersion,
      scoringVersion: payload.concepts.scoringVersion, selectedAt: payload.concepts.selectedAt,
      core: payload.concepts.core.map(compact), dynamic: payload.concepts.dynamic.map(compact) },
  }
}
