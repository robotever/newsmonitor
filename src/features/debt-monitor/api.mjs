import { parseFredCsv } from './model.mjs'

export const SERIES = Object.freeze({
  DGS2: { id: 'DGS2', name: '美国2年期国债', frequency: '日频' },
  DGS10: { id: 'DGS10', name: '美国10年期国债', frequency: '日频' },
  DFII10: { id: 'DFII10', name: '美国10年实际利率', frequency: '日频' },
  T10YIE: { id: 'T10YIE', name: '美国10年通胀补偿', frequency: '日频' },
  BAMLH0A0HYM2: { id: 'BAMLH0A0HYM2', name: '美国高收益债利差', frequency: '日频' },
  THREEFYTP10: { id: 'THREEFYTP10', name: '美国10年期限溢价', frequency: '日频' },
  IRLTLT01JPM156N: { id: 'IRLTLT01JPM156N', name: '日本10年期国债', frequency: '月频' },
  IRLTLT01DEM156N: { id: 'IRLTLT01DEM156N', name: '德国10年期国债', frequency: '月频' },
  IRLTLT01FRM156N: { id: 'IRLTLT01FRM156N', name: '法国10年期国债', frequency: '月频' },
  IRLTLT01ITM156N: { id: 'IRLTLT01ITM156N', name: '意大利10年期国债', frequency: '月频' },
})

export const DEFAULT_SERIES = Object.values(SERIES)

export async function loadDebtSeries(fetcher = fetch, definitions = DEFAULT_SERIES, options = {}) {
  const timeoutMs = options.timeoutMs ?? 12000
  const entries = await Promise.all(definitions.map(async definition => {
    let timeoutId
    try {
      const timeout = new Promise((_, reject) => {
        timeoutId = setTimeout(() => reject(new Error('请求超时')), timeoutMs)
      })
      const response = await Promise.race([
        fetcher(`/proxy-fred/graph/fredgraph.csv?id=${encodeURIComponent(definition.id)}`),
        timeout,
      ])
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const points = parseFredCsv(await response.text())
      if (points.length === 0) throw new Error('暂无有效数据')
      return [definition.id, points, null]
    } catch (error) {
      return [definition.id, [], error instanceof Error ? error.message : '加载失败']
    } finally {
      clearTimeout(timeoutId)
    }
  }))

  const series = {}
  const errors = {}
  for (const [id, points, error] of entries) {
    series[id] = points
    if (error) errors[id] = error
  }
  return { series, errors, updatedAt: Date.now() }
}
