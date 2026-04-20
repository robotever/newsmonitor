const PROXY_MAP = {
  '/proxy-cailian':    { target: 'https://www.cls.cn',               referer: 'https://www.cls.cn' },
  '/proxy-ftchinese':  { target: 'http://www.ftchinese.com' },
  '/proxy-investing':  { target: 'https://cn.investing.com' },
  '/proxy-bloomberg':  { target: 'https://feeds.bloomberg.com' },
  '/proxy-marketwatch':{ target: 'https://feeds.marketwatch.com' },
  '/proxy-yahoo':      { target: 'https://finance.yahoo.com' },
  '/proxy-producthunt':{ target: 'https://www.producthunt.com' },
  '/proxy-thepaper':   { target: 'https://cache.thepaper.cn' },
  '/proxy-eastmoney':  { target: 'https://newsapi.eastmoney.com',    referer: 'https://finance.eastmoney.com' },
  '/proxy-wallstreetcn':{ target: 'https://api-one.wallstcn.com',   referer: 'https://wallstreetcn.com' },
  '/proxy-jin10':      { target: 'https://www.jin10.com',            referer: 'https://www.jin10.com' },
  '/proxy-cankaoxiaoxi':{ target: 'https://china.cankaoxiaoxi.com' },
  '/proxy-mktnews':    { target: 'https://api.mktnews.net',          referer: 'https://mktnews.net' },
  '/proxy-36kr':       { target: 'https://www.36kr.com',             referer: 'https://www.36kr.com' },
  '/proxy-gelonghui':  { target: 'https://www.gelonghui.com',        referer: 'https://www.gelonghui.com' },
}

const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'

export async function onRequest(context) {
  const url = new URL(context.request.url)
  const pathname = url.pathname

  for (const [prefix, config] of Object.entries(PROXY_MAP)) {
    if (pathname.startsWith(prefix)) {
      const targetPath = pathname.slice(prefix.length) + url.search
      const targetUrl = config.target + targetPath

      const headers = new Headers()
      headers.set('User-Agent', UA)
      headers.set('Accept', 'application/rss+xml, application/xml, application/json, text/html, */*')
      if (config.referer) headers.set('Referer', config.referer)

      try {
        const response = await fetch(targetUrl, { headers })
        const newHeaders = new Headers(response.headers)
        newHeaders.set('Access-Control-Allow-Origin', '*')
        newHeaders.delete('Content-Security-Policy')
        newHeaders.delete('X-Frame-Options')
        return new Response(response.body, {
          status: response.status,
          statusText: response.statusText,
          headers: newHeaders,
        })
      } catch (err) {
        return new Response(JSON.stringify({ error: String(err) }), {
          status: 502,
          headers: { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' },
        })
      }
    }
  }

  return context.next()
}
