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

# Ý nghĩa: Danh sách mọi bảng đã thiết kế. Gold sẽ thêm ở Buổi 5.
TABLES: tuple[TableSpec, ...] = (
    PRICES_DAILY_B,
    RETURNS_DAILY_S,
    INSTRUMENTS_S,
    PORTFOLIO_WEIGHTS_S,
)


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
