import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

function proxy(target: string, referer?: string) {
  return {
    target,
    changeOrigin: true as const,
    configure: (p: any) => {
      p.on('proxyReq', (req: any) => {
        req.setHeader('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
        req.setHeader('Accept', 'application/rss+xml, application/xml, application/json, text/xml, */*')
        if (referer) req.setHeader('Referer', referer)
      })
    },
  }
}

const rw = (prefix: string) => ({ rewrite: (p: string) => p.replace(new RegExp(`^${prefix}`), '') })

export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  server: {
    port: 5173,
    proxy: {
      '/proxy-cailian':   { ...proxy('https://www.cls.cn', 'https://www.cls.cn'),           ...rw('/proxy-cailian') },
      '/proxy-ftchinese': { ...proxy('http://www.ftchinese.com'),                            ...rw('/proxy-ftchinese') },
      '/proxy-investing': { ...proxy('https://cn.investing.com'),                            ...rw('/proxy-investing') },
      '/proxy-bloomberg': { ...proxy('https://feeds.bloomberg.com'),                          ...rw('/proxy-bloomberg') },
      '/proxy-marketwatch':{ ...proxy('https://feeds.marketwatch.com'),                      ...rw('/proxy-marketwatch') },
      '/proxy-yahoo':     { ...proxy('https://finance.yahoo.com'),                           ...rw('/proxy-yahoo') },
      '/proxy-producthunt':{ ...proxy('https://www.producthunt.com'),                        ...rw('/proxy-producthunt') },
      '/proxy-thepaper':     { ...proxy('https://cache.thepaper.cn'),                                 ...rw('/proxy-thepaper') },
      '/proxy-eastmoney':    { ...proxy('https://newsapi.eastmoney.com', 'https://finance.eastmoney.com'), ...rw('/proxy-eastmoney') },
      '/proxy-wallstreetcn': { ...proxy('https://api-one.wallstcn.com', 'https://wallstreetcn.com'), ...rw('/proxy-wallstreetcn') },
      '/proxy-jin10':        { ...proxy('https://www.jin10.com', 'https://www.jin10.com'),           ...rw('/proxy-jin10') },
      '/proxy-cankaoxiaoxi': { ...proxy('https://china.cankaoxiaoxi.com'),                           ...rw('/proxy-cankaoxiaoxi') },
      '/proxy-mktnews':      { ...proxy('https://api.mktnews.net', 'https://mktnews.net'),           ...rw('/proxy-mktnews') },
      '/proxy-36kr':         { ...proxy('https://www.36kr.com', 'https://www.36kr.com'),             ...rw('/proxy-36kr') },
      '/proxy-gelonghui':    { ...proxy('https://www.gelonghui.com', 'https://www.gelonghui.com'),   ...rw('/proxy-gelonghui') },
    },
  },
})
