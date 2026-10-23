"""Nhóm B, C – thông tin bổ sung (không đổi thuật toán): khoảng ± 1,96 × RMSE, số ngày đi ngang (Bảng 4.1),
nhãn H2 ở Chạy thử, kiểm tra ngưỡng cảnh báo trên tập test."""
import numpy as np
import pytest

from forecast_engine.evaluate import H2_TRIAL_STATUS, hypotheses
from forecast_engine.report_extras import enrich, error_interval, flat_days, threshold_check


def test_khoang_theo_sai_so_lich_su():
    k = error_interval(26_000.0, 10.0)
    assert k["lo"] == pytest.approx(26_000 - 19.6) and k["hi"] == pytest.approx(26_000 + 19.6)
    assert k["z"] == 1.96 and k["rmse"] == 10.0


def test_so_ngay_ty_gia_khong_doi():
    r = flat_days([100, 100, 101, 101, 101, 102])          # thay đổi: 0, 1, 0, 0, 1
    assert r["flat_days"] == 3 and r["flat_days_pct"] == pytest.approx(60.0)


def _t45(n_down):
    """Bảng 4.5 đủ 3 mô hình × 3 chỉ tiêu; n_down phép so sánh (trên 18) có sai số giảm."""
    rows, k = [], 0
    for m in ("ANN", "RF", "XGB"):
        for met in ("MAE", "RMSE", "MAPE"):
            r = {"model": m, "metric": met, "after_ga": 1.0, "after_sa": 1.0}
            for a in ("ga", "sa"):
                r[f"impr_{a}"] = 1.0 if k < n_down else -1.0
                k += 1
            rows.append(r)
    return rows


T44 = [{"model": "ARIMA", "MAE": 10, "RMSE": 12, "MAPE": 0.05}, {"model": "ANN", "MAE": 9, "RMSE": 11, "MAPE": 0.04},
       {"model": "RF", "MAE": 11, "RMSE": 13, "MAPE": 0.06}, {"model": "XGB", "MAE": 8, "RMSE": 10, "MAPE": 0.06}]


def test_nhan_h2_chay_thu_chua_du_can_cu():
    h = hypotheses(T44, _t45(11), completed=True, cfg={"mode": "chay_thu", "n_hpo_runs": 1, "n_eval_seeds_per_config": 3},
                   ml_selected=None)
    assert h["H2"]["status"] == H2_TRIAL_STATUS == "Chưa đủ căn cứ (Chạy thử)"
    assert "11/18 phép so sánh" in h["H2"]["text"] and "1 lần chạy GA/SA × 3 seed" in h["H2"]["text"]
    assert h["H1"]["status"] == "Ủng hộ một phần" and h["H1"]["text"].startswith("5/9 phép so sánh")


@pytest.mark.parametrize("n_down,status", [(18, "Được ủng hộ"), (11, "Ủng hộ một phần"), (0, "Không được ủng hộ")])
def test_nhan_h2_chay_day_du_nhu_cu(n_down, status):
    h = hypotheses(T44, _t45(n_down), completed=True, cfg={"mode": "chay_day_du"}, ml_selected=None)
    assert h["H2"]["status"] == status and h["H2"]["text"].startswith(f"{n_down}/18 phép so sánh")


def test_kiem_tra_nguong_canh_bao_tren_test():
    prev = np.full(10, 1000.0)
    act = prev * (1 + np.array([0, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005, 0.0005, 0.002, -0.004]))
    r = threshold_check(act, prev, 0.10)                       # %Δ = 0; 0,05 ×7; +0,2; −0,4
    assert r["n_days"] == 10
    assert r["count"] == {"Tăng": 1, "Giảm": 1, "Ổn định": 8}
    assert r["share_pct"]["Ổn định"] == pytest.approx(80.0)
    assert r["dist"]["min"] == 0 and r["dist"]["max"] == pytest.approx(0.4)
    assert r["dist"]["median"] == pytest.approx(0.05)
    assert not r["mostly_stable"]
    assert threshold_check(prev * 1.0001, prev, 0.10)["mostly_stable"]             # 100% "Ổn định" -> ghi chú


# ---------------------------------------------------------------- Vòng phản hồi và backtest (mục 9 của yêu cầu)

def _ban_ghi(sai_so, bat_dau=0):
    """Dự báo giả: thực tế 1000, dự báo = thực tế − sai số, mỗi ngày một bản ghi."""
    import datetime as dt
    d0 = dt.date(2026, 1, 1)
    return [{"date": d0 + dt.timedelta(days=bat_dau + i), "forecast": 1000.0 - e, "actual": 1000.0}
            for i, e in enumerate(sai_so)]


def test_phat_hien_rmse_truot_vuot_nguong_5_phien_lien_tiep():
    from forecast_engine.feedback import rolling_status
    # RMSE test = 10 -> ngưỡng 12,5. 20 phiên sai 5 đồng rồi 5 phiên sai 100 đồng: 5 cửa sổ cuối đều vượt ngưỡng
    r = rolling_status(_ban_ghi([5] * 20 + [100] * 5), 10.0, window=20, factor=1.25, consecutive=5)
    assert r["limit"] == pytest.approx(12.5)
    assert all(x["RMSE"] > 12.5 for x in r["rolling"][-5:]) and r["rolling"][-6]["RMSE"] < 12.5
    assert r["reoptimize"] and r["level"] == "reoptimize" and "kích hoạt lại GA và SA" in r["status"]


def test_chua_du_5_phien_lien_tiep_thi_khong_chay_lai():
    from forecast_engine.feedback import rolling_status
    r = rolling_status(_ban_ghi([5] * 20 + [100] * 4), 10.0, window=20, factor=1.25, consecutive=5)
    assert not r["reoptimize"] and r["level"] == "refit"            # suy giảm nhưng chưa đủ 5 phiên liên tiếp
    r = rolling_status(_ban_ghi([5] * 30), 10.0)                     # luôn dưới RMSE test
    assert not r["reoptimize"] and r["level"] == "stable" and r["status"].startswith("Ổn định")


def test_window_20_phien_cuon_chieu():
    from forecast_engine.feedback import rolling_status
    r = rolling_status(_ban_ghi([100] * 5 + [1] * 20), 10.0)          # 5 phiên lỗi lớn đã ra khỏi cửa sổ 20 phiên
    assert r["latest"]["RMSE"] == pytest.approx(1.0) and not r["reoptimize"]


def test_backtest_khong_tinh_vao_vong_phan_hoi_tru_khi_bat():
    from forecast_engine.feedback import monitor_records, rolling_status
    that = _ban_ghi([5] * 3)
    gia_lap = _ban_ghi([100] * 25, bat_dau=10)
    assert monitor_records(that, gia_lap) == that
    assert rolling_status(monitor_records([], gia_lap), 10.0)["n"] == 0          # mặc định: không tính backtest
    r = rolling_status(monitor_records(that, gia_lap, include_backtest=True), 10.0)
    assert r["n"] == 28 and r["reoptimize"]


@pytest.fixture
def cfg_nho():
    from forecast_engine.run_config import build_run_config
    return build_run_config("chay_thu", ["RF"], ["Baseline"], n_refit_seeds=2, n_jobs=1)


def test_backtest_walk_forward_khong_dung_du_lieu_tuong_lai(series, cfg_nho):
    from forecast_engine import search_space as ss
    from forecast_engine.feedback import backtest
    y, dates = series["rate"].to_numpy(dtype=float), series["date"].to_numpy()
    params = {**ss.baseline("RF"), "n_estimators": 20}
    rows = backtest(y, dates, "RF", params, cfg_nho, n_days=3)
    assert [r["actual"] for r in rows] == list(y[-3:])
    assert [r["obs_rate"] for r in rows] == list(y[-4:-1])
    assert all(r["n_seeds"] == 2 for r in rows)
    assert all(r["alert"] in ("Ổn định", "Theo dõi", "Biến động mạnh") for r in rows)
    # Sửa dữ liệu SAU ngày được dự báo đầu tiên: dự báo ngày đó không đổi (chỉ dùng dữ liệu đến hôm trước)
    y2 = y.copy()
    y2[-2:] += 500
    rows2 = backtest(y2, dates, "RF", params, cfg_nho, n_days=3)
    assert rows2[0]["forecast"] == pytest.approx(rows[0]["forecast"])
    assert rows2[2]["forecast"] != pytest.approx(rows[2]["forecast"])


def test_backtest_arima(series, cfg_nho):
    from forecast_engine.feedback import backtest
    y, dates = series["rate"].to_numpy(dtype=float), series["date"].to_numpy()
    rows = backtest(y, dates, "ARIMA", {"order": [1, 1, 0], "trend": "n"}, cfg_nho, n_days=3)
    assert len(rows) == 3 and all(r["n_seeds"] == 1 for r in rows)
    assert all(abs(r["forecast"] - r["obs_rate"]) < 100 for r in rows)


def test_enrich_ket_qua_cu_khong_doi_so_lieu_goc():
    summ = lambda r: {"MAE": r, "RMSE": r, "MAPE": r / 1000, "SD_RMSE": 0.0, "CV_RMSE": 0.0, "n_runs": 3}
    kq = {"mode": "chay_thu", "settings": {"alert_watch_pct": 0.1, "alert_strong_pct": 0.3, "n_hpo_runs": 1,
                                           "n_eval_seeds_per_config": 3},
          "table_4_1": {"n_obs": 4}, "table_4_4": T44, "table_4_5": _t45(13),
          "table_4_6": {"Next_Forecast_Rate_Mean": 26_000.0, "Chosen_Mean_RMSE": 15.0, "Next_Forecast_P05": 25_990.0,
                        "Management_Alert": "Theo dõi"},
          "candidates": {"ARIMA": {"model": "ARIMA", "label": "ARIMA", "summary": summ(15.0)},
                         "XGB|SA": {"model": "XGB", "label": "XGBoost – SA", "summary": summ(16.0)}},
          "chosen_key": "ARIMA", "random_walk": {"RMSE": 20.0},
          "test": {"actual": [101.0, 102.0], "random_walk": [100.0, 101.0]},
          "hypotheses": {"H2": {"status": "Ủng hộ một phần"}}}
    enrich(kq, y=[100, 100, 101, 102])
    assert kq["table_4_1"]["flat_days"] == 1
    assert kq["error_interval"]["lo"] == pytest.approx(26_000 - 29.4)
    assert kq["alert_check"]["count"]["Tăng"] == 2
    assert kq["hypotheses"]["H2"]["status"] == H2_TRIAL_STATUS
    assert kq["legacy_selection"] and kq["chosen_key"] == "ARIMA"     # phiên cũ: đánh dấu, không đổi số liệu
    assert [x["key"] for x in kq["selection"]] == ["XGB|SA"]
    assert kq["table_4_6"]["Next_Forecast_P05"] == 25_990.0          # Bảng 4.6 giữ nguyên
