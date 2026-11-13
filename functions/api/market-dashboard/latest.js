import { errorResponse, jsonResponse, SCHEMA_VERSION, SCORING_VERSION, storedPayload } from '../../_lib/market-dashboard.js'

export async function onRequestGet({ env }) {
  try {
    const row = await env.MARKET_DB.prepare(`
      SELECT payload_json FROM market_dashboard_snapshots
      WHERE schema_version = ? AND scoring_version = ?
      ORDER BY observed_at DESC LIMIT 1
    `).bind(SCHEMA_VERSION, SCORING_VERSION).first()
    if (!row) return errorResponse('NO_SNAPSHOT', 404)
    return jsonResponse(storedPayload(row), 200, 'public, max-age=30, s-maxage=60')
  } catch { return errorResponse('STORAGE_UNAVAILABLE', 503) }
}
