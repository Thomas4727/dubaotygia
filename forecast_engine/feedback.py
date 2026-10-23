"""Vòng phản hồi khi vận hành (mục 3.3.5, 5.2.2 của bài).

Khi có tỷ giá thật mới:
  1. Tính sai số của các dự báo T+1 trước đây, cập nhật MAE/RMSE/MAPE cuốn chiếu (cửa sổ 20 phiên: [WEB]).
  2. Sai số ổn định: giữ mô hình.
  3. Suy giảm nhẹ: huấn luyện lại với bộ siêu tham số hiện hành (refit_current).
  4. Vượt ngưỡng nhiều kỳ liên tiếp (RMSE cuốn chiếu > 1,25 × RMSE test trong 5 phiên: [WEB]): kích hoạt lại GA và SA.
Backtest (dự báo giả lập walk-forward) là phần web bổ sung ngoài bài.
"""
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .features import build_features, to_level
from .models import arima_forecast_next, fit_model


def rolling_status(records, test_rmse, window=20, factor=1.25, consecutive=5):
    """records: list dict {date, forecast, actual} theo thời gian. Trả về trạng thái vòng phản hồi."""
    if not records:
        return {"n": 0, "status": "Chưa có dữ liệu", "reoptimize": False}
    recs = sorted(records, key=lambda r: r["date"])
    err = np.array([r["actual"] - r["forecast"] for r in recs], dtype=float)
    act = np.array([r["actual"] for r in recs], dtype=float)
    roll = []
    for i in range(len(err)):
        e, a = err[max(0, i + 1 - window):i + 1], act[max(0, i + 1 - window):i + 1]
        roll.append({"date": recs[i]["date"], "MAE": float(np.mean(np.abs(e))), "RMSE": float(np.sqrt(np.mean(e ** 2))),
                     "MAPE": float(np.mean(np.abs(e / a)) * 100)})
    limit = factor * test_rmse if test_rmse else None
    last = roll[-consecutive:]
    reopt = bool(limit) and len(last) >= consecutive and all(r["RMSE"] > limit for r in last)
    # Ba mức (mục 3.3.5, 5.2.2): ổn định -> giữ mô hình; suy giảm nhẹ -> huấn luyện lại với siêu tham số hiện hành;
    # vượt ngưỡng nhiều kỳ liên tiếp -> chạy lại GA và SA.
    # [WEB] ranh giới "suy giảm nhẹ" = RMSE cuốn chiếu mới nhất lớn hơn RMSE test; bài không nêu con số.
    degraded = bool(test_rmse) and roll[-1]["RMSE"] > test_rmse
    level = "reoptimize" if reopt else ("refit" if degraded else "stable")
    status = {"reoptimize": "Sai số vượt ngưỡng nhiều kỳ liên tiếp – kích hoạt lại GA và SA",
              "refit": "Suy giảm nhẹ – huấn luyện lại với bộ siêu tham số hiện hành",
              "stable": "Ổn định – giữ mô hình hiện tại"}[level]
    return {"n": len(recs), "rolling": roll, "latest": roll[-1], "limit": limit, "reoptimize": reopt,
            "level": level, "status": status}


def monitor_records(real, backtest=(), include_backtest=False):
    """Dữ liệu cho vòng phản hồi: chỉ các dự báo thật; dự báo backtest (giả lập) chỉ được tính khi người dùng bật."""
    return list(real) + (list(backtest) if include_backtest else [])


# ------------------------------------------------------------------ Lịch sử dự báo giả lập (backtest walk-forward)

def _bt_task(ctx, kind, params, seed, j):
    """Fit mô hình được chọn (giữ siêu tham số) trên dữ liệu đến hết ngày j−1, dự báo y_j (T+1)."""
    import warnings
    warnings.filterwarnings("ignore")
    train = np.arange(ctx.split.first_row, j - 1)              # mục tiêu y[first_row+1 .. j−1]
    pred, _ = ctx.run(kind, params, seed, train, np.array([j - 1]))
    return j, seed, float(pred[0])


def backtest(y, dates, model, params, cfg, n_days=30, on_step=None):
    """Lặp lại đúng chu trình dự báo T+1 của mô hình được chọn cho n_days ngày cuối của dữ liệu (walk-forward):
    với mỗi ngày j, huấn luyện lại trên dữ liệu đến ngày j−1 với siêu tham số hiện hành (như vòng phản hồi mục 8.8
    khi ổn định) rồi dự báo ngày j. Mô hình học máy dùng n_refit_seeds seed của chế độ (lấy trung bình), ARIMA là xác
    định nên fit 1 lần mỗi ngày. Trả về list dict theo thời gian."""
    from joblib import Parallel, delayed

    from .evaluate import alert
    from .pipeline import Context
    from .run_config import seeds

    y = np.asarray(y, dtype=float)
    days = list(range(len(y) - n_days, len(y)))
    preds = {j: [] for j in days}
    if model == "ARIMA":
        for i, j in enumerate(days, 1):
            preds[j].append(arima_forecast_next(y[:j], tuple(params["order"]), params.get("trend", cfg["arima_trend"]))[0])
            if on_step:
                on_step(i, len(days))
    else:
        ctx = Context(y, cfg)
        if days[0] - 1 - ctx.split.first_row < 20:
            raise ValueError("Không đủ dữ liệu trước giai đoạn backtest.")
        jobs = [(j, sd) for j in days for sd in seeds(cfg, cfg["n_refit_seeds"])]
        par = Parallel(n_jobs=cfg["n_jobs"], return_as="generator_unordered")
        for i, (j, sd, f) in enumerate(par(delayed(_bt_task)(ctx, model, params, sd, j) for j, sd in jobs), 1):
            preds[j].append(f)
            if on_step:
                on_step(i, len(jobs))
    rows = []
    for j in days:
        f = float(np.mean(preds[j]))
        chg = (f - y[j - 1]) / y[j - 1] * 100
        rows.append({"date": pd.Timestamp(dates[j]).date(), "obs_date": pd.Timestamp(dates[j - 1]).date(),
                     "obs_rate": float(y[j - 1]), "forecast": f, "actual": float(y[j]), "n_seeds": len(preds[j]),
                     "change_pct": float(chg), "alert": alert(chg, cfg["alert_watch_pct"])})
    return rows


def refit_current(bundle_path, df, out_dir=None):
    """Fit lại mô hình đã lưu (giữ siêu tham số) trên dữ liệu mới và dự báo T+1. Lưu phiên bản mới."""
    bundle = joblib.load(bundle_path)
    y = df["rate"].to_numpy(dtype=float)
    hp, st = bundle["hyperparameters"], bundle["settings"]
    if bundle["model"] == "ARIMA":
        f, _, _ = arima_forecast_next(y, tuple(hp["order"]), st["arima_trend"])
        forecasts, fitted = [f], []
    else:
        X, target, _ = build_features(y, hp["p"], hp.get("w"))          # ANN: không có w (chỉ p giá trị trễ)
        rows = np.arange(30, len(y) - 1)
        params = {k: v for k, v in hp.items() if k not in ("p", "w")}
        fitted = [fit_model(bundle["model"], params, m.seed, X[rows], target[rows],
                            es_frac=st["es_frac"], es_rounds=st["es_rounds"]) for m in bundle["fitted_models"]]
        last = np.array([len(y) - 1])
        forecasts = [float(to_level(y, last, m.predict(X[last]))[0]) for m in fitted]
    new = {**bundle, "version": datetime.now().strftime("%Y%m%d-%H%M%S"), "fitted_models": fitted,
           "last_date": f"{pd.Timestamp(df['date'].iloc[-1]):%Y-%m-%d}"}
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        joblib.dump(new, Path(out_dir) / f"model_bundle_{new['version']}.joblib")
    return {"forecast_mean": float(np.mean(forecasts)), "forecasts": forecasts, "version": new["version"]}
