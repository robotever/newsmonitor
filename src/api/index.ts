import type { NewsData } from '@/types'
import {
  fetchHackerNews, fetchReddit, fetchGithub,
  fetchFtchinese, fetchInvesting,
  fetchBloomberg, fetchMarketwatch, fetchProducthunt,
  fetchWallstreetcn, fetchJin10, fetchCankaoxiaoxi, fetchMktnews, fetchGelonghui, fetch36kr,
  fetchThepaper, fetchEastmoney,
} from './fetchers/direct'
import { getMockItems } from './mock'
import { limitNewsItems } from './news-policy.mjs'

const FETCHERS: Record<string, () => Promise<any[]>> = {
  hackernews:   fetchHackerNews,
  reddit:       fetchReddit,
  github:       fetchGithub,
  thepaper:     fetchThepaper,
  eastmoney:    fetchEastmoney,
  ftchinese:    fetchFtchinese,
  investing:    fetchInvesting,
  bloomberg:    fetchBloomberg,
  marketwatch:  fetchMarketwatch,
  producthunt:  fetchProducthunt,
  wallstreetcn: fetchWallstreetcn,
  jin10:        fetchJin10,
  cankaoxiaoxi: fetchCankaoxiaoxi,
  mktnews:      fetchMktnews,
  gelonghui:    fetchGelonghui,
  _36kr:        fetch36kr,
}

const DEMO_SOURCES = new Set<string>([])

export async function loadNewsSource(sourceId: string): Promise<NewsData> {
  if (DEMO_SOURCES.has(sourceId)) {
    return { source: sourceId, items: limitNewsItems(getMockItems(sourceId)), updatedAt: Date.now(), loading: false }
  }
  const fetcher = FETCHERS[sourceId]
  if (!fetcher) {
    return { source: sourceId, items: limitNewsItems(getMockItems(sourceId)), updatedAt: Date.now(), loading: false }
  }
  try {
    const items = await fetcher()
    return { source: sourceId, items: limitNewsItems(items), updatedAt: Date.now(), loading: false }
  } catch (err) {
    const msg = err instanceof Error ? err.message : '加载失败'
    console.error(`[${sourceId}]`, msg)
    return { source: sourceId, items: [], updatedAt: Date.now(), loading: false, error: msg }
  }
}
