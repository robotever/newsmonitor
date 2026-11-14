<template>
  <section class="market-concepts" aria-labelledby="market-concept-title">
    <div class="market-section-heading market-concepts__heading">
      <div><h3 id="market-concept-title">概念雷达 <span>WIND CONCEPTS</span></h3><p>Wind 结构化行情统一评分 · 妙想仅用于候选发现</p></div>
      <time :datetime="selectedAt">名单更新 {{ formatDate(selectedAt) }}</time>
    </div>
    <div class="market-concepts__summary" aria-label="概念摘要">
      <span>最强 <strong>{{ leader('strength') }}</strong></span><span>最热 <strong>{{ leader('heat') }}</strong></span><span>高风险 <strong>{{ leader('risk') }}</strong></span>
    </div>
    <div class="market-concepts__tabs" role="tablist" aria-label="概念范围">
      <button id="concept-tab-dynamic" type="button" role="tab" :aria-selected="activeTab === 'dynamic'" aria-controls="concept-panel" @click="activeTab = 'dynamic'">动态热点 10</button>
      <button id="concept-tab-core" type="button" role="tab" :aria-selected="activeTab === 'core'" aria-controls="concept-panel" @click="activeTab = 'core'">核心概念 25</button>
    </div>
    <div id="concept-panel" role="tabpanel" :aria-labelledby="`concept-tab-${activeTab}`">
      <div class="market-concept-grid">
        <details v-for="item in activeItems" :key="item.id" class="market-concept" :data-concept="item.id" :class="{ 'has-missing': item.evidenceInsufficient || item.freshness.stale }">
          <summary><span class="market-concept__name">{{ item.name ?? item.id }}</span><span class="market-concept__scores"><b>强 {{ item.strength ?? '—' }}</b><b>热 {{ item.heat ?? '—' }}</b><b>险 {{ item.risk ?? '—' }}</b></span><span class="market-concept__meta"><template v-if="item.retainedTradingDays === 1">今日新入选 · </template>完整度 {{ item.completeness }}%<i v-if="item.freshness.stale" class="market-badge is-stale">{{ item.freshness.label }}</i></span></summary>
          <MarketScoreCard :item="item" :title="item.name ?? item.id" :observed-at="observedAt" />
        </details>
      </div>
      <div class="market-rankings market-concept-rankings">
        <section v-for="ranking in rankingDefinitions" :key="ranking.key" class="market-ranking" :aria-label="ranking.title">
          <h4>{{ ranking.title }}</h4><p class="market-ranking__basis">{{ ranking.note }}</p>
          <ol><li v-for="(item, index) in activeRankings[ranking.key].slice(0, 5)" :key="item.id"><span class="market-ranking__position">{{ index + 1 }}</span><span class="market-ranking__name">{{ item.name ?? item.id }}<small v-if="ranking.key === 'improvement'">{{ item.improvementLabel }}</small></span><strong :class="ranking.key === 'improvement' ? 'strength' : ranking.key">{{ ranking.key === 'improvement' ? delta(item.improvementValue) : item[ranking.key] ?? '—' }}</strong></li></ol>
        </section>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MarketScoreCard from './MarketScoreCard.vue'
import type { MarketConceptView, MarketIndustryRankings, MarketScoreAxis } from '@/features/market-dashboard/types'
const props = defineProps<{ core: MarketConceptView[]; dynamic: MarketConceptView[];
  rankings: { core: MarketIndustryRankings<MarketConceptView>; dynamic: MarketIndustryRankings<MarketConceptView> };
  selectedAt: string; observedAt: string; initialTab?: 'dynamic' | 'core' }>()
const activeTab = ref<'dynamic' | 'core'>(props.initialTab ?? 'dynamic')
const activeItems = computed(() => activeTab.value === 'dynamic' ? props.dynamic : props.core)
const activeRankings = computed(() => props.rankings[activeTab.value])
const rankingDefinitions = [
  { key: 'strength', title: '强度前五', note: '当前强度分排序' },
  { key: 'improvement', title: '改善前五', note: '按 5 日 / 1 日强度变化排序' },
  { key: 'heat', title: '热度前五', note: '当前热度分排序' },
  { key: 'risk', title: '风险前五', note: '当前风险分排序' },
] as const
function leader(axis: MarketScoreAxis) { return activeRankings.value[axis][0]?.name ?? activeRankings.value[axis][0]?.id ?? '—' }
function delta(value: number | null) { return value == null ? '—' : `${value > 0 ? '+' : ''}${value}` }
function formatDate(value: string) { return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }) }
</script>
