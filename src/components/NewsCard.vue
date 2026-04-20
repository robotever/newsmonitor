<template>
  <div class="fv-card">
    <!-- 卡片头 -->
    <div class="fv-card-header">
      <div class="fv-card-header-title">
        <span :style="{
          display:'inline-flex', alignItems:'center', justifyContent:'center',
          width:'16px', height:'16px', borderRadius:'2px',
          background: source.color, color:'#fff', fontSize:'9px', fontWeight:700,
          flexShrink:0,
        }">{{ source.icon }}</span>
        <span>{{ source.name }}</span>
        <span v-if="isMock" style="color:#999; font-weight:400; font-size:10px;">演示</span>
      </div>
      <div style="display:flex; align-items:center; gap:6px;">
        <span v-if="data.updatedAt && !data.loading" style="font-size:10px; color:#667;">
          {{ timeAgo(data.updatedAt) }}
        </span>
        <button @click="$emit('refresh')" style="
          background:none; border:none; cursor:pointer; color:#667; font-size:11px; padding:0 2px;
          line-height:1;
        " :style="data.loading ? 'opacity:0.5' : ''" :disabled="data.loading">↻</button>
      </div>
    </div>

    <!-- 加载骨架 -->
    <div v-if="data.loading && !data.items.length" style="padding:6px 8px; display:flex; flex-direction:column; gap:5px;">
      <div v-for="i in 12" :key="i" class="fv-skeleton" :style="{ width: (50 + (i * 17 % 45)) + '%' }" />
    </div>

    <!-- 错误 -->
    <div v-else-if="data.error && !data.items.length"
      style="padding:8px; font-size:11px; color:#c0392b; display:flex; flex-direction:column; gap:4px; align-items:flex-start;">
      <span>{{ data.error }}</span>
      <button @click="$emit('refresh')" style="
        font-size:10px; color:#0052a3; background:none; border:none; cursor:pointer; padding:0;
      ">重试</button>
    </div>

    <!-- 新闻列表 -->
    <div v-else style="overflow-y:auto; max-height:360px;">
      <a
        v-for="(item, idx) in data.items"
        :key="item.id"
        :href="item.url === '#' ? undefined : item.url"
        :target="item.url === '#' ? undefined : '_blank'"
        rel="noopener"
        class="fv-row"
        style="text-decoration:none;"
      >
        <span class="fv-row-num" :class="{ hot: idx < 3 }">{{ idx + 1 }}</span>
        <span class="fv-row-title">{{ item.title }}</span>
        <span v-if="item.extra?.info" class="fv-row-meta">{{ item.extra.info }}</span>
      </a>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NewsSource, NewsData } from '@/types'

const props = defineProps<{ source: NewsSource; data: NewsData }>()
defineEmits<{ refresh: [] }>()

const isMock = computed(() => props.data.items.length > 0 && props.data.items[0].url === '#')

function timeAgo(ts: number): string {
  const m = Math.floor((Date.now() - ts) / 60000)
  if (m < 1) return '刚刚'
  if (m < 60) return `${m}分钟前`
  return `${Math.floor(m / 60)}小时前`
}
</script>
