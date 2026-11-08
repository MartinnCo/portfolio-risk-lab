"""check_env.py — kiểm tra môi trường Portfolio Risk Lab.

Chạy:  source session.sh  &&  uv run python check_env.py
Thoát mã 1 nếu có bất kỳ lỗi nào.
"""
import importlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

RISKLAB = "/Volumes/RiskLab"
PASSPORT = "/Volumes/My Passport"
ENV_VARS = ("RISKLAB_DATA", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR")
LIBS = ["numpy", "pandas", "scipy", "statsmodels", "duckdb",
        "pyiceberg", "pyarrow", "matplotlib", "plotly", "yfinance"]
SUBDIRS = ("raw", "warehouse", "mc_runs", "exports")
NAMESPACES = ("bronze", "silver", "gold", "work")

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)
    print(f"[LỖI] {msg}")


def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def on_risklab(path: str) -> bool:
    return str(path).startswith(RISKLAB + "/")


print("== 1. Ổ ảo RiskLab ==")
if os.path.ismount(RISKLAB):
    ok(f"{RISKLAB} đã mount")
else:
    fail(f"{RISKLAB} chưa mount — chạy hdiutil attach rồi source session.sh")

print("\n== 2. Biến môi trường ==")
for var in ENV_VARS:
    val = os.environ.get(var, "")
    if not val:
        fail(f"{var} chưa đặt — quên `source session.sh`?")
    elif not on_risklab(val):
        fail(f"{var}={val} không nằm trên RiskLab")
    else:
        ok(f"{var}={val}")

print("\n== 3. Python và venv ==")
py = sys.version.split()[0]
if sys.version_info[:2] == (3, 11):
    ok(f"Python {py}")
else:
    fail(f"Python {py}, dự án dùng 3.11")
for label, path in (("venv (sys.prefix)", sys.prefix),
                    ("python", sys.executable),
                    ("thư mục làm việc", os.getcwd())):
    if on_risklab(path):
        ok(f"{label}: {path}")
    else:
        fail(f"{label} không nằm trên RiskLab: {path}")

print("\n== 4. Không đường dẫn nào trỏ vào GeoLab ==")
checked = [os.environ.get(v, "") for v in ENV_VARS] + [sys.prefix, sys.executable, os.getcwd()]
geolab_hits = [p for p in checked if "/Volumes/GeoLab" in p]
if geolab_hits:
    for p in geolab_hits:
        fail(f"đường dẫn trỏ vào GeoLab: {p}")
else:
    ok("không có đường dẫn nào của dự án trỏ vào /Volumes/GeoLab")

print("\n== 5. Thư mục dữ liệu ghi được ==")
data_env = os.environ.get("RISKLAB_DATA", "")
data = Path(data_env) if data_env else None
if data is not None:
    for sub in SUBDIRS:
        p = data / sub
        if not p.is_dir():
            fail(f"thiếu thư mục {p}")
            continue
        try:
            with tempfile.NamedTemporaryFile(dir=p):
                pass
            ok(f"ghi được {p}")
        except OSError as e:
            fail(f"không ghi được {p}: {e}")

print("\n== 6. Dung lượng ==")
for mnt in (RISKLAB, PASSPORT):
    if os.path.ismount(mnt):
        u = shutil.disk_usage(mnt)
        info(f"{mnt}: trống {u.free / 1e9:.1f} GB / tổng {u.total / 1e9:.1f} GB")
    else:
        info(f"{mnt}: chưa mount")
info("RiskLab báo 'trống' theo trần 60GB; chỗ thật bị giới hạn bởi My Passport — xem cả hai số.")

print("\n== 7. Thư viện ==")
missing = False
for name in LIBS:
    try:
        m = importlib.import_module(name)
        ok(f"{name} {getattr(m, '__version__', '?')}")
    except ImportError as e:
        missing = True
        fail(f"thiếu {name}: {e}")

if not missing and data is not None and not errors:
    print("\n== 8. Smoke test ==")
    import duckdb
    import numpy as np

    # DuckDB — bản 2.x: relation không còn fetchone(), dùng fetchall()
    if duckdb.sql("SELECT 21 * 2").fetchall()[0][0] == 42:
        ok("DuckDB chạy được")
    else:
        fail("DuckDB trả kết quả sai")

    # PyIceberg: catalog SQLite trong warehouse trên RiskLab, tạo 4 namespace (idempotent)
    try:
        from pyiceberg.catalog.sql import SqlCatalog
        from pyiceberg.exceptions import NamespaceAlreadyExistsError

        wh = data / "warehouse"
        catalog = SqlCatalog(
            "risklab",
            uri=f"sqlite:///{wh}/catalog.db",
            warehouse=f"file://{wh}",
        )
        for ns in NAMESPACES:
            try:
                catalog.create_namespace(ns)
            except NamespaceAlreadyExistsError:
                pass
        found = sorted(n[0] for n in catalog.list_namespaces())
        ok(f"PyIceberg catalog tại {wh}/catalog.db, namespace: {found}")
    except Exception as e:  # noqa: BLE001 — muốn thấy mọi lỗi ở buổi 0
        fail(f"PyIceberg lỗi: {type(e).__name__}: {e}")

    # Seed: cùng seed → cùng số ngẫu nhiên
    seed = 42
    a = np.random.default_rng(seed).standard_normal(3)
    b = np.random.default_rng(seed).standard_normal(3)
    if np.array_equal(a, b):
        ok(f"seed={seed} tái lập được: {np.round(a, 4)}")
    else:
        fail("cùng seed nhưng khác kết quả")

    # Ước lượng bộ nhớ Monte Carlo: paths × steps × assets × 8 byte (float64)
    paths, steps, assets = 10_000, 21, 7
    mb = paths * steps * assets * 8 / 1e6
    info(f"MC {paths:,} path × {steps} phiên × {assets} mã (float64) ≈ {mb:.1f} MB RAM")

print("\n" + "=" * 50)
if errors:
    print(f"CÓ {len(errors)} LỖI — sửa trước khi sang GĐ 1:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("Môi trường OK — sẵn sàng cho GĐ 1.")
