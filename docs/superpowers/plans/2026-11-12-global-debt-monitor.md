# Global Debt Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a live, fault-tolerant global debt risk module to the NewsMonitor homepage.

**Architecture:** A pure JavaScript model parses FRED CSV and derives signals; a TypeScript API adapter loads public series through the existing Cloudflare proxy; a Vue component renders the four observation themes without coupling them to the news store. The homepage owns placement only.

**Tech Stack:** Vue 3, TypeScript, Vite, Node test runner, Cloudflare Pages Functions, FRED CSV

**Spec:** `docs/superpowers/specs/2026-11-12-global-debt-monitor-design.md`

## Global Constraints

- Preserve the existing Vue/Vite/Cloudflare Pages architecture and dark dense visual language.
- Require no account, API key, paid feed, or database.
- Label daily and monthly data frequencies accurately.
- Treat thresholds as research heuristics, never as trading advice.
- A failed series must not prevent successful series from rendering.

## Review Focus

- FRED missing-value marker `.` must not become zero.
- Out-of-order or malformed CSV rows must not corrupt latest/previous selection.
- Partial network failure must retain successful indicators.
- Monthly European/Japanese observations must visibly carry their observation date and frequency.
- Narrow screens must not create overlapping fixed columns.

---

### Task 1: Debt signal model

**Files:**
- Create: `src/features/debt-monitor/model.mjs`
- Create: `tests/debt-monitor-model.test.mjs`
- Modify: `package.json`

**Interfaces:**
- Produces: `parseFredCsv(text)`, `summarizeSeries(points)`, `deriveDebtDashboard(seriesMap)`.

- [ ] Write failing Node tests for missing values, malformed rows, latest change, European spreads, partial data, and risk levels.
- [ ] Run `npm test` and confirm failure because the production module is missing.
- [ ] Implement the three pure functions with literal thresholds from the design.
- [ ] Run `npm test` and confirm all model tests pass.

### Task 2: Public data adapter and Cloudflare proxy

**Files:**
- Create: `src/features/debt-monitor/api.ts`
- Modify: `functions/[[catchall]].js`
- Modify: `vite.config.ts`

**Interfaces:**
- Consumes: `parseFredCsv(text)`.
- Produces: `loadDebtSeries(): Promise<DebtSeriesLoadResult>` with per-series success/error state.

- [ ] Add a failing contract test that exercises the adapter with an injected fetch implementation and partial HTTP failure.
- [ ] Run `npm test` and confirm failure because the adapter contract does not exist.
- [ ] Implement fixed FRED series metadata, injected fetch support, and partial-result aggregation.
- [ ] Add the allowlisted `/proxy-fred` target to development and Pages Function proxy maps.
- [ ] Run `npm test` and confirm all tests pass.

### Task 3: Dashboard component and responsive placement

**Files:**
- Create: `src/components/DebtRiskDashboard.vue`
- Modify: `src/views/HomeView.vue`
- Modify: `src/style.css`

**Interfaces:**
- Consumes: `loadDebtSeries()` and `deriveDebtDashboard(seriesMap)`.
- Produces: a refreshable, fault-tolerant homepage module with four themes and a composite state.

- [ ] Implement semantic component states for loading, partial data, error, and populated data.
- [ ] Place the component above news cards and replace inline fixed layout rules with responsive classes.
- [ ] Run `npm test` and `npm run build`; both must exit 0.

### Task 4: Browser QA, documentation, and deployment

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: completed module and existing GitHub/Cloudflare Pages deployment.
- Produces: documented local/deploy workflow and a verified public release.

- [ ] Document architecture, commands, data frequencies, proxy path, and research-only disclaimer.
- [ ] Run full tests and production build with clean exit codes.
- [ ] Preview at desktop and narrow viewport; verify no overlap and readable error states.
- [ ] Commit and push to `main`, then verify Cloudflare Pages serves the new module and live data.
