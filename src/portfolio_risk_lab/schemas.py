# Ý nghĩa: Bản thiết kế (schema) của mọi bảng trong lakehouse, viết dưới dạng dữ liệu
# Python thuần: mỗi bảng là một TableSpec, mỗi cột là một Column. Từ một nguồn này ta
# (1) tạo bảng Iceberg (catalog.py), (2) sinh data dictionary (docs/data_dictionary.md),
# (3) viết unit test kiểm tra thiết kế (tests/test_schemas.py). Sửa thiết kế chỉ sửa ở đây.
"""Table specifications for the Portfolio Risk Lab lakehouse (single source of truth)."""

from __future__ import annotations

from dataclasses import dataclass, field

# Ý nghĩa: Các kiểu dữ liệu được phép, đặt đúng tên Iceberg dùng (str(IcebergType)).
ALLOWED_TYPES = {"string", "date", "int", "long", "double", "boolean", "timestamptz"}

# Ý nghĩa: Các câu hỏi nghiệp vụ của dự án. Mỗi bảng ghi mình phục vụ câu nào (truy vết).
BUSINESS_QUESTIONS: dict[str, str] = {
    "Q1": "1-month (21 trading days) VaR and CVaR at 95% / 99% for the portfolio",
    "Q2": "Which of the 4 VaR methods is most accurate when backtested on real data",
    "Q3": "How much correlation between holdings amplifies risk (correlation stress)",
    "Q4": "How much a normal distribution underestimates tail losses",
    "Q5": "How the portfolio behaves in crisis periods (2020, 2022)",
}


# Ý nghĩa: Mô tả một cột: tên, kiểu, có bắt buộc (NOT NULL) không, và giải thích.
@dataclass(frozen=True)
class Column:
    name: str
    type: str
    required: bool
    doc: str


# Ý nghĩa: Mô tả một bảng: thuộc namespace nào, grain (1 dòng = cái gì), khóa,
# các cột, và phục vụ câu hỏi nghiệp vụ nào.
@dataclass(frozen=True)
class TableSpec:
    namespace: str                 # bronze | silver | gold | work
    name: str                      # snake_case + hậu tố _b/_s/_g/_w
    description: str
    grain: str                     # "1 dòng = ..."
    key: tuple[str, ...]           # khóa logic; Iceberg ghi nhận nhưng KHÔNG chặn trùng
    columns: tuple[Column, ...]
    serves: tuple[str, ...] = field(default_factory=tuple)

    @property
    def identifier(self) -> str:
        return f"{self.namespace}.{self.name}"

    def column(self, name: str) -> Column:
        for col in self.columns:
            if col.name == name:
                return col
        raise KeyError(f"{self.identifier} không có cột {name}")


# Ý nghĩa: 3 cột kỹ thuật bắt buộc ở mọi bảng (quy ước dự án), luôn đặt cuối bảng.
# batch_id cho biết dòng đến từ lần tải raw nào: đó là sợi dây lineage nối gold về raw.
def tech_columns() -> tuple[Column, ...]:
    return (
        Column("batch_id", "string", True,
               "Raw batch the row derives from, e.g. 20261108T103206Z (lineage back to D1)"),
        Column("source_system", "string", True,
               "Origin of the data, e.g. yfinance; config for hand-maintained reference rows"),
        Column("ingest_ts", "timestamptz", True,
               "UTC time this row was written to this table"),
    )


# ---------------------------------------------------------------- BRONZE
# Ý nghĩa: Bronze = bản sao raw đưa vào bảng, gần như nguyên trạng: chỉ đổi tên cột sang
# snake_case và gắn cột kỹ thuật. Giữ mọi batch (batch_id nằm trong khóa) để so sánh
# Yahoo đã viết lại adj_close quá khứ thế nào giữa các lần tải.
PRICES_DAILY_B = TableSpec(
    namespace="bronze",
    name="prices_daily_b",
    description="Daily prices as delivered by yfinance (auto_adjust=False), one copy per raw batch.",
    grain="1 row = 1 ticker x 1 trading date x 1 raw batch",
    key=("batch_id", "ticker", "trade_date"),
    columns=(
        Column("ticker", "string", True, "Exchange symbol, e.g. NVDA, SPY"),
        Column("trade_date", "date", True, "Trading date (exchange local date, no time zone)"),
        Column("open", "double", False, "Opening price, split-adjusted, USD"),
        Column("high", "double", False, "Intraday high, split-adjusted, USD"),
        Column("low", "double", False, "Intraday low, split-adjusted, USD"),
        Column("close", "double", False, "Closing price, split-adjusted, not dividend-adjusted, USD"),
        Column("adj_close", "double", False, "Close adjusted for splits and dividends, USD; basis for returns"),
        Column("volume", "long", False, "Shares traded"),
    ) + tech_columns(),
    serves=("Q1", "Q2", "Q3", "Q4", "Q5"),
)

# ---------------------------------------------------------------- SILVER
# Ý nghĩa: Silver = dữ liệu đã làm sạch, đúng chuẩn, MỘT phiên bản sự thật: chỉ lấy
# một batch đã chọn, mỗi (ticker, trade_date) đúng 1 dòng. Dòng đầu tiên của mỗi mã
# không có return nên không có mặt ở đây.
RETURNS_DAILY_S = TableSpec(
    namespace="silver",
    name="returns_daily_s",
    description="Clean daily simple and log returns from adj_close, one chosen raw batch, aligned to the trading calendar.",
    grain="1 row = 1 ticker x 1 trading date (from the 2nd trading date of each ticker)",
    key=("ticker", "trade_date"),
    columns=(
        Column("ticker", "string", True, "Exchange symbol"),
        Column("trade_date", "date", True, "Trading date of the return (end of the holding day)"),
        Column("prev_trade_date", "date", True, "Previous trading date of this ticker; the return spans prev_trade_date -> trade_date"),
        Column("adj_close", "double", True, "adj_close on trade_date, USD"),
        Column("prev_adj_close", "double", True, "adj_close on prev_trade_date, USD"),
        Column("simple_return", "double", True, "adj_close / prev_adj_close - 1; add across assets (portfolio)"),
        Column("log_return", "double", True, "ln(adj_close / prev_adj_close); add across time (horizons)"),
        Column("gap_days", "int", True, "Calendar days between prev_trade_date and trade_date (weekend = 3; larger means a holiday or missing data)"),
        Column("dq_flag", "string", False, "Null when clean; otherwise a data quality rule code, e.g. extreme_move, missing_day"),
    ) + tech_columns(),
    serves=("Q1", "Q2", "Q3", "Q4", "Q5"),
)

# Ý nghĩa: Bảng tham chiếu danh sách mã, theo thời gian (valid_from/valid_to, kiểu SCD2):
# mã nào thuộc phạm vi dự án trong giai đoạn nào, có phải benchmark không.
INSTRUMENTS_S = TableSpec(
    namespace="silver",
    name="instruments_s",
    description="Reference list of instruments in scope, with validity period.",
    grain="1 row = 1 ticker x 1 validity period",
    key=("ticker", "valid_from"),
    columns=(
        Column("ticker", "string", True, "Exchange symbol"),
        Column("instrument_name", "string", False, "Company or fund name"),
        Column("asset_type", "string", True, "stock | etf"),
        Column("currency", "string", True, "Price currency, ISO 4217, e.g. USD"),
        Column("is_benchmark", "boolean", True, "True for SPY: compared against, never held in the portfolio"),
        Column("valid_from", "date", True, "First date this row applies (inclusive)"),
        Column("valid_to", "date", False, "Last date this row applies (exclusive); null = still valid"),
    ) + tech_columns(),
    serves=("Q1", "Q2", "Q3", "Q4", "Q5"),
)

# Ý nghĩa: Trọng số danh mục theo thời gian. Đổi trọng số = đóng dòng cũ (đặt valid_to)
# và thêm dòng mới, không sửa đè, nên VaR của ngày cũ luôn tính lại đúng trọng số lúc đó.
PORTFOLIO_WEIGHTS_S = TableSpec(
    namespace="silver",
    name="portfolio_weights_s",
    description="Target portfolio weights with validity period; weights of one portfolio sum to 1 on any date.",
    grain="1 row = 1 portfolio x 1 ticker x 1 validity period",
    key=("portfolio_id", "ticker", "valid_from"),
    columns=(
        Column("portfolio_id", "string", True, "Portfolio code, e.g. ew7 = 7 stocks equal weight"),
        Column("ticker", "string", True, "Exchange symbol (never the benchmark)"),
        Column("weight", "double", True, "Target weight, 0..1"),
        Column("rebalance_rule", "string", True, "daily = reset to target weights every day (decision #9)"),
        Column("valid_from", "date", True, "First date this weight applies (inclusive)"),
        Column("valid_to", "date", False, "Last date this weight applies (exclusive); null = still valid"),
    ) + tech_columns(),
    serves=("Q1", "Q2", "Q3", "Q5"),
)

# ---------------------------------------------------------------- GOLD
# Ý nghĩa: Gold = bảng kết quả, tổ chức THEO CÂU HỎI NGHIỆP VỤ (không theo nguồn).
# Quy ước chung của gold:
#   - VaR/ES lưu là SỐ DƯƠNG, tính bằng phần của giá trị danh mục (0.087 = lỗ 8,7%).
#   - Mức tin cậy và phân vị lưu số nguyên basis point (9500, 9750, 9900), KHÔNG double,
#     vì so sánh bằng trên số thực có thể sai ngầm (0.1 + 0.2 != 0.3).
#   - batch_id = batch raw mà dòng được tính ra từ đó (sợi dây lineage về raw);
#     source_system = "risklab" (do risk engine tính, không đến từ nguồn ngoài).

# Ý nghĩa: Các giá trị hợp lệ cho cột phân loại của gold (pipeline sẽ kiểm tra khi ghi).
VAR_METHODS = ("historical", "parametric", "mc_normal", "mc_t", "mc_bootstrap")
CONFIDENCE_BP = (9500, 9750, 9900)      # 97,5% là mức Expected Shortfall dùng trong FRTB
HORIZON_DAYS = (1, 21)
SCENARIO_TYPES = ("historical", "hypothetical")

# Ý nghĩa: Khóa chung của "một con số VaR": dùng lại ở 3 bảng để join 1:1 không lệch.
VAR_KEY = ("portfolio_id", "as_of_date", "method", "confidence_bp", "horizon_days", "window_days")


# Ý nghĩa: Các cột khóa của VAR_KEY, viết một lần, dùng lại cho các bảng có cùng khóa.
def var_key_columns() -> tuple[Column, ...]:
    return (
        Column("portfolio_id", "string", True, "Portfolio code, e.g. ew7"),
        Column("as_of_date", "date", True,
               "Date the estimate is made; only data dated <= as_of_date may be used (no look-ahead)"),
        Column("method", "string", True, "historical | parametric | mc_normal | mc_t | mc_bootstrap"),
        Column("confidence_bp", "int", True, "Confidence level in basis points: 9500, 9750, 9900"),
        Column("horizon_days", "int", True, "Holding horizon in trading days: 1 or 21"),
        Column("window_days", "int", True, "Number of trading days of history used to estimate the model"),
    )


# Ý nghĩa: Lợi nhuận ngày của cả danh mục = tổng (trọng số x simple return từng mã).
# Bảng nền cho mọi bảng gold khác. Cộng theo tài sản phải dùng simple return.
PORTFOLIO_RETURNS_G = TableSpec(
    namespace="gold",
    name="portfolio_returns_g",
    description="Daily portfolio returns: weighted sum of asset simple returns, using the weights valid on each date.",
    grain="1 row = 1 portfolio x 1 trading date",
    key=("portfolio_id", "trade_date"),
    columns=(
        Column("portfolio_id", "string", True, "Portfolio code, e.g. ew7"),
        Column("trade_date", "date", True, "Trading date of the return"),
        Column("simple_return", "double", True, "Sum over tickers of weight x simple_return (simple returns add across assets)"),
        Column("log_return", "double", True, "ln(1 + simple_return); use to add across time"),
        Column("n_assets", "int", True, "Number of tickers with a return on this date; less than expected means missing data"),
        Column("weights_valid_from", "date", True, "valid_from of the weight version used (trace to portfolio_weights_s)"),
    ) + tech_columns(),
    serves=("Q1", "Q2", "Q5"),
)

# Ý nghĩa: Mọi con số VaR/ES, mỗi dòng ghi đủ "tính ngày nào, cách nào, mức tin cậy nào,
# horizon nào, dùng bao nhiêu dữ liệu". window_end để kiểm toán look-ahead bias.
VAR_ESTIMATES_G = TableSpec(
    namespace="gold",
    name="var_estimates_g",
    description="VaR and Expected Shortfall estimates by method, confidence, horizon and estimation window.",
    grain="1 row = 1 portfolio x as_of_date x method x confidence x horizon x window",
    key=VAR_KEY,
    columns=var_key_columns() + (
        Column("window_start", "date", True, "First return date in the estimation window"),
        Column("window_end", "date", True, "Last return date in the estimation window; must be <= as_of_date"),
        Column("n_obs", "int", True, "Number of daily returns actually used"),
        Column("var_pct", "double", True, "Value at Risk as a positive fraction of portfolio value (0.087 = 8.7% loss)"),
        Column("es_pct", "double", True, "Expected Shortfall (CVaR): mean loss beyond VaR, positive fraction"),
        Column("run_id", "string", False, "Monte Carlo run folder in mc_runs; null for historical and parametric"),
        Column("seed", "long", False, "Random seed of the Monte Carlo run; null for non-simulation methods"),
        Column("n_paths", "int", False, "Number of simulated paths; null for non-simulation methods"),
    ) + tech_columns(),
    serves=("Q1", "Q4"),
)

# Ý nghĩa: Tóm tắt path Monte Carlo bằng phân vị theo từng ngày (để vẽ fan chart).
# KHÔNG lưu toàn bộ path ở gold: path đầy đủ nằm trong mc_runs/run_id=... kèm manifest.
MC_PATHS_SUMMARY_G = TableSpec(
    namespace="gold",
    name="mc_paths_summary_g",
    description="Quantiles of simulated cumulative portfolio return per day step of one Monte Carlo run (full paths stay in mc_runs).",
    grain="1 row = 1 Monte Carlo run x 1 day step x 1 quantile",
    key=("run_id", "step", "quantile_bp"),
    columns=(
        Column("run_id", "string", True, "Monte Carlo run folder in mc_runs"),
        Column("step", "int", True, "Trading days after as_of_date: 0 .. horizon_days"),
        Column("quantile_bp", "int", True, "Quantile in basis points, e.g. 100 = 1st percentile, 5000 = median"),
        Column("portfolio_id", "string", True, "Portfolio code"),
        Column("as_of_date", "date", True, "Start date of the simulation"),
        Column("method", "string", True, "mc_normal | mc_t | mc_bootstrap"),
        Column("cum_return", "double", True, "Cumulative simple portfolio return from as_of_date to this step, at this quantile"),
        Column("seed", "long", True, "Random seed of the run"),
        Column("n_paths", "int", True, "Number of simulated paths"),
    ) + tech_columns(),
    serves=("Q1",),
)

# Ý nghĩa: Backtest từng ngày: VaR dự báo hôm đó so với lãi/lỗ thực tế sau đó.
# Cùng khóa với var_estimates_g (1:1). Đây là bảng DUY NHẤT được đọc return sau as_of_date.
VAR_BACKTEST_G = TableSpec(
    namespace="gold",
    name="var_backtest_g",
    description="Each VaR estimate compared with the realised portfolio return over its horizon.",
    grain="1 row = 1 portfolio x as_of_date x method x confidence x horizon x window (1:1 with var_estimates_g)",
    key=VAR_KEY,
    columns=var_key_columns() + (
        Column("var_pct", "double", True, "VaR copied from var_estimates_g, positive fraction"),
        Column("realized_end_date", "date", True, "Last date of the realised window (horizon_days trading days after as_of_date)"),
        Column("realized_return", "double", True, "Realised cumulative simple portfolio return from as_of_date to realized_end_date"),
        Column("is_violation", "boolean", True, "True when realized_return < -var_pct (loss larger than VaR)"),
    ) + tech_columns(),
    serves=("Q2",),
)

# Ý nghĩa: Bảng KẾT LUẬN cho Q2: đếm vi phạm và kiểm định thống kê theo từng phương pháp.
# Christoffersen để null với horizon 21 (cửa sổ chồng lấn làm kiểm định độc lập sai).
VAR_TEST_RESULTS_G = TableSpec(
    namespace="gold",
    name="var_test_results_g",
    description="Backtest statistics per method: violation counts, Kupiec POF and Christoffersen independence tests.",
    grain="1 row = 1 portfolio x method x confidence x horizon x window x test period",
    key=("portfolio_id", "method", "confidence_bp", "horizon_days", "window_days", "test_start", "test_end"),
    columns=(
        Column("portfolio_id", "string", True, "Portfolio code"),
        Column("method", "string", True, "historical | parametric | mc_normal | mc_t | mc_bootstrap"),
        Column("confidence_bp", "int", True, "Confidence level in basis points"),
        Column("horizon_days", "int", True, "Holding horizon in trading days"),
        Column("window_days", "int", True, "Estimation window in trading days"),
        Column("test_start", "date", True, "First as_of_date in the test period"),
        Column("test_end", "date", True, "Last as_of_date in the test period"),
        Column("n_obs", "int", True, "Number of backtest rows tested"),
        Column("n_violations", "int", True, "Number of rows with is_violation = true"),
        Column("expected_violations", "double", True, "n_obs x (1 - confidence)"),
        Column("violation_rate", "double", True, "n_violations / n_obs"),
        Column("kupiec_lr", "double", False, "Kupiec proportion-of-failures likelihood ratio"),
        Column("kupiec_pvalue", "double", False, "p-value of the Kupiec test; small = violation rate is wrong"),
        Column("christoffersen_lr", "double", False, "Christoffersen independence likelihood ratio; null for overlapping horizons"),
        Column("christoffersen_pvalue", "double", False, "p-value of the Christoffersen test; small = violations cluster"),
    ) + tech_columns(),
    serves=("Q2", "Q4"),
)

# Ý nghĩa: VaR được chia cho từng mã (như chia hóa đơn theo ai gọi nhiều món).
# Tổng component_var_pct của các mã = var_pct của danh mục (pipeline kiểm tra).
RISK_CONTRIBUTION_G = TableSpec(
    namespace="gold",
    name="risk_contribution_g",
    description="Component VaR per ticker; contributions add up to the portfolio VaR in var_estimates_g.",
    grain="1 row = 1 portfolio x as_of_date x method x confidence x horizon x window x ticker",
    key=VAR_KEY + ("ticker",),
    columns=var_key_columns() + (
        Column("ticker", "string", True, "Exchange symbol"),
        Column("weight", "double", True, "Portfolio weight of the ticker on as_of_date"),
        Column("component_var_pct", "double", True, "Share of portfolio VaR due to this ticker, fraction of portfolio value"),
        Column("pct_of_total", "double", True, "component_var_pct / portfolio var_pct; sums to 1 over tickers"),
    ) + tech_columns(),
    serves=("Q3",),
)

# Ý nghĩa: Kịch bản căng thẳng. historical = chạy lại khủng hoảng thật (2020, 2022);
# hypothetical = tự đặt tương quan cao hơn (corr_override). Cột không áp dụng để null.
STRESS_SCENARIOS_G = TableSpec(
    namespace="gold",
    name="stress_scenarios_g",
    description="Stress test results: historical crisis replays and hypothetical correlation shocks.",
    grain="1 row = 1 scenario x 1 portfolio",
    key=("scenario_id", "portfolio_id"),
    columns=(
        Column("scenario_id", "string", True, "Scenario code, e.g. covid_2020, rates_2022, corr_080"),
        Column("portfolio_id", "string", True, "Portfolio code"),
        Column("scenario_type", "string", True, "historical | hypothetical"),
        Column("description", "string", True, "What the scenario assumes, in one sentence"),
        Column("start_date", "date", False, "First date of a historical window; null for hypothetical"),
        Column("end_date", "date", False, "Last date of a historical window; null for hypothetical"),
        Column("portfolio_return", "double", False, "Cumulative simple return over the historical window"),
        Column("max_drawdown", "double", False, "Largest peak-to-trough fall in the window, positive fraction"),
        Column("worst_day_return", "double", False, "Worst single-day portfolio return in the window"),
        Column("corr_override", "double", False, "Pairwise correlation imposed in a hypothetical scenario, e.g. 0.8"),
        Column("confidence_bp", "int", False, "Confidence of the stressed VaR, basis points"),
        Column("horizon_days", "int", False, "Horizon of the stressed VaR, trading days"),
        Column("base_var_pct", "double", False, "VaR without the shock, same confidence and horizon"),
        Column("stressed_var_pct", "double", False, "VaR under the shock; stressed / base = amplification"),
    ) + tech_columns(),
    serves=("Q3", "Q5"),
)

GOLD_TABLES: tuple[TableSpec, ...] = (
    PORTFOLIO_RETURNS_G,
    VAR_ESTIMATES_G,
    MC_PATHS_SUMMARY_G,
    VAR_BACKTEST_G,
    VAR_TEST_RESULTS_G,
    RISK_CONTRIBUTION_G,
    STRESS_SCENARIOS_G,
)

# Ý nghĩa: Danh sách mọi bảng đã thiết kế (bronze, silver ở Buổi 4; gold ở Buổi 5).
TABLES: tuple[TableSpec, ...] = (
    PRICES_DAILY_B,
    RETURNS_DAILY_S,
    INSTRUMENTS_S,
    PORTFOLIO_WEIGHTS_S,
) + GOLD_TABLES


# Ý nghĩa: Sinh data dictionary dạng Markdown từ TABLES, để tài liệu không bao giờ
# lệch với thiết kế: muốn sửa tài liệu thì sửa spec rồi sinh lại.
def render_data_dictionary(tables: tuple[TableSpec, ...] = TABLES) -> str:
    lines = [
        "# Data dictionary",
        "",
        "Generated from `src/portfolio_risk_lab/schemas.py` by `scripts/create_tables.py`. "
        "Do not edit by hand: change the spec and regenerate.",
        "",
        "Keys are logical: Iceberg records them as identifier fields but does not reject duplicates, "
        "so uniqueness is checked by data quality rules in the pipeline.",
        "",
        "## Business questions",
        "",
        "| Id | Question |",
        "|---|---|",
    ]
    lines += [f"| {qid} | {text} |" for qid, text in BUSINESS_QUESTIONS.items()]
    lines += ["", "## Tables", "", "| Table | Grain | Serves |", "|---|---|---|"]
    lines += [
        f"| `{t.identifier}` | {t.grain} | {', '.join(t.serves)} |" for t in tables
    ]
    for t in tables:
        lines += [
            "",
            f"## `{t.identifier}`",
            "",
            t.description,
            "",
            f"- Grain: {t.grain}",
            f"- Key: `{', '.join(t.key)}`",
            f"- Serves: {', '.join(t.serves)}",
            "",
            "| # | Column | Type | Required | Description |",
            "|---|---|---|---|---|",
        ]
        for i, c in enumerate(t.columns, start=1):
            key_mark = " (key)" if c.name in t.key else ""
            lines.append(
                f"| {i} | `{c.name}`{key_mark} | {c.type} | {'yes' if c.required else 'no'} | {c.doc} |"
            )
    return "\n".join(lines) + "\n"


# Ý nghĩa: Truy vết hai chiều giữa câu hỏi nghiệp vụ và bảng gold.
# Chiều xuôi: câu hỏi nào chưa có bảng gold trả lời. Chiều ngược: bảng gold nào
# không phục vụ câu nào. Cả hai danh sách phải rỗng (unit test kiểm tra).
def traceability_gaps(tables: tuple[TableSpec, ...] = TABLES) -> dict[str, list[str]]:
    gold = [t for t in tables if t.namespace == "gold"]
    served = {q for t in gold for q in t.serves}
    return {
        "questions_without_gold": [q for q in BUSINESS_QUESTIONS if q not in served],
        "gold_without_question": [t.identifier for t in gold
                                  if not set(t.serves) & set(BUSINESS_QUESTIONS)],
    }


# Ý nghĩa: Sinh docs/traceability.md: ma trận câu hỏi x bảng (x = bảng phục vụ câu đó),
# cho mọi tầng, kèm kết quả kiểm tra truy vết hai chiều.
def render_traceability(tables: tuple[TableSpec, ...] = TABLES) -> str:
    qids = list(BUSINESS_QUESTIONS)
    lines = [
        "# Traceability: business questions to tables",
        "",
        "Generated from `src/portfolio_risk_lab/schemas.py` by `scripts/render_traceability.py`. "
        "Do not edit by hand: change `serves` in the spec and regenerate.",
        "",
        "An `x` means the table helps answer the question. Which table is primary for each "
        "question is explained in [`layers.md`](layers.md).",
        "",
        "## Business questions",
        "",
        "| Id | Question |",
        "|---|---|",
    ]
    lines += [f"| {q} | {text} |" for q, text in BUSINESS_QUESTIONS.items()]
    lines += ["", "## Matrix", "", "| Table | " + " | ".join(qids) + " |",
              "|---|" + "---|" * len(qids)]
    for t in tables:
        marks = ["x" if q in t.serves else "" for q in qids]
        lines.append(f"| `{t.identifier}` | " + " | ".join(marks) + " |")
    gaps = traceability_gaps(tables)
    lines += ["", "## Checks", ""]
    lines.append("- Every question has at least one gold table: "
                 + ("yes" if not gaps["questions_without_gold"]
                    else "NO, missing " + ", ".join(gaps["questions_without_gold"])))
    lines.append("- Every gold table serves at least one question: "
                 + ("yes" if not gaps["gold_without_question"]
                    else "NO, orphan " + ", ".join(gaps["gold_without_question"])))
    return "\n".join(lines) + "\n"
