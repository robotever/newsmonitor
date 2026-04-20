<template>
  <div class="fv-card" style="display:flex; flex-direction:column; height:100%;">
    <!-- 头部 -->
    <div class="fv-card-header">
      <div class="fv-card-header-title">
        <span style="
          display:inline-flex; align-items:center; justify-content:center;
          width:16px; height:16px; border-radius:2px;
          background:#c0392b; color:#fff; font-size:9px; font-weight:700;
        ">▶</span>
        实时快讯滚动
      </div>
      <span style="font-size:10px; color:#555;">{{ items.length }} 条</span>
    </div>

    <!-- 滚动区域 -->
    <div
      ref="containerRef"
      style="flex:1; overflow:hidden; position:relative;"
      @mouseenter="paused = true"
      @mouseleave="paused = false"
    >
      <div ref="trackRef" style="will-change:transform;" :style="{ transform: `translateY(${offset}px)` }">
        <a
          v-for="(item, i) in doubled"
          :key="i"
          :href="item.url === '#' ? undefined : item.url"
          :target="item.url === '#' ? undefined : '_blank'"
          rel="noopener"
          class="fv-row"
          style="text-decoration:none; align-items:center;"
        >
          <!-- 来源标签 -->
          <span style="
            flex-shrink:0; font-size:9px; font-weight:700; padding:0 3px;
            border-radius:2px; color:#fff; white-space:nowrap; line-height:16px;
          " :style="{ background: item.sourceColor }">{{ item.source }}</span>

          <!-- 标题 -->
          <span class="fv-row-title" style="color:#b0c8e0;">{{ item.title }}</span>

          <!-- 时间 -->
          <span v-if="item.info" class="fv-row-meta">{{ item.info }}</span>
        </a>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useNewsStore } from '@/stores/news'
import { NEWS_SOURCES } from '@/api/sources'

const store = useNewsStore()
const containerRef = ref<HTMLElement | null>(null)
const trackRef = ref<HTMLElement | null>(null)
const offset = ref(0)
const paused = ref(false)
let raf: number

// 把所有来源的新闻拍平成一个列表
const items = computed(() => {
  const result: { source: string; sourceColor: string; title: string; url: string; info?: string }[] = []
  for (const src of NEWS_SOURCES) {
    const data = store.getNews(src.id)
    for (const item of data.items) {
      if (item.title && item.url !== '#') {
        result.push({
          source: src.name,
          sourceColor: src.color,
          title: item.title,
          url: item.url,
          info: item.extra?.info,
        })
      }
    }
  }
  return result
})

const doubled = computed(() => [...items.value, ...items.value])

function animate() {
  if (!paused.value && containerRef.value && trackRef.value) {
    offset.value -= 0.5
    const half = trackRef.value.scrollHeight / 2
    if (Math.abs(offset.value) >= half) offset.value = 0
  }
  raf = requestAnimationFrame(animate)
}

// 有新数据进来时重置位置
watch(() => items.value.length, () => { offset.value = 0 })

onMounted(() => { raf = requestAnimationFrame(animate) })
onUnmounted(() => cancelAnimationFrame(raf))
</script>
