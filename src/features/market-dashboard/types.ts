export type MarketScoreAxis = 'strength' | 'heat' | 'risk'
export type MarketFrequency = 'intraday' | 'daily' | 'monthly'
export type MarketStage = '冰点' | '修复' | '震荡' | '扩张' | '过热' | '退潮'
export type MarketHistoryWindow = '1d' | '5d' | '20d' | '90d'
export type MarketComparisonKey = 'change1d' | 'change5d'
export type MarketComparisonUnavailable = 'missingObservation' | 'missingCurrentScores' | 'missingTradingCalendar' | 'missingTargetTradingDate'
export interface MarketScores { strength: number | null; heat: number | null; risk: number | null }
export interface MarketScoreSummary extends MarketScores { id: string; completeness: number }
export interface MarketScoreObject extends MarketScoreSummary {
  name?: string
  frequency?: MarketFrequency
  observedAt?: string
  stage?: MarketStage | null
  missing: string[]
  contributors: { label: string; impact: number; evidence?: string }[]
  sourceTimestamps: { source: 'Wind' | 'FRED' | 'MX' | 'Derived'; timestamp: string }[]
  change1d: MarketScores | null
  change5d: MarketScores | null
  comparisonFallback?: 'close'
  comparisonUnavailable?: Partial<Record<MarketComparisonKey, MarketComparisonUnavailable>>
}
export interface MarketSourceMode {
  breadth: 'wind'; styles: 'wind'; industries: 'wind'
  global: Record<string, 'fred' | 'wind' | 'mx'>
}
export interface MarketDataStatus { completeness: number; stale: boolean; missing: string[] }
export interface MarketObservation {
  observedAt: string
  marketDate: string
  session: 'intraday' | 'close'
  scoringVersion: 'market-score-v0.1'
}
/** Runtime loader enforces global + A-share + exact 6 styles / 35 industries (43 objects). */
export interface MarketDashboardPayload extends MarketObservation {
  schemaVersion: 'market-dashboard-v1'
  global: MarketScoreObject
  aShare: MarketScoreObject
  styles: MarketScoreObject[]
  industries: MarketScoreObject[]
  dataStatus: MarketDataStatus
  sourceMode?: MarketSourceMode
}
export interface MarketHistorySnapshot extends MarketObservation {
  global: MarketScoreSummary
  aShare: MarketScoreSummary
  styles: MarketScoreSummary[]
  industries: MarketScoreSummary[]
}
export interface MarketHistoryPayload { window: MarketHistoryWindow; snapshots: MarketHistorySnapshot[] }
export type MarketLoadErrorCode = 'NO_SNAPSHOT' | 'HTTP_ERROR' | 'INVALID_JSON' | 'INVALID_SCHEMA' | 'TIMEOUT' | 'ABORTED' | 'NETWORK_ERROR' | 'INVALID_WINDOW'
export interface MarketLoadError { code: MarketLoadErrorCode; message: string; status?: number }
export type MarketLoadResult<T> = { data: T; error: null } | { data: null; error: MarketLoadError }
export interface MarketLoadOptions { timeoutMs?: number; signal?: AbortSignal }
export interface MarketViewOptions {
  /** Intraday: 30 minutes; daily: conservative 20 days; monthly: 75 days. */
  staleAfterMs?: Partial<Record<MarketFrequency, number>>
  /** Exact Asia/Shanghai exchange dates; omitted means weekday approximation. */
  tradingDates?: readonly string[]
}
export interface MarketFreshness { stale: boolean; ageMs: number; missingClose: boolean; label: string; oldestSourceAt?: string | null }
export interface MarketImprovement {
  improvementValue: number | null
  improvementWindow: '1d' | '5d' | null
  improvementLabel: string
}
export interface MarketScoreView extends MarketScoreObject, MarketImprovement {
  stage: MarketStage | null
  stageLabel: string
  scoreLabels: Record<MarketScoreAxis, string>
  evidenceInsufficient: boolean
  evidenceLabel: string
  freshness: MarketFreshness
  comparisonBadges: Record<MarketComparisonKey, string>
}
export interface MarketIndustryRankings<T extends MarketScoreObject = MarketScoreView> {
  strength: (T & MarketImprovement)[]
  heat: (T & MarketImprovement)[]
  risk: (T & MarketImprovement)[]
  improvement: (T & MarketImprovement)[]
}
export interface MarketDashboardView extends Omit<MarketDashboardPayload, 'global' | 'aShare' | 'styles' | 'industries'> {
  global: MarketScoreView
  aShare: MarketScoreView
  styles: MarketScoreView[]
  industries: MarketScoreView[]
  freshness: MarketFreshness
  rankings: MarketIndustryRankings
}
