# Ý nghĩa: Unit test cho thiết kế gold (Buổi 5). Kiểm tra thiết kế, chưa có dữ liệu:
# truy vết hai chiều, khóa không dùng double, các bảng cùng "một con số VaR" có cùng khóa.
"""Tests for gold table specs and traceability."""

import pytest

from portfolio_risk_lab.schemas import (
    BUSINESS_QUESTIONS,
    GOLD_TABLES,
    TABLES,
    VAR_BACKTEST_G,
    VAR_ESTIMATES_G,
    RISK_CONTRIBUTION_G,
    render_traceability,
    traceability_gaps,
)


# Ý nghĩa: Đủ 7 bảng gold, đúng namespace, đúng hậu tố, không trùng tên.
def test_gold_tables_named_correctly():
    assert len(GOLD_TABLES) == 7
    assert all(t.namespace == "gold" and t.name.endswith("_g") for t in GOLD_TABLES)
    names = [t.identifier for t in TABLES]
    assert len(names) == len(set(names))


# Ý nghĩa: Truy vết hai chiều: câu nào cũng có bảng gold, bảng gold nào cũng có câu.
def test_traceability_both_directions():
    gaps = traceability_gaps(TABLES)
    assert gaps["questions_without_gold"] == []
    assert gaps["gold_without_question"] == []


# Ý nghĩa: serves chỉ được chứa mã câu hỏi có thật (bắt lỗi gõ nhầm "Q6", "q1").
@pytest.mark.parametrize("table", TABLES, ids=lambda t: t.identifier)
def test_serves_only_known_questions(table):
    assert set(table.serves) <= set(BUSINESS_QUESTIONS)


# Ý nghĩa: Cột khóa phải tồn tại, bắt buộc (NOT NULL) và KHÔNG phải double.
@pytest.mark.parametrize("table", TABLES, ids=lambda t: t.identifier)
def test_key_columns_required_and_not_double(table):
    for name in table.key:
        col = table.column(name)
        assert col.required, f"{table.identifier}.{name} is a key but optional"
        assert col.type != "double", f"{table.identifier}.{name} is a key of type double"


# Ý nghĩa: Mức tin cậy và phân vị lưu số nguyên basis point ở mọi bảng có cột đó.
@pytest.mark.parametrize("table", GOLD_TABLES, ids=lambda t: t.identifier)
def test_confidence_and_quantile_are_int(table):
    for col in table.columns:
        if col.name in ("confidence_bp", "quantile_bp"):
            assert col.type == "int"


# Ý nghĩa: Backtest join 1:1 với ước lượng; risk contribution = khóa ước lượng + ticker.
def test_var_tables_share_key():
    assert VAR_BACKTEST_G.key == VAR_ESTIMATES_G.key
    assert RISK_CONTRIBUTION_G.key == VAR_ESTIMATES_G.key + ("ticker",)


# Ý nghĩa: Có cột để kiểm toán look-ahead (window_end) và ghi cửa sổ thực tế (realized_end_date).
def test_lookahead_audit_columns():
    assert VAR_ESTIMATES_G.column("window_end").type == "date"
    assert VAR_BACKTEST_G.column("realized_end_date").type == "date"


# Ý nghĩa: 3 cột kỹ thuật luôn nằm cuối mọi bảng gold, đúng thứ tự quy ước.
@pytest.mark.parametrize("table", GOLD_TABLES, ids=lambda t: t.identifier)
def test_gold_tech_columns_last(table):
    assert [c.name for c in table.columns[-3:]] == ["batch_id", "source_system", "ingest_ts"]


# Ý nghĩa: File traceability sinh ra có đủ mọi bảng và báo kiểm tra đạt.
def test_render_traceability():
    md = render_traceability(TABLES)
    assert all(f"`{t.identifier}`" in md for t in TABLES)
    assert "NO," not in md
