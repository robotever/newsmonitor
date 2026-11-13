import type { MarketDashboardPayload, MarketHistoryPayload, MarketHistoryWindow, MarketLoadOptions, MarketLoadResult } from './types'
export function loadMarketDashboard(fetcher?: typeof fetch, options?: MarketLoadOptions): Promise<MarketLoadResult<MarketDashboardPayload>>
export function loadMarketHistory(window: MarketHistoryWindow, fetcher?: typeof fetch, options?: MarketLoadOptions): Promise<MarketLoadResult<MarketHistoryPayload>>
