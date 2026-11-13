import { authorized, errorResponse, jsonResponse, readBoundedJson, validatePayload } from '../../_lib/market-dashboard.js'

export async function onRequestPost({ request, env }) {
  const token = env.MARKET_DASHBOARD_PUBLISH_TOKEN
  if (typeof token !== 'string' || token.length === 0) return errorResponse('SERVICE_UNAVAILABLE', 503)
  try {
    if (!await authorized(request, token)) return errorResponse('UNAUTHORIZED', 401)
  } catch { return errorResponse('SERVICE_UNAVAILABLE', 503) }
  let payload, observed
  try { payload = await readBoundedJson(request) }
  catch (error) {
    const code = error.message === 'PAYLOAD_TOO_LARGE' ? 'PAYLOAD_TOO_LARGE' : 'INVALID_JSON'
    return errorResponse(code, code === 'PAYLOAD_TOO_LARGE' ? 413 : 400)
  }
  try {
    observed = validatePayload(payload)
    const futureLimit = Date.now() + 5 * 60000
    const subMillisecond = Number(observed.utc.slice(-4, -1))
    if (observed.millis > futureLimit || observed.millis === futureLimit && subMillisecond > 0) {
      return errorResponse('INVALID_PAYLOAD', 400)
    }
  } catch { return errorResponse('INVALID_PAYLOAD', 400) }
  try {
    const result = await env.MARKET_DB.prepare(`
      INSERT INTO market_dashboard_snapshots
        (observed_at, market_date, session, schema_version, scoring_version, completeness, payload_json, created_at)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(observed_at, scoring_version) DO NOTHING
    `).bind(observed.utc, payload.marketDate, payload.session, payload.schemaVersion,
      payload.scoringVersion, payload.dataStatus.completeness, JSON.stringify(payload), new Date().toISOString()).run()
    const duplicate = result.meta.changes === 0
    return jsonResponse({ ok: true, duplicate, observedAt: payload.observedAt }, duplicate ? 200 : 201)
  } catch { return errorResponse('STORAGE_UNAVAILABLE', 503) }
}
