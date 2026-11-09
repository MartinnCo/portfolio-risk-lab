# Ý nghĩa: Unit test cho THIẾT KẾ bảng (không cần dữ liệu, không cần ổ RiskLab):
# kiểm tra mọi spec tuân thủ quy ước dự án. Thiết kế sai bị bắt ở đây, trước khi
# có bảng Iceberg nào bị tạo sai.  Chạy: uv run pytest -q
"""Design rules every table spec must follow."""

import re

import pytest

from portfolio_risk_lab.schemas import (
    ALLOWED_TYPES,
    BUSINESS_QUESTIONS,
    TABLES,
    render_data_dictionary,
)

SUFFIX = {"bronze": "_b", "silver": "_s", "gold": "_g", "work": "_w"}
SNAKE = re.compile(r"^[a-z][a-z0-9_]*$")
TECH = ("batch_id", "source_system", "ingest_ts")

ids = [t.identifier for t in TABLES]


# Ý nghĩa: Tên bảng đúng namespace + đúng hậu tố + snake_case.
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_table_name(t):
    assert t.namespace in SUFFIX
    assert t.name.endswith(SUFFIX[t.namespace])
    assert SNAKE.match(t.name)


# Ý nghĩa: Tên cột snake_case, không trùng, kiểu nằm trong danh sách cho phép, có mô tả.
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_columns(t):
    names = [c.name for c in t.columns]
    assert len(names) == len(set(names)), "cột trùng tên"
    for c in t.columns:
        assert SNAKE.match(c.name), c.name
        assert c.type in ALLOWED_TYPES, (c.name, c.type)
        assert c.doc.strip(), f"{c.name} thiếu mô tả"


# Ý nghĩa: 3 cột kỹ thuật có mặt, bắt buộc, đúng thứ tự ở cuối bảng.
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_tech_columns_last(t):
    assert tuple(c.name for c in t.columns[-3:]) == TECH
    assert all(c.required for c in t.columns[-3:])


# Ý nghĩa: Cột khóa phải tồn tại, bắt buộc, và không phải số thực (luật identifier field
# của Iceberg: float/double không làm khóa được vì so sánh bằng nhau không tin cậy).
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_key(t):
    for k in t.key:
        col = t.column(k)
        assert col.required, f"khóa {k} phải bắt buộc"
        assert col.type not in {"double"}, f"khóa {k} không được là double"


# Ý nghĩa: Ngày luôn là kiểu date (không timestamp có múi giờ), trừ ingest_ts.
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_dates_are_date(t):
    for c in t.columns:
        if c.name.endswith("_date") or c.name in {"valid_from", "valid_to"}:
            assert c.type == "date", c.name


# Ý nghĩa: Bảng theo thời gian có đủ valid_from (bắt buộc, nằm trong khóa) và valid_to (cho phép null).
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_validity_columns(t):
    names = {c.name for c in t.columns}
    if "valid_from" in names or "valid_to" in names:
        assert "valid_from" in t.key
        assert not t.column("valid_to").required


# Ý nghĩa: Mỗi bảng truy vết được tới ít nhất một câu hỏi nghiệp vụ có thật.
@pytest.mark.parametrize("t", TABLES, ids=ids)
def test_traceability(t):
    assert t.serves, "bảng không phục vụ câu hỏi nào"
    assert set(t.serves) <= set(BUSINESS_QUESTIONS)


# Ý nghĩa: Data dictionary sinh ra có đủ mọi bảng và mọi cột.
def test_dictionary_complete():
    md = render_data_dictionary()
    for t in TABLES:
        assert f"## `{t.identifier}`" in md
        for c in t.columns:
            assert f"`{c.name}`" in md
