// Public derived-data contract, paired with Task 3 publisher / Task 4 Pages API.
const AXES = ['strength', 'heat', 'risk']
const STYLES = ['000300.SH', '000852.SH', 'H30356.CSI', '399006.SZ', '000922.CSI', '000688.SH']
const INDUSTRIES = Array.from({ length: 37 }, (_, i) => 100 + i)
  .filter(code => code !== 117 && code !== 118).map(code => `882${code}.WI`)
const WINDOWS = ['1d', '5d', '20d', '90d']
const STAGES = ['冰点', '修复', '震荡', '扩张', '过热', '退潮']
const UNAVAILABLE = ['missingObservation', 'missingCurrentScores', 'missingTradingCalendar', 'missingTargetTradingDate']
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const shape = (value, required, optional = []) => record(value) && required.every(key => Object.hasOwn(value, key))
  && Object.keys(value).every(key => required.includes(key) || optional.includes(key))
const number = (value, min = 0, max = 100) => typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max
const strings = value => Array.isArray(value) && value.every(item => typeof item === 'string' && item.length <= 200)

function timestamp(value) {
  if (typeof value !== 'string') return false
  const match = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.exec(value)
  if (!match) return false
  const [, y, m, d, h, minute, s, offset] = match
  const year = Number(y), month = Number(m), day = Number(d)
  const days = new Date(Date.UTC(year, month, 0)).getUTCDate()
  if (year < 1 || month < 1 || month > 12 || day < 1 || day > days || Number(h) > 23 || Number(minute) > 59 || Number(s) > 59
    || offset !== 'Z' && (Number(offset.slice(1, 3)) > 23 || Number(offset.slice(4)) > 59)) return false
  const date = new Date(value.replace(' ', 'T'))
  return Number.isFinite(date.getTime()) && date.getUTCFullYear() >= 1 && date.getUTCFullYear() <= 9999
}
function validObservation(value) {
  return timestamp(value.observedAt) && typeof value.marketDate === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value.marketDate)
    && value.marketDate === new Date(Date.parse(value.observedAt.replace(' ', 'T')) + 8 * 3600000).toISOString().slice(0, 10)
    && ['intraday', 'close'].includes(value.session) && value.scoringVersion === 'market-score-v0.1'
}
function validScores(value) {
  return record(value) && AXES.every(axis => value[axis] === null || Number.isInteger(value[axis]) && number(value[axis]))
    && AXES.some(axis => value[axis] !== null) && number(value.completeness) && value.completeness > 0
}
function validChange(value) {
  return value === null || shape(value, AXES) && AXES.every(axis => value[axis] === null || number(value[axis], -100, 100))
}
function validObject(value) {
  return shape(value, ['id', ...AXES, 'completeness', 'missing', 'contributors', 'sourceTimestamps', 'change1d', 'change5d'],
    ['name', 'frequency', 'observedAt', 'stage', 'comparisonFallback', 'comparisonUnavailable'])
    && validScores(value) && strings(value.missing)
    && (!Object.hasOwn(value, 'name') || typeof value.name === 'string' && value.name.length <= 100)
    && (!Object.hasOwn(value, 'frequency') || ['intraday', 'daily', 'monthly'].includes(value.frequency))
    && (!Object.hasOwn(value, 'observedAt') || timestamp(value.observedAt))
    && (value.stage == null || value.completeness >= 50 && STAGES.includes(value.stage))
    && validChange(value.change1d) && validChange(value.change5d)
    && Array.isArray(value.sourceTimestamps) && value.sourceTimestamps.length > 0
    && value.sourceTimestamps.every(source => shape(source, ['source', 'timestamp'])
      && ['Wind', 'FRED', 'MX', 'Derived'].includes(source.source) && timestamp(source.timestamp))
    && Array.isArray(value.contributors) && value.contributors.length <= 3
    && value.contributors.every(item => shape(item, ['label', 'impact'], ['evidence'])
      && typeof item.label === 'string' && item.label.length <= 200 && number(item.impact, -100, 100)
      && (!Object.hasOwn(item, 'evidence') || typeof item.evidence === 'string' && item.evidence.length <= 200))
    && (!Object.hasOwn(value, 'comparisonFallback') || value.comparisonFallback === 'close')
    && (!Object.hasOwn(value, 'comparisonUnavailable') || shape(value.comparisonUnavailable, [], ['change1d', 'change5d'])
      && Object.values(value.comparisonUnavailable).every(reason => UNAVAILABLE.includes(reason)))
}
function validObjects(value, validator) {
  return record(value.global) && value.global.id === 'global' && validator(value.global)
    && record(value.aShare) && value.aShare.id === 'a-share' && validator(value.aShare)
    && [['styles', STYLES], ['industries', INDUSTRIES]].every(([key, ids]) => Array.isArray(value[key])
      && value[key].length === ids.length && new Set(value[key].map(item => item?.id)).size === ids.length
      && value[key].every(item => ids.includes(item?.id) && validator(item)))
}
function validLatest(value) {
  if (!shape(value, ['schemaVersion', 'scoringVersion', 'observedAt', 'marketDate', 'session', 'global', 'aShare', 'styles', 'industries', 'dataStatus'], ['sourceMode'])
    || value.schemaVersion !== 'market-dashboard-v1' || !validObservation(value) || !validObjects(value, validObject)) return false
  const status = value.dataStatus
  const objects = [value.global, value.aShare, ...value.styles, ...value.industries]
  if (!shape(status, ['completeness', 'stale', 'missing']) || !number(status.completeness) || typeof status.stale !== 'boolean'
    || !strings(status.missing) || status.completeness !== Math.floor(objects.reduce((sum, item) => sum + item.completeness, 0) / 43 + 0.5)
    || status.completeness <= 0) return false
  if (!Object.hasOwn(value, 'sourceMode')) return true
  const modes = value.sourceMode
  return shape(modes, ['breadth', 'styles', 'industries', 'global'])
    && ['breadth', 'styles', 'industries'].every(key => modes[key] === 'wind') && record(modes.global)
    && Object.entries(modes.global).every(([key, provider]) => /^[\p{L}\p{N}]+$/u.test(key) && ['fred', 'wind', 'mx'].includes(provider))
}
function validHistory(value, window) {
  return shape(value, ['window', 'snapshots']) && value.window === window && Array.isArray(value.snapshots) && value.snapshots.length > 0
    && value.snapshots.every((snapshot, i) => shape(snapshot, ['observedAt', 'marketDate', 'session', 'scoringVersion', 'global', 'aShare', 'styles', 'industries'])
      && validObservation(snapshot) && validObjects(snapshot, object => shape(object, ['id', ...AXES, 'completeness']) && validScores(object))
      && (i === 0 || Date.parse(snapshot.observedAt) >= Date.parse(value.snapshots[i - 1].observedAt)))
}
const messages = {
  NO_SNAPSHOT: '暂无有效快照', HTTP_ERROR: '服务暂不可用', INVALID_JSON: '响应不是有效 JSON', INVALID_SCHEMA: '快照格式无效',
  TIMEOUT: '请求超时', ABORTED: '请求已取消', NETWORK_ERROR: '网络请求失败', INVALID_WINDOW: '历史窗口无效',
}
function failure(code, status) {
  return { data: null, error: { code, message: messages[code], ...(status === undefined ? {} : { status }) } }
}

async function load(url, validate, fetcher, options) {
  if (options.signal?.aborted) return failure('ABORTED')
  const controller = new AbortController()
  let timer, stop, stopCode
  const stopped = new Promise(resolve => { stop = resolve })
  const cancel = code => {
    stopCode = code
    stop(failure(code))
    controller.abort()
  }
  const onAbort = () => cancel('ABORTED')
  options.signal?.addEventListener('abort', onAbort, { once: true })
  timer = setTimeout(() => cancel('TIMEOUT'), options.timeoutMs ?? 12000)
  try {
    const request = (async () => {
      try {
        const response = await fetcher(url, { signal: controller.signal })
        if (!response.ok) {
          if (response.status === 404) {
            const body = await response.json().catch(() => null)
            if (body?.error === 'NO_SNAPSHOT') return failure('NO_SNAPSHOT', 404)
          }
          return failure('HTTP_ERROR', response.status)
        }
        let body
        try { body = await response.json() }
        catch { return failure(stopCode ?? 'INVALID_JSON') }
        return validate(body) ? { data: body, error: null } : failure('INVALID_SCHEMA')
      } catch { return failure(stopCode ?? 'NETWORK_ERROR') }
    })()
    return await Promise.race([request, stopped])
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', onAbort)
  }
}

// These independent results can be combined with Promise.all; history failure never clears latest.
export function loadMarketDashboard(fetcher = fetch, options = {}) {
  return load('/api/market-dashboard/latest', validLatest, fetcher, options)
}
export function loadMarketHistory(window, fetcher = fetch, options = {}) {
  if (!WINDOWS.includes(window)) return Promise.resolve(failure('INVALID_WINDOW'))
  return load(`/api/market-dashboard/history?window=${window}`, body => validHistory(body, window), fetcher, options)
}
