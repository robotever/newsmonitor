<template>
  <article class="market-score-card" :class="{ 'is-compact': compact }" :data-score-object="item?.id" :aria-label="title">
    <header class="market-score-card__header">
      <h3>{{ title }}</h3>
      <span v-if="item && !compact" class="market-badge" :class="{ 'is-missing': !item.stage }">{{ item.stageLabel }}</span>
    </header>
    <div v-if="loading && !item" class="market-score-card__loading" role="status" aria-label="评分加载中">
      <div v-for="index in 3" :key="index" class="fv-skeleton" />
      <span>加载评分中…</span>
    </div>
    <template v-else-if="item">
      <div class="market-score-axes">
        <div v-for="axis in axes" :key="axis.key" class="market-score" :class="[axis.key, band(item[axis.key])]">
          <div class="market-score__label">{{ axis.label }}</div>
          <strong class="market-score__number">{{ item[axis.key] ?? '—' }}</strong>
          <span class="market-score__band">{{ item.scoreLabels[axis.key] }}</span>
          <div class="market-score__track" aria-hidden="true"><i :style="{ width: `${item[axis.key] ?? 0}%` }" /></div>
        </div>
      </div>
      <div v-if="!compact" class="market-changes" aria-label="分数变化">
        <div class="market-changes__head"><span>变化 / 分</span><span>强度</span><span>热度</span><span>风险</span></div>
        <div v-for="comparison in comparisons" :key="comparison.key">
          <span>{{ comparison.label }}</span><span v-for="axis in axes" :key="axis.key">{{ delta(item[comparison.key]?.[axis.key]) }}</span>
        </div>
      </div>
      <p v-else class="market-style-direction">5日强度 <strong>{{ delta(item.change5d?.strength) }}</strong></p>
      <div class="market-score-card__quality">
        <span :class="{ 'market-badge is-missing': item.evidenceInsufficient }">完整度 {{ item.completeness }}%<template v-if="item.evidenceInsufficient"> · 证据不足</template></span>
        <span v-if="item.freshness.stale" class="market-badge is-stale">{{ item.freshness.label }}</span>
      </div>
      <p v-if="!compact" class="market-object-time">{{ frequencyLabel }} · <time :datetime="item.observedAt ?? observedAt">{{ formatDate(item.observedAt ?? observedAt) }}</time></p>
      <details class="market-evidence">
        <summary>{{ compact ? '证据与口径' : '贡献因素与数据口径' }}<span aria-hidden="true"> ＋</span></summary>
        <div class="market-evidence__body">
          <p v-if="error" class="market-notice">{{ error }}</p>
          <ul v-if="item.contributors.length" class="market-contributors">
            <li v-for="(factor, index) in item.contributors.slice(0, 3)" :key="index"><span>{{ factor.label }} <b>{{ delta(factor.impact) }}</b></span><p v-if="factor.evidence">{{ factor.evidence }}</p></li>
          </ul>
          <p v-else>暂无贡献因素</p>
          <p v-if="item.missing.length" class="market-notice">缺失：{{ item.missing.join('、') }}</p>
          <p v-if="compact">{{ frequencyLabel }} · <time :datetime="item.observedAt ?? observedAt">{{ formatDate(item.observedAt ?? observedAt) }}</time></p>
          <p v-for="comparison in comparisons" :key="comparison.key">{{ comparison.label }}：{{ item.comparisonBadges[comparison.key] }}</p>
          <p>最旧来源：{{ formatDate(item.freshness.oldestSourceAt) }}</p>
          <ul class="market-sources"><li v-for="(source, index) in item.sourceTimestamps" :key="index">{{ source.source }} · <time :datetime="source.timestamp">{{ formatDate(source.timestamp) }}</time></li></ul>
        </div>
      </details>
      <p v-if="!compact" class="market-comparison-note">上次：{{ item.comparisonBadges.change1d }} · 5日：{{ item.comparisonBadges.change5d }}</p>
    </template>
    <p v-else class="market-score-card__unavailable">{{ error ?? '暂无有效评分' }}</p>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MarketScoreAxis, MarketScoreView } from '@/features/market-dashboard/types'
const props = defineProps<{ item?: MarketScoreView; title: string; observedAt?: string; compact?: boolean; loading?: boolean; error?: string }>()
const axes: { key: MarketScoreAxis; label: string }[] = [{ key: 'strength', label: '强度' }, { key: 'heat', label: '热度' }, { key: 'risk', label: '风险' }]
const comparisons = [{ key: 'change1d', label: '上次 / 1日' }, { key: 'change5d', label: '5日' }] as const
const frequencyLabel = computed(() => ({ intraday: '盘中', daily: '日频', monthly: '月频' })[props.item?.frequency ?? 'intraday'])
function delta(value?: number | null) { return value == null ? '—' : `${value > 0 ? '+' : ''}${value}` }
function band(value: number | null) { return value == null ? 'is-missing' : value < 30 ? 'is-low' : value < 70 ? 'is-medium' : 'is-high' }
function formatDate(value?: string | null) {
  return value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) : '—'
}
</script>
