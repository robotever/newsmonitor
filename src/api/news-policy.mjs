export const NEWS_ITEM_LIMIT = 10

export const ACTIVE_SOURCE_IDS = new Set([
  'ftchinese', 'investing', 'bloomberg', 'marketwatch',
  'hackernews', 'github', 'producthunt', 'thepaper', 'eastmoney',
  'wallstreetcn', 'jin10', 'cankaoxiaoxi', 'mktnews', '_36kr',
  'gelonghui', 'reddit',
])

export function limitNewsItems(items) {
  return Array.isArray(items) ? items.slice(0, NEWS_ITEM_LIMIT) : []
}
