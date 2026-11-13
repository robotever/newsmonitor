# NewsMonitor

市场研究首页、全球债务风险和实时财经新闻聚合：[生产页面](https://newsmonitor.pages.dev/)。市场研究面板目前为 **v0.1 / 试运行**，三交易日灰度验收尚未完成。

## 首页功能

- 全局环境、A 股整体、六类风格、35 个 Wind 二级行业，统一展示强度、热度、风险、完整度、时间与贡献因素。
- 本地 Python 采集 Wind / FRED / 妙想并计算二级指标，经认证 Pages Function 发布到 D1；浏览器只读最新快照及短期历史。供应商原始响应与凭证不上传。
- 保留全球债务四条主线（美国利率、信用与久期、日本资金、欧洲主权），新闻每 5 分钟刷新，实时快讯聚合成功来源。
- 缺失不补零；证据不足、滞后、无可比历史和刷新失败均明确披露。风险红色仅表达风险分，缺失为灰色虚线，滞后为灰紫实线。

2026-11-13 的首次真实收盘基线含 43 个评分对象，整体完整度 **40%**。这是有效输入权重的覆盖比例（含冷启动折扣），不是数据准确率或收益概率；缺少单位、过期数据与不可用跨资产指标会减少覆盖。低于 70% 提示证据不足，低于 50% 不给阶段结论。详见[运行手册](docs/market-dashboard-operations.md)。

## 开发与验证

技术栈：Vue 3、TypeScript、Vite、Pinia、Tailwind CSS、Cloudflare Pages Functions / D1。

```bash
npm ci
npm run dev
python3 -m unittest discover -s tools/market_dashboard/tests -v
python3 '/Users/robot_ever/Codex/Financial Knowledge Repository/scripts/regression_service_reliability.py'
PYTHONPYCACHEPREFIX=/private/tmp/newsmonitor-python-cache python3 '/Users/robot_ever/Codex/Financial Knowledge Repository/scripts/intake_health_check.py'
npm test
npm run build
```

开发地址为 [localhost:5173](http://localhost:5173)，构建输出 `dist/`。Vite 只提供现有新闻/FRED 代理；研究 API 需 Pages Functions 环境（如 `npx wrangler pages dev dist`）或本地测试中的受控 API 响应。

## 部署与运维

仓库：[robotever/newsmonitor](https://github.com/robotever/newsmonitor)。当前发布流程使用 Wrangler；GitHub 的 `main` 也连接 Pages，发布时只能选择一个触发路径，避免重复部署。必须一同保留 `functions/`、`migrations/` 与 `wrangler.toml` 中的 `MARKET_DB` 绑定。

[运行手册](docs/market-dashboard-operations.md)涵盖持久环境、证书、迁移、轮换、手工运行、诊断、回滚、停用及灰度清单。[macOS 调度说明](ops/macos/README.md)描述安装器的准备、启用和恢复行为。长期服务应指向稳定 checkout；本工作树的 Task 9 不部署、不安装或启用 LaunchAgent。

## 数据限制

- v0.1 权重、分位和阶段阈值是研究假设，尚未历史回测，不构成投资建议。
- 默认 A 股交易日仅按工作日近似；假日与跨日比较需要经确认的交易日历。
- 本机离线、供应商额度、字段/单位变化会中断更新；保留最后成功快照，不以模拟值填补或自动混用供应商口径。
- 全球序列含日频、月频，不能视作全部盘中实时；`sourceMode` 记录选定来源，不保证该来源的每项数据均可用。
