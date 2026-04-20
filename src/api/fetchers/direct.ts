import type { NewsItem } from '@/types'

// ── RSS / Atom 解析（兼容两种格式）────────────────────────

function parseRSSOrAtom(text: string): NewsItem[] {
  const xml = new DOMParser().parseFromString(text, 'application/xml')
  if (xml.querySelector('parsererror')) throw new Error('RSS解析失败')

  // RSS 2.0
  const items = Array.from(xml.getElementsByTagName('item'))
  if (items.length > 0) {
    return items.map((el, i) => ({
      id: el.getElementsByTagName('guid')[0]?.textContent?.trim() ?? String(i),
      title: el.getElementsByTagName('title')[0]?.textContent?.trim() ?? '',
      url: el.getElementsByTagName('link')[0]?.textContent?.trim() ?? '#',
    })).filter(n => n.title)
  }

  // Atom
  const entries = Array.from(xml.getElementsByTagName('entry'))
  return entries.map((el, i) => {
    const linkEl = el.querySelector('link[rel="alternate"]') ?? el.querySelector('link')
    return {
      id: el.getElementsByTagName('id')[0]?.textContent?.trim() ?? String(i),
      title: el.getElementsByTagName('title')[0]?.textContent?.trim() ?? '',
      url: linkEl?.getAttribute('href') ?? linkEl?.textContent?.trim() ?? '#',
    }
  }).filter(n => n.title)
}

async function fetchFeed(path: string): Promise<NewsItem[]> {
  const res = await fetch(path)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return parseRSSOrAtom(await res.text())
}

// ── 直连 API ──────────────────────────────────────────────

export async function fetchHackerNews(): Promise<NewsItem[]> {
  const ids: number[] = await fetch('https://hacker-news.firebaseio.com/v0/topstories.json').then(r => r.json())
  const stories = await Promise.all(
    ids.slice(0, 20).map(id => fetch(`https://hacker-news.firebaseio.com/v0/item/${id}.json`).then(r => r.json()))
  )
  return stories.filter(s => s?.title).map(s => ({
    id: String(s.id),
    title: s.title,
    url: s.url || `https://news.ycombinator.com/item?id=${s.id}`,
    extra: { info: s.score ? `${s.score}分` : undefined },
  }))
}

export async function fetchReddit(): Promise<NewsItem[]> {
  const res = await fetch('https://www.reddit.com/top.json?limit=25&t=day', { headers: { Accept: 'application/json' } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  return json.data.children.map((c: any) => ({
    id: c.data.id, title: c.data.title, url: c.data.url,
    extra: { info: `${c.data.score}分` },
  }))
}

export async function fetchGithub(): Promise<NewsItem[]> {
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10)
  const res = await fetch(
    `https://api.github.com/search/repositories?q=created:>${yesterday}&sort=stars&order=desc&per_page=25`,
    { headers: { Accept: 'application/vnd.github+json' } }
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  return (json.items ?? []).map((r: any) => ({
    id: String(r.id),
    title: `${r.full_name} — ${r.description ?? ''}`.trim(),
    url: r.html_url,
    extra: { info: `★${r.stargazers_count}` },
  }))
}

// ── 代理 JSON API ─────────────────────────────────────────

export const fetchV2ex = () =>
  fetch('/proxy-v2ex/api/topics/hot.json')
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
    .then((json: any[]) => json.map(t => ({
      id: String(t.id), title: t.title,
      url: `https://www.v2ex.com/t/${t.id}`,
      extra: { info: `${t.replies}回复` },
    })))

// 财联社热门
export async function fetchClsHot(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-cailian/v2/article/hot/list', { headers: { Referer: 'https://www.cls.cn' } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  const list: any[] = json?.data ?? []
  return list.map((k: any) => ({
    id: String(k.id),
    title: k.title || k.brief || '',
    url: `https://www.cls.cn/detail/${k.id}`,
    mobileUrl: k.shareurl,
  })).filter((i: NewsItem) => i.title)
}

// 财联社深度
export async function fetchClsDepth(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-cailian/v3/depth/home/assembled/1000', { headers: { Referer: 'https://www.cls.cn' } })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  const list: any[] = json?.data?.depth_list ?? []
  return list
    .sort((a: any, b: any) => b.ctime - a.ctime)
    .map((k: any) => ({
      id: String(k.id),
      title: k.title || k.brief || '',
      url: `https://www.cls.cn/detail/${k.id}`,
      mobileUrl: k.shareurl,
      extra: {
        info: k.ctime
          ? new Date(k.ctime * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          : undefined,
      },
    })).filter((i: NewsItem) => i.title)
}

// 财联社 — 正确参数来自 Python 脚本
export async function fetchCailian(): Promise<NewsItem[]> {
  const res = await fetch(
    '/proxy-cailian/nodeapi/telegraphList?app=CailianpressWeb&refresh_type=1&rn=50&sv=8.4.6',
    { headers: { Referer: 'https://www.cls.cn/telegraph' } }
  )
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  const list: any[] = json?.data?.roll_data ?? []
  if (list.length === 0) throw new Error('返回数据为空')
  return list.map((item: any, i: number) => {
    const text = (item.title || item.content || '').replace(/<[^>]*>/g, '').trim()
    return {
      id: String(item.id ?? i),
      title: text.slice(0, 100),
      url: `https://www.cls.cn/detail/${item.id}`,
      extra: {
        info: item.ctime
          ? new Date(item.ctime * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
          : undefined,
      },
    }
  }).filter(i => i.title)
}

// ── 代理 RSS / Atom ───────────────────────────────────────

// FT中文网
export const fetchFtchinese  = () => fetchFeed('/proxy-ftchinese/rss/news')
// Investing.com 中文
export const fetchInvesting  = () => fetchFeed('/proxy-investing/rss/news_25.rss')
// 国际财经
export const fetchBloomberg  = () => fetchFeed('/proxy-bloomberg/markets/news.rss')
export const fetchMarketwatch= () => fetchFeed('/proxy-marketwatch/marketwatch/topstories/')
export const fetchYahoo      = () => fetchFeed('/proxy-yahoo/news/rssindex')
export const fetchProducthunt= () => fetchFeed('/proxy-producthunt/feed')

// ── 新增财经源 ────────────────────────────────────────────

// 华尔街见闻 — 实时快讯
export async function fetchWallstreetcn(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-wallstreetcn/apiv1/content/lives?channel=global-channel&limit=30')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  return (json.data?.items ?? []).map((k: any) => ({
    id: String(k.id),
    title: k.title || k.content_text || '',
    url: k.uri || `https://wallstreetcn.com/articles/${k.id}`,
    extra: {
      info: k.display_time
        ? new Date(k.display_time * 1000).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
        : undefined,
    },
  })).filter((i: NewsItem) => i.title)
}

// 金十数据 — 财经快讯
export async function fetchJin10(): Promise<NewsItem[]> {
  const res = await fetch(`/proxy-jin10/flash_newest.js?t=${Date.now()}`)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const rawData = await res.text()
  const jsonStr = rawData.replace(/^var\s+newest\s*=\s*/, '').replace(/;*$/, '').trim()
  const data: any[] = JSON.parse(jsonStr)
  return data
    .filter(k => (k.data.title || k.data.content) && !k.channel?.includes(5))
    .map(k => {
      const text = (k.data.title || k.data.content).replace(/<\/?b>/g, '')
      const [, title, desc] = text.match(/^【([^】]*)】(.*)$/) ?? []
      return {
        id: String(k.id),
        title: title ?? text,
        url: `https://flash.jin10.com/detail/${k.id}`,
        extra: {
          info: k.important ? '重要' : undefined,
          hover: desc,
        },
      }
    })
}

// 参考消息 — 国际时事
export async function fetchCankaoxiaoxi(): Promise<NewsItem[]> {
  const channels = ['zhongguo', 'guandian', 'gj']
  const results = await Promise.all(
    channels.map(k =>
      fetch(`/proxy-cankaoxiaoxi/json/channel/${k}/list.json`)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
    )
  )
  return results
    .flatMap((res: any) => res.list ?? [])
    .map((k: any) => ({
      id: k.data.id,
      title: k.data.title,
      url: k.data.url,
    }))
    .filter((i: NewsItem) => i.title)
}

// 市场资讯 (MktNews) — 财经快讯
export async function fetchMktnews(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-mktnews/api/flash?type=0&limit=50')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  return (json.data ?? []).map((item: any) => ({
    id: String(item.id),
    title: item.data.title || item.data.content?.match(/^【([^】]*)】/)?.[1] || item.data.content || '',
    url: `https://mktnews.net/flashDetail.html?id=${item.id}`,
    extra: { info: item.important === 1 ? '重要' : undefined },
  })).filter((i: NewsItem) => i.title)
}

// 36氪 — 科技财经快讯
export async function fetch36kr(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-36kr/newsflashes', {
    headers: { Referer: 'https://www.36kr.com' },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const html = await res.text()
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const items: NewsItem[] = []
  doc.querySelectorAll('.newsflash-item').forEach(el => {
    const a = el.querySelector('a.item-title') as HTMLAnchorElement | null
    const url = a?.getAttribute('href')
    const title = a?.textContent?.trim()
    if (url && title) {
      items.push({
        id: url,
        title,
        url: url.startsWith('http') ? url : 'https://www.36kr.com' + url,
      })
    }
  })
  return items
}

// 澎湃新闻 — 热门新闻
export async function fetchThepaper(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-thepaper/contentapi/wwwIndex/rightSidebar')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const json = await res.json()
  const list: any[] = json?.data?.hotNews ?? []
  return list.map((k: any) => ({
    id: String(k.contId),
    title: k.name,
    url: `https://www.thepaper.cn/newsDetail_forward_${k.contId}`,
    mobileUrl: `https://m.thepaper.cn/newsDetail_forward_${k.contId}`,
  })).filter((i: NewsItem) => i.title)
}

// 东方财富 — 财经快讯
export async function fetchEastmoney(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-eastmoney/kuaixun/v1/getlist_102_ajaxResult_10_1_.html', {
    headers: { Referer: 'https://finance.eastmoney.com' },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const text = await res.text()
  const jsonStr = text.replace(/^var\s+ajaxResult\s*=\s*/, '').trim()
  const json = JSON.parse(jsonStr)
  const list: any[] = json?.LivesList ?? []
  return list.map((k: any) => ({
    id: String(k.id),
    title: k.title,
    url: k.url_w || `https://finance.eastmoney.com/a/${k.id}.html`,
    mobileUrl: k.url_m,
  })).filter((i: NewsItem) => i.title)
}

// 格隆汇 — 财经资讯
export async function fetchGelonghui(): Promise<NewsItem[]> {
  const res = await fetch('/proxy-gelonghui/news/')
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  const html = await res.text()
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const items: NewsItem[] = []
  doc.querySelectorAll('.article-content').forEach(el => {
    const a = el.querySelector('.detail-right>a') as HTMLAnchorElement | null
    const url = a?.getAttribute('href')
    const title = a?.querySelector('h2')?.textContent?.trim()
    const info = (el.querySelector('.time > span:nth-child(1)') as HTMLElement)?.innerText?.trim()
    if (url && title) {
      items.push({
        id: url,
        title,
        url: 'https://www.gelonghui.com' + url,
        extra: { info },
      })
    }
  })
  return items
}
