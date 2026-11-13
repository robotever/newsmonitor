import type { MarketDashboardPayload, MarketDashboardView, MarketFrequency, MarketIndustryRankings, MarketScoreObject, MarketViewOptions } from './types'
export const DEFAULT_STALE_AFTER_MS: Readonly<Record<MarketFrequency, number>>
export function deriveMarketDashboardView(payload: MarketDashboardPayload, now?: Date, options?: MarketViewOptions): MarketDashboardView
export function rankIndustries<T extends MarketScoreObject>(industries: readonly T[]): MarketIndustryRankings<T>
