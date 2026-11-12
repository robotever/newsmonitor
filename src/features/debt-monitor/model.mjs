const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

function isValidDate(value) {
  if (!DATE_RE.test(value ?? '')) return false
  const [year, month, day] = value.split('-').map(Number)
  const date = new Date(Date.UTC(year, month - 1, day))
  return date.getUTCFullYear() === year
    && date.getUTCMonth() === month - 1
    && date.getUTCDate() === day
}

export function parseFredCsv(text) {
  return String(text)
    .split(/\r?\n/)
    .slice(1)
    .map(line => line.split(','))
    .filter(([date, raw]) => isValidDate(date) && raw != null && raw.trim() !== '.')
    .map(([date, raw]) => ({ date, value: Number(raw) }))
    .filter(point => Number.isFinite(point.value))
    .sort((a, b) => a.date.localeCompare(b.date))
}

export function summarizeSeries(points) {
  if (!Array.isArray(points) || points.length === 0) return null
  const ordered = [...points].sort((a, b) => a.date.localeCompare(b.date))
  const latest = ordered.at(-1)
  const previous = ordered.at(-2)
  return {
    date: latest.date,
    value: latest.value,
    previousValue: previous?.value ?? null,
    change: previous ? Number((latest.value - previous.value).toFixed(4)) : null,
  }
}

function withFreshness(summary, maxAgeDays, now) {
  if (!summary) return null
  const ageDays = (now.getTime() - new Date(`${summary.date}T00:00:00Z`).getTime()) / 86400000
  return { ...summary, stale: ageDays > maxAgeDays }
}

function spread(left, right, now) {
  if (!Array.isArray(left) || !Array.isArray(right)) return null
  const rightByDate = new Map(right.map(point => [point.date, point.value]))
  const common = left
    .filter(point => rightByDate.has(point.date))
    .map(point => ({ date: point.date, value: Math.round((point.value - rightByDate.get(point.date)) * 100) }))
    .sort((a, b) => a.date.localeCompare(b.date))
  if (common.length === 0) return null
  const latest = common.at(-1)
  const previous = common.at(-2)
  return withFreshness({
    date: latest.date,
    value: latest.value,
    previousValue: previous?.value ?? null,
    change: previous ? latest.value - previous.value : null,
  }, 75, now)
}

export const DEBT_THRESHOLDS = Object.freeze({
  real10y: { warning: 2, alert: 2.5 },
  highYieldSpread: { warning: 4, alert: 5 },
  termPremium: { warning: 0.75, alert: 1.1 },
  japanMonthlyChange: { warning: 0.08, alert: 0.15 },
  franceGermanySpread: { warning: 75, alert: 125 },
  italyGermanySpread: { warning: 125, alert: 200 },
})

function levelFor(value, threshold) {
  if (value == null) return 'neutral'
  if (value >= threshold.alert) return 'alert'
  if (value >= threshold.warning) return 'warning'
  return 'stable'
}

function currentValue(summary) {
  return summary && !summary.stale ? summary.value : null
}

function currentChange(summary) {
  return summary && !summary.stale ? summary.change : null
}

function scoreDashboard(us, japan, europe) {
  let score = 0
  const real10y = currentValue(us.real10y)
  const highYieldSpread = currentValue(us.highYieldSpread)
  const termPremium = currentValue(us.termPremium)
  const japanChange = currentChange(japan.nominal10y)
  const franceSpread = currentValue(europe.franceGermanySpread)
  const italySpread = currentValue(europe.italyGermanySpread)
  if (real10y >= DEBT_THRESHOLDS.real10y.warning) score += 1
  if (real10y >= DEBT_THRESHOLDS.real10y.alert) score += 1
  if (highYieldSpread >= DEBT_THRESHOLDS.highYieldSpread.warning) score += 2
  if (highYieldSpread >= DEBT_THRESHOLDS.highYieldSpread.alert) score += 1
  if (termPremium >= DEBT_THRESHOLDS.termPremium.warning) score += 1
  if (termPremium >= DEBT_THRESHOLDS.termPremium.alert) score += 1
  if (japanChange >= DEBT_THRESHOLDS.japanMonthlyChange.warning) score += 1
  if (japanChange >= DEBT_THRESHOLDS.japanMonthlyChange.alert) score += 1
  if (franceSpread >= DEBT_THRESHOLDS.franceGermanySpread.warning) score += 1
  if (franceSpread >= DEBT_THRESHOLDS.franceGermanySpread.alert) score += 1
  if (italySpread >= DEBT_THRESHOLDS.italyGermanySpread.warning) score += 1
  if (italySpread >= DEBT_THRESHOLDS.italyGermanySpread.alert) score += 1
  return score
}

export function deriveDebtDashboard(seriesMap, now = new Date()) {
  const us = {
    policy2y: withFreshness(summarizeSeries(seriesMap.DGS2), 10, now),
    nominal10y: withFreshness(summarizeSeries(seriesMap.DGS10), 10, now),
    real10y: withFreshness(summarizeSeries(seriesMap.DFII10), 10, now),
    inflation10y: withFreshness(summarizeSeries(seriesMap.T10YIE), 10, now),
    highYieldSpread: withFreshness(summarizeSeries(seriesMap.BAMLH0A0HYM2), 10, now),
    termPremium: withFreshness(summarizeSeries(seriesMap.THREEFYTP10), 14, now),
  }
  const japan = {
    nominal10y: withFreshness(summarizeSeries(seriesMap.IRLTLT01JPM156N), 75, now),
  }
  const europe = {
    germany10y: withFreshness(summarizeSeries(seriesMap.IRLTLT01DEM156N), 75, now),
    france10y: withFreshness(summarizeSeries(seriesMap.IRLTLT01FRM156N), 75, now),
    italy10y: withFreshness(summarizeSeries(seriesMap.IRLTLT01ITM156N), 75, now),
    franceGermanySpread: spread(seriesMap.IRLTLT01FRM156N, seriesMap.IRLTLT01DEM156N, now),
    italyGermanySpread: spread(seriesMap.IRLTLT01ITM156N, seriesMap.IRLTLT01DEM156N, now),
  }
  const score = scoreDashboard(us, japan, europe)
  const coverage = [us.real10y, us.highYieldSpread, japan.nominal10y, europe.franceGermanySpread ?? europe.italyGermanySpread]
    .filter(summary => summary && !summary.stale).length
  const status = coverage < 3 ? 'insufficient' : score >= 8 ? 'alert' : score >= 2 ? 'warning' : 'stable'
  const labels = { insufficient: '数据不足', stable: '平稳', warning: '关注', alert: '警戒' }
  const availableCount = Object.values(seriesMap).filter(points => Array.isArray(points) && points.length > 0).length
  const creditLevel = levelFor(currentValue(us.highYieldSpread), DEBT_THRESHOLDS.highYieldSpread)
  const franceLevel = levelFor(currentValue(europe.franceGermanySpread), DEBT_THRESHOLDS.franceGermanySpread)
  const italyLevel = levelFor(currentValue(europe.italyGermanySpread), DEBT_THRESHOLDS.italyGermanySpread)
  const europeLevel = franceLevel === 'alert' || italyLevel === 'alert'
    ? 'alert'
    : franceLevel === 'warning' || italyLevel === 'warning' ? 'warning' : franceLevel === 'stable' || italyLevel === 'stable' ? 'stable' : 'neutral'

  return {
    status,
    label: labels[status],
    score,
    availableCount,
    us,
    japan,
    europe,
    signals: {
      credit: { level: creditLevel },
      europe: { level: europeLevel },
    },
  }
}
