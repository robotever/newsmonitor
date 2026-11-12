import type { DebtLoadResult, DebtSeriesDefinition } from './types'
export const SERIES: Record<string, DebtSeriesDefinition>
export const DEFAULT_SERIES: DebtSeriesDefinition[]
export function loadDebtSeries(
  fetcher?: typeof fetch,
  definitions?: DebtSeriesDefinition[],
  options?: { timeoutMs?: number },
): Promise<DebtLoadResult>
