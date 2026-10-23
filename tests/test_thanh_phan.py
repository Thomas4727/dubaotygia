"""Test bắt buộc (đặc tả v3 mục 11): rò rỉ đặc trưng, scaler, fold, GA/SA, tái lập."""
import numpy as np
import pytest

from forecast_engine import search_space as ss
from forecast_engine.budget import Evaluator
from forecast_engine.features import build_features
from forecast_engine.ga import run_ga
from forecast_engine.models import fit_model
from forecast_engine.pipeline import Context, _task_eval, _task_hpo
from forecast_engine.run_config import build_run_config
from forecast_engine.sa import run_sa


def test_dac_trung_tai_t_khong_doi_khi_sua_du_lieu_sau_t(series):
    y = series["rate"].to_numpy()
    X, _, _ = build_features(y, p=10, w=10)
    for t in (40, 150, 250):
        y2 = y.copy()
        y2[t + 1:] += np.random.default_rng(t).normal(0, 500, len(y) - t - 1)
        X2, _, _ = build_features(y2, p=10, w=10)
        np.testing.assert_array_equal(X[: t + 1], X2[: t + 1])


def test_muc_tieu_la_sai_phan_bac_1(series):
    y = series["rate"].to_numpy()
    _, target, cols = build_features(y, p=5, w=7)
    assert target[10] == y[11] - y[10] and np.isnan(target[-1])
    assert cols == ["d_lag0", "d_lag1", "d_lag2", "d_lag3", "d_lag4", "r", "d_mean_7", "d_std_7", "y_minus_ma_7", "momentum_7"]
    X, _, _ = build_features(y, p=5, w=7)
    assert X[20, -1] == y[20] - y[13]                                     # Momentum = y_t − y_{t−w}


@pytest.mark.parametrize("kind", ["ANN", "RF", "XGB"])
def test_scaler_fit_tren_train(series, kind):
    y = series["rate"].to_numpy()
    X, target, _ = build_features(y, 10, 10)
    X, target = X[30:-1], target[30:-1]
    params = {k: v for k, v in ss.baseline(kind).items() if k not in ("p", "w")}
    if kind == "ANN":
        params["epochs"] = 5
    m = fit_model(kind, params, 1, X[:150], target[:150])
    np.testing.assert_allclose(m.x_scaler.mean_, X[:150].mean(axis=0))
    np.testing.assert_allclose(m.x_scaler.scale_, X[:150].std(axis=0), rtol=1e-10)
    assert not np.allclose(m.x_scaler.mean_, X.mean(axis=0))
    if kind == "ANN":
        assert np.isclose(m.y_scaler.mean_[0], target[:150].mean())


@pytest.mark.parametrize("mode", ["chay_thu", "chay_day_du"])
def test_fold_dung_thu_tu_va_test_khong_giao_cv(series, mode):
    cfg = build_run_config(mode)
    ctx = Context(series["rate"].to_numpy(), cfg)
    s = ctx.split
    assert len(ctx.folds) == cfg["n_folds"]
    prev = 0
    test_targets = set(s.test_rows + 1)
    for tr, va in ctx.folds:
        assert tr[0] == 0 and len(tr) > prev and tr.max() < va.min()         # cửa sổ mở rộng, validation sau train
        prev = len(tr)
        used = set(s.dev_rows[tr] + 1) | set(s.dev_rows[va] + 1)
        assert not used & test_targets                                        # test không giao với CV
    assert len(ctx.folds[0][0]) == pytest.approx(len(s.dev_rows) * 0.5, abs=cfg["n_folds"])
    # tầng 1: train < validation < test theo thời gian
    assert s.train_rows.max() < s.val_rows.min() and s.val_rows.max() < s.test_rows.min()
    assert s.dev_rows.max() + 1 == s.n_dev - 1 and s.test_rows.min() + 1 == s.n_dev


TARGET = np.array([0.2, 0.7, 0.45])


def sphere(v):
    return float(np.sum((np.asarray(v) - TARGET) ** 2))


@pytest.mark.parametrize("algo", ["GA", "SA"])
def test_ga_sa_giam_J_va_khong_vuot_ngan_sach(algo):
    init = np.array([0.95, 0.05, 0.95])
    budget = 120
    ev = Evaluator(sphere, budget)
    rng = np.random.default_rng(1)
    cat = np.zeros(3, dtype=bool)
    if algo == "GA":
        res = run_ga(ev, 3, cat, rng, init, pop_size=10, max_generations=15, tournament_k=3, p_crossover=0.9,
                     p_mutation=0.15, sigma=0.1, elitism=2, patience=5)
    else:
        res = run_sa(ev, 3, cat, rng, init, t0_samples=10, accept0=0.8, cooling=0.9, moves_per_temp=5,
                     sigma=0.1, t_min_ratio=1e-3, patience=100)
    assert res["best_j"] < sphere(init)
    assert ev.n_evals <= budget


def test_cache_van_tinh_vao_ngan_sach():
    ev = Evaluator(sphere, budget=3)
    for _ in range(3):
        ev([0.1, 0.1, 0.1])
    assert ev.n_evals == 3 and ev.n_trained == 1


@pytest.mark.parametrize("model", ["ANN", "RF", "XGB"])
def test_ma_hoa_baseline_va_sua_loi(model):
    caps = build_run_config("chay_day_du")["caps"]
    base = ss.baseline(model)
    back = ss.decode(model, ss.encode(model, base, caps), caps)
    for k, v in base.items():
        if not (model == "XGB" and k == "reg_alpha"):         # reg_alpha = 0 nằm ngoài miền log [1e-4, 10]
            assert back[k] == v or (k == "max_samples" and v is None and back[k] == 1.0), k
    for u in np.random.default_rng(0).random((50, ss.dim(model, caps))):
        p = ss.decode(model, u, caps)
        assert 3 <= p["p"] <= 30
        assert ("w" not in p) if model == "ANN" else (5 <= p["w"] <= 30)   # ANN: Bảng 3.1 chỉ có p
        if model == "RF" and not p["bootstrap"]:
            assert p["max_samples"] is None
        if model == "XGB":
            assert "grow_policy" not in p                                # Bảng 3.3 không có grow_policy


def test_cung_seed_cung_ket_qua(series):
    cfg = build_run_config("chay_thu", n_jobs=1)
    ctx = Context(series["rate"].to_numpy(), cfg)
    a = _task_eval(ctx, "x", "ANN", {**ss.baseline("ANN"), "epochs": 10}, 7, 3)[2]
    b = _task_eval(ctx, "x", "ANN", {**ss.baseline("ANN"), "epochs": 10}, 7, 3)[2]
    np.testing.assert_array_equal(a, b)
    r1 = _task_hpo(ctx, "XGB", "SA", 1, 1, None, None)
    r2 = _task_hpo(ctx, "XGB", "SA", 1, 1, None, None)
    assert r1["params"] == r2["params"] and r1["J"] == r2["J"] and r1["history"] == r2["history"]
    assert r1["n_evals"] <= cfg["budget"]
