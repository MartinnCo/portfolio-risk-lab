# Traceability: business questions to tables

Generated from `src/portfolio_risk_lab/schemas.py` by `scripts/render_traceability.py`. Do not edit by hand: change `serves` in the spec and regenerate.

An `x` means the table helps answer the question. Which table is primary for each question is explained in [`layers.md`](layers.md).

## Business questions

| Id | Question |
|---|---|
| Q1 | 1-month (21 trading days) VaR and CVaR at 95% / 99% for the portfolio |
| Q2 | Which of the 4 VaR methods is most accurate when backtested on real data |
| Q3 | How much correlation between holdings amplifies risk (correlation stress) |
| Q4 | How much a normal distribution underestimates tail losses |
| Q5 | How the portfolio behaves in crisis periods (2020, 2022) |

## Matrix

| Table | Q1 | Q2 | Q3 | Q4 | Q5 |
|---|---|---|---|---|---|
| `bronze.prices_daily_b` | x | x | x | x | x |
| `silver.returns_daily_s` | x | x | x | x | x |
| `silver.instruments_s` | x | x | x | x | x |
| `silver.portfolio_weights_s` | x | x | x |  | x |
| `gold.portfolio_returns_g` | x | x |  |  | x |
| `gold.var_estimates_g` | x |  |  | x |  |
| `gold.mc_paths_summary_g` | x |  |  |  |  |
| `gold.var_backtest_g` |  | x |  |  |  |
| `gold.var_test_results_g` |  | x |  | x |  |
| `gold.risk_contribution_g` |  |  | x |  |  |
| `gold.stress_scenarios_g` |  |  | x |  | x |

## Checks

- Every question has at least one gold table: yes
- Every gold table serves at least one question: yes
