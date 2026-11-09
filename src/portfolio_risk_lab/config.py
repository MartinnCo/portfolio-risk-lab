# Ý nghĩa: Một nơi duy nhất giữ cấu hình dùng chung của dự án (danh sách mã,
# khoảng ngày, hằng số thời gian, seed mặc định) và các hàm trả về đường dẫn
# dữ liệu trên ổ ảo RiskLab. Notebook và script import từ đây thay vì tự khai báo lại.
"""Shared configuration for Portfolio Risk Lab (tickers, dates, paths)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

# Ý nghĩa: Phạm vi dữ liệu. Đổi bất kỳ dòng nào ở đây phải ghi vào Nhật ký quyết định.
STOCKS: tuple[str, ...] = ("NVDA", "AAPL", "TSLA", "MSFT", "JPM", "KO", "PEP")
BENCHMARK: str = "SPY"                          # benchmark, không nằm trong danh mục
TICKERS: tuple[str, ...] = STOCKS + (BENCHMARK,)  # mọi mã cần tải giá

START: date = date(2015, 1, 1)
END_EXCLUSIVE: date = date(2026, 11, 7)         # quyết định #8: cố định để tái lập

# Ý nghĩa: Hằng số thời gian dùng khi đổi vol/VaR giữa ngày, tháng, năm.
TRADING_DAYS_PER_YEAR: int = 252
HORIZON_DAYS: int = 21                          # 1 tháng ≈ 21 phiên

# Ý nghĩa: Seed mặc định cho mọi mô phỏng; luôn ghi seed thực dùng vào kết quả.
DEFAULT_SEED: int = 42

RISKLAB_MOUNT = Path("/Volumes/RiskLab")


# Ý nghĩa: Lấy thư mục dữ liệu từ biến môi trường RISKLAB_DATA và kiểm tra
# 3 điều trước khi trả về: biến đã đặt, RiskLab đang mount, đường dẫn nằm trên RiskLab.
# Viết thành hàm (không phải hằng số) để việc import config không bao giờ lỗi;
# chỉ khi thật sự cần đường dẫn mới kiểm tra.
def data_dir() -> Path:
    """Return $RISKLAB_DATA after checking it lives on the mounted RiskLab volume."""
    raw = os.environ.get("RISKLAB_DATA")
    if not raw:
        raise RuntimeError(
            "Thiếu biến RISKLAB_DATA. Chạy: "
            "source /Volumes/RiskLab/portfolio-risk-lab/session.sh"
        )
    if not os.path.ismount(RISKLAB_MOUNT):
        raise RuntimeError(f"{RISKLAB_MOUNT} chưa mount. Chạy hdiutil attach trước.")
    path = Path(raw).resolve()
    if RISKLAB_MOUNT not in path.parents:
        raise RuntimeError(f"RISKLAB_DATA={path} không nằm trên {RISKLAB_MOUNT}.")
    return path


# Ý nghĩa: Đường dẫn tới 4 vùng dữ liệu (khớp các data store D1, D2–D4/D6, D5, D7 trong DFD).
def raw_prices_dir() -> Path:
    return data_dir() / "raw" / "yfinance" / "prices_daily"   # D1


def warehouse_dir() -> Path:
    return data_dir() / "warehouse"                            # Iceberg: bronze/silver/gold/work


def mc_runs_dir() -> Path:
    return data_dir() / "mc_runs"                              # D5


def exports_dir() -> Path:
    return data_dir() / "exports"                              # D7


# Ý nghĩa: Tìm batch raw mới nhất. Tên thư mục batch_id=YYYYMMDDTHHMMSSZ sắp xếp
# theo chữ cũng chính là sắp xếp theo thời gian, nên lấy phần tử cuối là mới nhất.
def latest_raw_batch() -> Path:
    """Return the newest raw price batch directory (append-only store D1)."""
    batches = sorted(p for p in raw_prices_dir().glob("batch_id=*") if p.is_dir())
    if not batches:
        raise FileNotFoundError(f"Chưa có batch nào trong {raw_prices_dir()}")
    return batches[-1]


# Ý nghĩa: Chạy thử bằng `uv run python -m portfolio_risk_lab.config` để in cấu hình
# và kiểm tra đường dẫn. Khi file được import, khối này không chạy.
if __name__ == "__main__":
    print(f"TICKERS      : {TICKERS}")
    print(f"Khoảng ngày  : {START} -> {END_EXCLUSIVE} (không gồm ngày cuối)")
    print(f"data_dir     : {data_dir()}")
    print(f"raw mới nhất : {latest_raw_batch()}")
