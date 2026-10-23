"""Thống kê mô tả (Bảng 4.1) và kiểm định tính dừng ADF + Phillips–Perron (Bảng 4.2). Mục 4.1 của bài."""
import warnings

import numpy as np
from statsmodels.tsa.stattools import adfuller

from .report_extras import flat_days

LEVELS = (("a", "1%"), ("b", "5%"), ("c", "10%"))       # a: ý nghĩa 1%, b: 5%, c: 10%


def descriptive(df):
    """Bảng 4.1. df: cột date, rate (đã làm sạch)."""
    y = df["rate"].to_numpy(dtype=float)
    first, last = float(y[0]), float(y[-1])
    i_max = int(np.argmax(y))
    return {
        "n_obs": int(len(y)),
        "start_date": f"{df['date'].iloc[0]:%Y-%m-%d}", "end_date": f"{df['date'].iloc[-1]:%Y-%m-%d}",
        "first": first, "last": last,
        "min": float(y.min()), "max": float(y.max()), "max_date": f"{df['date'].iloc[i_max]:%Y-%m-%d}",
        "mean": float(y.mean()), "median": float(np.median(y)), "std": float(y.std(ddof=1)),
        "change_abs": last - first, "change_pct": (last / first - 1) * 100,
        "vnd_depreciation_pct": (1 - first / last) * 100,          # 1 − đầu kỳ / cuối kỳ
        **flat_days(y),                                             # số ngày không đổi so với hôm trước, tỷ lệ %
    }


def _mark(stat, crit):
    """Dấu a/b/c theo giá trị tới hạn (thống kê càng âm càng bác bỏ H0 nghiệm đơn vị)."""
    for mark, level in LEVELS:
        if stat < crit[level]:
            return mark
    return ""


def _adf(x, trend):
    stat, p, _, _, crit, _ = adfuller(x, regression=trend, autolag="AIC")
    return float(stat), float(p), {k: float(v) for k, v in crit.items()}


def _pp(x, trend):
    from arch.unitroot import PhillipsPerron
    res = PhillipsPerron(x, trend=trend)
    return float(res.stat), float(res.pvalue), {k: float(v) for k, v in res.critical_values.items()}


def stationarity(y):
    """Bảng 4.2: ADF và PP, dạng Intercept (c) và Intercept & trend (ct), cho EXR và D.EXR.

    Trả về (danh sách dòng, kết luận dict). Bậc tích hợp d = bậc nhỏ nhất mà ADF dạng Intercept
    bác bỏ nghiệm đơn vị ở mức 5% (dùng cho ARIMA, mục 6.1).
    """
    y = np.asarray(y, dtype=float)
    series = {"EXR": y, "D.EXR": np.diff(y)}
    rows = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for name, x in series.items():
            for test, fn in (("ADF", _adf), ("PP", _pp)):
                for trend, label in (("c", "Intercept"), ("ct", "Intercept & trend")):
                    stat, p, crit = fn(x, trend)
                    rows.append({"series": name, "test": test, "form": label, "trend": trend,
                                 "stat": stat, "pvalue": p, "mark": _mark(stat, crit), "crit": crit})

    def stationary(name):
        r = next(r for r in rows if r["series"] == name and r["test"] == "ADF" and r["trend"] == "c")
        return r["mark"] in ("a", "b")

    if stationary("EXR"):
        d = 0
    elif stationary("D.EXR"):
        d = 1
    else:
        d = 2
    text = {0: "Chuỗi dừng ở bậc gốc: I(0).",
            1: "Chuỗi không dừng ở bậc gốc nhưng dừng ở sai phân bậc 1: I(1).",
            2: "Chuỗi chưa dừng ở sai phân bậc 1 (d = 2)."}[d]
    return rows, {"d": d, "text": text}
