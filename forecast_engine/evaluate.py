"""Chỉ tiêu đánh giá, các bảng kết quả, quy tắc chọn mô hình và kết luận giả thuyết (đặc tả v3 mục 4, 8)."""
import numpy as np

H2_TRIAL_STATUS = "Chưa đủ căn cứ (Chạy thử)"


def metrics(actual, pred):
    """MAE, RMSE, MAPE (%), Sai số TB = mean(thực tế − dự báo), Sai số chuẩn = SD của sai số."""
    actual, pred = np.asarray(actual, dtype=float), np.asarray(pred, dtype=float)
    e = actual - pred
    return {"MAE": float(np.mean(np.abs(e))), "RMSE": float(np.sqrt(np.mean(e ** 2))),
            "MAPE": float(np.mean(np.abs(e / actual)) * 100), "MeanErr": float(np.mean(e)),
            "SdErr": float(np.std(e, ddof=1))}


def summarize(per_run):
    """Trung bình các chỉ tiêu qua các lần chạy + SD và hệ số biến thiên (CV) của RMSE."""
    rmse = np.array([m["RMSE"] for m in per_run])
    out = {k: float(np.mean([m[k] for m in per_run])) for k in ("MAE", "RMSE", "MAPE", "MeanErr", "SdErr")}
    out["SD_RMSE"] = float(rmse.std(ddof=1)) if len(rmse) > 1 else 0.0
    out["CV_RMSE"] = out["SD_RMSE"] / out["RMSE"] if out["RMSE"] else None
    out["n_runs"] = len(per_run)
    return out


def improvement(before, after):
    """Công thức 3.35 / 3.36: 100 × (trước − sau) / trước."""
    return None if before in (None, 0) or after is None else 100 * (before - after) / before


ALERTS = ("Tăng", "Giảm", "Ổn định")
# Bảng 4.6 của bài: đúng 16 trường, theo thứ tự này
FIELDS_46 = ["Latest_Observed_Date", "Latest_Observed_Rate", "Chosen_Model", "Chosen_Variant", "Chosen_Selection_Basis",
             "Chosen_Mean_RMSE", "Chosen_SD_RMSE", "Chosen_Mean_MAE", "Chosen_Mean_MAPE_Percent", "Next_Forecast_Date",
             "Next_Forecast_Rate_Mean", "Next_Forecast_Rate_SD", "Next_Forecast_P05", "Next_Forecast_P95",
             "Next_Forecast_Change_Percent_Mean", "Management_Alert"]


def alert(change_pct, threshold_pct):
    """Cảnh báo quản trị theo Hình 3.3: |% thay đổi dự báo| nhỏ hơn ngưỡng người dùng đặt -> "Ổn định";
    ngược lại "Tăng" hoặc "Giảm" theo chiều thay đổi. Ngưỡng mặc định 0,10%: [WEB] – bài để người dùng tự đặt."""
    if abs(change_pct) < threshold_pct:
        return "Ổn định"
    return "Tăng" if change_pct > 0 else "Giảm"


def direction(change):
    """Chiều biến động dự kiến (Bảng 4.6, trường bổ sung theo yêu cầu): theo dấu của mức thay đổi dự báo."""
    return "Tăng" if change > 0 else ("Giảm" if change < 0 else "Không đổi")


def choose(candidates):
    """Quy tắc Bảng 4.6: 'Minimum Mean RMSE across repeated Test runs'. candidates: {khóa: tóm tắt} – CHỈ gồm ANN, RF,
    XGBoost × Baseline/GA/SA; ARIMA và random walk là chuẩn đối chiếu (mục 3.3.5), không bao giờ được chọn.
    Trả về None khi không có ứng viên học máy (ví dụ chỉ chạy ARIMA)."""
    if not candidates:
        return None
    return min(candidates, key=lambda k: candidates[k]["RMSE"])


def table_4_5(before, after):
    """before: {model: tóm tắt Baseline tầng 3}; after: {(model, 'GA'|'SA'): tóm tắt}. Trả về list dòng."""
    rows = []
    for model, b in before.items():
        sa, ga = after.get((model, "SA")), after.get((model, "GA"))
        if sa is None and ga is None:
            continue
        for metric in ("MAE", "RMSE", "MAPE"):
            rows.append({
                "model": model, "metric": metric, "before": b[metric],
                "after_sa": sa[metric] if sa else None, "after_ga": ga[metric] if ga else None,
                "impr_sa": improvement(b[metric], sa[metric]) if sa else None,
                "impr_ga": improvement(b[metric], ga[metric]) if ga else None,
                "sd_before": b["SD_RMSE"] if metric == "RMSE" else None,
                "sd_sa": sa["SD_RMSE"] if sa and metric == "RMSE" else None,
                "sd_ga": ga["SD_RMSE"] if ga and metric == "RMSE" else None,
            })
    return rows


METRIC_TEXT = {"MAE": "MAE", "RMSE": "RMSE", "MAPE": "MAPE (%)"}


def _vn(x, nd):
    return f"{x:,.{nd}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def hypotheses(t44, t45, completed, cfg, ml_selected=None, h3=None):
    """Kết luận H1–H3 tự động từ số liệu chạy thật. Kèm nhãn Chạy thử nếu cần.
    Quy tắc gắn nhãn "Được ủng hộ / Ủng hộ một phần / Không được ủng hộ" là [WEB] – bài kết luận bằng lời.
    h3: {"accuracy": {...}, "automation": bool, "management": {...}} – ba tiêu chí của mục 3.1.1 (xem h3_inputs)."""
    label = " (kết quả Chạy thử, không dùng để so với bài)" if cfg["mode"] == "chay_thu" else ""
    out = {}

    # H1 (mục 4.3): sai số trung bình MAE, RMSE, MAPE của từng mô hình học máy (Bảng 4.4) so với ARIMA
    arima = next((r for r in t44 if r["model"] == "ARIMA"), None)
    ml = [r for r in t44 if r["model"] in ("ANN", "RF", "XGB")]
    if arima is None or not ml:
        need = [x for x, ok in (("ARIMA", arima is not None), ("ít nhất một mô hình học máy ở cấu hình Baseline", bool(ml))) if not ok]
        out["H1"] = {"status": "Chưa đủ dữ liệu", "text": "Chưa đủ dữ liệu để kết luận – cần chạy thêm " + " và ".join(need) + "."}
    else:
        detail, lower, total = [], 0, 0
        names = {"ANN": "ANN", "RF": "Random Forest", "XGB": "XGBoost"}
        for r in ml:
            parts, low_m, high_m = [], [], []
            for met in ("MAE", "RMSE", "MAPE"):
                nd = 4 if met == "MAPE" else 2
                is_low = r[met] < arima[met]
                lower += is_low
                total += 1
                (low_m if is_low else high_m).append(met)
                parts.append(f"{METRIC_TEXT[met]} {_vn(r[met], nd)} {'<' if is_low else ('=' if r[met] == arima[met] else '>')} "
                             f"{_vn(arima[met], nd)} ({'thấp hơn' if is_low else 'không thấp hơn'})")
            tom_tat = ("thấp hơn ARIMA ở cả 3 chỉ tiêu" if not high_m else
                       "không thấp hơn ARIMA ở chỉ tiêu nào" if not low_m else
                       f"thấp hơn ARIMA ở {', '.join(low_m)}; không thấp hơn ở {', '.join(high_m)}")
            detail.append(f"{names[r['model']]}: {'; '.join(parts)} → {tom_tat}")
        status = "Được ủng hộ" if lower == total else ("Ủng hộ một phần" if lower else "Không được ủng hộ")
        out["H1"] = {"status": status,
                     "text": f"{lower}/{total} phép so sánh (mô hình × MAE, RMSE, MAPE) có sai số trung bình thấp hơn ARIMA{label}.",
                     "detail": detail}

    # H2: đếm phép so sánh trước/sau (tối đa 3 mô hình × 3 chỉ tiêu × 2 thuật toán = 18) có sai số giảm
    comps = [(r["model"], r["metric"], algo, r[f"impr_{algo.lower()}"])
             for r in t45 for algo in ("GA", "SA") if r[f"after_{algo.lower()}"] is not None]
    if not comps:
        out["H2"] = {"status": "Chưa đủ dữ liệu",
                     "text": "Chưa đủ dữ liệu để kết luận – cần chạy thêm tối ưu GA hoặc SA cho ít nhất một mô hình học máy."}
    else:
        down = sum(1 for c in comps if c[3] is not None and c[3] > 0)
        note = "" if len(comps) == 18 else f" (phạm vi chạy có {len(comps)}/18 phép so sánh)"
        text = f"{down}/{len(comps)} phép so sánh có sai số giảm sau tối ưu{note}{label}."
        if cfg["mode"] == "chay_thu":
            # Chạy thử: Bảng 4.5 chỉ có 1 lần chạy GA/SA × 3 seed mỗi ô – chưa đủ căn cứ để kết luận H2
            status = H2_TRIAL_STATUS
            text = (f"Bảng 4.5 ở chế độ Chạy thử chỉ có {cfg.get('n_hpo_runs', 1)} lần chạy GA/SA × "
                    f"{cfg.get('n_eval_seeds_per_config', 3)} seed mỗi ô, chưa đủ căn cứ để kết luận. Thông tin phụ: {text}")
        else:
            status = "Được ủng hộ" if down == len(comps) else ("Ủng hộ một phần" if down else "Không được ủng hộ")
        out["H2"] = {"status": status, "text": text,
                     "detail": [f"{m} · {met} · {a}: {'giảm' if v and v > 0 else 'không giảm'} ({'+' if v > 0 else ''}{_vn(v, 2)}%)"
                                for m, met, a, v in comps]}

    # H3 (mục 3.1.1): tính chính xác, tính tự động hóa, tính hữu ích quản lý của công cụ tích hợp
    if not completed:
        out["H3"] = {"status": "Chưa đủ dữ liệu", "text": "Quy trình chưa chạy xong."}
    elif not h3 or h3.get("accuracy") is None:
        out["H3"] = {"status": "Chưa đủ dữ liệu",
                     "text": "Chưa đủ dữ liệu để kết luận – cần chạy ít nhất một mô hình học máy để có mô hình tích hợp (mô hình chính)."}
    else:
        a, m = h3["accuracy"], h3["management"]
        ref_name, ref_rmse = a["reference"], a["reference_RMSE"]
        acc_ok = a["RMSE"] <= ref_rmse
        crit = [
            ("Tính chính xác", acc_ok,
             f"Mô hình tích hợp ({a['label']}): MAE {_vn(a['MAE'], 2)}, RMSE {_vn(a['RMSE'], 2)}, MAPE {_vn(a['MAPE'], 4)}% "
             f"trên tập kiểm tra; RMSE {'≤' if acc_ok else '>'} {ref_name} ({_vn(ref_rmse, 2)}). "
             f"(Ngưỡng 'đạt' – lựa chọn của web, bài không quy định: RMSE không cao hơn chuẩn đối chiếu {ref_name}.)"),
            ("Tính tự động hóa", bool(h3["automation"]),
             "Chạy tuần tự từ dữ liệu tải lên đến dự báo T+1 không cần can thiệp thủ công" if h3["automation"]
             else "Quy trình cần can thiệp thủ công"),
            ("Tính hữu ích quản lý", all(m.values()),
             "Có dự báo T+1 (Bảng 4.6): " + ("có" if m["forecast"] else "không") + "; cảnh báo Tăng/Giảm/Ổn định: "
             + ("có" if m["alert"] else "không") + "; báo cáo (bảng, biểu đồ, file kết quả): " + ("có" if m["report"] else "không")),
        ]
        met = sum(ok for _, ok, _ in crit)
        status = "Được ủng hộ" if met == 3 else ("Ủng hộ một phần" if met else "Không được ủng hộ")
        out["H3"] = {"status": status, "text": f"Đạt {met}/3 tiêu chí của mục 3.1.1 (chính xác, tự động hóa, hữu ích quản lý){label}.",
                     "detail": [f"{name}: {'đạt' if ok else 'chưa đạt'} – {txt}" for name, ok, txt in crit]}
    return out


def h3_inputs(candidates, chosen_key, rw_metrics, t46, report_saved):
    """Số liệu cho ba tiêu chí H3. Chuẩn đối chiếu cho tính chính xác: ARIMA nếu có chạy, ngược lại random walk."""
    if chosen_key is None:
        return None
    ch = candidates[chosen_key]["summary"]
    ref = candidates.get("ARIMA")
    return {
        "accuracy": {"label": candidates[chosen_key]["label"], "MAE": ch["MAE"], "RMSE": ch["RMSE"], "MAPE": ch["MAPE"],
                     "reference": "ARIMA" if ref else "Random walk",
                     "reference_RMSE": ref["summary"]["RMSE"] if ref else rw_metrics["RMSE"]},
        "automation": True,           # pipeline chạy liền một mạch, không có bước thủ công giữa dữ liệu và dự báo
        "management": {"forecast": bool(t46 and t46.get("Next_Forecast_Rate_Mean") is not None),
                       "alert": bool(t46 and t46.get("Management_Alert")), "report": bool(report_saved)},
    }
