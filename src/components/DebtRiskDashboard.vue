<template>
  <section class="debt-dashboard fv-card" aria-labelledby="debt-dashboard-title">
    <div class="fv-card-header debt-dashboard__header">
      <div>
        <div class="fv-card-header-title">
          <span class="debt-dashboard__icon">债</span>
          <span id="debt-dashboard-title">全球债务风险</span>
          <span v-if="dashboard" class="debt-dashboard__status" :class="`is-${dashboard.status}`">
            {{ dashboard.label }}
          </span>
        </div>
        <p class="debt-dashboard__subtitle">利率 · 信用 · 跨境资金 · 主权利差</p>
      </div>
      <div class="debt-dashboard__actions">
        <span v-if="updatedAt">更新于 {{ formatTime(updatedAt) }}</span>
        <button type="button" :disabled="loading" @click="refresh">{{ loading ? '加载中' : '刷新' }}</button>
      </div>
    </div>

    <div v-if="loading && !dashboard" class="debt-dashboard__loading">
      <div v-for="index in 4" :key="index" class="fv-skeleton" />
    </div>

    <div v-else-if="dashboard" class="debt-dashboard__body">
      <div class="debt-dashboard__themes">
        <article class="debt-theme">
          <div class="debt-theme__heading"><span>US</span> 美国利率结构</div>
          <MetricRow label="2年期" :metric="dashboard.us.policy2y" unit="%" />
          <MetricRow label="10年期" :metric="dashboard.us.nominal10y" unit="%" />
          <MetricRow label="10年实际利率" :metric="dashboard.us.real10y" unit="%" emphasized />
          <MetricRow label="通胀补偿" :metric="dashboard.us.inflation10y" unit="%" />
          <p>实际利率抬升通常压制黄金和高估值成长资产。</p>
        </article>

        <article class="debt-theme">
          <div class="debt-theme__heading"><span>CR</span> 信用与久期压力</div>
          <MetricRow label="高收益债 OAS" :metric="dashboard.us.highYieldSpread" unit="%" emphasized />
          <MetricRow label="10年期限溢价" :metric="dashboard.us.termPremium" unit="%" />
          <div class="debt-theme__signal" :class="creditSignal.className">{{ creditSignal.text }}</div>
          <p>收益率下降但信用利差扩大，往往比单纯利率上升更值得警惕。</p>
        </article>

        <article class="debt-theme">
          <div class="debt-theme__heading"><span>JP</span> 日本资金回流</div>
          <MetricRow label="日本10年期" :metric="dashboard.japan.nominal10y" unit="%" frequency="月频" emphasized />
          <div class="debt-theme__signal is-neutral">观察日债上行 + 日元升值 + 全球股市走弱</div>
          <p>组合出现时，需防范套息交易平仓与全球久期重定价。</p>
        </article>

        <article class="debt-theme">
          <div class="debt-theme__heading"><span>EU</span> 欧洲主权信用</div>
          <MetricRow label="法德10年利差" :metric="dashboard.europe.franceGermanySpread" unit="bp" frequency="月频" emphasized />
          <MetricRow label="意德10年利差" :metric="dashboard.europe.italyGermanySpread" unit="bp" frequency="月频" />
          <div class="debt-theme__signal" :class="europeSignal.className">{{ europeSignal.text }}</div>
          <p>利差持续扩大后，继续观察银行信用与美元融资压力是否同步恶化。</p>
        </article>
      </div>

      <div class="debt-dashboard__footer">
        <span>数据：FRED；美国为日频，日欧长债为月频 OECD 序列</span>
        <span v-if="errorCount" class="debt-dashboard__partial">{{ errorCount }} 项暂不可用</span>
        <span>启发式研究参考 · 非交易信号</span>
      </div>
    </div>

    <div v-else class="debt-dashboard__error">
      <strong>债务数据暂时不可用</strong>
      <span>{{ firstError }}</span>
      <button type="button" @click="refresh">重试</button>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, onMounted, ref } from 'vue'
import { loadDebtSeries } from '@/features/debt-monitor/api.mjs'
import { deriveDebtDashboard } from '@/features/debt-monitor/model.mjs'
import type { DebtDashboardModel, DebtSummary } from '@/features/debt-monitor/types'

const loading = ref(false)
const dashboard = ref<DebtDashboardModel | null>(null)
const errors = ref<Record<string, string>>({})
const updatedAt = ref(0)

const errorCount = computed(() => Object.keys(errors.value).length)
const firstError = computed(() => Object.values(errors.value)[0] ?? '请稍后重试')
const creditSignal = computed(() => {
  const level = dashboard.value?.signals.credit.level ?? 'neutral'
  const text = { neutral: '信用数据待恢复', stable: '信用市场仍属常态区间', warning: '信用条件需要关注', alert: '信用压力明显扩大' }[level]
  return { text, className: `is-${level}` }
})
const europeSignal = computed(() => {
  const level = dashboard.value?.signals.europe.level ?? 'neutral'
  const text = { neutral: '主权利差数据待恢复', stable: '区域利差相对平稳', warning: '主权利差需要关注', alert: '主权风险进入警戒区' }[level]
  return { text, className: `is-${level}` }
})

async function refresh() {
  loading.value = true
  const result = await loadDebtSeries()
  errors.value = result.errors
  updatedAt.value = result.updatedAt
  dashboard.value = result.series && Object.values(result.series).some(points => points.length)
    ? deriveDebtDashboard(result.series)
    : null
  loading.value = false
}

function formatTime(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const MetricRow = defineComponent({
  props: {
    label: { type: String, required: true },
    metric: { type: Object as () => DebtSummary | null, default: null },
    unit: { type: String, default: '%' },
    frequency: { type: String, default: '日频' },
    emphasized: { type: Boolean, default: false },
  },
  setup(props) {
    return () => h('div', { class: ['debt-metric', props.emphasized && 'is-emphasized'] }, [
      h('span', { class: 'debt-metric__label' }, props.label),
      h('span', { class: ['debt-metric__frequency', props.metric?.stale && 'is-stale'] }, `${props.frequency}${props.metric?.stale ? '·滞后' : ''}`),
      h('strong', props.metric ? `${props.metric.value.toFixed(2)}${props.unit}` : '—'),
      h('span', { class: ['debt-metric__change', props.metric?.change == null || props.metric.change === 0 ? 'is-flat' : props.metric.change > 0 ? 'is-up' : 'is-down'] },
        props.metric?.change == null ? '' : `${props.metric.change > 0 ? '+' : ''}${props.metric.change.toFixed(2)}`),
      h('time', props.metric?.date ?? ''),
    ])
  },
})

onMounted(refresh)
</script>
