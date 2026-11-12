import type { DebtDashboardModel, DebtPoint, DebtSummary } from './types'
export function parseFredCsv(text: string): DebtPoint[]
export function summarizeSeries(points?: DebtPoint[]): DebtSummary | null
export function deriveDebtDashboard(seriesMap: Record<string, DebtPoint[]>, now?: Date): DebtDashboardModel
