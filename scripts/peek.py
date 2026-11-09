# Ý nghĩa: Xem nhanh 5 dòng đầu và số dòng của raw (file Parquet), bronze và silver
# (bảng Iceberg). Chỉ đọc, không ghi gì.
# Chạy trong repo, sau `source session.sh`:  uv run python scripts/peek.py
"""Peek at the first rows of raw, bronze and silver."""

from __future__ import annotations

import pandas as pd
import pyarrow.parquet as pq
from pyiceberg.exceptions import NoSuchTableError

from portfolio_risk_lab import config
from portfolio_risk_lab.catalog import get_catalog

N = 5

# Ý nghĩa: Cho pandas in đủ mọi cột trên một dòng thay vì cắt bằng "...".
pd.set_option("display.max_columns", None)
pd.set_option("display.width", 200)


# Ý nghĩa: Raw là file Parquet thường. Số dòng đọc từ phần metadata ở cuối file
# (không phải đọc dữ liệu); 5 dòng đầu thì cắt từ bảng đã đọc.
def peek_raw() -> None:
    path = config.latest_raw_batch() / "prices.parquet"
    n_rows = pq.ParquetFile(path).metadata.num_rows
    print(f"=== RAW  {path.parent.name}  ({n_rows:,} dòng)")
    print(pq.read_table(path).slice(0, N).to_pandas(), "\n")


# Ý nghĩa: Bảng Iceberg. Chưa từng ghi thì current_snapshot() là None, nghĩa là 0 dòng.
# Đã ghi thì số dòng nằm sẵn trong summary của snapshot (không phải quét dữ liệu).
# scan(limit=5) chỉ đọc đủ 5 dòng.
def peek_iceberg(identifier: str) -> None:
    try:
        table = get_catalog().load_table(identifier)
    except NoSuchTableError:
        print(f"=== {identifier}: chưa có bảng. Chạy: uv run python scripts/create_tables.py\n")
        return
    snap = table.current_snapshot()
    if snap is None:
        print(f"=== {identifier}: 0 dòng (chưa có snapshot nào, bảng chưa từng được ghi)")
        print(f"    Cột: {[f.name for f in table.schema().fields]}\n")
        return
    total = snap.summary["total-records"] if snap.summary else "?"
    print(f"=== {identifier}  ({total} dòng, snapshot {snap.snapshot_id})")
    print(table.scan(limit=N).to_pandas(), "\n")


if __name__ == "__main__":
    peek_raw()
    for ident in ("bronze.prices_daily_b", "silver.returns_daily_s"):
        peek_iceberg(ident)
