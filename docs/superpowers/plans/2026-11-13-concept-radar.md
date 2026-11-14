# Concept Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the existing 35-industry dashboard and add a separately scored concept radar with 25 fixed core concepts and 10 end-of-day dynamic concepts.

**Architecture:** Wind specialized index-price data supplies all numeric concept scores; MX remains discovery-only and does not enter v0.1 concept scoring. A versioned concept universe is collected and normalized as one cross-section, a pure selector produces the 10 dynamic slots, and the public payload advances to `market-dashboard-v2` with an independent `concept-score-v0.1`. The Vue homepage renders dynamic concepts by default and core concepts in a second tab without changing the existing industry component.

**Tech Stack:** Python 3.13, Wind MCP CLI, JSON configuration, `unittest`, Cloudflare Pages Functions and D1, Node test runner, Vue 3, TypeScript, Vite.

**Spec:** `docs/superpowers/specs/2026-11-13-concept-radar-design.md`

## Global Constraints

- Keep all 35 current Wind industries, six styles, global, A-share, debt and news behavior unchanged.
- Numeric concept scoring uses Wind specialized index-price fields only; MX values and Wind natural-language technical/fundamental results do not enter scores.
- Maintain exactly 25 configured core concepts and exactly 10 dynamic concepts selected from a verified 60–100 concept A-share universe.
- Dynamic identity changes only after the close; intraday snapshots reuse the current trading day's selection.
- Cross-sectional normalization uses the full eligible concept universe, never only the 35 visible concepts.
- Do not store provider raw responses or credentials in D1, local state, API responses or logs.
- Missing data remains missing; no zero fill and no silent MX fallback.
- Public schema becomes `market-dashboard-v2`; existing market objects keep `market-score-v0.1`, concepts use `concept-score-v0.1` and selection uses `concept-selection-v0.1`.
- Extend `sourceMode` with exactly `concepts: "wind"`; do not claim MX discovery on a snapshot unless separate evidence is actually present.
- The serialized publish body remains at or below 256 KiB.

## Review Focus

- A Wind batch succeeds partially or returns the wrong identities: reject the entire concept batch and preserve the last successful dynamic selection.
- A concept is returned with ambiguous units, missing timestamp or a duplicate code: exclude it from selection and lower completeness rather than coercing data.
- A previous dynamic concept falls sharply during its two-day minimum hold: retain it only if its data remains valid; invalid concepts leave immediately.
- The v2 payload contains a dynamic concept duplicated in core or two dynamic slots with the same ID: validation must reject the payload before any network write.
- A dynamic concept has no same-ID 1-day or 5-day snapshot: publish it with an explicit unavailable-comparison reason and render that state honestly.

---

## File Structure

- `config/market-concepts.json` — versioned eligible Wind concept universe, 25 core IDs, category labels and selection settings.
- `config/market-dashboard.json` — concept score weights and selection normalization settings.
- `tools/market_dashboard/concepts.py` — config validation, selection-score calculation and deterministic dynamic-slot governance.
- `tools/market_dashboard/sources.py` — batched Wind concept-price collection and identity/unit preservation.
- `tools/market_dashboard/job.py` — concept input derivation, orchestration, state reuse and v2 payload validation.
- `tools/market_dashboard/scoring.py` — generic concept-family scoring and concept comparisons.
- `tools/market_dashboard/fixtures/wind-concepts.json` — sanitized concept source fixture.
- `tools/market_dashboard/tests/test_concepts.py` — universe validation and dynamic selection tests.
- Existing Python test files — collector, scorer, job and operational regression coverage.
- `functions/_lib/market-dashboard.js` — server-side v2 validation and compact concept history.
- Pages API handlers — v2 latest/history version checks.
- `src/features/market-dashboard/{api.mjs,types.ts,model.mjs}` — browser v2 validation, types, presentation and concept rankings.
- `src/components/ConceptRadar.vue` — dynamic/core tabs, concept heatmap, rankings and details.
- `src/components/MarketResearchDashboard.vue` and `src/style.css` — mount and responsive layout.
- Existing Node tests — contract, Functions, model and component regression coverage.

### Task 1: Versioned concept universe and Wind collector

**Files:**
- Create: `config/market-concepts.json`
- Create: `tools/market_dashboard/fixtures/wind-concepts.json`
- Create: `tools/market_dashboard/concepts.py`
- Create: `tools/market_dashboard/tests/test_concepts.py`
- Modify: `tools/market_dashboard/sources.py`
- Modify: `tools/market_dashboard/tests/test_sources.py`

**Interfaces:**
- Produces: `load_concept_config(path: str | Path | None = None) -> dict`
- Produces: `concept_definitions(config: dict) -> tuple[tuple[str, str], ...]`
- Produces: `core_concept_ids(config: dict) -> tuple[str, ...]`
- Produces: `collect_wind_concepts(runner, dashboard_config, concept_config) -> SourceBatch`

- [ ] **Step 1: Write failing concept-config tests**

Assert `selectionVersion == "concept-selection-v0.1"`, 60–100 unique eligible IDs, exactly 25 unique core IDs, every core ID belongs to the universe, every ID ends in `.WI`, and excluded prefixes/names for HK, US, broker gold picks, region-only, ownership-only and temporary ranking indices are rejected.

- [ ] **Step 2: Run the focused tests and confirm failure**

Run: `python3 -m unittest tools.market_dashboard.tests.test_concepts -v`  
Expected: FAIL because `tools.market_dashboard.concepts` and the configuration do not exist.

- [ ] **Step 3: Resolve and record the verified universe**

Use Wind `index_data.get_index_basicinfo` to resolve standard codes, names and constituent counts, then verify the complete field set with `index_data.get_index_price_indicators` in batches of at most 50. Seed the 25 core intents across these five groups, five per group:

1. AI and digital infrastructure: artificial intelligence, AI compute, data centers, cloud computing, data elements;
2. Semiconductors and key hardware: semiconductor selection, memory chips, third-generation semiconductors, lithography, PCB;
3. Advanced manufacturing: humanoid robots, industrial machine tools, robot actuators/reducers, low-altitude economy, industrial automation;
4. Energy transition and materials: solid-state batteries, energy storage, charging infrastructure, ultra-high voltage/grid equipment, rare-earth/performance materials;
5. Defense, space, health and structural consumption: commercial space, defense informatization, innovative drugs, weight-loss drugs, silver economy.

If an intent has no stable Wind concept with the required fields, replace it only within the same group and document the resolved name in `market-concepts.json`.

- [ ] **Step 4: Implement strict config loading**

Implement `load_concept_config`, `concept_definitions` and `core_concept_ids`. Reject malformed versions, counts, duplicates, unknown core IDs, unsafe names and non-Wind codes with `ConceptConfigError`; never repair invalid configuration implicitly.

- [ ] **Step 5: Write failing collector tests**

Cover two batches for more than 50 codes, exact identity coverage, duplicate/wrong/missing IDs, ambiguous units, missing timestamps, a first-batch probe failure that prevents later calls, and a second-batch failure that rejects the full collection.

- [ ] **Step 6: Implement batched concept collection**

Add `CONCEPT_PRICE_FIELDS` with exact specialized fields: latest trade date/time, Chinese name, 1/5/20-day returns, amount, turnover, 1/5/20-day main flow, up/down/flat counts and Wind code. Collect serially in chunks of at most 50, preserve provider values/units, require full identity equality, and return one `SourceBatch(source="Wind", source_mode="wind")` only when all batches validate.

- [ ] **Step 7: Add the sanitized fixture and pass focused tests**

Run:

```bash
python3 -m unittest tools.market_dashboard.tests.test_concepts -v
python3 -m unittest tools.market_dashboard.tests.test_sources -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```bash
git add config/market-concepts.json tools/market_dashboard/concepts.py tools/market_dashboard/fixtures/wind-concepts.json tools/market_dashboard/sources.py tools/market_dashboard/tests/test_concepts.py tools/market_dashboard/tests/test_sources.py
git commit -m "feat: add verified concept universe and collector"
```

### Task 2: Concept scoring and deterministic dynamic selection

**Files:**
- Modify: `config/market-dashboard.json`
- Modify: `tools/market_dashboard/concepts.py`
- Modify: `tools/market_dashboard/job.py`
- Modify: `tools/market_dashboard/scoring.py`
- Modify: `tools/market_dashboard/tests/test_concepts.py`
- Modify: `tools/market_dashboard/tests/test_scoring.py`

**Interfaces:**
- Consumes: Task 1 `SourceBatch` rows and concept configuration.
- Produces: `derive_concept_candidates(batch: SourceBatch, market_amount: float | None, market_risk: int | None, now: datetime, config: dict) -> list[dict]`
- Produces: `select_dynamic_concepts(candidates: list[dict], previous: list[dict], market_date: str, config: dict) -> list[dict]`
- Produces: `build_concept_payload(candidates: list[dict], previous_dynamic: list[dict], market_date: str, selected_at: str, config: dict) -> dict`

- [ ] **Step 1: Write failing concept-score tests**

Assert the exact concept weights from the design, full-universe cross-sectional histories, no MX inputs, unit rejection, missing-value propagation, separate `concept-score-v0.1`, and unchanged industry score results for the existing fixture.

- [ ] **Step 2: Run focused scoring tests and confirm failure**

Run: `python3 -m unittest tools.market_dashboard.tests.test_scoring tools.market_dashboard.tests.test_concepts -v`  
Expected: FAIL because the concept family and selector do not exist.

- [ ] **Step 3: Add concept score configuration**

Add the exact strength/heat/risk weights from the approved design to `families.concept`. Add selection weights `momentum=35`, `flow=30`, `breadth=20`, `activity=15`, `minimumHoldTradingDays=2`, `exitBufferRank=15`, `dynamicSlots=10`, and `minimumCompleteness=70`.

- [ ] **Step 4: Implement full-universe concept derivation**

Implement `derive_concept_candidates` using the same unit-checked helpers as industries, but create concept-specific indicators and histories from every fresh eligible candidate. Derive momentum acceleration only from returned 1/5/20-day fields; do not call technical/fundamental natural-language tools.

- [ ] **Step 5: Write failing governance tests**

Cover deterministic ties, core exclusion, exactly 10 unique IDs, two-day valid retention, immediate invalid-data exit, rank-15 buffer behavior after the hold, no intraday identity change, first-day selection, and fewer-than-10 eligible candidates causing an explicit selection failure.

- [ ] **Step 6: Implement selection and concept payload assembly**

Compute a separate 0–100 selection score from normalized momentum, flow, breadth and activity. At a close snapshot, retain valid prior members for two trading days, then retain only members ranked 15 or better; fill remaining slots by score, then flow, 5-day strength and Wind code. Intraday snapshots reuse the persisted same-day dynamic list. Emit `selectionScore`, `selectedOn` and `retainedTradingDays` only on dynamic objects.

- [ ] **Step 7: Run focused and Python regression tests**

Run:

```bash
python3 -m unittest tools.market_dashboard.tests.test_concepts tools.market_dashboard.tests.test_scoring -v
python3 -m unittest discover -s tools/market_dashboard/tests -v
```

Expected: PASS, including the unchanged industry fixture scores.

- [ ] **Step 8: Commit Task 2**

```bash
git add config/market-dashboard.json tools/market_dashboard/concepts.py tools/market_dashboard/job.py tools/market_dashboard/scoring.py tools/market_dashboard/tests
git commit -m "feat: score concepts and select dynamic themes"
```

### Task 3: Local job, v2 payload and state behavior

**Files:**
- Modify: `tools/market_dashboard/job.py`
- Modify: `tools/market_dashboard/tests/test_job.py`
- Modify: `tools/market_dashboard/tests/test_operations.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: Task 1 collection and Task 2 concept payload assembly.
- Produces: `market-dashboard-v2` payload with `concepts.selectionVersion`, `concepts.scoringVersion`, `concepts.selectedAt`, `concepts.core[25]`, and `concepts.dynamic[10]`.

- [ ] **Step 1: Write failing v2 job tests**

Assert fixture collection includes concepts; v2 validation requires 25/10 unique, disjoint concept arrays; source modes include `concepts: "wind"` and `conceptDiscovery: "mx"`; the body is at most 256 KiB; concept collection failure does not corrupt persisted selection; and a successful close snapshot advances selection state exactly once.

- [ ] **Step 2: Run focused job tests and confirm failure**

Run: `python3 -m unittest tools.market_dashboard.tests.test_job -v`  
Expected: FAIL because the local job still emits v1 without concepts.

- [ ] **Step 3: Integrate concepts into collection and derivation**

Load `config/market-concepts.json` once per run, collect concept batches after the one-code breadth probe, derive candidate inputs against the full universe, and build core/dynamic payloads. Keep all existing non-concept groups independent.

- [ ] **Step 4: Upgrade local validation and safe state**

Require v2 and concept versions, exact counts, disjoint identities, allowed dynamic metadata, valid timestamps and source names. Extend health source counts with `concepts` and `sourceMode` with `concepts: "wind"`. Recompute overall completeness across all 78 visible score objects: global + A-share + 6 styles + 35 industries + 25 core concepts + 10 dynamic concepts. Persist only derived payloads and selection metadata; do not persist source rows.

- [ ] **Step 5: Add failure and schedule behavior**

If concept collection fails, publish the other market groups only when a previously validated concept block can be carried forward and marked stale; otherwise fail validation rather than fabricate concepts. Intraday runs reuse the day's selection, and close runs select once per bucket.

- [ ] **Step 6: Update operator documentation**

Document v2 counts, concept source responsibility, dry-run output and the rule that MX discovers but does not score concepts.

- [ ] **Step 7: Run local fixture and regression verification**

Run:

```bash
python3 -m unittest discover -s tools/market_dashboard/tests -v
python3 -m tools.market_dashboard.job --fixture --dry-run
```

Expected: PASS and a derived-only v2 payload containing 25 core and 10 dynamic concepts.

- [ ] **Step 8: Commit Task 3**

```bash
git add tools/market_dashboard/job.py tools/market_dashboard/tests README.md
git commit -m "feat: publish concept radar payloads locally"
```

### Task 4: Cloudflare Functions and D1 history contract

**Files:**
- Modify: `functions/_lib/market-dashboard.js`
- Modify: `functions/api/market-dashboard/latest.js`
- Modify: `functions/api/market-dashboard/history.js`
- Modify: `functions/api/market-dashboard/publish.js`
- Modify: `tests/market-dashboard-functions.test.mjs`

**Interfaces:**
- Consumes: Task 3 v2 payload.
- Produces: latest v2 response and compact history snapshots containing core/dynamic concepts.

- [ ] **Step 1: Write failing Functions tests**

Add a valid v2 fixture and mutations for wrong versions, 24/26 core, 9/11 dynamic, duplicates, core/dynamic overlap, unsafe selection metadata, unknown concept source mode, payloads over 256 KiB and missing dynamic comparison reasons.

- [ ] **Step 2: Run focused Node tests and confirm failure**

Run: `node --test tests/market-dashboard-functions.test.mjs`  
Expected: FAIL because server validation only accepts v1.

- [ ] **Step 3: Implement strict v2 validation**

Export `SCHEMA_VERSION = "market-dashboard-v2"`; validate the nested concept block, per-object dynamic metadata, versions, identity separation and source modes. Keep the same bounded read, authorization, D1 transaction and payload-size rules.

- [ ] **Step 4: Extend compact history**

Include `concepts.core` and `concepts.dynamic` compact objects plus concept versions and selection time. Do not include selection score, contributors, raw source data or source mode in history.

- [ ] **Step 5: Pass focused and complete Node tests**

Run:

```bash
node --test tests/market-dashboard-functions.test.mjs
npm test
```

Expected: PASS.

- [ ] **Step 6: Commit Task 4**

```bash
git add functions tests/market-dashboard-functions.test.mjs
git commit -m "feat: serve concept radar snapshots"
```

### Task 5: Browser contract, presentation model and concept rankings

**Files:**
- Modify: `src/features/market-dashboard/api.mjs`
- Modify: `src/features/market-dashboard/api.d.mts`
- Modify: `src/features/market-dashboard/types.ts`
- Modify: `src/features/market-dashboard/model.mjs`
- Modify: `src/features/market-dashboard/model.d.mts`
- Modify: `tests/market-dashboard-api.test.mjs`
- Modify: `tests/market-dashboard-model.test.mjs`

**Interfaces:**
- Consumes: Task 4 latest/history responses.
- Produces: `MarketConceptsPayload`, `MarketConceptView`, `conceptRankings`, `coreConcepts`, and `dynamicConcepts` on `MarketDashboardView`.

- [ ] **Step 1: Write failing browser-contract tests**

Mirror all server v2 concept mutations, validate compact history concepts, and assert v1 or malformed concept responses fail closed without clearing a prior successful result.

- [ ] **Step 2: Run focused API tests and confirm failure**

Run: `node --test tests/market-dashboard-api.test.mjs`  
Expected: FAIL because the browser accepts only v1.

- [ ] **Step 3: Add exact TypeScript contracts and runtime validation**

Define nested concept versions and arrays, allowed dynamic metadata, concept source modes and compact history types. Runtime validation must enforce the same counts, disjoint IDs, versions and numeric bounds as the server.

- [ ] **Step 4: Write failing presentation tests**

Assert core preserves configured order, dynamic preserves selection order, rankings are deterministic, new concepts display unavailable comparisons, stale source timestamps propagate, and industry rankings remain unchanged.

- [ ] **Step 5: Extend the model**

Reuse `present()` and generalized ranking logic without mutating the payload. Return separately presented core/dynamic arrays and rankings for each tab; do not merge them with industry rankings.

- [ ] **Step 6: Pass focused model/API tests**

Run:

```bash
node --test tests/market-dashboard-api.test.mjs tests/market-dashboard-model.test.mjs
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```bash
git add src/features/market-dashboard tests/market-dashboard-api.test.mjs tests/market-dashboard-model.test.mjs
git commit -m "feat: model concept radar data in the browser"
```

### Task 6: Concept radar user interface

**Files:**
- Create: `src/components/ConceptRadar.vue`
- Modify: `src/components/MarketResearchDashboard.vue`
- Modify: `src/style.css`
- Modify: `tests/market-dashboard-components.test.mjs`

**Interfaces:**
- Consumes: Task 5 `MarketConceptView[]` and per-tab rankings.
- Produces: accessible dynamic/core tabs and concept cards on the homepage.

- [ ] **Step 1: Write failing component tests**

Assert “动态热点 10” is the default tab, “核心概念 25” is available, only the active tab's cards render, summary leaders and selection time appear, four rankings are scoped to the active tab, Wind scoring/MX discovery wording is accurate, and stale/missing/newly-selected states are visible.

- [ ] **Step 2: Run component tests and confirm failure**

Run: `node --test tests/market-dashboard-components.test.mjs`  
Expected: FAIL because `ConceptRadar.vue` does not exist.

- [ ] **Step 3: Implement `ConceptRadar.vue`**

Use native buttons with `role="tab"`, `aria-selected` and connected tab panels. Reuse score bands and `MarketScoreCard` details, but keep concept-specific labels and data attributes. Default to dynamic and keep tab state local.

- [ ] **Step 4: Mount the module and add responsive styles**

Place the radar immediately after `IndustryHeatmap`. Desktop shows the 10 dynamic cards in a compact grid; core uses the same grid only when selected. Mobile keeps dynamic as the default and renders a two-column compact grid without pre-rendering the hidden 25-card panel.

- [ ] **Step 5: Pass component tests and production build**

Run:

```bash
node --test tests/market-dashboard-components.test.mjs
npm test
npm run build
```

Expected: PASS and a successful Vue/TypeScript production build.

- [ ] **Step 6: Commit Task 6**

```bash
git add src/components/ConceptRadar.vue src/components/MarketResearchDashboard.vue src/style.css tests/market-dashboard-components.test.mjs
git commit -m "feat: add concept radar to the homepage"
```

### Task 7: Live shadow verification and release readiness

**Files:**
- Modify if required by observed provider shape: concept source/config/test files only
- Modify: `docs/superpowers/specs/2026-11-13-concept-radar-design.md` status line
- Create: `docs/verification/2026-11-13-concept-radar.md`

**Interfaces:**
- Consumes: completed Tasks 1–6.
- Produces: verified live dry-run evidence and a release-ready branch.

- [ ] **Step 1: Run live dry-run without publishing**

Run the local job with real configured sources, `--force --dry-run`, and a temporary state root. Record only counts, completeness, versions, payload byte size, concept identities and safe error codes; do not record credentials or raw responses.

- [ ] **Step 2: Verify live invariants**

Confirm 35 industries remain unchanged, concept universe meets its configured size, core=25, dynamic=10, arrays are disjoint, every scored concept has valid Wind timestamps/units, body size is within 256 KiB, and no MX values appear in score contributors.

- [ ] **Step 3: Visually inspect desktop and mobile builds**

Check default dynamic tab, core tab switching, expanded details, missing/stale/new states, industry preservation and homepage density at desktop and mobile widths.

- [ ] **Step 4: Run the complete verification suite**

Run:

```bash
python3 -m unittest discover -s tools/market_dashboard/tests -v
npm test
npm run build
git diff --check
```

Expected: all tests pass, build succeeds and no whitespace errors are reported.

- [ ] **Step 5: Write the verification record and mark design implemented**

Document commands, counts, payload size, known provider limitations and any intentionally unavailable fields. Change the design status from `已批准，待实施` to `已实施，待发布` only after all checks pass.

- [ ] **Step 6: Commit Task 7**

```bash
git add docs/superpowers/specs/2026-11-13-concept-radar-design.md docs/verification/2026-11-13-concept-radar.md
git commit -m "docs: verify concept radar release"
```

### Task 8: Production release and post-deploy verification

**Files:**
- Modify only if verification exposes a release-specific defect: the owning source and test file
- Modify: `docs/verification/2026-11-13-concept-radar.md`

**Interfaces:**
- Consumes: Task 7 verified build and existing `newsmonitor` Pages/D1 bindings.
- Produces: a production Pages deployment and the first valid v2 production snapshot.

- [ ] **Step 1: Confirm the release target without changing infrastructure**

Verify `wrangler.toml` still points to Pages project `newsmonitor`, output `dist`, and the existing `newsmonitor-market-dashboard` D1 binding. Do not create, replace or migrate a database; the snapshot table already stores versioned JSON.

- [ ] **Step 2: Deploy the verified build through the existing Wrangler path**

Run the current repository's Pages deployment for project `newsmonitor`. Do not rotate secrets and do not enable a second GitHub-triggered deployment path.

- [ ] **Step 3: Publish the first live v2 snapshot**

Run the market-dashboard job once with `--force` through the existing authenticated publish endpoint. Require a successful publish before calling the feature live.

- [ ] **Step 4: Verify production behavior**

Check the canonical homepage, `/api/market-dashboard/latest`, and `/api/market-dashboard/history?window=5d`. Confirm v2, 35 industries, 25 core concepts, 10 dynamic concepts, correct source wording, responsive tab behavior and no regression in debt/news modules.

- [ ] **Step 5: Record immutable deployment evidence**

Add the Pages deployment URL, canonical URL, first v2 observed time, safe counts, completeness and verification commands to the verification record. Never include tokens, raw provider payloads or D1 identifiers beyond the already versioned binding name.

- [ ] **Step 6: Commit release evidence**

```bash
git add docs/verification/2026-11-13-concept-radar.md
git commit -m "docs: record concept radar deployment"
```

