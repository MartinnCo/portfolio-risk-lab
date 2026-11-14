# Data dictionary

Generated from `src/portfolio_risk_lab/schemas.py` by `scripts/create_tables.py`. Do not edit by hand: change the spec and regenerate.

Keys are logical: Iceberg records them as identifier fields but does not reject duplicates, so uniqueness is checked by data quality rules in the pipeline.

## Business questions

| Id | Question |
|---|---|
| Q1 | 1-month (21 trading days) VaR and CVaR at 95% / 99% for the portfolio |
| Q2 | Which of the 4 VaR methods is most accurate when backtested on real data |
| Q3 | How much correlation between holdings amplifies risk (correlation stress) |
| Q4 | How much a normal distribution underestimates tail losses |
| Q5 | How the portfolio behaves in crisis periods (2020, 2022) |

## Tables

| Table | Grain | Serves |
|---|---|---|
| `bronze.prices_daily_b` | 1 row = 1 ticker x 1 trading date x 1 raw batch | Q1, Q2, Q3, Q4, Q5 |
| `silver.returns_daily_s` | 1 row = 1 ticker x 1 trading date (from the 2nd trading date of each ticker) | Q1, Q2, Q3, Q4, Q5 |
| `silver.instruments_s` | 1 row = 1 ticker x 1 validity period | Q1, Q2, Q3, Q4, Q5 |
| `silver.portfolio_weights_s` | 1 row = 1 portfolio x 1 ticker x 1 validity period | Q1, Q2, Q3, Q5 |
| `gold.portfolio_returns_g` | 1 row = 1 portfolio x 1 trading date | Q1, Q2, Q5 |
| `gold.var_estimates_g` | 1 row = 1 portfolio x as_of_date x method x confidence x horizon x window | Q1, Q4 |
| `gold.mc_paths_summary_g` | 1 row = 1 Monte Carlo run x 1 day step x 1 quantile | Q1 |
| `gold.var_backtest_g` | 1 row = 1 portfolio x as_of_date x method x confidence x horizon x window (1:1 with var_estimates_g) | Q2 |
| `gold.var_test_results_g` | 1 row = 1 portfolio x method x confidence x horizon x window x test period | Q2, Q4 |
| `gold.risk_contribution_g` | 1 row = 1 portfolio x as_of_date x method x confidence x horizon x window x ticker | Q3 |
| `gold.stress_scenarios_g` | 1 row = 1 scenario x 1 portfolio | Q3, Q5 |

## `bronze.prices_daily_b`

Daily prices as delivered by yfinance (auto_adjust=False), one copy per raw batch.

- Grain: 1 row = 1 ticker x 1 trading date x 1 raw batch
- Key: `batch_id, ticker, trade_date`
- Serves: Q1, Q2, Q3, Q4, Q5

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `ticker` (key) | string | yes | Exchange symbol, e.g. NVDA, SPY |
| 2 | `trade_date` (key) | date | yes | Trading date (exchange local date, no time zone) |
| 3 | `open` | double | no | Opening price, split-adjusted, USD |
| 4 | `high` | double | no | Intraday high, split-adjusted, USD |
| 5 | `low` | double | no | Intraday low, split-adjusted, USD |
| 6 | `close` | double | no | Closing price, split-adjusted, not dividend-adjusted, USD |
| 7 | `adj_close` | double | no | Close adjusted for splits and dividends, USD; basis for returns |
| 8 | `volume` | long | no | Shares traded |
| 9 | `batch_id` (key) | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 10 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 11 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `silver.returns_daily_s`

Clean daily simple and log returns from adj_close, one chosen raw batch, aligned to the trading calendar.

- Grain: 1 row = 1 ticker x 1 trading date (from the 2nd trading date of each ticker)
- Key: `ticker, trade_date`
- Serves: Q1, Q2, Q3, Q4, Q5

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `ticker` (key) | string | yes | Exchange symbol |
| 2 | `trade_date` (key) | date | yes | Trading date of the return (end of the holding day) |
| 3 | `prev_trade_date` | date | yes | Previous trading date of this ticker; the return spans prev_trade_date -> trade_date |
| 4 | `adj_close` | double | yes | adj_close on trade_date, USD |
| 5 | `prev_adj_close` | double | yes | adj_close on prev_trade_date, USD |
| 6 | `simple_return` | double | yes | adj_close / prev_adj_close - 1; add across assets (portfolio) |
| 7 | `log_return` | double | yes | ln(adj_close / prev_adj_close); add across time (horizons) |
| 8 | `gap_days` | int | yes | Calendar days between prev_trade_date and trade_date (weekend = 3; larger means a holiday or missing data) |
| 9 | `dq_flag` | string | no | Null when clean; otherwise a data quality rule code, e.g. extreme_move, missing_day |
| 10 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 11 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 12 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `silver.instruments_s`

Reference list of instruments in scope, with validity period.

- Grain: 1 row = 1 ticker x 1 validity period
- Key: `ticker, valid_from`
- Serves: Q1, Q2, Q3, Q4, Q5

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `ticker` (key) | string | yes | Exchange symbol |
| 2 | `instrument_name` | string | no | Company or fund name |
| 3 | `asset_type` | string | yes | stock | etf |
| 4 | `currency` | string | yes | Price currency, ISO 4217, e.g. USD |
| 5 | `is_benchmark` | boolean | yes | True for SPY: compared against, never held in the portfolio |
| 6 | `valid_from` (key) | date | yes | First date this row applies (inclusive) |
| 7 | `valid_to` | date | no | Last date this row applies (exclusive); null = still valid |
| 8 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 9 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 10 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `silver.portfolio_weights_s`

Target portfolio weights with validity period; weights of one portfolio sum to 1 on any date.

- Grain: 1 row = 1 portfolio x 1 ticker x 1 validity period
- Key: `portfolio_id, ticker, valid_from`
- Serves: Q1, Q2, Q3, Q5

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `portfolio_id` (key) | string | yes | Portfolio code, e.g. ew7 = 7 stocks equal weight |
| 2 | `ticker` (key) | string | yes | Exchange symbol (never the benchmark) |
| 3 | `weight` | double | yes | Target weight, 0..1 |
| 4 | `rebalance_rule` | string | yes | daily = reset to target weights every day (decision #9) |
| 5 | `valid_from` (key) | date | yes | First date this weight applies (inclusive) |
| 6 | `valid_to` | date | no | Last date this weight applies (exclusive); null = still valid |
| 7 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 8 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 9 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.portfolio_returns_g`

Daily portfolio returns: weighted sum of asset simple returns, using the weights valid on each date.

- Grain: 1 row = 1 portfolio x 1 trading date
- Key: `portfolio_id, trade_date`
- Serves: Q1, Q2, Q5

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `portfolio_id` (key) | string | yes | Portfolio code, e.g. ew7 |
| 2 | `trade_date` (key) | date | yes | Trading date of the return |
| 3 | `simple_return` | double | yes | Sum over tickers of weight x simple_return (simple returns add across assets) |
| 4 | `log_return` | double | yes | ln(1 + simple_return); use to add across time |
| 5 | `n_assets` | int | yes | Number of tickers with a return on this date; less than expected means missing data |
| 6 | `weights_valid_from` | date | yes | valid_from of the weight version used (trace to portfolio_weights_s) |
| 7 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 8 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 9 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.var_estimates_g`

VaR and Expected Shortfall estimates by method, confidence, horizon and estimation window.

- Grain: 1 row = 1 portfolio x as_of_date x method x confidence x horizon x window
- Key: `portfolio_id, as_of_date, method, confidence_bp, horizon_days, window_days`
- Serves: Q1, Q4

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `portfolio_id` (key) | string | yes | Portfolio code, e.g. ew7 |
| 2 | `as_of_date` (key) | date | yes | Date the estimate is made; only data dated <= as_of_date may be used (no look-ahead) |
| 3 | `method` (key) | string | yes | historical | parametric | mc_normal | mc_t | mc_bootstrap |
| 4 | `confidence_bp` (key) | int | yes | Confidence level in basis points: 9500, 9750, 9900 |
| 5 | `horizon_days` (key) | int | yes | Holding horizon in trading days: 1 or 21 |
| 6 | `window_days` (key) | int | yes | Number of trading days of history used to estimate the model |
| 7 | `window_start` | date | yes | First return date in the estimation window |
| 8 | `window_end` | date | yes | Last return date in the estimation window; must be <= as_of_date |
| 9 | `n_obs` | int | yes | Number of daily returns actually used |
| 10 | `var_pct` | double | yes | Value at Risk as a positive fraction of portfolio value (0.087 = 8.7% loss) |
| 11 | `es_pct` | double | yes | Expected Shortfall (CVaR): mean loss beyond VaR, positive fraction |
| 12 | `run_id` | string | no | Monte Carlo run folder in mc_runs; null for historical and parametric |
| 13 | `seed` | long | no | Random seed of the Monte Carlo run; null for non-simulation methods |
| 14 | `n_paths` | int | no | Number of simulated paths; null for non-simulation methods |
| 15 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 16 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 17 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.mc_paths_summary_g`

Quantiles of simulated cumulative portfolio return per day step of one Monte Carlo run (full paths stay in mc_runs).

- Grain: 1 row = 1 Monte Carlo run x 1 day step x 1 quantile
- Key: `run_id, step, quantile_bp`
- Serves: Q1

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `run_id` (key) | string | yes | Monte Carlo run folder in mc_runs |
| 2 | `step` (key) | int | yes | Trading days after as_of_date: 0 .. horizon_days |
| 3 | `quantile_bp` (key) | int | yes | Quantile in basis points, e.g. 100 = 1st percentile, 5000 = median |
| 4 | `portfolio_id` | string | yes | Portfolio code |
| 5 | `as_of_date` | date | yes | Start date of the simulation |
| 6 | `method` | string | yes | mc_normal | mc_t | mc_bootstrap |
| 7 | `cum_return` | double | yes | Cumulative simple portfolio return from as_of_date to this step, at this quantile |
| 8 | `seed` | long | yes | Random seed of the run |
| 9 | `n_paths` | int | yes | Number of simulated paths |
| 10 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 11 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 12 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.var_backtest_g`

Each VaR estimate compared with the realised portfolio return over its horizon.

- Grain: 1 row = 1 portfolio x as_of_date x method x confidence x horizon x window (1:1 with var_estimates_g)
- Key: `portfolio_id, as_of_date, method, confidence_bp, horizon_days, window_days`
- Serves: Q2

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `portfolio_id` (key) | string | yes | Portfolio code, e.g. ew7 |
| 2 | `as_of_date` (key) | date | yes | Date the estimate is made; only data dated <= as_of_date may be used (no look-ahead) |
| 3 | `method` (key) | string | yes | historical | parametric | mc_normal | mc_t | mc_bootstrap |
| 4 | `confidence_bp` (key) | int | yes | Confidence level in basis points: 9500, 9750, 9900 |
| 5 | `horizon_days` (key) | int | yes | Holding horizon in trading days: 1 or 21 |
| 6 | `window_days` (key) | int | yes | Number of trading days of history used to estimate the model |
| 7 | `var_pct` | double | yes | VaR copied from var_estimates_g, positive fraction |
| 8 | `realized_end_date` | date | yes | Last date of the realised window (horizon_days trading days after as_of_date) |
| 9 | `realized_return` | double | yes | Realised cumulative simple portfolio return from as_of_date to realized_end_date |
| 10 | `is_violation` | boolean | yes | True when realized_return < -var_pct (loss larger than VaR) |
| 11 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 12 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 13 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.var_test_results_g`

Backtest statistics per method: violation counts, Kupiec POF and Christoffersen independence tests.

- Grain: 1 row = 1 portfolio x method x confidence x horizon x window x test period
- Key: `portfolio_id, method, confidence_bp, horizon_days, window_days, test_start, test_end`
- Serves: Q2, Q4

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `portfolio_id` (key) | string | yes | Portfolio code |
| 2 | `method` (key) | string | yes | historical | parametric | mc_normal | mc_t | mc_bootstrap |
| 3 | `confidence_bp` (key) | int | yes | Confidence level in basis points |
| 4 | `horizon_days` (key) | int | yes | Holding horizon in trading days |
| 5 | `window_days` (key) | int | yes | Estimation window in trading days |
| 6 | `test_start` (key) | date | yes | First as_of_date in the test period |
| 7 | `test_end` (key) | date | yes | Last as_of_date in the test period |
| 8 | `n_obs` | int | yes | Number of backtest rows tested |
| 9 | `n_violations` | int | yes | Number of rows with is_violation = true |
| 10 | `expected_violations` | double | yes | n_obs x (1 - confidence) |
| 11 | `violation_rate` | double | yes | n_violations / n_obs |
| 12 | `kupiec_lr` | double | no | Kupiec proportion-of-failures likelihood ratio |
| 13 | `kupiec_pvalue` | double | no | p-value of the Kupiec test; small = violation rate is wrong |
| 14 | `christoffersen_lr` | double | no | Christoffersen independence likelihood ratio; null for overlapping horizons |
| 15 | `christoffersen_pvalue` | double | no | p-value of the Christoffersen test; small = violations cluster |
| 16 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 17 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 18 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.risk_contribution_g`

Component VaR per ticker; contributions add up to the portfolio VaR in var_estimates_g.

- Grain: 1 row = 1 portfolio x as_of_date x method x confidence x horizon x window x ticker
- Key: `portfolio_id, as_of_date, method, confidence_bp, horizon_days, window_days, ticker`
- Serves: Q3

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `portfolio_id` (key) | string | yes | Portfolio code, e.g. ew7 |
| 2 | `as_of_date` (key) | date | yes | Date the estimate is made; only data dated <= as_of_date may be used (no look-ahead) |
| 3 | `method` (key) | string | yes | historical | parametric | mc_normal | mc_t | mc_bootstrap |
| 4 | `confidence_bp` (key) | int | yes | Confidence level in basis points: 9500, 9750, 9900 |
| 5 | `horizon_days` (key) | int | yes | Holding horizon in trading days: 1 or 21 |
| 6 | `window_days` (key) | int | yes | Number of trading days of history used to estimate the model |
| 7 | `ticker` (key) | string | yes | Exchange symbol |
| 8 | `weight` | double | yes | Portfolio weight of the ticker on as_of_date |
| 9 | `component_var_pct` | double | yes | Share of portfolio VaR due to this ticker, fraction of portfolio value |
| 10 | `pct_of_total` | double | yes | component_var_pct / portfolio var_pct; sums to 1 over tickers |
| 11 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 12 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 13 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |

## `gold.stress_scenarios_g`

Stress test results: historical crisis replays and hypothetical correlation shocks.

- Grain: 1 row = 1 scenario x 1 portfolio
- Key: `scenario_id, portfolio_id`
- Serves: Q3, Q5

| # | Column | Type | Required | Description |
|---|---|---|---|---|
| 1 | `scenario_id` (key) | string | yes | Scenario code, e.g. covid_2020, rates_2022, corr_080 |
| 2 | `portfolio_id` (key) | string | yes | Portfolio code |
| 3 | `scenario_type` | string | yes | historical | hypothetical |
| 4 | `description` | string | yes | What the scenario assumes, in one sentence |
| 5 | `start_date` | date | no | First date of a historical window; null for hypothetical |
| 6 | `end_date` | date | no | Last date of a historical window; null for hypothetical |
| 7 | `portfolio_return` | double | no | Cumulative simple return over the historical window |
| 8 | `max_drawdown` | double | no | Largest peak-to-trough fall in the window, positive fraction |
| 9 | `worst_day_return` | double | no | Worst single-day portfolio return in the window |
| 10 | `corr_override` | double | no | Pairwise correlation imposed in a hypothetical scenario, e.g. 0.8 |
| 11 | `confidence_bp` | int | no | Confidence of the stressed VaR, basis points |
| 12 | `horizon_days` | int | no | Horizon of the stressed VaR, trading days |
| 13 | `base_var_pct` | double | no | VaR without the shock, same confidence and horizon |
| 14 | `stressed_var_pct` | double | no | VaR under the shock; stressed / base = amplification |
| 15 | `batch_id` | string | yes | Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1) |
| 16 | `source_system` | string | yes | Origin of the data, e.g. yfinance; config for hand-maintained reference rows |
| 17 | `ingest_ts` | timestamptz | yes | UTC time this row was written to this table |
