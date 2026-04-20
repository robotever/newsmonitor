<template>
  <div v-if="items.length" style="
    background:#040d14; border-bottom:1px solid #0e2030;
    display:flex; align-items:center; overflow:hidden; height:20px;
  ">
    <div style="
      flex-shrink:0; padding:0 8px; height:100%; display:flex; align-items:center;
      background:#c0392b; color:#fff; font-size:10px; font-weight:700; letter-spacing:0.5px;
    ">LIVE</div>
    <div style="flex:1; overflow:hidden; position:relative;">
      <div
        ref="tickerRef"
        style="display:flex; align-items:center; gap:24px; white-space:nowrap; will-change:transform;"
        :style="{ transform: `translateX(${offset}px)` }"
        @mouseenter="paused = true"
        @mouseleave="paused = false"
      >
        <template v-for="(item, i) in doubled" :key="i">
          <a :href="item.url" target="_blank" rel="noopener" style="
            font-size:11px; color:#7ab8e0; text-decoration:none;
            display:flex; align-items:center; gap:5px;
          ">
            <span :style="{ color: item.sourceColor, fontWeight: 600 }">{{ item.source }}</span>
            <span style="color:#4a8aaa;">{{ item.title }}</span>
          </a>
          <span style="color:#0e2a3a; font-size:10px;">●</span>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { TickerItem } from '@/types'

const props = defineProps<{ items: TickerItem[] }>()
const tickerRef = ref<HTMLElement | null>(null)
const offset = ref(0)
const paused = ref(false)
let raf: number

const doubled = computed(() => [...props.items, ...props.items])

function animate() {
  if (!paused.value && tickerRef.value) {
    offset.value -= 0.6
    const half = tickerRef.value.scrollWidth / 2
    if (Math.abs(offset.value) >= half) offset.value = 0
  }
  raf = requestAnimationFrame(animate)
}

onMounted(() => { raf = requestAnimationFrame(animate) })
onUnmounted(() => cancelAnimationFrame(raf))
</script>
