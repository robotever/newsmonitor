# 市场研究面板运行手册

状态：**v0.1 / 试运行**。本文最后核验于 2026-11-13。首个真实收盘快照是 day 0 基线；三个完整交易日的灰度验收仍待执行。任务分支尚待主代理审查、整合稳定 checkout、最终部署与显式服务启用。

## 数据职责与解释边界

| 来源 | 当前职责 | 已验证限制 |
| --- | --- | --- |
| Wind | `881001.WI` 广度、固定 6 风格与 35 二级行业；三次批量采集 | day 0 行数 1 / 6 / 35。默认行业用 `index_data.get_index_price_indicators`；旧 analytics 路径仅显式 opt-in。身份、时间、单位必须匹配，不推测缺少的 `%` |
| FRED | 美债、信用、日欧主权、VIX、美元及美股日/月频历史 | day 0 `THREEFYTP10`、意大利主权、美元部分过期；不当作盘中实时 |
| 妙想 MX | 黄金、原油、离岸人民币的配置来源 | day 0 对应角色缺少可用指标，保持缺失；不是行业主源 |
| 新闻/RSS | 现有 11 个新闻源与解释背景 | 每 5 分钟刷新；当前不进入核心评分，失败源独立显示 |

`sourceMode` 表示每组/角色选择的供应商，即使某角色不可用也保留来源；不意味着每个字段均成功。当前没有自动供应商切换，也不把 AkShare/东方财富公开接口作为关键评分的唯一来源。

首个真实快照：2026-11-13 **18:01:47 北京时间**（`10:01:47.822199Z`），`session=close`，43 个对象，整体完整度 **40%**，各对象 30–68%。这是在有效、未过期、单位兼容的输入权重上计算的覆盖比例，再考虑历史不足的 0.85 折扣；整体为 43 对象完整度的四舍五入平均。它不是准确率、置信概率或推荐仓位。缺失不补零，低于 70 显示“证据不足”，低于 50 不输出阶段；发布阈值默认仅要求大于零，可配置 `publication.minimumCompleteness`，不得靠删去缺失项提高分母覆盖。

版本为 `market-dashboard-v1` / `market-score-v0.1`。权重、阈值、单位和来源语义改变必须评估评分版本，不能把不同版本历史直接拼成变化。冷启动历史不足 20 个观测时走版本化固定阈值（仅已配置的指标有此路径）并折扣；无可用阈值则缺失。最多使用 60 个滚动观测，不代表 60 个交易日。无明确交易日历时，1日/5日盘中比较保持缺失；缺少同一时点时才允许对应交易日收盘回退，并披露回退。

## 运行路径与持久环境

真实父项目：`/Users/robot_ever/Codex/Financial Knowledge Repository`。长期 checkout 预期为其 `newsmonitor/` 子目录。以下命令必须在已整合且核验干净的稳定 checkout 中运行；临时 `.codex/worktrees` 默认被安装器拒绝，不用于长期调度。

```bash
cd '/Users/robot_ever/Codex/Financial Knowledge Repository/newsmonitor'
export MARKET_DASHBOARD_PROJECT_ROOT='/Users/robot_ever/Codex/Financial Knowledge Repository'
export MARKET_DASHBOARD_PYTHON='/Library/Frameworks/Python.framework/Versions/3.13/bin/python3'
```

父项目 `.env` 为 0600，包含 `MARKET_DASHBOARD_PUBLISH_TOKEN`、生产 `MARKET_DASHBOARD_PUBLISH_URL=https://newsmonitor.pages.dev/api/market-dashboard/publish` 及 `SSL_CERT_FILE`。2026-11-13 已核验 CA 实际路径：`/Library/Frameworks/Python.framework/Versions/3.13/lib/python3.13/site-packages/certifi/cacert.pem`。换 Python 后用 `python3 -m certifi` 重新确认文件可读，再更新这一项。不要禁用 TLS 校验。

wrapper 按单行字面量解析 `.env`，不执行 `source` / `eval` / `$()`；已有进程环境优先。不要把 shell 表达式 `$(python3 -m certifi)` 原样写进 `.env`，应写计算出的路径。Wind 沿用本机既有配置与 skill；妙想使用本机 MX 配置。切勿把 token 放在 CLI 参数、plist、仓库、Vault、截图或日志。

已核验运行环境：Python 3.13.7、Node 22.20.0、Vite 8.0.8、Wrangler 4.160.1；依赖以锁文件为准。当前轮已用真实 wrapper + fixture dry-run 验证 URL、CA、token 被读取，只保留布尔检查结果，不输出值。

运行产生的文件均位于父项目：

- `state/market-dashboard/last-success.json`：成功 bucket、二级快照、90 天内本地派生历史；失败不覆盖。
- `state/market-dashboard/job.lock`：非阻塞进程锁；现场排障不要直接删除正在使用的锁。
- `state/service-health/market-dashboard.json`：阶段、源行数、完整度、最后发布状态与安全错误码。
- `logs/market-dashboard/`：0700；job/launchd 日志为 0600，沿用 2 MB / 三备份 copy-truncate。wrapper 与安装器拒绝 `logs` 或 `logs/market-dashboard` 为软链接；日志文件也拒绝软链接。

采集不创建 Vault Inbox 或 In Progress 笔记，不上传供应商原始响应。

## 调度与服务生命周期

全部业务时钟为 Asia/Shanghai。LaunchAgent 每 300 秒唤醒，Python gate 决定是否运行：交易日 09:30–11:30、13:00–15:00，每 15 分钟 bucket 最多成功一次；15:00–15:30 为一次最终 close 的补采窗口。收盘数据必须在当日 15:00 或之后；同日收盘观测可持续有效到当地日期结束。`--force` 只绕过时段限制，不绕过锁、schema 或成功 bucket 去重。

默认工作日只是近似。要识别休市日，给版本化配置增加 `schedule.tradingDates`（ISO 日期字符串列表），同时让根 health 读取同一已安装 checkout 的配置。未提供日历时不可声称交易所假日已覆盖。

仅准备（不会加载/启动）；先审核生成 plist、稳定路径与私有权限：

```bash
./ops/macos/install-market-dashboard-service.sh --prepare
plutil -lint "$HOME/Library/LaunchAgents/com.robot-ever.newsmonitor.market-dashboard.plist"
# 在最终整合和部署验收后才显式启用：
./ops/macos/install-market-dashboard-service.sh --enable
launchctl print "gui/$(id -u)/com.robot-ever.newsmonitor.market-dashboard"
```

无 RunAtLoad/KeepAlive，无 kickstart。已加载的旧 plist 不自动重启；路径变化先 `--disable` 再 `--enable`。此轮未安装、加载或启用真实服务，不能把 one-shot 成功当作定时运行证据。

```bash
./ops/macos/install-market-dashboard-service.sh --disable
./ops/macos/install-market-dashboard-service.sh --uninstall
# 恢复首次安装前备份，保持禁用：
./ops/macos/install-market-dashboard-service.sh --restore
```

disable 只停止该 label；uninstall 将 plist 留为 `.plist.disabled`，保留 `.plist.bak`、state、logs 和全部远端 D1 数据。restore 不启动。**不得删除 D1 数据库或表作为停用步骤。**

## 手工验证与发布

```bash
# 离线合成 fixture，只用于本地验证，禁止发布到生产：
./ops/macos/run-market-dashboard.sh --fixture --dry-run
# 真实采集/校验；遵守时段与成功 bucket，不写成功快照或健康文件：
./ops/macos/run-market-dashboard.sh --dry-run
# 诊断指定时段外的新 bucket，可绕过时段；成功 bucket 仍会返回 duplicate：
./ops/macos/run-market-dashboard.sh --dry-run --force
# 正常真实发布：
./ops/macos/run-market-dashboard.sh
```

wrapper 将摘要写入私有 `job.log`。live dry-run 仍获取锁，可能创建锁目录；不发布、不改成功/health。`--skip-publish` 会更新 health 而不推进成功 bucket，不要将它当作完全无写入检查。`--fixture` 无法真实发布。已有 day 0 close 的同一 bucket 返回 duplicate 是预期行为；不要删 state 强行重发。后续人工补采若需 `--force`，应先核验时钟、源观测、目标与未成功 bucket。

只读查看：

```bash
curl --fail --silent --show-error https://newsmonitor.pages.dev/api/market-dashboard/latest
curl --fail --silent --show-error 'https://newsmonitor.pages.dev/api/market-dashboard/history?window=5d'
PYTHONDONTWRITEBYTECODE=1 python3 '/Users/robot_ever/Codex/Financial Knowledge Repository/scripts/regression_service_reliability.py'
PYTHONPYCACHEPREFIX=/private/tmp/newsmonitor-python-cache python3 '/Users/robot_ever/Codex/Financial Knowledge Repository/scripts/intake_health_check.py'
```

公开接口仅允许 `1d` / `5d` / `20d` / `90d` 历史窗口。初始仅一条真实快照时历史长度 1、变化缺失正常；不是可用于验证日间斜率的历史。

## Cloudflare、迁移与凭证轮换

项目为 `newsmonitor`，生产域名 `newsmonitor.pages.dev`；`wrangler.toml` 的 `MARKET_DB` 绑定到 `newsmonitor-market-dashboard`，真实 UUID 只按配置使用。不要操作既有其他数据库。

初次部署前（day 0 已完成，日常无需反复建库）：

```bash
npx wrangler d1 migrations list newsmonitor-market-dashboard --local
npx wrangler d1 migrations apply newsmonitor-market-dashboard --local
npx wrangler d1 migrations list newsmonitor-market-dashboard --remote
npx wrangler d1 migrations apply newsmonitor-market-dashboard --remote
```

`0001_market_dashboard.sql` 是增量建表/索引，唯一键为 `(observed_at, scoring_version)`，服务端将 `observed_at` 规范化为 UTC；`payload_json` 保留严格校验的43对象二级分数、缺失/贡献/来源时间摘要。本地派生历史按90天裁剪；D1 当前不自动清理，保留至少90天，后续如需保留策略应单独审查，不能声称已存在远端清理任务。公开 latest/history 不返回原始供应商行、本机路径或凭证。

生产和 preview 都需同名 `MARKET_DASHBOARD_PUBLISH_TOKEN` Secret 与 `MARKET_DB` 绑定。轮换是单独运维动作，本轮未轮换：先停止本地服务，安全生成新随机 token，仅在内存中处理；用 Wrangler Secret 输入/安全 stdin 设置 preview 与 production，核验 Secret **名称和类型**，再原子更新父 `.env` 的对应赋值并保留0600、其余内容。使用 `npx wrangler pages secret put MARKET_DASHBOARD_PUBLISH_TOKEN --project-name newsmonitor --env preview` 和 `npx wrangler pages secret put MARKET_DASHBOARD_PUBLISH_TOKEN --project-name newsmonitor --env production`，分别经隐藏输入或安全 stdin 传入值。Wrangler 4.160.1 本地实现已核验只接受 production/preview（该参数在帮助中隐藏）。值不得进入参数、shell history、临时凭证文件或报告。

Secret 更新后核验目标环境已使用新绑定，先在 preview 检查新 token 可用、旧 token 拒绝；如需要部署以生效，走同一经审查发布路径，再更新/恢复本地。避免轮换中途继续定时发布。不要为证明 token 有效往生产注入合成快照；下一个真实新 bucket 的发布才是生产业务验证。

发布使用单一路径：当前采用 Wrangler 手工发布，需构建 `dist` 并携带 `functions/`；不要同时推 `main` 触发 Git 构建。具体最终发布与稳定 checkout 整合由主代理完成，本轮只读生产。

## 滞后、额度、故障诊断

1. 比较页面北京时间、市场日期、session 与 `sourceTimestamps`。`dataStatus.stale=true` 可由任一过期组件触发，不代表当天 close 缺失。页面“收盘确认”与“数据滞后”可同时出现。
2. 已启用服务的 intraday bucket 有10分钟 grace；15:30 起缺少当日成功 close 会持续报错至该交易日结束。午休、盘前、周末及配置非交易日不报盘中延迟。未启用时 health 仅提示 informational。
3. 看安全 health：`stage`、`sourceCounts`、`completeness`、`errorCode` 与 `lastPublishStatus`。期望 Wind 行数 1/6/35；global 的16行表示配置角色数，不能据此推断16项都有效。
4. 若行数正确而完整度低，检查字段名、单位、时间和配置来源；没有 `%` 不能自行补单位。daily/monthly source adapter 默认最大年龄为7/75天；前端显示容忍度为20/75天，仍尊重 payload 的 stale 标记。尚未按各源正式发布日历实现“两周期”判定，应在灰度中核验。
5. provider quota/429 或工具超时：停止额外探测，保留最后成功快照；锁与15分钟 gate 防重叠。不并行加压，不自动切源，不伪造数据。记录发生时段、组别、行数/安全错误码、耗时与已知限额；供应商原文只在受控本地排障，不进日志/报告/D1。
6. 发布 401：核对环境、Secret 名称和本地 token 同步；403 检查边缘规则和固定发布 User-Agent。TLS 错误先核验所选 Python 与 `SSL_CERT_FILE` 可读，不使用 insecure curl/禁用验证。网络/5xx 有有限重试；4xx 不重试。检查公开 latest 仍为最后成功值。
7. D1/API 失败：页面保留本次会话最后成功快照并提示失败；新会话无成功值则显示 unavailable，不显示模拟分数。missing 用灰色虚线、stale 用灰紫实线，红色保留风险语义。

## 回滚与数据保留

应用回滚可在 Cloudflare Pages 历史中选择已核验的此前部署 `d925c945-7259-4aaa-81dc-518acc3e0419`（源 `9de6d5c`），或通过唯一 Wrangler 路径部署经审查的旧 checkout。Task 8 当前生产为 `1aaa18b2-98c2-437f-8a5a-4f73831bd8a5`（`b683fb0`）；最终部署后应更新这一记录。回滚保留 `MARKET_DB`、增量 schema、真实快照及 Secret；停用本地发布器后再排查兼容性。不要 drop 数据库/表，也不要删成功 state 绕过去重。

父项目 health 与 regression 的 Task 7 改动不属于此 Git 仓库；文件为上文两个绝对路径，有同目录 `.task7-20261113.bak` 和 `.task7-round1-20261113.bak`。只在确认后续改动后恢复相应版本，不盲目覆盖。

## 三交易日灰度记录（尚未完成）

2026-11-13 close 作为 **day 0 / 基线**，不是完整灰度日；当日上午/下午没有计划任务证据。接下来三个经交易所日历确认的完整交易日逐日填写。所有必需时段通过后才能讨论移除 `v0.1 / 试运行`，目前不得宣称已通过。

| 检查项 | day 0：2026-11-13 | Day 1（待确认日期） | Day 2（待确认日期） | Day 3（待确认日期） |
| --- | --- | --- | --- | --- |
| 上午每15分钟 bucket 发布 | 未执行/无证据 | 待记录 | 待记录 | 待记录 |
| 下午每15分钟 bucket 发布 | 未执行/无证据 | 待记录 | 待记录 | 待记录 |
| 15:00–15:30 唯一 close | 18:01 人工 force 成功，非窗口内定时验证 | 待记录 | 待记录 | 待记录 |
| Wind 广度/风格/行业行数 | 1 / 6 / 35 | 待记录 | 待记录 | 待记录 |
| 字段、单位、时间稳定性 | `%` 单位缺失；不能算通过 | 待记录 | 待记录 | 待记录 |
| 采集耗时/额度错误 | 未保留完整耗时/额度证据 | 待记录 | 待记录 | 待记录 |
| public API 延迟 | 单次 latest 968ms；history 719–862ms，非SLA | 待记录分布 | 待记录分布 | 待记录分布 |
| 整体/逐对象完整度 | 40% / 30–68% | 待记录与解释变化 | 待记录与解释变化 | 待记录与解释变化 |
| stale与缺失、午休/收盘健康 | payload stale；部分FRED/MX缺失，午间未验收 | 待记录 | 待记录 | 待记录 |
| 桌面/手机及原有债务/新闻 | 只读/本地最终UI复核 | 待复核 | 待复核 | 待复核 |
| 当日结论/证据定位 | 基线已建立，非灰度通过 | 待人工签核 | 待人工签核 | 待人工签核 |

每日将安全汇总记录在项目运维记录，不将原始响应、token 或完整本机环境写入 Vault。通过条件是每个应有 bucket 成功或有解释/恢复记录、行数身份与字段单位稳定、收盘成功、没有未处置额度/时延问题，且完整度与 stale 披露符合真实可用性；不能通过降低阈值、补零或隐藏缺失达标。
