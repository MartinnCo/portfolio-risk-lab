# Ý nghĩa: Sinh docs/traceability.md từ schemas.py (ma trận câu hỏi x bảng + kiểm tra
# truy vết hai chiều). Chạy từ thư mục gốc repo: uv run python scripts/render_traceability.py
"""Render docs/traceability.md from the table specs."""

from pathlib import Path

from portfolio_risk_lab.schemas import TABLES, render_traceability, traceability_gaps

# Ý nghĩa: Đường dẫn file đích, tính từ vị trí script (scripts/ -> gốc repo -> docs/).
OUT = Path(__file__).resolve().parent.parent / "docs" / "traceability.md"


def main() -> None:
    # Ý nghĩa: Ghi file Markdown rồi in kết quả kiểm tra để thấy ngay trên terminal.
    OUT.write_text(render_traceability(TABLES), encoding="utf-8")
    gaps = traceability_gaps(TABLES)
    print(f"Wrote {OUT} ({len(TABLES)} tables)")
    print("Questions without gold table:", gaps["questions_without_gold"] or "none")
    print("Gold tables without question:", gaps["gold_without_question"] or "none")


if __name__ == "__main__":
    main()
