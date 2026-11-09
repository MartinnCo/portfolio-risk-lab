# Ý nghĩa: Điểm chạy của Buổi 4 (GĐ 2b). Ba việc, theo thứ tự:
# (1) so cột của file raw thật với thiết kế bảng bronze, (2) tạo namespace và bảng
# Iceberg còn thiếu (chạy lại nhiều lần vẫn an toàn), (3) sinh docs/data_dictionary.md.
# Chạy trong repo, sau `source session.sh`:  uv run python scripts/create_tables.py
"""Create Iceberg tables from specs and regenerate the data dictionary."""

from __future__ import annotations

from pathlib import Path

import pyarrow.parquet as pq

from portfolio_risk_lab import config
from portfolio_risk_lab.catalog import ensure_tables, get_catalog
from portfolio_risk_lab.schemas import PRICES_DAILY_B, TABLES, render_data_dictionary

REPO_ROOT = Path(__file__).resolve().parents[1]
TECH = {"batch_id", "source_system", "ingest_ts"}


# Ý nghĩa: Đọc schema (chỉ phần đầu file, không đọc dữ liệu) của raw batch mới nhất
# và so với các cột nghiệp vụ của bronze. Thiết kế phải khớp dữ liệu thật trước khi
# viết pipeline ở GĐ 2c.
def check_raw_against_bronze() -> None:
    raw_file = config.latest_raw_batch() / "prices.parquet"
    raw_schema = pq.read_schema(raw_file)
    raw_cols = {name: str(raw_schema.field(name).type) for name in raw_schema.names}
    bronze_cols = {c.name for c in PRICES_DAILY_B.columns} - TECH

    print(f"[1] Raw: {raw_file.parent.name}")
    for name, typ in raw_cols.items():
        print(f"      {name:<12} {typ}")
    missing = sorted(bronze_cols - set(raw_cols))
    extra = sorted(set(raw_cols) - bronze_cols)
    print(f"    Cột bronze không có trong raw: {missing or 'không'}")
    print(f"    Cột raw không có trong bronze: {extra or 'không'}")


# Ý nghĩa: Tạo bảng và in trạng thái từng bảng (created / exists, matches spec / DRIFT).
def create_tables() -> None:
    catalog = get_catalog()
    print(f"\n[2] Catalog '{catalog.name}' tại {catalog.properties['uri']}")
    for identifier, state in ensure_tables(TABLES).items():
        print(f"    {identifier:<28} {state}")
    for ns in ("bronze", "silver", "gold", "work"):
        if catalog.namespace_exists(ns):
            tables = [".".join(t) for t in catalog.list_tables(ns)]
            print(f"    namespace {ns:<7}: {tables}")
    print("\n    Schema của silver.returns_daily_s theo catalog:")
    print(catalog.load_table("silver.returns_daily_s").schema())


# Ý nghĩa: Ghi data dictionary sinh từ spec vào docs/.
def write_dictionary() -> None:
    out = REPO_ROOT / "docs" / "data_dictionary.md"
    out.write_text(render_data_dictionary(), encoding="utf-8")
    print(f"\n[3] Đã ghi {out.relative_to(REPO_ROOT)} ({out.stat().st_size:,} byte)")


if __name__ == "__main__":
    check_raw_against_bronze()
    create_tables()
    write_dictionary()
