<template>
  <main class="home-layout">
    <div class="home-content">
      <DebtRiskDashboard />
      <div class="news-grid">
      <div
        v-for="source in NEWS_SOURCES"
        :key="source.id"
        class="news-grid__item"
      >
        <NewsCard
          :source="source"
          :data="store.getNews(source.id)"
          @refresh="store.fetchSource(source.id)"
        />
      </div>
      <div class="news-grid__footer">
        NewsMonitor · 每5分钟自动刷新
      </div>
      </div>
    </div>

  <aside class="home-ticker">
    <VerticalTicker />
  </aside>
  </main>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useNewsStore } from '@/stores/news'
import { NEWS_SOURCES } from '@/api/sources'
import NewsCard from '@/components/NewsCard.vue'
import VerticalTicker from '@/components/VerticalTicker.vue'
import DebtRiskDashboard from '@/components/DebtRiskDashboard.vue'

const store = useNewsStore()
onMounted(() => { store.fetchAll(); store.startAutoRefresh() })
</script>
