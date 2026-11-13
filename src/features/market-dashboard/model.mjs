const MINUTE = 60000
const DAY = 86400000
// Daily tolerance is deliberately conservative (weekends / holidays); callers may tighten it.
export const DEFAULT_STALE_AFTER_MS = Object.freeze({ intraday: 30 * MINUTE, daily: 20 * DAY, monthly: 75 * DAY })
const LABELS = { strength: ['弱', '中性', '强'], heat: ['冷', '正常', '热'], risk: ['低', '中等', '高'] }
const finite = value => typeof value === 'number' && Number.isFinite(value)
const byId = (a, b) => a.id < b.id ? -1 : a.id > b.id ? 1 : 0
function scoreLabel(axis, value) { return finite(value) ? LABELS[axis][value < 30 ? 0 : value < 70 ? 1 : 2] : '暂无数据' }
function beijing(time) {
  const date = new Date(time + 8 * 3600000)
  return { date: date.toISOString().slice(0, 10), weekday: date.getUTCDay(),
    minute: date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60 + date.getUTCMilliseconds() / MINUTE }
}
function context(payload, now, options) {
  const time = now.getTime()
  const local = beijing(time)
  // Without an explicit exchange calendar, weekdays are only a scheduling approximation.
  const tradingDay = options.tradingDates ? options.tradingDates.includes(local.date) : local.weekday > 0 && local.weekday < 6
  const trading = tradingDay && (local.minute >= 570 && local.minute < 690 || local.minute >= 780 && local.minute < 900)
  const observed = beijing(Date.parse(payload.observedAt))
  const confirmedClose = payload.session === 'close' && payload.marketDate === local.date
    && observed.date === local.date && observed.minute >= 900
  return { time, trading, missingClose: tradingDay && local.minute > 930 && !confirmedClose,
    thresholds: { ...DEFAULT_STALE_AFTER_MS, ...options.staleAfterMs }, forcedStale: payload.dataStatus.stale }
}
function freshness(timestamp, frequency, ctx, oldestSourceAt) {
  const ageMs = Math.max(0, ctx.time - Date.parse(timestamp))
  const delayed = frequency === 'intraday' ? ctx.trading && ageMs > ctx.thresholds.intraday : ageMs > ctx.thresholds[frequency]
  const missingClose = frequency === 'intraday' && ctx.missingClose
  const stale = ctx.forcedStale || delayed || missingClose
  return { stale, ageMs, missingClose, label: ctx.forcedStale ? '数据滞后' : missingClose ? '缺少收盘确认' : stale ? '数据滞后' : '正常',
    ...(oldestSourceAt === undefined ? {} : { oldestSourceAt }) }
}
function comparisonBadge(object, key) {
  const reason = object.comparisonUnavailable?.[key]
  if (reason === 'missingTradingCalendar') return '缺少交易日历'
  if (reason === 'missingTargetTradingDate') return '缺少目标交易日'
  if (object[key] == null || reason) return '暂无可比快照'
  return object.comparisonFallback === 'close' ? '收盘回退' : '同口径比较'
}
function improvement(object) {
  const five = object.change5d?.strength, one = object.change1d?.strength
  if (finite(five)) return { improvementValue: five, improvementWindow: '5d', improvementLabel: '5日强度改善' }
  if (finite(one)) return { improvementValue: one, improvementWindow: '1d', improvementLabel: '1日强度改善（回退）' }
  return { improvementValue: null, improvementWindow: null, improvementLabel: '暂无可比快照' }
}
function descending(axis) {
  return (a, b) => {
    const left = a[axis], right = b[axis]
    if (!finite(left)) return finite(right) ? 1 : byId(a, b)
    if (!finite(right)) return -1
    return right - left || byId(a, b)
  }
}
// Rankings include all objects; consumers can take the first five and render unavailable entries honestly.
export function rankIndustries(industries) {
  const entries = industries.map(object => ({ ...object, ...improvement(object) }))
  return { strength: [...entries].sort(descending('strength')), heat: [...entries].sort(descending('heat')),
    risk: [...entries].sort(descending('risk')), improvement: [...entries].sort(descending('improvementValue')) }
}
export function deriveMarketDashboardView(payload, now = new Date(), options = {}) {
  const ctx = context(payload, now, options)
  const present = object => {
    const sources = object.sourceTimestamps.map(source => source.timestamp)
    const oldestSourceAt = [...sources].sort((a, b) => Date.parse(a) - Date.parse(b))[0] ?? null
    const timestamps = [object.observedAt ?? payload.observedAt, ...sources]
    const oldest = timestamps.sort((a, b) => Date.parse(a) - Date.parse(b))[0]
    const stage = object.completeness < 50 ? null : object.stage ?? null
    return { ...object, stage, stageLabel: stage ?? (object.completeness < 50 ? '证据不足' : '暂无阶段结论'),
      scoreLabels: Object.fromEntries(Object.keys(LABELS).map(axis => [axis, scoreLabel(axis, object[axis])])),
      evidenceInsufficient: object.completeness < 70, evidenceLabel: object.completeness < 70 ? '证据不足' : '证据充分',
      freshness: freshness(oldest, object.frequency ?? 'intraday', ctx, oldestSourceAt),
      comparisonBadges: { change1d: comparisonBadge(object, 'change1d'), change5d: comparisonBadge(object, 'change5d') }, ...improvement(object) }
  }
  const industries = payload.industries.map(present).sort(byId)
  return { ...payload, global: present(payload.global), aShare: present(payload.aShare), styles: payload.styles.map(present),
    industries, freshness: freshness(payload.observedAt, 'intraday', ctx), rankings: rankIndustries(industries) }
}
