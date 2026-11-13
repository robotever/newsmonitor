import { compactSnapshot, errorResponse, jsonResponse, SCHEMA_VERSION, SCORING_VERSION, timestamp } from '../../_lib/market-dashboard.js'

const WINDOWS = { '1d': 1, '5d': 5, '20d': 20, '90d': 90 }

export async function onRequestGet({ request, env }) {
  const windows = new URL(request.url).searchParams.getAll('window')
  const window = windows.length === 0 ? '5d' : windows[0]
  if (windows.length > 1 || !Object.hasOwn(WINDOWS, window)) return errorResponse('INVALID_WINDOW', 400)
  try {
    // Anchor to the last observation so offline collectors retain useful history.
    const latest = await env.MARKET_DB.prepare(`
      SELECT observed_at FROM market_dashboard_snapshots
      WHERE schema_version = ? AND scoring_version = ?
      ORDER BY observed_at DESC LIMIT 1
    `).bind(SCHEMA_VERSION, SCORING_VERSION).first()
    if (!latest) return errorResponse('NO_SNAPSHOT', 404)
    const anchor = timestamp(latest.observed_at)
    const lower = new Date(anchor.millis - WINDOWS[window] * 86400000).toISOString()
      .replace(/\.(\d{3})Z$/, `.$1${anchor.utc.slice(-4, -1)}Z`)
    const rows = await env.MARKET_DB.prepare(`
      SELECT observed_at, payload_json FROM market_dashboard_snapshots
      WHERE schema_version = ? AND scoring_version = ? AND observed_at >= ? AND observed_at <= ?
      ORDER BY observed_at ASC
    `).bind(SCHEMA_VERSION, SCORING_VERSION, lower, latest.observed_at).all()
    return jsonResponse({ window, snapshots: rows.results.map(compactSnapshot) }, 200, 'public, max-age=300, s-maxage=600')
  } catch { return errorResponse('STORAGE_UNAVAILABLE', 503) }
}
