# Ý nghĩa: Nối thiết kế bảng (schemas.py) với Iceberg: mở catalog SQLite trên RiskLab,
# đổi TableSpec thành Iceberg Schema, tạo bảng nếu chưa có, và cảnh báo khi bảng
# đã có trong catalog khác với thiết kế hiện tại (schema drift).
"""Iceberg catalog helpers: open the SQLite catalog and create tables from specs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pyiceberg.catalog.sql import SqlCatalog
from pyiceberg.schema import Schema
from pyiceberg.table import Table
from pyiceberg.types import (
    BooleanType,
    DateType,
    DoubleType,
    IntegerType,
    LongType,
    NestedField,
    StringType,
    TimestamptzType,
)

from portfolio_risk_lab.config import warehouse_dir
from portfolio_risk_lab.schemas import TableSpec

DEFAULT_CATALOG_NAME = "risklab"
DEFAULT_CATALOG_FILE = "catalog.db"

# Ý nghĩa: Bảng tra từ tên kiểu trong spec sang lớp kiểu của Iceberg.
_ICEBERG_TYPES = {
    "string": StringType,
    "date": DateType,
    "int": IntegerType,
    "long": LongType,
    "double": DoubleType,
    "boolean": BooleanType,
    "timestamptz": TimestamptzType,
}


# Ý nghĩa: Tìm file catalog SQLite đã tạo ở Buổi 0 trong thư mục warehouse.
# Có đúng 1 file .db thì dùng nó; chưa có thì dùng catalog.db; có nhiều thì dừng để
# không vô tình chia dữ liệu ra hai catalog.
def _catalog_file() -> Path:
    wh = warehouse_dir()
    dbs = sorted(wh.glob("*.db"))
    if len(dbs) > 1:
        raise RuntimeError(f"Có nhiều file catalog trong {wh}: {[p.name for p in dbs]}. Giữ một file.")
    return dbs[0] if dbs else wh / DEFAULT_CATALOG_FILE


# Ý nghĩa: SqlCatalog lưu tên catalog trong từng dòng của file SQLite. Mở bằng tên khác
# thì không thấy namespace/bảng cũ. Hàm này đọc tên đã dùng (Buổi 0) bằng sqlite3 có sẵn.
def _existing_catalog_name(db_file: Path) -> str | None:
    if not db_file.exists():
        return None
    names: set[str] = set()
    with sqlite3.connect(db_file) as con:
        for tbl in ("iceberg_namespace_properties", "iceberg_tables"):
            try:
                names |= {r[0] for r in con.execute(f"SELECT DISTINCT catalog_name FROM {tbl}")}
            except sqlite3.OperationalError:  # bảng chưa tồn tại
                pass
    if len(names) > 1:
        raise RuntimeError(f"File {db_file.name} chứa nhiều catalog: {sorted(names)}")
    return names.pop() if names else None


# Ý nghĩa: Mở catalog Iceberg: metadata trong file SQLite, file dữ liệu dưới warehouse/.
def get_catalog() -> SqlCatalog:
    db_file = _catalog_file()
    name = _existing_catalog_name(db_file) or DEFAULT_CATALOG_NAME
    return SqlCatalog(
        name,
        uri=f"sqlite:///{db_file}",
        warehouse=f"file://{warehouse_dir()}",
    )


# Ý nghĩa: Đổi TableSpec sang Iceberg Schema. field_id đánh số 1, 2, 3...; Iceberg dùng
# số này (không dùng tên) để nhận ra cột, nên đổi tên cột về sau không làm hỏng dữ liệu cũ.
# Cột khóa được đánh dấu identifier field.
def to_iceberg_schema(spec: TableSpec) -> Schema:
    fields = [
        NestedField(
            field_id=i,
            name=c.name,
            field_type=_ICEBERG_TYPES[c.type](),
            required=c.required,
            doc=c.doc,
        )
        for i, c in enumerate(spec.columns, start=1)
    ]
    id_by_name = {f.name: f.field_id for f in fields}
    return Schema(*fields, identifier_field_ids=[id_by_name[k] for k in spec.key])


# Ý nghĩa: So sánh bảng đang có trong catalog với spec theo (tên, kiểu, bắt buộc).
# Trả về danh sách khác biệt; rỗng nghĩa là khớp.
def schema_drift(table: Table, spec: TableSpec) -> list[str]:
    actual = [(f.name, str(f.field_type), f.required) for f in table.schema().fields]
    expected = [(c.name, c.type, c.required) for c in spec.columns]
    if actual == expected:
        return []
    diffs = [f"thiếu trong catalog: {e}" for e in expected if e not in actual]
    diffs += [f"thừa trong catalog: {a}" for a in actual if a not in expected]
    if not diffs:
        diffs = ["cùng cột nhưng khác thứ tự"]
    return diffs


# Ý nghĩa: Tạo namespace và bảng còn thiếu. Chạy lại bao nhiêu lần cũng an toàn
# (idempotent): bảng đã có thì giữ nguyên, chỉ báo nếu lệch thiết kế. KHÔNG tự sửa
# hay xóa bảng; đổi schema là quyết định có chủ đích, làm bằng tay và ghi nhật ký.
def ensure_tables(specs: tuple[TableSpec, ...]) -> dict[str, str]:
    catalog = get_catalog()
    status: dict[str, str] = {}
    for spec in specs:
        if not catalog.namespace_exists(spec.namespace):
            catalog.create_namespace(spec.namespace)
        existed = catalog.table_exists(spec.identifier)
        table = catalog.create_table_if_not_exists(
            identifier=spec.identifier,
            schema=to_iceberg_schema(spec),
            properties={"comment": spec.description},
        )
        if not existed:
            status[spec.identifier] = "created"
        else:
            drift = schema_drift(table, spec)
            status[spec.identifier] = "exists, matches spec" if not drift else "DRIFT: " + "; ".join(drift)
    return status
