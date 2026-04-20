import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { NEWS_SOURCES } from '@/api/sources'
import { loadNewsSource } from '@/api'
import type { NewsData, TickerItem } from '@/types'

export const useNewsStore = defineStore('news', () => {
  const newsData = ref<Map<string, NewsData>>(new Map())
  const darkMode = ref(window.matchMedia('(prefers-color-scheme: dark)').matches)
  const refreshInterval = ref<ReturnType<typeof setInterval> | null>(null)

  const tickerItems = computed<TickerItem[]>(() => {
    const items: TickerItem[] = []
    for (const source of NEWS_SOURCES) {
      const data = newsData.value.get(source.id)
      if (data?.items.length && data.items[0].url !== '#') {
        items.push({
          title: data.items[0].title,
          url: data.items[0].url,
          source: source.name,
          sourceColor: source.color,
        })
      }
    }
    return items
  })

  function getNews(sourceId: string): NewsData {
    return newsData.value.get(sourceId) ?? {
      source: sourceId, items: [], updatedAt: 0, loading: true,
    }
  }

  async function fetchSource(sourceId: string) {
    newsData.value.set(sourceId, { ...getNews(sourceId), loading: true })
    const result = await loadNewsSource(sourceId)
    newsData.value.set(sourceId, result)
  }

  async function fetchAll() {
    await Promise.allSettled(NEWS_SOURCES.map(s => fetchSource(s.id)))
  }

  function toggleDark() {
    darkMode.value = !darkMode.value
    document.documentElement.classList.toggle('dark', darkMode.value)
  }

  function startAutoRefresh(ms = 5 * 60 * 1000) {
    if (refreshInterval.value) clearInterval(refreshInterval.value)
    refreshInterval.value = setInterval(fetchAll, ms)
  }

  return { newsData, darkMode, getNews, fetchSource, fetchAll, toggleDark, startAutoRefresh, tickerItems }
})
