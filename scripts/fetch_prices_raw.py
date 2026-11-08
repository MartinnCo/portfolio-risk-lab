"""Buổi 1 – Tải giá ngày (raw) từ yfinance cho danh mục mặc định.

Chạy từ repo, sau khi `source session.sh`:
    uv run python scripts/fetch_prices_raw.py

Ghi vào: $RISKLAB_DATA/raw/yfinance/prices_daily/batch_id=<UTC>/
    prices.parquet  (dạng dài: ticker, trade_date, open, high, low, close, adj_close, volume
                     + ingest_ts, source_system, batch_id)
    manifest.json   (tham số tải, phiên bản thư viện, số dòng, ngày đầu/cuối từng mã)

Đây là bản tải thô cho EDA của GĐ 1. Pipeline idempotent vào Iceberg làm ở GĐ 2c.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

TICKERS = ["NVDA", "AAPL", "TSLA", "MSFT", "JPM", "KO", "PEP", "SPY"]
START = "2015-01-01"
END = "2026-11-07"  # yfinance coi end là exclusive -> dữ liệu đến hết 2026-11-06; cố định để tái lập
AUTO_ADJUST = False  # Nhật ký quyết định #4: luôn ghi rõ. False -> có cả Close và Adj Close
SOURCE_SYSTEM = "yfinance"

COLMAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def check_paths() -> Path:
    data_root = os.environ.get("RISKLAB_DATA", "")
    if not os.path.ismount("/Volumes/RiskLab"):
        sys.exit("Dừng: /Volumes/RiskLab chưa mount. Chạy hdiutil attach rồi source session.sh.")
    if not data_root.startswith("/Volumes/RiskLab/"):
        sys.exit(f"Dừng: RISKLAB_DATA='{data_root}' không nằm trên RiskLab. Quên source session.sh?")
    return Path(data_root)


def main() -> None:
    data_root = check_paths()
    ingest_ts = datetime.now(timezone.utc).replace(microsecond=0)
    batch_id = ingest_ts.strftime("%Y%m%dT%H%M%SZ")

    print(f"yfinance {yf.__version__}, pandas {pd.__version__}")
    print(f"Tải {len(TICKERS)} mã, {START} -> {END} (exclusive), auto_adjust={AUTO_ADJUST}")
    wide = yf.download(
        TICKERS,
        start=START,
        end=END,
        interval="1d",
        auto_adjust=AUTO_ADJUST,
        actions=False,
        group_by="column",
        progress=False,
        threads=False,  # chậm hơn chút nhưng ít bị rate limit hơn
    )
    if wide is None or wide.empty:
        sys.exit("Dừng: yfinance trả về rỗng (mạng, rate limit, hoặc API đổi).")
    if wide.columns.nlevels != 2:
        sys.exit(f"Dừng: mong cột 2 tầng (giá, mã), nhận {wide.columns.nlevels} tầng.")

    # Tìm tầng chứa mã thay vì giả định tên tầng ('Ticker') – tên này từng thay đổi giữa các phiên bản
    lvl = next(
        (i for i in range(2) if set(TICKERS) <= set(wide.columns.get_level_values(i))), None
    )
    if lvl is None:
        sys.exit(f"Dừng: thiếu mã trong kết quả. Có: {sorted(set(wide.columns.get_level_values(1)))}")
    price_fields = set(wide.columns.get_level_values(1 - lvl))
    missing = set(COLMAP) - price_fields
    if missing:
        sys.exit(f"Dừng: thiếu cột {missing}. Kiểm tra lại auto_adjust với yfinance {yf.__version__}.")

    frames = []
    for t in TICKERS:
        sub = wide.xs(t, axis=1, level=lvl)[list(COLMAP)].rename(columns=COLMAP)
        idx = pd.DatetimeIndex(sub.index)
        if idx.tz is not None:
            idx = idx.tz_localize(None)
        sub = sub.copy()
        sub.insert(0, "trade_date", idx.normalize().date)
        sub.insert(0, "ticker", t)
        frames.append(sub.reset_index(drop=True))
    df = pd.concat(frames, ignore_index=True)

    n_before = len(df)
    df = df.dropna(subset=["adj_close"])  # ngày mã chưa niêm yết / Yahoo trả NaN
    n_dropped = n_before - len(df)

    df["ingest_ts"] = pd.Timestamp(ingest_ts)
    df["source_system"] = SOURCE_SYSTEM
    df["batch_id"] = batch_id

    dup = df.duplicated(subset=["ticker", "trade_date"]).sum()
    if dup:
        sys.exit(f"Dừng: {dup} dòng trùng khóa (ticker, trade_date).")

    out_dir = data_root / "raw" / "yfinance" / "prices_daily" / f"batch_id={batch_id}"
    out_dir.mkdir(parents=True, exist_ok=False)
    out_file = out_dir / "prices.parquet"
    df.to_parquet(out_file, index=False)

    per_ticker = (
        df.groupby("ticker")["trade_date"].agg(["count", "min", "max"]).reindex(TICKERS)
    )
    manifest = {
        "batch_id": batch_id,
        "ingest_ts_utc": ingest_ts.isoformat(),
        "source_system": SOURCE_SYSTEM,
        "tickers": TICKERS,
        "start": START,
        "end_exclusive": END,
        "interval": "1d",
        "auto_adjust": AUTO_ADJUST,
        "yfinance_version": yf.__version__,
        "pandas_version": pd.__version__,
        "rows": int(len(df)),
        "rows_dropped_nan_adj_close": int(n_dropped),
        "file_bytes": out_file.stat().st_size,
        "per_ticker": {
            t: {"rows": int(r["count"]), "first": str(r["min"]), "last": str(r["max"])}
            for t, r in per_ticker.iterrows()
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    print(per_ticker.to_string())
    print(f"Bỏ {n_dropped} dòng adj_close rỗng; ghi {len(df)} dòng, {out_file.stat().st_size/1024:.0f} KB")
    print(f"-> {out_dir}")


if __name__ == "__main__":
    main()
