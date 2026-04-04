# Architecture Decisions

## 2026-04-04: Added 8 new data sources inspired by WeThePeople

**Context:** Reviewed [Obelus-Labs-LLC/WeThePeople](https://github.com/Obelus-Labs-LLC/WeThePeople) for valuable data sources and methodology. Their platform has 39 sources focused on civic transparency; ours is general-purpose public data analysis.

**Decision:** Added 8 sources with broad utility: USASpending, ClinicalTrials.gov, OpenFDA, CFPB, SEC EDGAR, Federal Register, EPA GHGRP, FDIC. Skipped 20+ narrowly political sources (FEC, lobbying, congressional votes) as they don't fit our general-purpose mission.

**Rationale:** Prioritized sources that are (1) free with no/easy auth, (2) broadly useful for research, and (3) return structured data. All 8 return JSON from their download methods, ensuring consistent handling.

## 2026-04-04: Shared HTTP client with circuit breaker and disk cache

**Context:** Each source had its own `httpx.AsyncClient` with inconsistent retry/error handling. WeThePeople's centralized `HTTPClient` with circuit breaker was a clear improvement.

**Decision:** Created `http_client.py` with `SourceHTTPClient` class providing per-source circuit breakers, `tenacity`-based retry (3 attempts, exponential backoff), and `diskcache`-based response caching (1hr TTL, 500MB limit).

**Rationale:** Circuit breakers prevent cascade failures when a government API goes down. Disk cache survives restarts (unlike in-memory caches) and reduces API load during development. Used JSON serialization instead of pickle to mitigate CVE-2025-69872 in diskcache.

## 2026-04-04: PDF, XML, GeoJSON, ZIP format support in datastore

**Context:** The datastore only handled CSV, JSON, Parquet, and Excel. New and existing sources (Harvard Dataverse, HUD, data.gov) can return PDF reports, XML feeds, GeoJSON maps, or ZIP archives.

**Decision:** Added `pdfplumber` for PDF table extraction, `lxml` for XML parsing, custom GeoJSON flattener (properties + geometry → DataFrame), and ZIP extraction (finds largest supported file inside).

**Rationale:** PDF tables are common in government reports. XML is used by Federal Register and FDA APIs. GeoJSON appears in HUD and EPA datasets. ZIP is used by Harvard Dataverse and data.gov for multi-file downloads. All converters produce DataFrames that DuckDB can query.

## 2026-04-04: Nested JSON fallback with pd.json_normalize

**Context:** DuckDB's `read_json_auto()` fails on deeply nested JSON like FDA FAERS adverse events or SEC filing metadata with inconsistent nesting depth.

**Decision:** Added a fallback in `load_dataset()`: when `read_json_auto()` fails, unwrap common API response wrappers (`results`, `data`, `hits`, etc.) and flatten with `pd.json_normalize(max_level=2)`.

**Rationale:** This handles the 80% case without custom per-source flattening. Source adapters that need deeper control (ClinicalTrials, BLS) already do their own flattening before writing JSON.

## 2026-04-04: SSRF hardening — DNS rebinding guard and redirect validation

**Context:** CodeQL flagged the `_download_file` function for SSRF. The existing domain allowlist was solid but didn't protect against DNS rebinding or open redirects on allowed domains.

**Decision:** Added (1) DNS resolution check via `socket.getaddrinfo()` to block allowed hostnames that resolve to private IPs, and (2) an httpx `event_hook` that validates every redirect target against the same allowlist.

**Rationale:** Defence-in-depth. The allowlist prevents direct SSRF, the DNS check prevents rebinding attacks, and the redirect hook prevents open-redirect chaining through allowed domains.

## 2026-04-04: Self-service password change + admin password reset

**Context:** No way to change passwords. Users who forgot their password needed direct database access.

**Decision:** Added `PUT /api/auth/change-password` (authenticated, requires current password) and `PUT /api/admin/reset-password` (admin-only). Both use `user_store.set_password()`.

**Rationale:** Self-service reduces admin burden. Admin reset is needed for users who can't remember their password at all. Both validate password length (8-128 chars) via Pydantic.

## 2026-04-04: Sandbox enhanced with datetime and scipy.stats

**Context:** New data sources bring time series (FRED, BLS, FDIC quarterly), statistical analysis needs (clinical trials, adverse events), and financial data requiring date parsing.

**Decision:** Pre-injected `datetime` and `scipy_stats` (scipy.stats) into the sandbox globals. Updated AI prompts with guidance for financial format stripping, choropleth maps, BLS/FRED period codes, and nested column names.

**Rationale:** These are safe, read-only modules that dramatically expand what AI-generated analysis code can do without additional imports. The prompt guidance prevents common errors with the new data types.

## 2026-04-04: Search quality fixes for OWID, Chicago Health Atlas, Federal Register

**Context:** Testing "how is life span changing" returned only 4 marginal results — OWID (life expectancy charts), Chicago Health Atlas (life expectancy by community), and data.gov (NCHS death rates) all failed to return relevant data despite having it.

**Decision:** Three fixes: (1) OWID — truncate refined query to 3 keywords (their API AND-alls all terms, so long queries return nothing), (2) Chicago Health Atlas — add isinstance guard for subcategory entries that are strings instead of dicts, (3) Federal Register — handle document_number as list instead of string.

**Rationale:** OWID was the most impactful — "life expectancy" alone returns perfect results but the 8-keyword refined query returned zero. The other two were runtime crashes that silently dropped results.

## 2026-04-04: Stress test bugs — SEC EDGAR, USASpending, .tab files

**Context:** Stress test (10 queries across 25 sources) revealed 3 runtime bugs: SEC EDGAR crashes on list-type `accession_no`, USASpending 422 errors from long keyword phrases, Harvard Dataverse `.tab` files fail DuckDB auto-detection.

**Decision:** (1) SEC EDGAR — unwrap list to string for `accession_no`, (2) USASpending — split query into individual keywords via `extract_keywords()`, (3) Datastore — hint `delim='\t'` for `.tsv`/`.tab` files.

**Rationale:** All three were silent failures that dropped entire sources from search results. After fixes, 9/10 stress test queries (previously failing) load successfully.

## 2026-04-04: Chart titles rendered as HTML instead of Plotly SVG

**Context:** Long chart titles were truncated/clipped inside Plotly's SVG viewport (60px top margin). Users couldn't read full titles, especially in a 2-column grid.

**Decision:** Extract title from Plotly spec, render as a styled HTML `<div>` above the chart with `word-wrap: break-word`. Reduced Plotly top margin from 60px to 20px. Fixed grid to `repeat(2, 1fr)` for consistent 2-column layout.

**Rationale:** HTML text wraps naturally; SVG text does not. This gives full title visibility at any chart width without requiring user interaction.

## 2026-04-04: Dashboard auto-exit on last unpin

**Context:** Unpinning the last chart in dashboard view hid the "Exit Dashboard" button, trapping users in an empty view with no way back.

**Decision:** (1) Auto-exit dashboard view when `pinnedIndices` becomes empty, (2) Always show the back button while in dashboard view regardless of pin count. Renamed button to "Back to Analysis".

**Rationale:** Simple state management fix. The button visibility condition changed from `pinnedIndices.size > 0` to `pinnedIndices.size > 0 || dashboardView`.

## 2026-04-04: GitHub Actions workflow permissions

**Context:** CodeQL flagged 6 alerts for missing `permissions` block in `ci.yml`, meaning all jobs had write access to the repository.

**Decision:** Added top-level `permissions: contents: read` to restrict all jobs to read-only by default.

**Rationale:** Principle of least privilege. Only the deploy job needs write access (handled via Azure credentials, not GITHUB_TOKEN).
