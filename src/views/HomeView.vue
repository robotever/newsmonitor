<template>
  <!-- 左侧内容区：右侧留出 40% 给固定定位的跑马灯 -->
  <div style="padding: 8px; padding-right: calc(40% + 6px);">
    <div style="display: flex; flex-wrap: wrap; gap: 6px;">
      <div
        v-for="source in NEWS_SOURCES"
        :key="source.id"
        style="flex: 0 0 calc(33.333% - 4px); min-width: 0;"
      >
        <NewsCard
          :source="source"
          :data="store.getNews(source.id)"
          @refresh="store.fetchSource(source.id)"
        />
      </div>
      <div style="flex: 0 0 100%; text-align:center; font-size:10px; color:#555; padding:4px 0;">
        NewsMonitor · 每5分钟自动刷新
      </div>
    </div>
  </div>

  <!-- 右侧跑马灯：固定在右边 40% 宽度 -->
  <div style="
    position: fixed;
    top: 62px;
    right: 8px;
    width: calc(40% - 16px);
    height: calc(100vh - 70px);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  ">
    <VerticalTicker />
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useNewsStore } from '@/stores/news'
import { NEWS_SOURCES } from '@/api/sources'
import NewsCard from '@/components/NewsCard.vue'
import VerticalTicker from '@/components/VerticalTicker.vue'

const store = useNewsStore()
onMounted(() => { store.fetchAll(); store.startAutoRefresh() })
</script>
