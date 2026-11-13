<template>
  <section class="market-styles" aria-labelledby="market-styles-title">
    <div class="market-section-heading"><h3 id="market-styles-title">风格状态 <span>06 STYLES</span></h3><span>五日方向 = 强度变化 / 分</span></div>
    <div class="market-style-grid">
      <MarketScoreCard v-for="style in fixedStyles" :key="style.id" :title="style.label" :item="items.find(item => item.id === style.id)" :observed-at="observedAt" compact />
    </div>
  </section>
</template>
<script setup lang="ts">
import MarketScoreCard from './MarketScoreCard.vue'
import type { MarketScoreView } from '@/features/market-dashboard/types'
defineProps<{ items: MarketScoreView[]; observedAt: string }>()
const fixedStyles = [
  { id: '000300.SH', label: '大盘' }, { id: '000852.SH', label: '小盘' },
  { id: 'H30356.CSI', label: '价值' }, { id: '399006.SZ', label: '成长' },
  { id: '000922.CSI', label: '红利' }, { id: '000688.SH', label: '科技' },
]
</script>
