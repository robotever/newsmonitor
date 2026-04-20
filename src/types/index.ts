export interface NewsItem {
  id: string
  title: string
  url: string
  mobileUrl?: string
  score?: number
  timestamp?: number
  extra?: {
    icon?: string
    info?: string
    hover?: string
  }
}

export interface NewsSource {
  id: string
  name: string
  type: 'china' | 'global' | 'tech' | 'finance'
  color: string
  icon: string
  description: string
  enabled: boolean
}

export interface NewsData {
  source: string
  items: NewsItem[]
  updatedAt: number
  loading: boolean
  error?: string
}

export interface TickerItem {
  title: string
  url: string
  source: string
  sourceColor: string
}
