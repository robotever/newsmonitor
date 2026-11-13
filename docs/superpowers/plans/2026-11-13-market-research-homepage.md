# Market Research Homepage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a NewsMonitor homepage that converts Wind, MX, FRED, and official-source inputs into versioned 0–100 strength, heat, and risk scores for the global environment, A-share market, six styles, and 35 Wind level-2 industries.

**Architecture:** A macOS-local Python job collects and scores source data every 15 minutes, then publishes one validated dashboard payload to authenticated Cloudflare Pages Functions backed by D1. The Vue frontend reads only the processed payload and short score history; raw credentials and provider responses remain local.

**Tech Stack:** Python 3.13, Wind MCP CLI, MX Data, FRED CSV, `unittest`, Vue 3, TypeScript, Node test runner, Cloudflare Pages Functions, D1, Wrangler, macOS LaunchAgent.

**Spec:** `docs/superpowers/specs/2026-11-13-market-research-homepage-design.md`

## Global Constraints

- Scoring version is exactly `market-score-v0.1`; payload schema is exactly `market-dashboard-v1`.
- All score outputs are integers in `0–100`; missing inputs reduce completeness and are never converted to zero.
- Wind is the primary source for A-share breadth, six style indices, and 35 Wind level-2 industries.
- MX is supplementary and may cross-check values, but one score must not mix incompatible source definitions.
- Industry, style, and A-share collection targets 15-minute updates during A-share sessions plus a final close snapshot.
- News does not enter v0.1 scores and is not automatically attributed to industries.
- Provider credentials never enter frontend bundles, D1 rows, logs, fixtures, or Git history.
- Production never substitutes mock data for unavailable providers.
- Existing news feeds and the global debt module must remain functional.
- Root `Financial Knowledge Repository` is not a Git repository; commits apply to the nested `newsmonitor` Git repository. Operational files outside it require explicit verification instead of a commit.

## Review Focus

- Wind returns a partial or reordered 35-industry set: reject silent remapping, preserve the last good snapshot, and reduce completeness.
- Intraday comparison lacks a same-clock prior snapshot: fall back to the prior close and expose `comparisonFallback: "close"`.
- D1 contains duplicate or out-of-order publishes: enforce idempotency and never let an older observation become latest.
- One source is stale while others are current: calculate per-object completeness and suppress stage labels below 50.
- Mobile width and partial API failure: keep the four research regions readable and show stale/error state without mock values.

---

## File Structure

### Local collection and scoring

- `config/market-dashboard.json` — versioned codes, weights, thresholds, staleness rules, and provider roles.
- `tools/market_dashboard/scoring.py` — pure normalization, completeness, score, stage, and payload functions.
- `tools/market_dashboard/sources.py` — Wind/MX/FRED command adapters and provider-response parsers.
- `tools/market_dashboard/job.py` — session gate, collection orchestration, state, publication, and CLI.
- `tools/market_dashboard/tests/` — Python unit and fixture tests.
- `tools/market_dashboard/fixtures/` — sanitized successful, partial, stale, and malformed provider responses.

### Cloudflare storage and API

- `migrations/0001_market_dashboard.sql` — D1 schema and indexes.
- `wrangler.toml` — Pages output directory and `MARKET_DB` binding.
- `functions/_lib/market-dashboard.js` — payload validation, authentication, D1 query helpers, and responses.
- `functions/api/market-dashboard/publish.js` — authenticated POST handler.
- `functions/api/market-dashboard/latest.js` — public latest-snapshot GET handler.
- `functions/api/market-dashboard/history.js` — bounded public history GET handler.
- `tests/market-dashboard-functions.test.mjs` — API and D1 behavior tests.

### Vue homepage

- `src/features/market-dashboard/types.ts` — frontend contract types.
- `src/features/market-dashboard/api.mjs` and `.d.mts` — latest/history fetch with timeout and error normalization.
- `src/features/market-dashboard/model.mjs` and `.d.mts` — stale, labels, ranking, and view-model functions.
- `src/components/MarketResearchDashboard.vue` — four-region container and top status bar.
- `src/components/MarketScoreCard.vue` — global/A-share score card.
- `src/components/MarketStyleGrid.vue` — six-style comparison.
- `src/components/IndustryHeatmap.vue` — 35-industry heatmap and four rankings.
- `src/views/HomeView.vue` — place research dashboard above debt details and news.
- `src/style.css` — dense desktop and responsive mobile styles.
- `tests/market-dashboard-model.test.mjs` and `tests/market-dashboard-api.test.mjs` — frontend model/API tests.

### Operations

- `ops/macos/run-market-dashboard.sh` — load parent `.env` and run the local job.
- `ops/macos/com.robot-ever.newsmonitor.market-dashboard.plist` — five-minute scheduler; job enforces 15-minute buckets.
- `ops/macos/install-market-dashboard-service.sh` — validate and install only this LaunchAgent.
- `README.md` — architecture, score semantics, data frequency, rollout, and failure behavior.

---

### Task 1: Versioned Scoring Core

**Files:**
- Create: `config/market-dashboard.json`
- Create: `tools/market_dashboard/__init__.py`
- Create: `tools/market_dashboard/scoring.py`
- Create: `tools/market_dashboard/tests/test_scoring.py`

**Interfaces:**
- Consumes: normalized source dictionaries with value, timestamp, unit, and source identity.
- Produces: `percentile_rank(values, value) -> float | None`, `weighted_score(components) -> ScoreResult`, `compute_completeness(components) -> int`, `classify_market_stage(scores, slopes, completeness) -> str | None`, and `build_dashboard_payload(inputs, previous, config) -> dict`.

- [ ] **Step 1: Write failing normalization and missing-data tests**

Add `test_percentile_winsorizes_extremes`, `test_reverse_indicator_changes_direction`, and `test_missing_component_reduces_completeness_without_zero_score`. Assert exact `0–100` bounds and weighted-denominator behavior.

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `python3 -m unittest tools.market_dashboard.tests.test_scoring -v`

Expected: import or missing-function failures.

- [ ] **Step 3: Implement normalization and weighted score primitives**

Implement the interfaces above using 5%/95% winsorization, rolling or cross-sectional percentile modes, explicit reverse flags, and integer output rounding only at the public boundary.

- [ ] **Step 4: Add failing tests for A-share, global, style, and industry formulas**

Use small deterministic fixtures and assert the exact weights from the design. Include a weight-sum assertion for every score family.

- [ ] **Step 5: Implement the four score families and completeness**

Read all weights and thresholds from `config/market-dashboard.json`; do not duplicate constants in Python.

- [ ] **Step 6: Add failing stage and comparison tests**

Cover all six stage labels, completeness below 50 returning no stage, same-clock comparisons, close fallback, and close-to-close comparison.

- [ ] **Step 7: Implement stage and comparison logic**

Expose `comparisonFallback` only when a fallback occurred; keep stage thresholds in configuration.

- [ ] **Step 8: Run tests and commit**

Run: `python3 -m unittest discover -s tools/market_dashboard/tests -v`

Expected: all scoring tests pass.

```bash
git add config/market-dashboard.json tools/market_dashboard
git commit -m "feat: add versioned market scoring core"
```

---

### Task 2: Wind, MX, and FRED Source Adapters

**Files:**
- Create: `tools/market_dashboard/sources.py`
- Create: `tools/market_dashboard/tests/test_sources.py`
- Create: `tools/market_dashboard/fixtures/wind-breadth.json`
- Create: `tools/market_dashboard/fixtures/wind-styles.json`
- Create: `tools/market_dashboard/fixtures/wind-industries.json`
- Create: `tools/market_dashboard/fixtures/fred-series.csv`
- Create: `tools/market_dashboard/fixtures/mx-global.json`

**Interfaces:**
- Consumes: injected command runner/fetcher and configuration from Task 1.
- Produces: `collect_wind_breadth(runner, config) -> SourceBatch`, `collect_wind_styles(runner, config) -> SourceBatch`, `collect_wind_industries(runner, config) -> SourceBatch`, `collect_global_inputs(runner, fetcher, config) -> SourceBatch`, and `parse_wind_content(envelope) -> list[dict]`.

- [ ] **Step 1: Save sanitized fixtures from verified response shapes**

Retain column names, units, timestamps, 6 styles, and all 35 industry identifiers; remove request IDs, credentials, and unrelated raw content.

- [ ] **Step 2: Write failing Wind parser tests**

Test nested `content[0].text`, unit retention, industry reordering, missing industry rejection, null values, and primary-sector naming differences.

- [ ] **Step 3: Implement Wind parser and command adapter**

Use only documented CLI calls. Probe once per parameter group, run serially, and stop a group on `AUTH_ERROR`, `RATE_LIMIT_ERROR`, `backend_error`, or malformed output.

- [ ] **Step 4: Write failing global-source tests**

Cover FRED `.` values, stale daily/monthly observations, MX partial cross-asset data, and source-mode separation.

- [ ] **Step 5: Implement global adapters**

Reuse the existing FRED series definitions where possible. Do not merge MX and Wind values for one metric; choose by configured role and record `sourceMode`.

- [ ] **Step 6: Add the market-open smoke command**

Add `python3 -m tools.market_dashboard.sources --probe` that prints only source names, row counts, field names, units, and timestamps—never raw credentials.

- [ ] **Step 7: Run tests and commit**

Run: `python3 -m unittest tools.market_dashboard.tests.test_sources -v`

Expected: all adapter tests pass without network access.

```bash
git add tools/market_dashboard
git commit -m "feat: add market dashboard data adapters"
```

---

### Task 3: Local Dashboard Job and Publisher

**Files:**
- Create: `tools/market_dashboard/job.py`
- Create: `tools/market_dashboard/tests/test_job.py`
- Create at runtime only: `../state/market-dashboard/last-success.json`
- Create at runtime only: `../state/service-health/market-dashboard.json`

**Interfaces:**
- Consumes: source adapters from Task 2 and `build_dashboard_payload` from Task 1.
- Produces: `should_collect(now, state, config) -> bool`, `run_job(args, deps) -> JobResult`, `publish_payload(payload, url, token, timeout) -> PublishResult`, and CLI flags `--dry-run`, `--fixture`, `--force`, `--skip-publish`.

- [ ] **Step 1: Write failing schedule and idempotency tests**

Cover A-share morning/afternoon sessions, lunch break, weekends, repeated 15-minute buckets, and one final-close snapshot.

- [ ] **Step 2: Implement session gate and lock/state handling**

Use Asia/Shanghai time. A repeated bucket returns success without collecting; `--force` bypasses only the schedule gate, not validation.

- [ ] **Step 3: Write failing publication tests**

Assert Bearer authentication, timeout, secret redaction, retry only for transient network/5xx failures, no retry for 4xx, and preservation of last-success state on failure.

- [ ] **Step 4: Implement payload validation and publisher**

Reject payloads with wrong versions, out-of-range scores, missing timestamps, or completeness below the schema requirements before any network call.

- [ ] **Step 5: Write failing fixture-mode end-to-end test**

Run all sanitized fixtures through collect → score → validate and assert 1 global object, 1 A-share object, 6 styles, and 35 industries.

- [ ] **Step 6: Implement orchestration and health-state output**

Health JSON records stage, observed time, source counts, completeness, last publish status, and redacted error code.

- [ ] **Step 7: Verify dry run and commit**

Run:

```bash
python3 -m unittest tools.market_dashboard.tests.test_job -v
python3 -m tools.market_dashboard.job --fixture --dry-run
```

Expected: tests pass; dry run prints only a compact payload summary.

```bash
git add tools/market_dashboard
git commit -m "feat: add local market dashboard publisher"
```

---

### Task 4: Cloudflare D1 Storage and Pages APIs

**Files:**
- Create: `migrations/0001_market_dashboard.sql`
- Create: `wrangler.toml`
- Create: `functions/_lib/market-dashboard.js`
- Create: `functions/api/market-dashboard/publish.js`
- Create: `functions/api/market-dashboard/latest.js`
- Create: `functions/api/market-dashboard/history.js`
- Create: `tests/market-dashboard-functions.test.mjs`

**Interfaces:**
- Consumes: `market-dashboard-v1` payloads from Task 3 and bindings `MARKET_DB`, `MARKET_DASHBOARD_PUBLISH_TOKEN`.
- Produces: POST publish, GET latest, and GET bounded history endpoints specified by the design.

- [ ] **Step 1: Write failing schema migration test**

Assert the SQL contains the required table, a unique observation key, latest index, and all spec columns. Add a unique constraint on `(observed_at, scoring_version)` for idempotency.

- [ ] **Step 2: Add migration and Wrangler binding configuration**

Use `pages_build_output_dir = "dist"`; leave the actual D1 database ID to the provisioning task.

- [ ] **Step 3: Write failing publish-handler tests**

Cover missing/wrong Bearer token, invalid JSON, body over 256 KiB, invalid version/range, duplicate idempotent publish, and older observation not replacing latest.

- [ ] **Step 4: Implement shared validation and publish handler**

Use constant-time token comparison where supported. Store the payload JSON only after validation; return stable JSON error codes without provider details.

- [ ] **Step 5: Write failing latest/history tests**

Cover empty D1 (`404 NO_SNAPSHOT`), latest selection, allowed `1d|5d|20d|90d` windows, invalid-window rejection, and chronological compact history.

- [ ] **Step 6: Implement read handlers and caching**

Set short public cache for latest and longer cache for history. Return UTC timestamps unchanged.

- [ ] **Step 7: Run Node tests and commit**

Run: `npm test`

Expected: all existing and market-dashboard function tests pass.

```bash
git add migrations wrangler.toml functions tests/market-dashboard-functions.test.mjs
git commit -m "feat: add D1 market dashboard API"
```

---

### Task 5: Frontend API and View Model

**Files:**
- Create: `src/features/market-dashboard/types.ts`
- Create: `src/features/market-dashboard/api.mjs`
- Create: `src/features/market-dashboard/api.d.mts`
- Create: `src/features/market-dashboard/model.mjs`
- Create: `src/features/market-dashboard/model.d.mts`
- Create: `tests/market-dashboard-api.test.mjs`
- Create: `tests/market-dashboard-model.test.mjs`

**Interfaces:**
- Consumes: endpoints from Task 4.
- Produces: `loadMarketDashboard(fetcher?, options?)`, `loadMarketHistory(window, fetcher?, options?)`, `deriveMarketDashboardView(payload, now)`, `rankIndustries(industries)`, and TypeScript types used by Task 6.

- [ ] **Step 1: Write failing API tests**

Cover success, HTTP error, invalid JSON, timeout, empty snapshot, and partial history without discarding the latest valid payload.

- [ ] **Step 2: Implement API loader**

Mirror the debt API's injectable fetcher and timeout pattern; never import mock data.

- [ ] **Step 3: Write failing view-model tests**

Cover score labels, stale thresholds, completeness below 50 suppressing stage, 70 threshold labels, comparison fallback badges, four industry rankings, and reordered industries.

- [ ] **Step 4: Implement view-model functions and declarations**

Keep presentation-only derivations in JavaScript; do not recompute core scores in the browser.

- [ ] **Step 5: Run tests and commit**

Run: `npm test`

Expected: all API/model tests pass.

```bash
git add src/features/market-dashboard tests/market-dashboard-api.test.mjs tests/market-dashboard-model.test.mjs
git commit -m "feat: add market dashboard frontend model"
```

---

### Task 6: Research Dashboard Components and Homepage Layout

**Files:**
- Create: `src/components/MarketResearchDashboard.vue`
- Create: `src/components/MarketScoreCard.vue`
- Create: `src/components/MarketStyleGrid.vue`
- Create: `src/components/IndustryHeatmap.vue`
- Modify: `src/views/HomeView.vue:1-36`
- Modify: `src/style.css:1-210`

**Interfaces:**
- Consumes: Task 5 loaders, view model, and TypeScript types.
- Produces: one responsive homepage research dashboard with global, A-share, styles, and industries above the existing debt/news content.

- [ ] **Step 1: Create score-card component with all degradation states**

Render three scores, 1d/5d changes, stage, contributors, completeness, data time, stale state, comparison fallback, loading skeleton, and error state.

- [ ] **Step 2: Create six-style grid**

Use fixed order from the design; show strength/heat/risk and five-day direction without a new route.

- [ ] **Step 3: Create 35-industry heatmap and rankings**

Support sorting by each score, four required rankings, keyboard-accessible inline expansion, and evidence factors only.

- [ ] **Step 4: Build the dashboard container**

Fetch latest and 5-day history, preserve last successful in-memory payload during refresh errors, and show schema/scoring versions in the status bar.

- [ ] **Step 5: Integrate into HomeView**

Order: market research dashboard → existing debt details → existing news grid; retain the right-side ticker.

- [ ] **Step 6: Add responsive styles**

Desktop first row is two cards; style grid is six compact items; mobile becomes one column and moves ticker below content. Risk, heat, strength, stale, and missing colors must remain distinct.

- [ ] **Step 7: Run tests, build, and visual inspection**

Run:

```bash
npm test
npm run build
```

Expected: tests pass and Vite production build completes.

Start `npm run dev`, inspect desktop and mobile widths, and capture screenshots for the implementation handoff.

- [ ] **Step 8: Commit**

```bash
git add src/components src/views/HomeView.vue src/style.css
git commit -m "feat: add market research homepage"
```

---

### Task 7: macOS Scheduling and Operational Health

**Files:**
- Create: `ops/macos/run-market-dashboard.sh`
- Create: `ops/macos/com.robot-ever.newsmonitor.market-dashboard.plist`
- Create: `ops/macos/install-market-dashboard-service.sh`
- Create: `tools/market_dashboard/tests/test_operations.py`
- Modify outside nested Git repo: `../scripts/intake_health_check.py`
- Modify outside nested Git repo: `../scripts/regression_service_reliability.py`

**Interfaces:**
- Consumes: Task 3 CLI and environment variables `MARKET_DASHBOARD_PUBLISH_URL`, `MARKET_DASHBOARD_PUBLISH_TOKEN`, `MX_APIKEY`, and Wind's existing configuration.
- Produces: one recoverable LaunchAgent and business-health status visible to the Financial Knowledge Repository health check.

- [ ] **Step 1: Write failing operations tests**

Assert wrapper loads the parent `.env` without echoing it, plist uses the wrapper and five-minute `StartInterval`, install script avoids destructive bootstrapping, and health check flags stale successful state.

- [ ] **Step 2: Implement wrapper, plist, and installer**

The job itself enforces 15-minute buckets. Logs go under `../logs/market-dashboard/` and rotate through the existing project log policy.

- [ ] **Step 3: Extend root health and regression checks**

Treat source delay during non-trading periods as normal; alert only when an expected bucket or close snapshot is missing.

- [ ] **Step 4: Run project-level regressions**

Run:

```bash
python3 -m unittest tools.market_dashboard.tests.test_operations -v
python3 ../scripts/regression_service_reliability.py
python3 ../scripts/intake_health_check.py
```

Expected: all tests pass; health is OK before installation with service marked not yet enabled, then OK after installation.

- [ ] **Step 5: Commit Git-owned files**

```bash
git add ops/macos tools/market_dashboard/tests/test_operations.py
git commit -m "ops: schedule market dashboard snapshots"
```

Record the verified root-file changes in the final handoff because the parent directory has no Git history.

---

### Task 8: Cloudflare Provisioning and Secure Deployment

**Files:**
- Modify: `wrangler.toml` with the created D1 database ID.
- Modify: `.gitignore` only if local Wrangler artifacts are not already excluded.
- No credential files are created.

**Interfaces:**
- Consumes: Cloudflare authentication already granted to Wrangler and the Pages project `newsmonitor`.
- Produces: production D1 database, remote migration, secret binding, and deployed Pages Functions.

- [ ] **Step 1: Re-verify Cloudflare account and project non-destructively**

Run the current Wrangler account/project listing commands and confirm the target project is exactly `newsmonitor` before creating resources.

- [ ] **Step 2: Create D1 and update binding**

Create database `newsmonitor-market-dashboard`, place its returned ID only in `wrangler.toml`, and apply `migrations/0001_market_dashboard.sql` locally then remotely.

- [ ] **Step 3: Generate and store the publish token**

Generate a high-entropy token without printing it, store it in parent `.env`, and set the matching Cloudflare Pages secret `MARKET_DASHBOARD_PUBLISH_TOKEN`.

- [ ] **Step 4: Verify endpoints before frontend rollout**

Deploy to a preview or production-safe Pages environment. Assert unauthorized publish is `401`, empty latest is `404 NO_SNAPSHOT`, an authenticated fixture publish succeeds, latest returns it, and history returns it once.

- [ ] **Step 5: Run a real local dry run and publish one snapshot**

Use `--force` only for this verified publish. Confirm D1 timestamps, versions, object counts, units, and no credential leakage.

- [ ] **Step 6: Run full build and deploy**

Run:

```bash
npm test
npm run build
```

Deploy through the existing GitHub-connected workflow or the verified Wrangler Pages path, but not both for the same revision.

- [ ] **Step 7: Commit binding configuration**

```bash
git add wrangler.toml .gitignore
git commit -m "ops: configure market dashboard D1"
```

---

### Task 9: End-to-End Verification, Documentation, and Gray Rollout

**Files:**
- Modify: `README.md:1-45`
- Create: `docs/market-dashboard-operations.md`
- Modify: `docs/superpowers/specs/2026-11-13-market-research-homepage-design.md` only for verified implementation notes, without changing approved product decisions.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verified production page, operational runbook, and a three-trading-day gray-rollout checklist.

- [ ] **Step 1: Write the operations runbook**

Document source roles, schedule, score versions, D1 migration, secret rotation, manual dry run, stale diagnosis, provider quota handling, rollback, and how to disable the LaunchAgent without deleting data.

- [ ] **Step 2: Run complete automated verification**

Run:

```bash
python3 -m unittest discover -s tools/market_dashboard/tests -v
python3 ../scripts/regression_service_reliability.py
npm test
npm run build
```

Expected: all commands exit 0.

- [ ] **Step 3: Verify the production UI**

Check desktop and mobile: four regions, latest timestamp, 6 styles, 35 industries, contributors, stale/error behavior, existing debt details, news cards, and ticker.

- [ ] **Step 4: Verify archive and operational consistency**

Confirm no Inbox/In Progress artifacts were created, no credentials entered Vault/Git/logs, root health remains OK, and D1 contains only processed scores and evidence summaries.

- [ ] **Step 5: Begin three-trading-day gray collection**

For each trading day record morning, afternoon, and close success; Wind row counts; field stability; API latency; quota errors; completeness; and stale flags. Keep the UI labeled `v0.1 / 试运行` until all three days pass.

- [ ] **Step 6: Update documentation and commit**

```bash
git add README.md docs
git commit -m "docs: document market research dashboard rollout"
```

- [ ] **Step 7: Final branch verification**

Run `git status --short`, review the full diff for secrets and generated data, and verify only intended files remain changed.

