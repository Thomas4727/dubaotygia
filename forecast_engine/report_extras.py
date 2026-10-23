"""Thông tin BỔ SUNG NGOÀI BÀI để đọc kết quả trung thực hơn (không đổi thuật toán, không đổi tiêu chí chọn mô hình).

- flat_days: số ngày tỷ giá không đổi so với hôm trước (Bảng 4.1) – dữ liệu đi ngang làm RMSE nhỏ hơn thực tế.
- error_interval: khoảng dự báo theo sai số lịch sử = dự báo ± 1,96 × RMSE của mô hình được chọn (Bảng 4.6).
- threshold_check: phân phối |% thay đổi thực tế T+1| trên tập test so với ngưỡng cảnh báo (chỉ báo cáo).
- enrich: bổ sung các mục trên cho kết quả đã lưu từ trước khi có tính năng này.
"""
import numpy as np

Z_95 = 1.96
STABLE_SHARE_NOTE = 0.95        # hơn 95% ngày "Ổn định" thì ghi chú để người dùng cân nhắc chỉnh ngưỡng
ML_MODELS = ("ANN", "RF", "XGB")


def flat_days(y):
    """Số ngày tỷ giá bằng đúng hôm trước và tỷ lệ % trên số ngày có hôm trước (n − 1)."""
    d = np.diff(np.asarray(y, dtype=float))
    n = int(np.sum(d == 0))
    return {"flat_days": n, "flat_days_pct": 100 * n / len(d) if len(d) else None}


def error_interval(forecast, rmse, z=Z_95):
    return {"lo": float(forecast - z * rmse), "hi": float(forecast + z * rmse), "z": z, "rmse": float(rmse)}


def threshold_check(actual, previous, threshold_pct):
    """% thay đổi thực tế của từng ngày test (y_{t+1} so với y_t), phân loại Tăng / Giảm / Ổn định theo cùng quy tắc
    với cảnh báo (Hình 3.3)."""
    from .evaluate import ALERTS, alert
    actual, previous = np.asarray(actual, dtype=float), np.asarray(previous, dtype=float)
    chg = (actual - previous) / previous * 100
    labels = [alert(c, threshold_pct) for c in chg]
    a = np.abs(chg)
    n = len(chg)
    count = {k: sum(1 for x in labels if x == k) for k in ALERTS}
    share = {k: v / n * 100 for k, v in count.items()}
    return {
        "n_days": n, "threshold_pct": threshold_pct,
        "dist": {"min": float(a.min()), "median": float(np.median(a)), "p90": float(np.quantile(a, 0.90)),
                 "p95": float(np.quantile(a, 0.95)), "max": float(a.max())},
        "share_pct": share, "count": count,
        "mostly_stable": share["Ổn định"] > STABLE_SHARE_NOTE * 100,
    }


def enrich(result, y=None):
    """Thêm các mục bổ sung còn thiếu vào kết quả (dùng cho cả kết quả mới và kết quả đã lưu trước đây).
    y: chuỗi tỷ giá đã làm sạch (cần cho số ngày đi ngang nếu Bảng 4.1 chưa có).
    Kết quả cũ (trước khi sửa quy tắc chọn) giữ nguyên số liệu; chỉ đánh dấu `legacy_selection` để giao diện ghi chú."""
    from .evaluate import h3_inputs, hypotheses, metrics
    t41, t46 = result["table_4_1"], result.get("table_4_6")
    if "flat_days" not in t41 and y is not None:
        t41.update(flat_days(y))
    if "error_interval" not in result and t46:
        result["error_interval"] = error_interval(t46["Next_Forecast_Rate_Mean"], t46["Chosen_Mean_RMSE"])
    ac = result.get("alert_check")
    if ac is None or "threshold_pct" not in ac:
        result["alert_check"] = threshold_check(result["test"]["actual"], result["test"]["random_walk"],
                                                result["settings"]["alert_watch_pct"])
    ch_key = result.get("chosen_key")
    if ch_key and result["candidates"][ch_key]["model"] not in ML_MODELS:
        result["legacy_selection"] = True                # phiên cũ: ARIMA đã được chọn theo quy tắc trước đây
    if "hpo_parity" not in result:                       # kết quả cũ: GA/SA chạy bằng cùng một hàm, không lưu chi tiết
        result["hpo_parity"] = None
    if "selection" not in result:                        # kết quả cũ: dựng bảng xếp hạng ứng viên học máy (không có chi phí)
        ml = {k: c for k, c in result["candidates"].items() if c["model"] in ML_MODELS}
        result["selection"] = [{"key": k, "label": c["label"], "RMSE": c["summary"]["RMSE"], "SD_RMSE": c["summary"]["SD_RMSE"],
                                "CV_RMSE": c["summary"].get("CV_RMSE"), "n_runs": c["summary"]["n_runs"], "cost_seconds": None}
                               for k, c in sorted(ml.items(), key=lambda kv: kv[1]["summary"]["RMSE"])]
    # Kết luận H1–H3 luôn tính lại theo quy tắc hiện hành từ các bảng đã lưu (không đổi số liệu)
    cands = result["candidates"]
    ml_keys = {k: c["summary"] for k, c in cands.items() if c["model"] in ML_MODELS}
    integrated = ch_key if ch_key in ml_keys else (min(ml_keys, key=lambda k: ml_keys[k]["RMSE"]) if ml_keys else None)
    rw = result["random_walk"] if "RMSE" in result["random_walk"] else metrics(result["test"]["actual"], result["test"]["random_walk"])
    result["hypotheses"] = hypotheses(result["table_4_4"], result["table_4_5"], completed=True,
                                      cfg={**result["settings"], "mode": result["mode"]},
                                      h3=h3_inputs(cands, integrated, rw, t46, report_saved=bool(t46)))
    return result
