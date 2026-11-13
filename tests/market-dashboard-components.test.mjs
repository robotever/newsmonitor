import test, { before, after } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import { createServer } from 'vite'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { deriveMarketDashboardView } from '../src/features/market-dashboard/model.mjs'

let server
before(async () => { server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false, watch: null }, appType: 'custom' }) })
after(async () => { await server?.close() })
async function render(name, props) {
  assert.ok(existsSync(new URL(`../src/components/${name}.vue`, import.meta.url)), `${name} must exist`)
  const module = await server.ssrLoadModule(`/src/components/${name}.vue`)
  return renderToString(createSSRApp({ render: () => h(module.default, props) }))
}
const observed = '2026-11-13T02:15:00Z'
const object = (id, fields = {}) => ({ id, name: id, strength: 63, heat: 78, risk: 24,
  completeness: 80, missing: [], contributors: [], sourceTimestamps: [{ source: 'Wind', timestamp: observed }],
  change1d: null, change5d: null, ...fields })
function view(fields = {}) {
  return deriveMarketDashboardView({ schemaVersion: 'market-dashboard-v1', scoringVersion: 'market-score-v0.1',
    observedAt: observed, marketDate: '2026-11-13', session: 'intraday', global: object('global'), aShare: object('a-share'),
    styles: [], industries: [], dataStatus: { completeness: 80, stale: false, missing: [] }, ...fields }, new Date(observed))
}
test('score card preserves null, missing evidence and stale/comparison disclosures', async () => {
  const item = view({ global: object('global', { strength: null, completeness: 49, missing: ['成交广度'],
    contributors: [{ label: '已提供因素', impact: -3, evidence: '已提供证据' }], comparisonFallback: 'close',
    change5d: { strength: null, heat: 0, risk: -2 } }), dataStatus: { completeness: 49, stale: true, missing: [] } }).global
  const html = await render('MarketScoreCard', { item, title: '全局环境', observedAt: observed })
  for (const text of ['—', '证据不足', '数据滞后', '成交广度', '已提供因素', '已提供证据', '收盘回退', '暂无可比快照']) assert.ok(html.includes(text), text)
  assert.match(html, /class="market-badge is-stale">数据滞后<\/span>/)
  assert.match(html, /class="market-badge is-missing">完整度 49%/)
  assert.ok(!html.includes('扩张'))
  assert.match(html, /<details/)
  assert.match(html, /datetime="2026-11-13T02:15:00Z"/)
})
test('score card renders loading and honest unavailable state without scores', async () => {
  assert.match(await render('MarketScoreCard', { loading: true, title: '全局环境' }), /加载/)
  const html = await render('MarketScoreCard', { title: '全局环境', error: '暂无有效快照' })
  assert.match(html, /暂无有效快照/)
  assert.ok(!html.includes('market-score__number'))
})
test('style grid uses six fixed design identities regardless of server array order', async () => {
  const ids = ['000300.SH', '000852.SH', 'H30356.CSI', '399006.SZ', '000922.CSI', '000688.SH']
  const items = view({ styles: ids.toReversed().map(id => object(id)) }).styles
  const html = await render('MarketStyleGrid', { items, observedAt: observed })
  const positions = ['大盘', '小盘', '价值', '成长', '红利', '科技'].map(label => html.indexOf(label))
  assert.ok(positions.every((position, i) => position >= 0 && (i === 0 || position > positions[i - 1])))
  assert.match(html, /5日/)
  assert.equal((html.match(/data-score-object=/g) ?? []).length, 6)
})
test('industry panorama renders all 35 accessible expansions and four truthful rankings', async () => {
  const dashboard = view({ industries: Array.from({ length: 35 }, (_, i) => object(`industry-${i}`, { name: `行业${i}`, change5d: null })), dataStatus: { completeness: 80, stale: true, missing: [] } })
  const html = await render('IndustryHeatmap', { items: dashboard.industries, rankings: dashboard.rankings, observedAt: observed })
  assert.equal((html.match(/data-industry=/g) ?? []).length, 35)
  for (const text of ['强度前五', '低位改善前五', '过热拥挤前五', '风险恶化前五', '暂无可比快照', '当前风险分排序', '不额外判断低位']) assert.ok(html.includes(text), text)
  assert.match(html.replace(/<!--[\s\S]*?-->/g, ''), /market-industry__quality">80%<span class="market-badge is-stale">数据滞后/)
  assert.match(html, /<select/)
  assert.equal((html.match(/<summary><span class="market-industry__name"/g) ?? []).length, 35)
})
