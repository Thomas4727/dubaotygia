"""Ghi kết quả: result.json, CSV so sánh từng ngày của mỗi ứng viên, gói mô hình joblib (mục 8.8)."""
import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def daily_table(result, key):
    """Bảng từng ngày trên tập test của một ứng viên (mục 13.3): Ngày, thực tế, dự báo, sai lệch, sai lệch %."""
    t = result["test"]
    pred = result["test"]["random_walk"] if key == "RW" else result["candidates"][key]["pred"]
    df = pd.DataFrame({"Ngay": t["dates"], "TyGiaThucTe": t["actual"], "DuBao": pred})
    df["SaiLech"] = df["TyGiaThucTe"] - df["DuBao"]
    df["SaiLechPct"] = df["SaiLech"] / df["TyGiaThucTe"] * 100
    if key == "ARIMA" and result.get("figure_4_1"):
        df["Duoi95"], df["Tren95"] = result["figure_4_1"]["lo"], result["figure_4_1"]["hi"]
    return df


def save_outputs(result, output_dir, chosen_models, cfg):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=_json_default), encoding="utf-8")
    for key in list(result["candidates"]) + ["RW"]:
        daily_table(result, key).to_csv(out / f"so_sanh_{key.replace('|', '_')}.csv", index=False, encoding="utf-8-sig")
    if result["chosen_key"] is None:                   # chỉ chạy ARIMA (đối chiếu): không có mô hình chính để lưu
        return
    ch = result["candidates"][result["chosen_key"]]
    from .features import build_features
    p, w = ch["params"].get("p"), ch["params"].get("w")
    joblib.dump({
        "version": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "mode": cfg["mode"], "model": ch["model"], "variant": ch["variant"], "hyperparameters": ch["params"],
        "trained_on": "development",                   # huấn luyện lại trên toàn bộ tập phát triển (mục 3.3.5)
        "feature_config": {"p": p, "w": w, "target": "diff (Δy_{t+1}), khôi phục mức ŷ = y_t + Δŷ",
                           "columns": build_features([1.0] * (max(p, w or 0) + 2), p, w)[2]},
        "preprocessing": "StandardScaler fit trên tập huấn luyện của lần fit (lưu trong từng fitted_models[i].x_scaler)",
        "fitted_models": list(chosen_models),          # mô hình + scaler của từng seed refit
        "last_date": result["table_4_6"]["Latest_Observed_Date"],
        "test_rmse": ch["summary"]["RMSE"],
        "settings": {k: cfg[k] for k in ("es_frac", "es_rounds", "monitor_window", "monitor_factor", "monitor_consecutive",
                                         "alert_watch_pct", "arima_trend")},
    }, out / "model_bundle.joblib")
