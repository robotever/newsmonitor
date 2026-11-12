import type { NewsSource } from '@/types'
import { ACTIVE_SOURCE_IDS } from './news-policy.mjs'

const ALL_NEWS_SOURCES: NewsSource[] = [
  // 中文财经
  { id: 'ftchinese', name: 'FT中文网',     type: 'finance', color: '#fff200', icon: 'FT', description: '金融时报中文版',    enabled: true },
  { id: 'investing',  name: 'Investing中文', type: 'finance', color: '#e84141', icon: 'IV', description: 'Investing.com中文财经', enabled: true },
  { id: 'sinafinance', name: '新浪财经股票', type: 'finance', color: '#d71920', icon: '新', description: '新浪财经股票滚动新闻', enabled: true },
  { id: 'stcn',        name: '证券时报快讯', type: 'finance', color: '#c7000b', icon: '证', description: '人民财讯7×24小时快讯', enabled: true },
  // 国际财经
  { id: 'bloomberg',  name: 'Bloomberg',   type: 'finance', color: '#000000', icon: 'BL', description: '彭博财经新闻',      enabled: true },
  { id: 'marketwatch',name: 'MarketWatch', type: 'finance', color: '#00a651', icon: 'MW', description: 'MarketWatch财经',   enabled: true },
  // 新增财经
  { id: 'eastmoney',   name: '东方财富',   type: 'finance', color: '#cf1414', icon: '东', description: '东方财富财经快讯',   enabled: true },
  { id: 'wallstreetcn', name: '华尔街见闻', type: 'finance', color: '#f5a623', icon: '华', description: '华尔街见闻实时快讯', enabled: true },
  { id: 'jin10',      name: '金十数据',    type: 'finance', color: '#f0a500', icon: '金', description: '金十财经快讯',       enabled: true },
  { id: 'cankaoxiaoxi', name: '参考消息',  type: 'finance', color: '#c0392b', icon: '参', description: '参考消息国际时事',   enabled: true },
  { id: 'mktnews',    name: '市场资讯',    type: 'finance', color: '#1a6ab1', icon: 'MK', description: 'MktNews财经快讯',    enabled: true },
  { id: 'gelonghui',  name: '格隆汇',      type: 'finance', color: '#2ecc71', icon: '格', description: '格隆汇财经资讯',     enabled: true },
]

export const NEWS_SOURCES = ALL_NEWS_SOURCES.filter(source => ACTIVE_SOURCE_IDS.has(source.id))
