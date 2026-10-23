"""Bám sát bài NCKH gốc: (a) ARIMA, random walk không bao giờ được chọn; (b) scaler, đặc trưng không dùng dữ liệu sau
thời điểm dự báo; (c) GA và SA cùng không gian, cùng ngân sách; (d) 18 phép so sánh của Bảng 4.5; (e) Bảng 4.6 đủ trường.
Thêm: cảnh báo Tăng/Giảm/Ổn định, H1 theo từng chỉ tiêu, H3 theo 3 tiêu chí, vòng phản hồi 3 mức, làm sạch 6 bước, cột VCB."""
import numpy as np
import pandas as pd
import pytest

import forecast_engine.pipeline as pl
from forecast_engine import search_space as ss
from forecast_engine.data_io import clean, parse_table, read_table
from forecast_engine.evaluate import alert, choose, hypotheses, improvement, table_4_5
from forecast_engine.feedback import rolling_status
from forecast_engine.evaluate import FIELDS_46 as FIELDS_46_ENGINE
from forecast_engine.run_config import MODES, ML_MODELS, build_run_config

FIELDS_46 = ["Latest_Observed_Date", "Latest_Observed_Rate", "Chosen_Model", "Chosen_Variant", "Chosen_Selection_Basis",
             "Chosen_Mean_RMSE", "Chosen_SD_RMSE", "Chosen_Mean_MAE", "Chosen_Mean_MAPE_Percent", "Next_Forecast_Date",
             "Next_Forecast_Rate_Mean", "Next_Forecast_Rate_SD", "Next_Forecast_P05", "Next_Forecast_P95",
             "Next_Forecast_Change_Percent_Mean", "Management_Alert"]


class _Fake:
    seed = 0

    def __init__(self, bias):
        self.bias = bias

    def predict(self, X):
        return np.full(len(X), self.bias)


@pytest.fixture
def chay_gia(monkeypatch):
    """Chạy pipeline thật (ARIMA thật) nhưng mô hình học máy là bản giả dự báo Δy = +200 (rất tệ),
    GA/SA giả đánh giá đúng 1 lần -> chạy nhanh. ARIMA chắc chắn có RMSE thấp hơn mọi ứng viên học máy."""
    def fake_fit_predict(kind, params, seed, X, target, train_rows, pred_rows, *a, **k):
        bias = 200.0 + {"ANN": 0, "RF": 10, "XGB": 20}[kind]
        return np.full(len(pred_rows), bias), _Fake(bias)

    def fake_algo(evaluator, dim, categorical, rng, init_vector, **k):
        evaluator(init_vector)
        return {"best_vector": evaluator.best_vector, "best_j": evaluator.best_j, "n_evals": evaluator.n_evals,
                "generations": 0, "T0": 1.0, "T_final": 1.0, "stop_reason": "giả"}

    monkeypatch.setattr(pl, "fit_predict", fake_fit_predict)
    monkeypatch.setattr(pl, "run_ga", fake_algo)
    monkeypatch.setattr(pl, "run_sa", fake_algo)

    def run(series, models=("ARIMA", "ANN", "RF", "XGB"), variants=("Baseline", "GA", "SA")):
        return pl.run_pipeline(series, build_run_config("chay_thu", list(models), list(variants), n_jobs=1))
    return run


# ---------------------------------------------------------------- (a) ARIMA và random walk không bao giờ được chọn

def test_a_arima_khong_duoc_chon_du_rmse_thap_nhat(series, chay_gia):
    r = chay_gia(series)
    arima = r["candidates"]["ARIMA"]["summary"]["RMSE"]
    assert all(arima < c["summary"]["RMSE"] for k, c in r["candidates"].items() if k != "ARIMA")
    assert r["candidates"][r["chosen_key"]]["model"] in ML_MODELS
    assert r["candidates"]["ARIMA"]["in_selection"] is False and not r["candidates"]["ARIMA"]["chosen"]
    assert r["table_4_6"]["Chosen_Model"] in ("ANN", "Random Forest", "XGBoost")
    assert {x["key"] for x in r["selection"]} == {k for k in r["candidates"] if k != "ARIMA"}
    assert r["chosen_key"] == r["selection"][0]["key"]                     # Mean RMSE thấp nhất trong học máy
    assert all("cost_seconds" in x and "CV_RMSE" in x for x in r["selection"])  # kèm độ ổn định và chi phí


def test_a_chi_chay_arima_thi_khong_co_mo_hinh_chinh(series, chay_gia):
    r = chay_gia(series, models=["ARIMA"], variants=["Baseline"])
    assert r["chosen_key"] is None and r["table_4_6"] is None
    assert "ARIMA" in r["candidates"] and r["candidates"]["ARIMA"]["t1"]["mean"] > 0      # vẫn có dự báo đối chiếu
    assert r["hypotheses"]["H3"]["status"] == "Chưa đủ dữ liệu"


def test_a_choose_bo_qua_tap_rong():
    assert choose({}) is None
    assert choose({"RF|GA": {"RMSE": 2.0}, "XGB|SA": {"RMSE": 1.0}}) == "XGB|SA"


# ---------------------------------------------------------------- (b) không dùng dữ liệu sau thời điểm dự báo

@pytest.mark.parametrize("kind", ["RF", "XGB"])
def test_b_du_bao_tai_t_khong_doi_khi_sua_du_lieu_sau_t(series, kind):
    cfg = build_run_config("chay_thu", n_jobs=1)
    y = series["rate"].to_numpy(dtype=float)
    params = {**ss.baseline(kind), "n_estimators": 30}
    t = 200
    pred1, m1 = pl.Context(y, cfg).run(kind, params, 1, np.arange(30, t), np.array([t]))
    y2 = y.copy()
    y2[t + 1:] += 1_000                                                   # tương lai sau ngày t (kể cả y_{t+1})
    pred2, m2 = pl.Context(y2, cfg).run(kind, params, 1, np.arange(30, t), np.array([t]))
    np.testing.assert_allclose(pred1, pred2)
    np.testing.assert_allclose(m1.x_scaler.mean_, m2.x_scaler.mean_)


def test_b_refit_t1_chi_tren_tap_phat_trien(series):
    """Mô hình dự báo T+1 huấn luyện lại trên toàn bộ tập phát triển: scaler = thống kê của các dòng development."""
    cfg = build_run_config("chay_thu", n_jobs=1)
    ctx = pl.Context(series["rate"].to_numpy(dtype=float), cfg)
    _, _, _, model = pl._task_refit(ctx, "RF|Baseline", "RF", {**ss.baseline("RF"), "n_estimators": 20}, 1)
    X, _, _ = ctx.features(10, 10)
    np.testing.assert_allclose(model.x_scaler.mean_, X[ctx.split.dev_rows].mean(axis=0))
    assert ctx.split.dev_rows.max() + 1 < ctx.split.test_rows.min() + 1     # không có mục tiêu nào thuộc tập kiểm tra


# ---------------------------------------------------------------- (c) GA và SA cùng không gian, cùng ngân sách

def test_c_ga_sa_cung_khong_gian_va_ngan_sach_trong_phien(series, chay_gia):
    r = chay_gia(series, models=["RF", "XGB"], variants=["GA", "SA"])
    assert len(r["hpo_parity"]) == 2
    for x in r["hpo_parity"]:
        assert x["applicable"] and x["ok"] and all(x["checks"].values())
        assert x["budget"] == build_run_config("chay_thu")["budget"]
        assert x["space"] == [p.name for p in ss.space(x["model"], build_run_config("chay_thu")["caps"])]


def test_c_phat_hien_khac_ngan_sach():
    a = {"space": ["p"], "objective": "J", "folds": [[0, 1, 2, 3]], "budget": 30}
    runs = [{"model": "RF", "algo": "GA", "parity": a, "n_evals": 30},
            {"model": "RF", "algo": "SA", "parity": {**a, "budget": 20}, "n_evals": 20}]
    x = pl.hpo_parity(runs, [("RF", "GA"), ("RF", "SA")])[0]
    assert x["ok"] is False and x["checks"]["budget"] is False and x["checks"]["space"] is True


# ---------------------------------------------------------------- (d) 18 phép so sánh Bảng 4.5

def test_d_cong_thuc_cai_thien_ra_dung_18_phep_so_sanh():
    s = lambda v: {"MAE": v, "RMSE": v * 1.5, "MAPE": v / 100, "SD_RMSE": 0.1}
    before = {m: s(10.0) for m in ("ANN", "RF", "XGB")}
    after = {(m, a): s(9.0 if a == "SA" else 11.0) for m in before for a in ("GA", "SA")}
    rows = table_4_5(before, after)
    assert len(rows) == 9                                                  # 3 mô hình × 3 chỉ tiêu
    comps = [(r["model"], r["metric"], a, r[f"impr_{a.lower()}"]) for r in rows for a in ("GA", "SA")]
    assert len(comps) == 18
    assert all(c[3] == pytest.approx(10.0) for c in comps if c[2] == "SA")   # 100 × (10 − 9) / 10
    assert all(c[3] == pytest.approx(-10.0) for c in comps if c[2] == "GA")
    assert improvement(40.4895, 37.2890) == pytest.approx(7.9047, abs=1e-3)   # RF RMSE SA của bài: 7,90%


# ---------------------------------------------------------------- (e) Bảng 4.6 đủ trường

def test_g_bang_4_6_dung_16_truong_cua_bai(series, chay_gia):
    r = chay_gia(series)
    t46 = r["table_4_6"]
    assert list(t46) == FIELDS_46                                          # đúng 16 trường, đúng thứ tự của bài
    assert "Expected_Direction" not in t46 and "Next_Forecast_Change_Abs" not in t46
    assert t46["Chosen_Selection_Basis"] == "Minimum Mean RMSE across 3 repeated Test runs"
    assert t46["Management_Alert"] == "Tăng"                               # mô hình giả dự báo +200 (> ngưỡng)
    # Mức thay đổi tuyệt đối: đầu ra theo mục 3.3.5, nằm ngoài Bảng 4.6
    assert r["outputs_335"]["change_abs"] == pytest.approx(t46["Next_Forecast_Rate_Mean"] - t46["Latest_Observed_Rate"])


def test_canh_bao_hinh_3_3():
    assert alert(-0.0027, 0.10) == "Ổn định"                               # ví dụ của bài
    assert alert(0.15, 0.10) == "Tăng" and alert(-0.15, 0.10) == "Giảm"
    assert alert(0.10, 0.10) == "Tăng"


# ---------------------------------------------------------------- H1, H3

def test_h1_ghi_dung_tung_chi_tieu():
    t44 = [{"model": "ARIMA", "MAE": 24.72, "RMSE": 34.99, "MAPE": 0.0943},
           {"model": "XGB", "MAE": 24.95, "RMSE": 34.85, "MAPE": 0.0951}]
    h = hypotheses(t44, [], completed=True, cfg={"mode": "chay_day_du"})["H1"]
    d = h["detail"][0]
    assert "RMSE 34,85 < 34,99 (thấp hơn)" in d and "MAE 24,95 > 24,72 (không thấp hơn)" in d
    assert "thấp hơn ARIMA ở RMSE; không thấp hơn ở MAE, MAPE" in d
    assert h["status"] == "Ủng hộ một phần" and h["text"].startswith("1/3 phép so sánh")


def test_h3_ba_tieu_chi(series, chay_gia):
    h3 = chay_gia(series)["hypotheses"]["H3"]
    assert [d.split(":")[0] for d in h3["detail"]] == ["Tính chính xác", "Tính tự động hóa", "Tính hữu ích quản lý"]
    assert "12 công đoạn" not in h3["text"]
    assert "Tính chính xác: chưa đạt" in h3["detail"][0]                   # mô hình giả tệ hơn ARIMA
    assert h3["status"] == "Ủng hộ một phần"


# ---------------------------------------------------------------- Vòng phản hồi 3 mức

def _rec(errs):
    return [{"date": i, "forecast": 1000.0 - e, "actual": 1000.0} for i, e in enumerate(errs)]


def test_vong_phan_hoi_ba_muc():
    assert rolling_status(_rec([5] * 25), 10.0)["level"] == "stable"
    assert rolling_status(_rec([5] * 20 + [30] * 2), 10.0)["level"] == "refit"            # suy giảm nhẹ
    r = rolling_status(_rec([5] * 20 + [100] * 5), 10.0)
    assert r["level"] == "reoptimize" and "GA và SA" in r["status"]


# ---------------------------------------------------------------- Dữ liệu: làm sạch 6 bước, cột Vietcombank

def test_nhat_ky_lam_sach_du_6_buoc_dung_thu_tu(sample_df):
    _, log, _ = clean(sample_df, build_run_config("chay_thu"))
    buoc = [l.split(" – ")[0] for l in log if l.startswith("Bước")]
    assert buoc == [f"Bước {i}" for i in range(1, 7)]


def test_file_vietcombank_lay_cot_mua_chuyen_khoan():
    dong = ["Ngày,Mua tiền mặt,Mua chuyển khoản,Bán"] + [f"{d:%d/%m/%Y},{24000 + i},{24050 + i},{24400 + i}"
                                                         for i, d in enumerate(pd.bdate_range("2000-01-03", periods=10))]
    df, info = parse_table(read_table("\n".join(dong).encode("utf-8"), "vcb.csv"))
    assert info["rate_column"] == "Mua chuyển khoản" and df["rate"].iloc[0] == 24050


def test_g_hang_so_truong_bang_4_6_khop_bai():
    assert FIELDS_46_ENGINE == FIELDS_46


# ---------------------------------------------------------------- (e) ANN không còn w; XGBoost không có grow_policy

def test_e_ann_khong_co_w_va_chi_dung_gia_tri_tre(series):
    from forecast_engine.features import build_features
    caps = build_run_config("chay_day_du")["caps"]
    names = [p.name for p in ss.space("ANN", caps)]
    assert "w" not in names and names[0] == "p"
    assert names[1:] == ["n_layers", "units", "learning_rate", "epochs", "batch_size", "dropout"]   # Bảng 3.1 (ReLU cố định)
    assert "w" not in ss.baseline("ANN")
    assert {"p", "w"} <= {p.name for p in ss.space("RF", caps)} and {"p", "w"} <= {p.name for p in ss.space("XGB", caps)}
    assert "grow_policy" not in [p.name for p in ss.space("XGB", caps)] and "grow_policy" not in ss.baseline("XGB")
    X, _, cols = build_features(series["rate"].to_numpy(), p=4)            # ANN: công thức 3.9, chỉ p giá trị trễ
    assert cols == ["d_lag0", "d_lag1", "d_lag2", "d_lag3"] and X.shape[1] == 4
    ctx = pl.Context(series["rate"].to_numpy(dtype=float), build_run_config("chay_thu", n_jobs=1))
    pred, model = ctx.run("ANN", {**ss.baseline("ANN"), "epochs": 3}, 1, np.arange(30, 150), np.array([150]))
    assert model.x_scaler.mean_.shape == (ss.baseline("ANN")["p"],)


# ---------------------------------------------------------------- (b) Chạy đầy đủ: đúng 30 lần ở mọi bước bài quy định

def test_b_chay_day_du_dung_30_lan(series, monkeypatch):
    s = pl.Context(series["rate"].to_numpy(dtype=float), build_run_config("chay_day_du")).split
    dem = {"bang_4_4": 0, "danh_gia_test": 0, "refit": 0, "cv": 0}

    def fake_fit_predict(kind, params, seed, X, target, train_rows, pred_rows, *a, **k):
        if np.array_equal(train_rows, s.train_rows):
            dem["bang_4_4"] += 1
        elif np.array_equal(train_rows, s.dev_rows):
            dem["refit" if len(pred_rows) == 1 else "danh_gia_test"] += 1
        else:
            dem["cv"] += 1
        return np.zeros(len(pred_rows)), _Fake(0.0)

    runs = {"GA": 0, "SA": 0}

    def fake_algo(name):
        def f(evaluator, dim, categorical, rng, init_vector, **k):
            runs[name] += 1
            evaluator(init_vector)
            return {"best_vector": evaluator.best_vector, "best_j": evaluator.best_j, "n_evals": evaluator.n_evals,
                    "generations": 0, "T0": 1.0, "T_final": 1.0, "stop_reason": "giả"}
        return f
    monkeypatch.setattr(pl, "fit_predict", fake_fit_predict)
    monkeypatch.setattr(pl, "run_ga", fake_algo("GA"))
    monkeypatch.setattr(pl, "run_sa", fake_algo("SA"))
    r = pl.run_pipeline(series, build_run_config("chay_day_du", ["ANN", "RF", "XGB"], ["Baseline", "GA", "SA"], n_jobs=1))
    n = MODES["chay_day_du"]
    assert n["n_baseline_seeds"] == n["n_hpo_runs"] == n["n_test_seeds_baseline"] == n["n_refit_seeds"] == 30
    assert dem["bang_4_4"] == 3 * 30                                       # Bảng 4.4: 30 lần mỗi mô hình
    assert runs == {"GA": 3 * 30, "SA": 3 * 30}                            # 30 lần chạy độc lập GA/SA mỗi mô hình
    # tầng 3: Baseline 30 seed + Bảng 4.5 (30 lần chạy × 1 seed) + đánh giá ứng viên GA, SA 30 seed
    assert dem["danh_gia_test"] == 3 * (30 + 2 * 30 * 1 + 2 * 30)
    assert dem["refit"] == 9 * 30                                          # 9 ứng viên × 30 seed huấn luyện lại
    assert all(r["candidates"][k]["summary"]["n_runs"] == 30 for k in r["candidates"])
    assert all(r["candidates"][k]["t1"]["n_seeds"] == 30 for k in r["candidates"])
    assert all(x["n_runs"] == 30 for x in r["table_4_4"])


# ---------------------------------------------------------------- (h) Chạy tiếp sau khi ngắt cho cùng kết quả

def _gon(r):
    """Phần kết quả so sánh được (bỏ thời gian chạy, tiến trình)."""
    import json
    bo = {"elapsed_seconds", "progress", "estimate", "checkpoint_reused", "hpo_runs"}
    out = {k: v for k, v in r.items() if k not in bo}
    for c in out["candidates"].values():
        c.pop("cost_seconds", None)
    out["selection"] = [{k: v for k, v in x.items() if k != "cost_seconds"} for x in out["selection"]]
    return json.loads(json.dumps(out, default=str))


def test_h_chay_tiep_sau_khi_ngat_cho_cung_ket_qua(series, tmp_path):
    from forecast_engine.progress import Cancelled
    cfg = build_run_config("chay_thu", ["ARIMA", "RF", "XGB"], ["Baseline", "GA", "SA"], n_jobs=1, budget=6,
                           ga_pop_size=3, ga_max_generations=2, sa_t0_samples=2, sa_moves_per_temp=2,
                           caps={"ANN_epochs": 50, "RF_n_estimators": 120, "XGB_n_estimators": 120})
    mot_mach = pl.run_pipeline(series, cfg)

    dem = {"n": 0}

    def ngat(snap):                          # yêu cầu hủy khi đang ở bước 9 (đã xong Bảng 4.4 và GA/SA)
        if any(st["id"] == 9 and st["status"] == "dang_chay" for st in snap["steps"]):
            dem["n"] += 1
            return dem["n"] > 3
        return False
    with pytest.raises(Cancelled):
        pl.run_pipeline(series, cfg, on_progress=ngat, checkpoint_dir=tmp_path / "cp")
    da_luu = len(list((tmp_path / "cp").glob("*.joblib")))
    assert da_luu > 0
    tiep = pl.run_pipeline(series, cfg, checkpoint_dir=tmp_path / "cp")
    assert tiep["checkpoint_reused"] >= da_luu - 1                         # phần đã xong không chạy lại
    assert _gon(tiep) == _gon(mot_mach)                                    # giống hệt khi chạy một mạch
