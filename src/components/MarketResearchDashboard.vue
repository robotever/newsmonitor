<template>
  <section class="market-dashboard fv-card" aria-labelledby="market-dashboard-title" :aria-busy="loading">
    <header class="market-dashboard__header">
      <div><div class="market-dashboard__eyebrow">MARKET RESEARCH / 全市场研究</div><h2 id="market-dashboard-title">市场研究雷达 <span>强度 · 热度 · 风险</span></h2></div>
      <button type="button" class="market-button" :disabled="loading" @click="refresh">{{ loading ? '加载中…' : '刷新研究数据' }}</button>
    </header>
    <div class="market-status" aria-live="polite">
      <template v-if="dashboard">
        <time :datetime="dashboard.observedAt">{{ formatDate(dashboard.observedAt) }} 北京时间</time>
        <span>{{ dashboard.session === 'close' ? '收盘确认' : '盘中快照' }}</span>
        <span :class="{ 'market-badge is-missing': dashboard.dataStatus.completeness < 70 }">完整度 {{ dashboard.dataStatus.completeness }}%<template v-if="dashboard.dataStatus.completeness < 70"> · 证据不足</template></span>
        <span class="market-badge" :class="{ 'is-missing': dashboard.freshness.stale }">{{ dashboard.freshness.label }}</span>
        <span class="market-status__version">{{ dashboard.schemaVersion }} / {{ dashboard.scoringVersion }}</span>
      </template>
      <span v-else>{{ loading ? '正在读取最新研究快照…' : '等待有效研究快照' }}</span>
    </div>
    <div v-if="latestError" class="market-notice market-dashboard__notice" role="status"><strong>{{ dashboard ? '刷新失败 · 保留本次会话最后成功快照' : latestError.code === 'NO_SNAPSHOT' ? '暂无研究快照' : '研究数据暂不可用' }}</strong><span>{{ latestError.message }}<template v-if="dashboard"> · 最后成功读取 {{ formatDate(lastSuccessAt) }}</template></span></div>
    <details v-if="dashboard?.dataStatus.missing.length" class="market-notice market-dashboard__missing"><summary>输入缺失 {{ dashboard.dataStatus.missing.length }} 项 · 展开查看</summary><p>{{ dashboard.dataStatus.missing.join('、') }}</p></details>
    <div class="market-dashboard__body">
      <div class="market-primary-grid">
        <MarketScoreCard title="全局环境" :item="dashboard?.global" :observed-at="dashboard?.observedAt" :loading="loading" :error="latestError?.message" />
        <MarketScoreCard title="A 股市场" :item="dashboard?.aShare" :observed-at="dashboard?.observedAt" :loading="loading" :error="latestError?.message" />
      </div>
      <template v-if="dashboard">
        <div class="market-history" aria-label="五日窗口强度历史">
          <div class="market-history__label">强度轨迹 <span>5日窗口 · {{ history?.snapshots.length ?? 0 }} 个观测</span></div>
          <p v-if="historyError" class="market-notice">历史数据暂不可用 · {{ historyError.message }}<template v-if="history"> · 图示保留上次成功历史</template></p>
          <div v-if="history" class="market-history__series"><figure v-for="series in historySeries" :key="series.key"><figcaption>{{ series.label }}</figcaption><div class="market-history__bars"><span v-for="(point, index) in history.snapshots" :key="index" :title="`${formatDate(point.observedAt)}：${point[series.key].strength ?? '—'}`" :class="{ 'is-missing': point[series.key].strength == null }" :style="{ height: `${point[series.key].strength ?? 0}%` }" /></div></figure></div>
          <p v-else-if="!historyError">{{ loading ? '历史加载中…' : '暂无历史轨迹' }}</p>
        </div>
        <MarketStyleGrid :items="dashboard.styles" :observed-at="dashboard.observedAt" />
        <IndustryHeatmap :items="dashboard.industries" :rankings="dashboard.rankings" :observed-at="dashboard.observedAt" />
      </template>
      <div v-else-if="!loading" class="market-empty"><h3>研究面板等待首次有效数据</h3><p>全局环境、A 股、六类风格与 35 个行业将在快照可用后显示。</p><button class="market-button" type="button" @click="refresh">重新读取</button></div>
    </div>
    <footer class="market-dashboard__footer"><span>统一评分 0–100 · 高强度不等于低风险</span><span>缺失项以 — 表示 · 研究参考，非买卖建议</span></footer>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import { loadMarketDashboard, loadMarketHistory } from '@/features/market-dashboard/api.mjs'
import { deriveMarketDashboardView } from '@/features/market-dashboard/model.mjs'
import type { MarketDashboardPayload, MarketHistoryPayload, MarketLoadError } from '@/features/market-dashboard/types'
import MarketScoreCard from './MarketScoreCard.vue'
import MarketStyleGrid from './MarketStyleGrid.vue'
import IndustryHeatmap from './IndustryHeatmap.vue'
const latest = shallowRef<MarketDashboardPayload | null>(null)
const history = shallowRef<MarketHistoryPayload | null>(null)
const latestError = ref<MarketLoadError | null>(null)
const historyError = ref<MarketLoadError | null>(null)
const lastSuccessAt = ref('')
const now = ref(new Date())
const loading = ref(true)
const dashboard = computed(() => latest.value ? deriveMarketDashboardView(latest.value, now.value) : undefined)
const historySeries = [{ key: 'global', label: '全球' }, { key: 'aShare', label: 'A 股' }] as const
let controller: AbortController | undefined
let freshnessTimer: ReturnType<typeof setInterval> | undefined
let refreshTimer: ReturnType<typeof setInterval> | undefined
let disposed = false
async function refresh() {
  if (controller) return
  controller = new AbortController()
  loading.value = true
  const options = { signal: controller.signal }
  // Keep the independent latest result responsive even if history times out.
  await Promise.all([
    loadMarketDashboard(undefined, options).then(result => {
      if (disposed) return
      latestError.value = result.error
      if (result.data) { latest.value = result.data; lastSuccessAt.value = new Date().toISOString() }
      now.value = new Date()
    }),
    loadMarketHistory('5d', undefined, options).then(result => {
      if (disposed) return
      historyError.value = result.error
      if (result.data) history.value = result.data
    }),
  ])
  controller = undefined
  if (!disposed) loading.value = false
}
function formatDate(value: string) {
  return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}
onMounted(() => {
  refresh()
  freshnessTimer = setInterval(() => { now.value = new Date() }, 60_000)
  refreshTimer = setInterval(refresh, 5 * 60_000)
})
onUnmounted(() => { disposed = true; controller?.abort(); clearInterval(freshnessTimer); clearInterval(refreshTimer) })
</script>
