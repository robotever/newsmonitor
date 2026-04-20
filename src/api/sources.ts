import type { NewsSource } from '@/types'

export const NEWS_SOURCES: NewsSource[] = [
  // 中文财经
  { id: 'cailian',      name: '财联社',     type: 'finance', color: '#c0392b', icon: '财', description: '财联社实时电报快讯', enabled: true },
  { id: 'ftchinese', name: 'FT中文网',     type: 'finance', color: '#fff200', icon: 'FT', description: '金融时报中文版',    enabled: true },
  { id: 'investing',  name: 'Investing中文', type: 'finance', color: '#e84141', icon: 'IV', description: 'Investing.com中文财经', enabled: true },
  // 国际财经
  { id: 'bloomberg',  name: 'Bloomberg',   type: 'finance', color: '#000000', icon: 'BL', description: '彭博财经新闻',      enabled: true },
  { id: 'marketwatch',name: 'MarketWatch', type: 'finance', color: '#00a651', icon: 'MW', description: 'MarketWatch财经',   enabled: true },
  { id: 'yahoo',      name: 'Yahoo Finance',type: 'finance', color: '#6001d2', icon: 'YF', description: 'Yahoo财经新闻',    enabled: true },
  // 科技
  { id: 'hackernews', name: 'Hacker News', type: 'tech',    color: '#ff6600', icon: 'HN', description: 'YC旗下科技社区',   enabled: true },
  { id: 'github',     name: 'GitHub趋势',  type: 'tech',    color: '#24292f', icon: 'GH', description: 'GitHub每日热门项目', enabled: true },
  { id: 'producthunt',name: 'Product Hunt',type: 'tech',    color: '#da552f', icon: 'PH', description: '今日最热新产品',    enabled: true },
  // 新增财经
  { id: 'thepaper',    name: '澎湃新闻',   type: 'finance', color: '#0066cc', icon: '湃', description: '澎湃新闻热门资讯',   enabled: true },
  { id: 'eastmoney',   name: '东方财富',   type: 'finance', color: '#cf1414', icon: '东', description: '东方财富财经快讯',   enabled: true },
  { id: 'wallstreetcn', name: '华尔街见闻', type: 'finance', color: '#f5a623', icon: '华', description: '华尔街见闻实时快讯', enabled: true },
  { id: 'jin10',      name: '金十数据',    type: 'finance', color: '#f0a500', icon: '金', description: '金十财经快讯',       enabled: true },
  { id: 'cankaoxiaoxi', name: '参考消息',  type: 'finance', color: '#c0392b', icon: '参', description: '参考消息国际时事',   enabled: true },
  { id: 'mktnews',    name: '市场资讯',    type: 'finance', color: '#1a6ab1', icon: 'MK', description: 'MktNews财经快讯',    enabled: true },
  { id: '_36kr',      name: '36氪',        type: 'finance', color: '#e03c31', icon: '氪', description: '36氪科技财经资讯',   enabled: true },
  { id: 'gelonghui',  name: '格隆汇',      type: 'finance', color: '#2ecc71', icon: '格', description: '格隆汇财经资讯',     enabled: true },
  // 综合
  { id: 'reddit',     name: 'Reddit',      type: 'global',  color: '#ff4500', icon: 'Rd', description: 'Reddit热门帖子',    enabled: true },
]
