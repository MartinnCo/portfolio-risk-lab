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
