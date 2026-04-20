import type { NewsItem } from '@/types'

export const RSSHUB_ROUTES: Record<string, string> = {
  weibo:       '/weibo/search/hot',
  zhihu:       '/zhihu/hotlist',
  baidu:       '/baidu/hot',
  bilibili:    '/bilibili/ranking/0',
  douyin:      '/douyin/hot',
  toutiao:     '/toutiao/hot',
  sspai:       '/sspai/rank/latest',
  '36kr':      '/36kr/hot-list',
  hackernews:  '/hackernews/best',
  v2ex:        '/v2ex/topics/hot',
  github:      '/github/trending/daily/any/zh',
  producthunt: '/producthunt/today',
  reddit:      '/reddit/top',
  xueqiu:      '/xueqiu/hot_stock_comments',
  eastmoney:   '/eastmoney/hot',
  twitter:     '/twitter/trends',
}

function getText(el: Element, tag: string): string {
  return el.getElementsByTagName(tag)[0]?.textContent?.trim() ?? ''
}

export async function fetchRSSHub(sourceId: string): Promise<NewsItem[]> {
  const path = RSSHUB_ROUTES[sourceId]
  if (!path) throw new Error('no route')

  const res = await fetch(`/rsshub${path}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)

  const text = await res.text()
  const xml = new DOMParser().parseFromString(text, 'application/xml')

  if (xml.querySelector('parsererror')) {
    throw new Error('RSS 格式解析失败')
  }

  const items = Array.from(xml.getElementsByTagName('item'))
  if (items.length === 0) throw new Error('返回数据为空')

  return items.map((el, i) => ({
    id: getText(el, 'guid') || `${sourceId}-${i}`,
    title: getText(el, 'title'),
    url: getText(el, 'link') || '#',
  })).filter(item => item.title)
}
