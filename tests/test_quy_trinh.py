"""Test quy trình (đặc tả v3 mục 11): Chạy thử toàn bộ, Chạy thử từng thuật toán riêng, hai chế độ cùng một hàm.

Hai test đầu chạy thật trên data/tygia_mau.csv (mất vài phút).
"""
import numpy as np
import pytest

import forecast_engine.pipeline as pl
from forecast_engine.run_config import MODES, build_run_config

BANG = ["table_4_1", "table_4_2", "table_4_3", "figure_4_1", "table_4_4", "table_4_5", "table_4_6"]
FIELDS_46 = ["Latest_Observed_Date", "Latest_Observed_Rate", "Chosen_Model", "Chosen_Variant", "Chosen_Selection_Basis",
             "Chosen_Mean_RMSE", "Chosen_SD_RMSE", "Chosen_Mean_MAE", "Chosen_Mean_MAPE_Percent", "Next_Forecast_Date",
             "Next_Forecast_Rate_Mean", "Next_Forecast_Rate_SD", "Next_Forecast_P05", "Next_Forecast_P95",
             "Next_Forecast_Change_Percent_Mean", "Management_Alert"]


@pytest.fixture(scope="module")
def ket_qua_tat_ca(sample_df):
    return pl.run_pipeline(sample_df, {"mode": "chay_thu", "models": ["ARIMA", "ANN", "RF", "XGB"],
                                       "variants": ["Baseline", "GA", "SA"]})


def test_chay_thu_tat_ca_ra_du_bang_4_1_den_4_6(ket_qua_tat_ca):
    r = ket_qua_tat_ca
    for b in BANG:
        assert r[b], b
    assert len(r["table_4_2"]) == 8                               # ADF, PP × c, ct × EXR, D.EXR
    assert len(r["table_4_3"]) == 3
    assert {x["model"] for x in r["table_4_4"]} == {"ARIMA", "ANN", "RF", "XGB"}
    assert len(r["table_4_5"]) == 9                               # 3 mô hình × 3 chỉ tiêu
    assert all(k in r["table_4_6"] for k in FIELDS_46)
    assert len(r["candidates"]) == 10                             # ARIMA + 3 × 3
    assert all(s["status"] == "xong" for s in r["progress"]["steps"])
    assert set(r["hypotheses"]) == {"H1", "H2", "H3"}
    chosen = r["candidates"][r["chosen_key"]]
    assert chosen["model"] in ("ANN", "RF", "XGB")                     # ARIMA, random walk chỉ là chuẩn đối chiếu
    assert chosen["summary"]["RMSE"] == min(c["summary"]["RMSE"] for k, c in r["candidates"].items() if k != "ARIMA")
    assert all(x["ok"] for x in r["hpo_parity"])                       # GA/SA cùng không gian, J, fold, ngân sách


def test_chay_thu_co_thong_tin_bo_sung(ket_qua_tat_ca):
    """Khoảng ± 1,96 × RMSE, số ngày đi ngang, nhãn H2 Chạy thử, kiểm tra ngưỡng trên test – không đổi tiêu chí chọn."""
    r = ket_qua_tat_ca
    t46 = r["table_4_6"]
    assert r["error_interval"]["lo"] == pytest.approx(t46["Next_Forecast_Rate_Mean"] - 1.96 * t46["Chosen_Mean_RMSE"])
    assert r["error_interval"]["hi"] == pytest.approx(t46["Next_Forecast_Rate_Mean"] + 1.96 * t46["Chosen_Mean_RMSE"])
    assert 0 <= r["table_4_1"]["flat_days"] < r["table_4_1"]["n_obs"]
    assert r["hypotheses"]["H2"]["status"] == "Chưa đủ căn cứ (Chạy thử)"
    assert r["alert_check"]["n_days"] == len(r["test"]["actual"])
    assert sum(r["alert_check"]["count"].values()) == r["alert_check"]["n_days"]


RIENG = [(["ARIMA"], ["Baseline"])] + [([m], [v]) for m in ("ANN", "RF", "XGB") for v in ("Baseline", "GA", "SA")]


@pytest.mark.parametrize("models,variants", RIENG, ids=[f"{m[0]}-{v[0]}" for m, v in RIENG])
def test_chay_thu_tung_thuat_toan_rieng(sample_df, ket_qua_tat_ca, models, variants):
    r = pl.run_pipeline(sample_df, {"mode": "chay_thu", "models": models, "variants": variants})
    steps = {s["id"]: s for s in r["progress"]["steps"]}
    assert all(s["status"] in ("xong", "bo_qua") for s in steps.values())
    if models == ["ARIMA"]:
        assert all(steps[i]["status"] == "bo_qua" for i in (6, 7, 8, 9))
        assert steps[10]["status"] == "bo_qua" and r["chosen_key"] is None and r["table_4_6"] is None
        c = r["candidates"]["ARIMA"]                                   # ARIMA vẫn có số liệu so sánh với thực tế
        assert len(c["pred"]) == len(r["test"]["actual"]) and c["t1"]["mean"] > 0
        np.testing.assert_allclose(c["pred"], ket_qua_tat_ca["candidates"]["ARIMA"]["pred"], rtol=1e-9)
        return
    else:
        assert steps[5]["status"] == "bo_qua"                    # không chọn ARIMA
        v = variants[0]
        assert steps[7]["status"] == ("xong" if v == "GA" else "bo_qua")
        assert steps[8]["status"] == ("xong" if v == "SA" else "bo_qua")
        assert steps[6]["status"] == ("xong" if v == "Baseline" else "bo_qua")
        key = f"{models[0]}|{v}"
        if v != "Baseline":                                        # vẫn chạy Baseline làm mốc "Trước" Bảng 4.5
            assert r["table_4_5"] and r["table_4_5"][0]["before"] is not None
    assert steps[10]["status"] == "bo_qua"                        # chỉ một ứng viên học máy -> dùng luôn
    assert r["chosen_key"] == key and list(r["candidates"]) == [key]
    c = r["candidates"][key]
    assert len(c["pred"]) == len(r["test"]["actual"])             # có số liệu so sánh với thực tế
    assert c["t1"]["mean"] > 0
    # Chạy riêng cho CÙNG kết quả với phần tương ứng khi chạy tất cả (cùng seed, cùng chế độ)
    np.testing.assert_allclose(c["summary"]["RMSE"], ket_qua_tat_ca["candidates"][key]["summary"]["RMSE"], rtol=1e-9)
    np.testing.assert_allclose(c["pred"], ket_qua_tat_ca["candidates"][key]["pred"], rtol=1e-9)


def test_hai_che_do_goi_cung_mot_ham(series, monkeypatch):
    """Hai chế độ gọi cùng các hàm; số lần gọi GA/SA đúng bảng mục 12 (thay mô hình bằng bản giả cho nhanh)."""
    calls = {"GA": 0, "SA": 0, "fit": 0}

    class Fake:
        seed = 0

        def predict(self, X):
            return np.zeros(len(X))

    def fake_fit_predict(kind, params, seed, X, target, train_rows, pred_rows, *a, **k):
        calls["fit"] += 1
        return np.zeros(len(pred_rows)), Fake()

    def fake_ga(evaluator, dim, categorical, rng, init_vector, **k):
        calls["GA"] += 1
        evaluator(init_vector)
        return {"best_vector": evaluator.best_vector, "best_j": evaluator.best_j, "n_evals": evaluator.n_evals,
                "generations": 0, "stop_reason": "giả"}

    def fake_sa(evaluator, dim, categorical, rng, init_vector, **k):
        calls["SA"] += 1
        evaluator(init_vector)
        return {"best_vector": evaluator.best_vector, "best_j": evaluator.best_j, "n_evals": evaluator.n_evals,
                "T0": 1.0, "T_final": 1.0, "stop_reason": "giả"}

    monkeypatch.setattr(pl, "fit_predict", fake_fit_predict)
    monkeypatch.setattr(pl, "run_ga", fake_ga)
    monkeypatch.setattr(pl, "run_sa", fake_sa)
    for mode in ("chay_thu", "chay_day_du"):
        for k in calls:
            calls[k] = 0
        cfg = build_run_config(mode, ["ANN", "RF", "XGB"], ["Baseline", "GA", "SA"], n_jobs=1)
        pl.run_pipeline(series, cfg)
        n = MODES[mode]
        assert calls["GA"] == 3 * n["n_hpo_runs"], mode
        assert calls["SA"] == 3 * n["n_hpo_runs"], mode
        # Chọn cấu hình cuối chỉ dùng kết quả CV (không đánh giá thêm trên tập kiểm tra)
        expected_fit = 3 * (n["n_baseline_seeds"]                                  # tầng 1 (Bảng 4.4)
                            + 2 * n["n_hpo_runs"] * n["n_folds"]                   # 1 lần đánh giá J / lần chạy GA, SA
                            + n["n_test_seeds_baseline"]                           # tầng 3 Baseline
                            + 2 * n["n_hpo_runs"] * n["n_eval_seeds_per_config"]   # tầng 3 GA, SA (Bảng 4.5)
                            + 2 * n["n_test_seeds_baseline"]                       # đánh giá ứng viên GA, SA (mục 4.5)
                            + 3 * n["n_refit_seeds"])                              # huấn luyện lại 3 biến thể
        assert calls["fit"] == expected_fit, mode
