# NewsMonitor

面向日常市场研究的实时新闻聚合与全球债务风险看板。

线上地址：<https://newsmonitor.pages.dev/>

## 功能

- 聚合中文财经、国际财经与科技新闻源，每 5 分钟自动刷新。
- 右侧实时快讯滚动区汇总已成功加载的新闻。
- “全球债务风险”模块从四条主线观察跨资产环境：
  - 美国利率结构：2 年、10 年、10 年实际利率、10 年通胀补偿。
  - 信用与久期压力：美国高收益债 OAS、10 年期限溢价。
  - 日本资金回流：日本 10 年期国债收益率。
  - 欧洲主权信用：法德、意德 10 年期国债利差。

债务模块使用 FRED 公共 CSV。美国序列为日频，日欧长期国债采用月频 OECD/FRED 序列，并在界面中明确标注观测日期。综合状态和阈值属于启发式研究参考，不是经过历史回测的交易信号。

## 技术结构

- Vue 3 + TypeScript + Vite
- Pinia 状态管理
- Tailwind CSS 与项目自定义高密度深色样式
- Cloudflare Pages 静态部署
- Cloudflare Pages Functions 为外部新闻源和 FRED 提供固定白名单代理

## 本地开发

```bash
npm ci
npm run dev
```

默认地址为 <http://localhost:5173>。

## 测试与构建

```bash
npm test
npm run build
```

单元测试覆盖 FRED CSV 缺失值、乱序数据、部分请求失败、请求超时、欧洲利差计算与综合风险分级。生产构建输出到 `dist/`。

## 部署

GitHub 仓库：<https://github.com/robotever/newsmonitor>

Cloudflare Pages 连接 `main` 分支。推送到 `main` 后由 Cloudflare 自动构建和发布。Pages Functions 位于 `functions/`，因此部署时需保留该目录。

## 数据与限制

- 公共数据源可能变更接口、限流或临时不可用；页面会保留成功指标并标出失败项。
- 页面不会用模拟数据替代失败的宏观序列。
- 月频指标用于结构观察，不能当作盘中实时信号。
- 本项目仅用于研究与信息整理，不构成投资建议。
