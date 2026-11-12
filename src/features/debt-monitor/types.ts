export interface DebtPoint { date: string; value: number }
export interface DebtSummary { date: string; value: number; previousValue: number | null; change: number | null; stale?: boolean }
export interface DebtSeriesDefinition { id: string; name: string; frequency: '日频' | '月频' }
export interface DebtLoadResult { series: Record<string, DebtPoint[]>; errors: Record<string, string>; updatedAt: number }
export interface DebtDashboardModel {
  status: 'insufficient' | 'stable' | 'warning' | 'alert'
  label: '数据不足' | '平稳' | '关注' | '警戒'
  score: number
  availableCount: number
  us: Record<string, DebtSummary | null>
  japan: Record<string, DebtSummary | null>
  europe: Record<string, DebtSummary | null>
  signals: {
    credit: { level: 'neutral' | 'stable' | 'warning' | 'alert' }
    europe: { level: 'neutral' | 'stable' | 'warning' | 'alert' }
  }
}
