"""Đọc CSV/XLSX nhiều định dạng và làm sạch dữ liệu (mục 1 đặc tả).

Định dạng hỗ trợ: Ngay,TyGia (mặc định) · Date,Price (Investing.com) · Date,Close (Yahoo Finance).
Ngày: 24/09/2026 · 2026-09-24 · 09/24/2026. Khi mơ hồ dd/mm hay mm/dd: thử cả hai, chọn cách
cho chuỗi ngày đơn điệu và hợp lệ.
"""
import re
import unicodedata
from io import BytesIO, StringIO
from pathlib import Path

import numpy as np
import pandas as pd

# Tên cột (đã bỏ dấu, viết thường, chỉ giữ chữ cái). Thứ tự = độ ưu tiên.
DATE_COLUMNS = ["ngay", "date", "thoigian", "time", "day"]
RATE_COLUMNS = ["tygia", "giatri", "close", "price", "giaban", "ban", "sell", "rate", "gia", "value"]


class DataError(ValueError):
    """Lỗi do dữ liệu người dùng; thông báo hiển thị thẳng cho người dùng."""


# ---------------------------------------------------------------- Đọc file

def read_table(source, filename=None):
    """source: đường dẫn, bytes hoặc file-like. Trả về DataFrame thô (mọi cột dạng chuỗi với CSV)."""
    if isinstance(source, (str, Path)):
        filename = filename or str(source)
        raw = Path(source).read_bytes()
    elif isinstance(source, bytes):
        raw = source
    else:
        raw = source.read()
    suffix = Path(filename or "").suffix.lower()
    try:
        if suffix in (".xlsx", ".xlsm"):
            return pd.read_excel(BytesIO(raw))
        if suffix in (".csv", ".txt", ""):
            for encoding in ("utf-8-sig", "cp1258", "latin-1"):
                try:
                    text = raw.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            # sep=None: tự đoán dấu phân cách (, ; tab)
            return pd.read_csv(StringIO(text), sep=None, engine="python", dtype=str)
    except Exception as e:
        raise DataError(f"Không đọc được file: {e}") from e
    raise DataError("Chỉ hỗ trợ file .csv hoặc .xlsx.")


def _norm_name(name):
    name = unicodedata.normalize("NFD", str(name)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", name.lower())


def _find_rate_column(columns):
    """File Vietcombank có nhiều cột tỷ giá: bài dùng "tỷ giá chuyển khoản" = cột MUA chuyển khoản (người dùng xác nhận).
    Ưu tiên cột có tên chứa "chuyenkhoan" mà không phải cột bán; sau đó mới theo RATE_COLUMNS."""
    normalized = {c: _norm_name(c) for c in columns}
    ck = [c for c, n in normalized.items() if "chuyenkhoan" in n and "ban" not in n.replace("chuyenkhoan", "")]
    return ck[0] if ck else _find_column(columns, RATE_COLUMNS)


def _find_column(columns, priority):
    normalized = {c: _norm_name(c) for c in columns}
    for key in priority:
        for col, name in normalized.items():
            if name == key:
                return col
    for key in priority:
        for col, name in normalized.items():
            if name.startswith(key):
                return col
    return None


# ---------------------------------------------------------------- Ngày và số

def _is_monotonic(dates):
    valid = dates.dropna()
    return len(valid) > 1 and (valid.is_monotonic_increasing or valid.is_monotonic_decreasing)


def parse_dates(column):
    """Trả về (Series datetime, mô tả định dạng đã chọn)."""
    if pd.api.types.is_datetime64_any_dtype(column):
        return column, "datetime"
    s = column.astype(str).str.strip()
    parts = s.str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
    if parts.notna().all(axis=1).mean() > 0.9:
        unified = parts[0] + "/" + parts[1] + "/" + parts[2]
        year_fmt = "%Y" if parts[2].str.len().max() == 4 else "%y"
        candidates = []
        for label, fmt in (("dd/mm", f"%d/%m/{year_fmt}"), ("mm/dd", f"%m/%d/{year_fmt}")):
            parsed = pd.to_datetime(unified, format=fmt, errors="coerce")
            # Ưu tiên: nhiều ngày hợp lệ nhất, rồi chuỗi đơn điệu, rồi dd/mm (kiểu Việt Nam)
            candidates.append((parsed.notna().sum(), _is_monotonic(parsed), label == "dd/mm", label, parsed))
        best = max(candidates, key=lambda c: c[:3])
        return best[4], best[3]
    return pd.to_datetime(s, errors="coerce", format="mixed"), "tự nhận diện"


def parse_number(x):
    if isinstance(x, (int, float, np.number)):
        return float(x)
    s = re.sub(r"[^\d.,\-]", "", str(x))
    if not s:
        return np.nan
    if "," in s and "." in s:
        # Dấu đứng sau cùng là dấu thập phân: 26,345.50 hoặc 26.345,50
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", "") if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s) else s.replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")          # 26.345 (kiểu Việt Nam) -> 26345
    try:
        return float(s)
    except ValueError:
        return np.nan


def parse_table(table):
    """Bảng thô -> DataFrame(date, rate) theo THỨ TỰ trong file (chưa làm sạch) + thông tin nhận diện."""
    table = table.dropna(how="all")
    if table.shape[1] < 2:
        raise DataError("File cần ít nhất 2 cột: Ngày và Tỷ giá.")
    date_col = _find_column(table.columns, DATE_COLUMNS)
    rest = [c for c in table.columns if c != date_col]
    rate_col = _find_rate_column(rest)
    if date_col is None or rate_col is None:
        thieu = " và ".join(t for t, c in (("cột Ngày", date_col), ("cột Tỷ giá", rate_col)) if c is None)
        raise DataError(f"Không tìm thấy {thieu} trong dòng tiêu đề của file. Dòng đầu tiên phải là tên cột, ví dụ "
                        "Ngay,TyGia (mặc định), Date,Price (Investing.com) hoặc Date,Close (Yahoo Finance).")
    dates, date_format = parse_dates(table[date_col])
    if dates.notna().mean() < 0.8:
        raise DataError(f"Cột '{date_col}' không đúng định dạng ngày (dd/mm/yyyy, yyyy-mm-dd hoặc mm/dd/yyyy).")
    df = pd.DataFrame({"date": dates.values, "rate": table[rate_col].map(parse_number).values})
    if df["rate"].notna().mean() < 0.8:
        raise DataError(f"Cột '{rate_col}' không phải số tỷ giá (ví dụ 26345 hoặc 26.345,50).")
    info = {"date_column": str(date_col), "rate_column": str(rate_col), "date_format": date_format}
    return df, info


# ---------------------------------------------------------------- Làm sạch (mục 1.1)

def basic_clean(df):
    """Bước 1–4 theo đúng thứ tự của bài (mục 3.3.1): chuẩn hóa định dạng ngày; sắp xếp tăng dần; loại trùng lặp
    (giữ dòng cuối); kiểm tra giá trị âm hoặc bằng 0 (và ô tỷ giá trống). Mỗi bước ghi 1 dòng nhật ký. Trả về (df, log)."""
    log = []
    n0 = len(df)
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.normalize()
    bad_date = df["date"].isna()
    log.append(f"Bước 1 – Chuẩn hóa định dạng ngày: {n0 - int(bad_date.sum())} dòng đọc được ngày"
               + (f", bỏ {int(bad_date.sum())} dòng không đọc được ngày." if bad_date.any() else "."))
    df = df[~bad_date]
    # Sắp xếp ổn định để các dòng trùng ngày vẫn giữ thứ tự trong file -> keep="last" = dòng cuối
    df = df.sort_values("date", kind="mergesort")
    log.append("Bước 2 – Sắp xếp tăng dần theo thời gian"
               + (f": {df['date'].iloc[0]:%d/%m/%Y} → {df['date'].iloc[-1]:%d/%m/%Y}." if len(df) else "."))
    dup = df.duplicated("date", keep="last")
    log.append(f"Bước 3 – Loại trùng lặp: {int(dup.sum())} dòng trùng ngày" + (" (giữ dòng cuối)." if dup.any() else "."))
    df = df[~dup]
    bad = df["rate"].isna() | (df["rate"] <= 0)
    log.append(f"Bước 4 – Kiểm tra giá trị âm hoặc bằng 0: {int(bad.sum())} dòng tỷ giá trống, âm hoặc bằng 0"
               + (" (đã loại)." if bad.any() else "."))
    df = df[~bad].reset_index(drop=True)
    if n0 and len(df) < 0.8 * n0:
        raise DataError(f"Chỉ {len(df)}/{n0} dòng hợp lệ. Hãy kiểm tra cột ngày và cột tỷ giá.")
    return df, log


def remove_anomalies(df, jump=0.01, revert=0.002):
    """Bước 5: |%Δ| > jump so với hôm trước VÀ hôm sau quay về trong phạm vi `revert` của hôm trước."""
    y = df["rate"].to_numpy()
    drop = []
    for i in range(1, len(y) - 1):
        if abs(y[i] / y[i - 1] - 1) > jump and abs(y[i + 1] / y[i - 1] - 1) <= revert:
            drop.append(i)
    removed = df.iloc[drop]
    return df.drop(df.index[drop]).reset_index(drop=True), removed


def clean(df, cfg):
    """Quy trình làm sạch 6 bước của bài (mục 3.3.1; đặc tả v3 mục 2).

    cfg: run_config (dict). Trả về (df sạch, log list[str], thống kê dict).
    1. chuẩn hóa ngày  2. sắp xếp  3. loại trùng  4. giá trị âm/0   (basic_clean)
    5. dị thường theo %Δ liên tiếp  6. tính liên tục của lịch: giữ tần suất ngày làm việc, không nội suy.
    """
    n0 = len(df)
    df, log = basic_clean(df)
    df, removed = remove_anomalies(df, cfg["anomaly_jump"], cfg["anomaly_revert"])
    log.append(f"Bước 5 – Kiểm tra điểm dị thường bằng thay đổi phần trăm liên tiếp (|%Δ| > {cfg['anomaly_jump']:.0%} "
               f"rồi hôm sau quay về trong {cfg['anomaly_revert']:.1%}): "
               f"{len(removed)} điểm" + (" (đã loại):" if len(removed) else "."))
    for _, row in removed.iterrows():
        log.append(f"    · {row['date']:%d/%m/%Y}: {row['rate']:,.2f}")

    # Bước 6: đối chiếu tính liên tục của lịch quan sát – giữ tần suất ngày làm việc, không nội suy
    weekend = df["date"].dt.weekday >= 5
    df = df[~weekend].reset_index(drop=True)
    missing = 0
    if len(df) > 1:
        full = pd.bdate_range(df["date"].iloc[0], df["date"].iloc[-1])
        missing = len(full) - len(df)
    log.append(f"Bước 6 – Đối chiếu tính liên tục của lịch quan sát: bỏ {int(weekend.sum())} dòng rơi vào thứ 7/chủ nhật; "
               f"{missing} ngày làm việc không có quan sát (lễ, nghỉ) – không nội suy thêm.")

    if len(df) < cfg["min_rows"]:
        raise DataError(f"Chỉ còn {len(df)} dòng hợp lệ, cần ít nhất {cfg['min_rows']}.")
    stats = {"rows_in": n0, "rows_out": len(df), "rows_removed": n0 - len(df),
             "anomalies": len(removed), "missing_business_days": missing}
    return df, log, stats


def load(source, cfg, filename=None):
    """Đọc + nhận diện + làm sạch. Trả về (df[date, rate], báo cáo dict)."""
    raw, info = parse_table(read_table(source, filename))
    df, log, stats = clean(raw, cfg)
    return df, {**info, **stats, "log": log}
