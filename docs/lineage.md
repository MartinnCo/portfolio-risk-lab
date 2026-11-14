# Table-level lineage (DFD level 2)

This page breaks the level-0 and level-1 data flow diagrams in [`architecture.md`](architecture.md) down to individual tables. Table purposes, grains and keys are in [`layers.md`](layers.md). Columns are in [`data_dictionary.md`](data_dictionary.md).

**Notation**

| Shape | Meaning |
|---|---|
| Rectangle | External entity (outside the system) |
| Rounded box `Pn` | Process (a script or pipeline step) |
| Cylinder | Data store (raw folder, Iceberg table, run folder) |

Colours mark the layer: raw (grey), bronze (brown), silver (blue-grey), gold (amber), runs and exports (green).

**Status:** P1 exists (`scripts/fetch_prices_raw.py`). The other processes are planned, and the "Stage" column of the process catalogue says when each is built.

## 1. End to end

Where every store lives: everything inside the RiskLab box sits on the external drive and is never committed. GitHub holds only code and docs.

```mermaid
flowchart LR
    YF["Yahoo Finance via yfinance"]:::ext
    CFG["config.py: tickers, dates, weights"]:::ext
    USER["Reader of the risk report"]:::ext

    subgraph RL["RiskLab volume: /Volumes/RiskLab/risklab-data"]
        RAW[("raw/batch_id=...")]:::raw
        subgraph WH["warehouse/ - Iceberg + SQLite catalog"]
            BR[("bronze: 1 table")]:::bronze
            SI[("silver: 3 tables")]:::silver
            GO[("gold: 7 tables")]:::gold
        end
        MCR[("mc_runs/run_id=...")]:::run
        EXP[("exports/")]:::run
    end

    YF -->|daily prices| P1("P1 Fetch raw prices")
    P1 --> RAW
    RAW --> P2("P2-P4 Ingest and clean")
    CFG --> P2
    P2 --> BR
    P2 --> SI
    SI --> P5("P5-P10 Risk engine")
    P5 --> MCR
    P5 --> GO
    GO --> P11("P11 Build report")
    P11 --> EXP
    EXP -->|HTML risk summary| USER

    classDef ext fill:#ffffff,stroke:#333333,stroke-width:1px
    classDef raw fill:#e6e6e6,stroke:#666666
    classDef bronze fill:#ead7c3,stroke:#8b5a2b
    classDef silver fill:#dfe6ee,stroke:#5b6b7b
    classDef gold fill:#f8e2a8,stroke:#b8860b
    classDef run fill:#dcefdc,stroke:#3c7d3c
```

## 2. Ingestion and cleansing: raw → bronze → silver

```mermaid
flowchart LR
    YF["Yahoo Finance via yfinance"]:::ext
    CFG["config.py"]:::ext

    P1("P1 Fetch raw prices<br/>fetch_prices_raw.py")
    RAW[("raw/batch_id=...<br/>Parquet + manifest")]:::raw
    P2("P2 Load bronze<br/>type cast, stamp batch_id")
    B1[("bronze.prices_daily_b<br/>ticker x date x batch")]:::bronze
    P3("P3 Clean to silver<br/>pick one batch, align calendar,<br/>drop missing, flag gaps and outliers")
    S1[("silver.returns_daily_s<br/>ticker x date")]:::silver
    DQ[("exports/dq_report")]:::run
    P4("P4 Load reference tables")
    S2[("silver.instruments_s")]:::silver
    S3[("silver.portfolio_weights_s<br/>valid_from, valid_to")]:::silver

    YF -->|OHLCV, adj_close| P1
    CFG -->|tickers, START, END| P1
    P1 --> RAW
    RAW --> P2
    P2 --> B1
    B1 --> P3
    CFG -->|chosen batch_id| P3
    P3 --> S1
    P3 -->|row counts, gaps, outliers| DQ
    CFG -->|tickers, weights| P4
    P4 --> S2
    P4 --> S3
    S2 -.->|valid tickers| P3

    classDef ext fill:#ffffff,stroke:#333333,stroke-width:1px
    classDef raw fill:#e6e6e6,stroke:#666666
    classDef bronze fill:#ead7c3,stroke:#8b5a2b
    classDef silver fill:#dfe6ee,stroke:#5b6b7b
    classDef run fill:#dcefdc,stroke:#3c7d3c
```

Key points:

- Raw is append-only, and bronze keeps every batch. Only P3 decides which batch becomes the truth, which makes a rebuild reproducible.
- P3 is idempotent: rerunning it with the same `batch_id` produces the same silver tables.
- The dotted arrow is a lookup: P3 keeps only tickers listed in `instruments_s`.

## 3. Risk engine: silver → gold

```mermaid
flowchart LR
    S1[("silver.returns_daily_s")]:::silver
    S3[("silver.portfolio_weights_s")]:::silver

    P5("P5 Portfolio returns<br/>weights valid on each date")
    G1[("gold.portfolio_returns_g")]:::gold
    P6("P6 Historical and<br/>parametric VaR, ES")
    P7("P7 Monte Carlo simulation<br/>Cholesky, normal / t / bootstrap,<br/>fixed seed")
    MCR[("mc_runs/run_id=...<br/>paths float32 + manifest")]:::run
    G2[("gold.var_estimates_g")]:::gold
    G3[("gold.mc_paths_summary_g<br/>quantiles only")]:::gold
    P8("P8 Risk contribution<br/>per ticker")
    G6[("gold.risk_contribution_g")]:::gold

    S1 --> P5
    S3 --> P5
    P5 --> G1
    G1 --> P6
    S1 -->|asset returns, covariance| P7
    S3 -->|weights| P7
    P6 --> G2
    P7 -->|full paths| MCR
    MCR -->|quantiles| G3
    MCR -->|VaR, ES + run_id, seed| G2
    S1 --> P8
    S3 --> P8
    G2 -->|total VaR, for sum check| P8
    P8 --> G6

    classDef silver fill:#dfe6ee,stroke:#5b6b7b
    classDef gold fill:#f8e2a8,stroke:#b8860b
    classDef run fill:#dcefdc,stroke:#3c7d3c
```

Key points:

- Every estimate at `as_of_date` reads only rows with `trade_date ≤ as_of_date` (no look-ahead).
- Monte Carlo writes full paths to `mc_runs/` first. Gold gets only summaries, so gold stays small and every number traces back to a `run_id` and `seed`.
- P8 checks that per-ticker contributions sum to the total VaR in `var_estimates_g`.

## 4. Backtest, stress test and report: gold → gold → exports

```mermaid
flowchart LR
    S1[("silver.returns_daily_s")]:::silver
    S3[("silver.portfolio_weights_s")]:::silver
    G1[("gold.portfolio_returns_g")]:::gold
    G2[("gold.var_estimates_g")]:::gold
    G3[("gold.mc_paths_summary_g")]:::gold
    G6[("gold.risk_contribution_g")]:::gold

    P9("P9 Backtest<br/>compare VaR with realised P&L")
    G4[("gold.var_backtest_g<br/>1 row per day")]:::gold
    P10("P10 Statistical tests<br/>Kupiec POF, Christoffersen")
    G5[("gold.var_test_results_g<br/>1 row per method")]:::gold
    P12("P12 Stress scenarios<br/>historical 2020, 2022;<br/>hypothetical correlation")
    G7[("gold.stress_scenarios_g")]:::gold
    P11("P11 Build risk report")
    EXP[("exports/risk_summary.html")]:::run

    G2 --> P9
    G1 -->|realised returns after as_of_date| P9
    P9 --> G4
    G4 --> P10
    P10 --> G5
    G1 -->|crisis windows| P12
    S1 -->|correlation matrix| P12
    S3 --> P12
    P12 --> G7
    G2 --> P11
    G3 --> P11
    G5 --> P11
    G6 --> P11
    G7 --> P11
    P11 --> EXP

    classDef silver fill:#dfe6ee,stroke:#5b6b7b
    classDef gold fill:#f8e2a8,stroke:#b8860b
    classDef run fill:#dcefdc,stroke:#3c7d3c
```

Key points:

- P9 is the only process allowed to read returns **after** `as_of_date`, because comparing a forecast with what actually happened is its purpose. It records `realized_end_date` on every row.
- P10 runs formal tests on the 1-day horizon. 21-day windows overlap, so their violations are reported descriptively.

## Process catalogue

| ID | Process | Reads | Writes | Stage | Status |
|---|---|---|---|---|---|
| P1 | Fetch raw prices | yfinance, `config.py` | `raw/batch_id=…` | Session 1 | Done |
| P2 | Load bronze | raw | `bronze.prices_daily_b` | Stage 2c | Planned |
| P3 | Clean to silver | `prices_daily_b`, `instruments_s` | `returns_daily_s`, DQ report | Stage 2c | Planned |
| P4 | Load reference tables | `config.py` | `instruments_s`, `portfolio_weights_s` | Stage 2c | Planned |
| P5 | Portfolio returns | `returns_daily_s`, `portfolio_weights_s` | `portfolio_returns_g` | Stage 3 | Planned |
| P6 | Historical and parametric VaR, ES | `portfolio_returns_g` | `var_estimates_g` | Stage 3 | Planned |
| P7 | Monte Carlo simulation | `returns_daily_s`, `portfolio_weights_s` | `mc_runs/`, `mc_paths_summary_g`, `var_estimates_g` | Stage 4 | Planned |
| P8 | Risk contribution | `returns_daily_s`, `portfolio_weights_s`, `var_estimates_g` | `risk_contribution_g` | Stage 6 | Planned |
| P9 | Backtest | `var_estimates_g`, `portfolio_returns_g` | `var_backtest_g` | Stage 5 | Planned |
| P10 | Statistical tests | `var_backtest_g` | `var_test_results_g` | Stage 5 | Planned |
| P11 | Build risk report | gold tables | `exports/risk_summary.html` | Stage 6 | Planned |
| P12 | Stress scenarios | `portfolio_returns_g`, `returns_daily_s`, `portfolio_weights_s` | `stress_scenarios_g` | Stages 4–5 | Planned |

## Table → upstream (quick lookup)

| Table | Direct upstream |
|---|---|
| `bronze.prices_daily_b` | raw |
| `silver.returns_daily_s` | `bronze.prices_daily_b`, `silver.instruments_s` |
| `silver.instruments_s` | `config.py` |
| `silver.portfolio_weights_s` | `config.py` |
| `gold.portfolio_returns_g` | `returns_daily_s`, `portfolio_weights_s` |
| `gold.var_estimates_g` | `portfolio_returns_g` (historical, parametric); `mc_runs/` (Monte Carlo) |
| `gold.mc_paths_summary_g` | `mc_runs/` |
| `gold.var_backtest_g` | `var_estimates_g`, `portfolio_returns_g` |
| `gold.var_test_results_g` | `var_backtest_g` |
| `gold.risk_contribution_g` | `returns_daily_s`, `portfolio_weights_s`, `var_estimates_g` |
| `gold.stress_scenarios_g` | `portfolio_returns_g`, `returns_daily_s`, `portfolio_weights_s` |
