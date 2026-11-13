<template>
  <section class="market-industries" aria-labelledby="market-industry-title">
    <div class="market-section-heading">
      <h3 id="market-industry-title">行业全景 <span>{{ items.length }} INDUSTRIES</span></h3>
      <label class="market-sort">排序 <select v-model="sortBy" aria-label="行业排序"><option value="strength">强度 ↓</option><option value="heat">热度 ↓</option><option value="risk">风险 ↓</option></select></label>
    </div>
    <p class="market-legend"><span class="strength">强度：灰 → 蓝绿</span><span class="heat">热度：灰 → 黄</span><span class="risk">风险：绿 → 红</span><span>— / 虚线：缺失 · 灰紫实线：滞后</span></p>
    <div class="market-heatmap">
      <details v-for="item in sorted" :key="item.id" class="market-industry" :data-industry="item.id" :class="{ 'has-missing': item.evidenceInsufficient || item.freshness.stale }">
        <summary>
          <span class="market-industry__name">{{ item.name ?? item.id }}</span>
          <span class="market-industry__scores"><span v-for="axis in axes" :key="axis.key" class="market-heat-cell" :class="[axis.key, band(item[axis.key])]" :aria-label="`${axis.label} ${item[axis.key] ?? '暂无数据'}`"><small>{{ axis.short }}</small>{{ item[axis.key] ?? '—' }}</span></span>
          <span class="market-industry__quality">{{ item.completeness }}%<template v-if="item.evidenceInsufficient"> · 证据不足</template><span v-if="item.freshness.stale" class="market-badge is-stale">{{ item.freshness.label }}</span><span class="market-industry__expand" aria-hidden="true">＋</span></span>
        </summary>
        <MarketScoreCard :item="item" :title="item.name ?? item.id" :observed-at="observedAt" />
      </details>
    </div>
    <div class="market-rankings">
      <section v-for="ranking in rankingDefinitions" :key="ranking.key" class="market-ranking" :aria-label="ranking.title">
        <h4>{{ ranking.title }}</h4><p class="market-ranking__basis">{{ ranking.note }}</p>
        <ol><li v-for="(item, index) in rankings[ranking.key].slice(0, 5)" :key="item.id"><span class="market-ranking__position">{{ index + 1 }}</span><span class="market-ranking__name">{{ item.name ?? item.id }}<small v-if="ranking.key === 'improvement'">{{ item.improvementLabel }}</small></span><strong :class="ranking.key === 'improvement' ? 'strength' : ranking.key">{{ ranking.key === 'improvement' ? delta(item.improvementValue) : item[ranking.key] ?? '—' }}</strong></li></ol>
      </section>
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, ref } from 'vue'
import MarketScoreCard from './MarketScoreCard.vue'
import type { MarketScoreAxis, MarketScoreView, MarketIndustryRankings } from '@/features/market-dashboard/types'
const props = defineProps<{ items: MarketScoreView[]; rankings: MarketIndustryRankings; observedAt: string }>()
const sortBy = ref<MarketScoreAxis>('strength')
const sorted = computed(() => props.rankings[sortBy.value])
const axes: { key: MarketScoreAxis; label: string; short: string }[] = [{ key: 'strength', label: '强度', short: '强' }, { key: 'heat', label: '热度', short: '热' }, { key: 'risk', label: '风险', short: '险' }]
const rankingDefinitions = [
  { key: 'strength', title: '强度前五', note: '当前强度分排序' },
  { key: 'improvement', title: '低位改善前五', note: '按强度变化排序；不额外判断低位' },
  { key: 'heat', title: '过热拥挤前五', note: '当前热度分排序；不额外判定拥挤' },
  { key: 'risk', title: '风险恶化前五', note: '当前风险分排序；不代表风险增幅' },
] as const
function delta(value: number | null) { return value == null ? '—' : `${value > 0 ? '+' : ''}${value}` }
function band(value: number | null) { return value == null ? 'is-missing' : value < 30 ? 'is-low' : value < 70 ? 'is-medium' : 'is-high' }
</script>
