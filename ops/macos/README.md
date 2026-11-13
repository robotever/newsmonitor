# Market dashboard LaunchAgent

This directory prepares one user LaunchAgent. Preparation does not load or start
it. No credentials belong in these files or in a plist.

Use a stable checkout, rather than a temporary worktree, for a long-lived job.
From that checkout, set the Financial Knowledge Repository root explicitly when
the checkout is not its direct `newsmonitor/` child:

```bash
export MARKET_DASHBOARD_PROJECT_ROOT="/Users/robot_ever/Codex/Financial Knowledge Repository"
# Optional: choose an absolute Python executable with the required local tools.
export MARKET_DASHBOARD_PYTHON="$(command -v python3)"
./ops/macos/install-market-dashboard-service.sh --prepare
```

Preparation validates the existing `scripts/rotate_service_logs.py` path, writes
`~/Library/LaunchAgents/com.robot-ever.newsmonitor.market-dashboard.plist` with
mode 0600, and creates `logs/market-dashboard/` with mode 0700 and private logs.
It preserves the first differing pre-install plist as `.plist.bak`. Repeating
preparation with identical configuration leaves that backup intact.

Review the rendered plist before opting in:

```bash
./ops/macos/install-market-dashboard-service.sh --enable
```

The explicit enable action enables and bootstraps an unloaded job. It never
bootouts/restarts a loaded job or kickstarts a run. To apply changed paths to a
loaded job, use `--disable` followed by `--enable`. No RunAtLoad or KeepAlive is
configured. Launchd wakes every 300 seconds; the Python job owns Shanghai
session gating, one successful publication per 15-minute bucket, process locking
and one final close snapshot in its 15:00–15:30 catch-up window.

The wrapper parses the parent `.env` as literal assignments without executing
shell expressions or printing values. Existing process variables take
precedence. Shell variable/command expansion and multiline dotenv values are
not supported. Wind keeps its existing user configuration; the plist PATH
includes Homebrew locations. The wrapper exports `MARKET_DASHBOARD_STATE_ROOT`
as `<project root>/state`, then execs `python -m tools.market_dashboard.job`.
Logs use the existing project's 2 MB / three-backup copy-truncate policy at each
wake. Neither source nor installer writes tokens, a publication URL or MX keys.

Stop and remove the service with explicit actions:

```bash
./ops/macos/install-market-dashboard-service.sh --disable
./ops/macos/install-market-dashboard-service.sh --uninstall
# Restore the saved pre-install plist, while leaving the job disabled:
./ops/macos/install-market-dashboard-service.sh --restore
```

Uninstall retains the rendered plist as `.plist.disabled`, its original
`.plist.bak`, snapshots and logs. Restore does not load/start the restored job.
Re-enable is always explicit. These actions affect only this dashboard label.

The Financial project's health script treats an uninstalled/unloaded dashboard
as informational. For an enabled dashboard, intraday buckets receive a
ten-minute collection grace. A missing same-day published close remains an
error from 15:30 through that trading day's end. Lunch, pre-open, weekends and
explicit configured non-trading dates do not create intraday source-delay
errors. Weekdays are an approximation unless `schedule.tradingDates` is present
in the checkout's versioned config; supply the same calendar for job and health
before relying on holiday suppression.
