export const NEWS_ITEM_LIMIT = 10

export const ACTIVE_SOURCE_IDS = new Set([
  'ftchinese', 'investing', 'bloomberg', 'marketwatch',
  'sinafinance', 'stcn', 'eastmoney', 'wallstreetcn', 'jin10',
  'cankaoxiaoxi', 'mktnews', 'gelonghui',
])

export function limitNewsItems(items) {
  return Array.isArray(items) ? items.slice(0, NEWS_ITEM_LIMIT) : []
}
