import type { NewsData } from '@/types'
import {
  fetchHackerNews, fetchReddit, fetchGithub,
  fetchCailian, fetchFtchinese, fetchInvesting,
  fetchBloomberg, fetchMarketwatch, fetchYahoo, fetchProducthunt,
  fetchWallstreetcn, fetchJin10, fetchCankaoxiaoxi, fetchMktnews, fetchGelonghui, fetch36kr,
  fetchThepaper, fetchEastmoney,
} from './fetchers/direct'
import { getMockItems } from './mock'

const FETCHERS: Record<string, () => Promise<any[]>> = {
  hackernews:   fetchHackerNews,
  reddit:       fetchReddit,
  github:       fetchGithub,
  cailian:      fetchCailian,
  thepaper:     fetchThepaper,
  eastmoney:    fetchEastmoney,
  ftchinese:    fetchFtchinese,
  investing:    fetchInvesting,
  bloomberg:    fetchBloomberg,
  marketwatch:  fetchMarketwatch,
  yahoo:        fetchYahoo,
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
    return { source: sourceId, items: getMockItems(sourceId), updatedAt: Date.now(), loading: false }
  }
  const fetcher = FETCHERS[sourceId]
  if (!fetcher) {
    return { source: sourceId, items: getMockItems(sourceId), updatedAt: Date.now(), loading: false }
  }
  try {
    const items = await fetcher()
    return { source: sourceId, items: items.slice(0, 30), updatedAt: Date.now(), loading: false }
  } catch (err) {
    const msg = err instanceof Error ? err.message : '加载失败'
    console.error(`[${sourceId}]`, msg)
    return { source: sourceId, items: [], updatedAt: Date.now(), loading: false, error: msg }
  }
}
