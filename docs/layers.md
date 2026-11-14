# Tables by layer

This page describes every table in the Portfolio Risk Lab lakehouse, layer by layer: what each table is for, what one row means (grain), its key, and how it is written.

- **Full column lists** live in [`data_dictionary.md`](data_dictionary.md). That file is generated from `src/portfolio_risk_lab/schemas.py`, the single source of truth for table design. This page does not repeat column types, so the two cannot drift apart.
- **Data flow between tables** is drawn in [`lineage.md`](lineage.md).
- **Status:** raw, bronze and silver were designed in Session 4. Gold was designed in Session 5 and becomes authoritative once its specs are added to `schemas.py`.

## Storage at a glance

| Layer | Physical location | Format | Write pattern | In Git? |
|---|---|---|---|---|
| raw | `$RISKLAB_DATA/raw/batch_id=<YYYYMMDDTHHMMSSZ>/` | Parquet + JSON manifest | Append-only, never overwritten | No |
| bronze | `$RISKLAB_DATA/warehouse/` (namespace `bronze`) | Iceberg, SQLite catalog | Append by `batch_id` | No |
| silver | `$RISKLAB_DATA/warehouse/` (namespace `silver`) | Iceberg | Idempotent rebuild from one chosen batch | No |
| gold | `$RISKLAB_DATA/warehouse/` (namespace `gold`) | Iceberg | Idempotent: rerun replaces rows with the same key | No |
| mc_runs | `$RISKLAB_DATA/mc_runs/run_id=<id>/` | Parquet float32 + JSON manifest | One folder per run; deleted after experiment | No |
| exports | `$RISKLAB_DATA/exports/` | HTML, PNG, CSV | Overwritten per report | No |

`$RISKLAB_DATA` = `/Volumes/RiskLab/risklab-data` (a dedicated APFS sparse-bundle volume). Only code and docs are committed to GitHub.

## Conventions (all layers)

- `snake_case` names. Table suffixes: `_b` bronze, `_s` silver, `_g` gold, `_w` work.
- Technical columns on every Iceberg table: `ingest_ts` (timestamptz, UTC), `source_system`, `batch_id`.
- Time-versioned config tables use a half-open interval `[valid_from, valid_to)`. A change closes the old row and inserts a new one, so a backtest always sees the weights that were valid on each date.
- Dates are `date`, never timezone-aware timestamps.
- Sign convention: return < 0 is a loss. VaR and ES are stored as **positive fractions of portfolio value**. For example, `var_pct = 0.087` means a loss of at most 8.7% at the stated confidence.
- Key columns are never `double`. Confidence levels and quantiles are stored as integer basis points (`confidence_bp` 9500, 9750, 9900; `quantile_bp` 100 … 9900), because floating-point equality filters fail silently.
- Iceberg identifier fields declare the key but do not enforce uniqueness. Duplicate checks are data-quality rules in the pipeline.
- No table is partitioned yet: total volume is a few MB. Revisit with the VN market extension (E3).

---

## raw

Untouched downloads, kept as evidence and for reproducibility.

| Object | Grain | Key | Produced by | Notes |
|---|---|---|---|---|
| raw prices (Parquet) | 1 ticker × 1 trading day × 1 download | `ticker`, `trade_date`, `batch_id` | `scripts/fetch_prices_raw.py` | `batch_id` = UTC download time; the manifest records tickers, `START`, `END` (exclusive), yfinance version and `auto_adjust` |

## bronze

Everything the source sent, typed and stamped, nothing dropped.

| Table | Grain | Key | Purpose |
|---|---|---|---|
| `bronze.prices_daily_b` | 1 ticker × 1 trading day × 1 batch | `ticker`, `trade_date`, `batch_id` | Typed copy of raw. Price columns are nullable, so gaps in the source stay visible. Several batches coexist: Yahoo rewrites historical `adj_close`, so batches can differ. |

**Do not compute statistics on bronze directly.** With two batches loaded, rows interleave (A₁₆, B₁₆, A₁₇, …): half the returns are ≈ 0 and volatility comes out about 29% too low (σ/√2), with no error raised.

## silver

Clean, conformed, one version of the truth per business key.

| Table | Grain | Key | Purpose |
|---|---|---|---|
| `silver.returns_daily_s` | 1 ticker × 1 trading day | `ticker`, `trade_date` | Adjusted prices and daily returns from **one** chosen batch. Price columns are required; rows with missing prices are removed and the next row carries `dq_flag` and a large `gap_days`. |
| `silver.instruments_s` | 1 instrument (per validity interval) | see data dictionary | Reference data for tickers in scope (name, type: stock or ETF benchmark). |
| `silver.portfolio_weights_s` | 1 portfolio × 1 ticker × 1 validity interval | `portfolio_id`, `ticker`, `valid_from` | Target weights over time, `[valid_from, valid_to)`. Default portfolio: 7 stocks, equal weight, rebalanced daily (decision #9). |

## gold

Built **per business question**, not per source. Every gold table must serve at least one question, and every question must have at least one table (see the traceability matrix below).

| ID | Business question |
|---|---|
| Q1 | What are 95%/99% VaR and CVaR of the portfolio over the next 1 day and 21 trading days? |
| Q2 | Which of the four methods estimates risk most accurately when backtested on real data? |
| Q3 | How much does rising correlation between assets amplify portfolio risk? |
| Q4 | How much does the normal-distribution assumption underestimate tail risk? |
| Q5 | How did the portfolio cope with the 2020 and 2022 crises? |

| Table | Grain | Key | Main business columns | Built in |
|---|---|---|---|---|
| `gold.portfolio_returns_g` | 1 portfolio × 1 trading day | `portfolio_id`, `trade_date` | `simple_return`, `log_return`, `n_assets`, `weights_valid_from` | Stage 3 |
| `gold.var_estimates_g` | 1 portfolio × as-of date × method × confidence × horizon × window | `portfolio_id`, `as_of_date`, `method`, `confidence_bp`, `horizon_days`, `window_days` | `var_pct`, `es_pct`, `n_obs`; Monte Carlo only: `run_id`, `seed`, `n_paths` | Stages 3–4 |
| `gold.mc_paths_summary_g` | 1 MC run × 1 day step × 1 quantile | `run_id`, `step`, `quantile_bp` | `as_of_date`, `method`, `cum_return`, `seed`, `n_paths` | Stage 4 |
| `gold.var_backtest_g` | Same as `var_estimates_g` (1:1) | Same as `var_estimates_g` | `var_pct`, `realized_return`, `realized_end_date`, `is_violation` | Stage 5 |
| `gold.var_test_results_g` | 1 portfolio × method × confidence × horizon × window × test period | `portfolio_id`, `method`, `confidence_bp`, `horizon_days`, `window_days`, `test_start`, `test_end` | `n_obs`, `n_violations`, `expected_violations`, `kupiec_pvalue`, `christoffersen_pvalue` | Stage 5 |
| `gold.risk_contribution_g` | 1 portfolio × as-of date × method × confidence × horizon × 1 ticker | `portfolio_id`, `as_of_date`, `method`, `confidence_bp`, `horizon_days`, `ticker` | `weight`, `component_var_pct`, `pct_of_total` | Stage 6 |
| `gold.stress_scenarios_g` | 1 scenario × 1 portfolio | `scenario_id`, `portfolio_id` | `scenario_type` (`historical` / `hypothetical`), `start_date`, `end_date`, `corr_override`, `portfolio_return`, `max_drawdown`, `worst_day_return`, `stressed_var_pct` | Stages 4–5 |

`method` values: `historical`, `parametric`, `mc_normal`, `mc_t`, `mc_bootstrap`.

### Design rules specific to gold

- **No look-ahead.** Every estimate row uses only data dated ≤ `as_of_date`. Backtest rows also carry `realized_end_date`, the end of the profit-and-loss window the estimate is compared with. For a 21-day horizon that is about 21 trading days after `as_of_date`.
- **Detail versus conclusion.** `var_backtest_g` holds one row per day: was the VaR exceeded? `var_test_results_g` holds the aggregated test statistics that actually answer Q2.
- **Overlapping windows.** Formal tests (Kupiec, Christoffersen) use the 1-day horizon. 21-day results are descriptive, or sampled every 21 days so windows do not overlap.
- **Monte Carlo paths are not stored in gold.** Full paths go to `mc_runs/` with a manifest. Gold keeps quantiles only (`mc_paths_summary_g`), tagged with `run_id` and `seed` so any figure can be reproduced.
- **Risk contributions add up.** For each (`as_of_date`, `method`, `confidence_bp`, `horizon_days`), `component_var_pct` summed over tickers equals `var_pct` in `var_estimates_g` (tested).
- **Q4 has no table of its own on purpose.** It is answered by comparing `parametric` with `historical` / `mc_t` rows in `var_estimates_g`, and the violation rate of `parametric` in `var_test_results_g`.

### Traceability matrix

| | portfolio_returns_g | var_estimates_g | mc_paths_summary_g | var_backtest_g | var_test_results_g | risk_contribution_g | stress_scenarios_g |
|---|---|---|---|---|---|---|---|
| Q1 VaR / CVaR | base | **primary** | distribution | | | | |
| Q2 Best method | base | | | detail | **primary** | | |
| Q3 Correlation amplification | | | | | | supporting | **primary** (hypothetical) |
| Q4 Normal underestimates tails | | compare methods | | | **primary** | | |
| Q5 Crises 2020, 2022 | drawdown | | | | | | **primary** (historical) |

### Expected size

| Table | Rough rows | Rough size |
|---|---|---|
| `portfolio_returns_g` | ~3 thousand | < 1 MB |
| `var_estimates_g` | ~2,970 days × 5 methods × 3 confidences × 2 horizons ≈ 89 thousand | a few MB |
| `mc_paths_summary_g` (rolling, 7 quantiles) | ~2,970 × 22 steps × 7 ≈ 460 thousand | < 20 MB |
| others | < 100 thousand each | < 5 MB |

Gold stays far inside the 5 GB warehouse budget. The space-heavy item is full Monte Carlo paths in `mc_runs/` (budget 25 GB).
