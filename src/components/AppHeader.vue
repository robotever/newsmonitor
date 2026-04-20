<template>
  <header style="background: linear-gradient(180deg, #0b1e2f 0%, #071525 100%); border-bottom: 1px solid #162635;">
    <div style="max-width:1920px; margin:0 auto; padding:0 8px; height:32px; display:flex; align-items:center; justify-content:space-between;">

      <!-- Logo -->
      <div style="display:flex; align-items:center; gap:8px;">
        <span style="
          color:#00c8ff; font-size:15px; font-weight:700; letter-spacing:2px;
          text-shadow: 0 0 12px rgba(0, 200, 255, 0.6);
          font-family:'Inter', sans-serif;
        ">NEWS</span>
        <span style="
          color:#4a9eda; font-size:15px; font-weight:400; letter-spacing:2px;
          font-family:'Inter', sans-serif;
        ">MONITOR</span>
        <span style="color:#1e4a6a; font-size:10px; margin-left:4px; letter-spacing:0.05em;">实时热榜聚合</span>
      </div>

      <!-- 右侧操作 -->
      <div style="display:flex; align-items:center; gap:6px;">
        <span style="color:#2a6a9a; font-size:10px; font-family:'Inter', monospace;">
          {{ lastUpdate ? '更新于 ' + lastUpdate : '' }}
        </span>
        <button @click="store.fetchAll()" style="
          background:#0a1e30; border:1px solid #1a3a55; color:#4a9eda;
          font-family:inherit; font-size:11px; padding:2px 10px; cursor:pointer;
          transition: border-color 0.15s, color 0.15s;
        " title="刷新全部"
          @mouseenter="e => { e.target.style.borderColor='#00c8ff'; e.target.style.color='#00c8ff'; }"
          @mouseleave="e => { e.target.style.borderColor='#1a3a55'; e.target.style.color='#4a9eda'; }"
        >
          刷新
        </button>
        <button @click="store.toggleDark()" style="
          background:#0a1e30; border:1px solid #1a3a55; color:#4a9eda;
          font-family:inherit; font-size:11px; padding:2px 8px; cursor:pointer;
        ">
          {{ store.darkMode ? '☀' : '☾' }}
        </button>
      </div>
    </div>
  </header>

  <!-- 滚动快讯 -->
  <NewsTicker :items="store.tickerItems" />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useNewsStore } from '@/stores/news'
import NewsTicker from '@/components/NewsTicker.vue'

const store = useNewsStore()
const lastUpdate = computed(() => {
  const times = [...store.newsData.values()].map(d => d.updatedAt).filter(Boolean)
  if (!times.length) return ''
  const t = new Date(Math.max(...times))
  return t.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
})
</script>
