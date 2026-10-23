"""Các mô hình (đặc tả v3 mục 6): ARIMA, ANN (MLP, PyTorch), Random Forest, XGBoost, Random walk.

Mọi lần huấn luyện học máy đi qua MỘT hàm fit_predict() (dùng chung cho mọi tầng và cả hai chế độ).
StandardScaler luôn fit trên phần train của lượt đó rồi mới áp sang tập đánh giá.
"""
import warnings

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler

from .splits import early_stop_split


# ---------------------------------------------------------------- ANN (PyTorch)

def _train_ann(X, y, params, seed):
    import torch
    from torch import nn

    torch.set_num_threads(1)
    torch.manual_seed(seed)
    gen = torch.Generator().manual_seed(seed)
    layers, width, in_dim = [], params["units"], X.shape[1]
    for _ in range(params["n_layers"]):
        layers += [nn.Linear(in_dim, width), nn.ReLU(), nn.Dropout(params["dropout"])]
        in_dim = width
    layers.append(nn.Linear(in_dim, 1))                     # lớp ra tuyến tính
    net = nn.Sequential(*layers)
    opt = torch.optim.Adam(net.parameters(), lr=params["learning_rate"])   # Adam [CHỐT]
    loss_fn = nn.MSELoss()
    Xt = torch.tensor(X, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.float32).reshape(-1, 1)
    n, bs = len(Xt), int(params["batch_size"])
    net.train()
    for _ in range(int(params["epochs"])):
        order = torch.randperm(n, generator=gen)           # xáo thứ tự mini-batch TRONG tập train
        for i in range(0, n, bs):
            idx = order[i:i + bs]
            opt.zero_grad()
            loss_fn(net(Xt[idx]), yt[idx]).backward()
            opt.step()
    net.eval()
    return net


def _predict_ann(net, X):
    import torch
    with torch.no_grad():
        return net(torch.tensor(X, dtype=torch.float32)).numpy().ravel()


# ---------------------------------------------------------------- Mô hình đã fit

class FittedModel:
    """Mô hình + scaler; lưu được bằng joblib (vòng phản hồi mục 8.8)."""

    def __init__(self, kind, params, seed, model, x_scaler, y_scaler=None, best_iteration=None):
        self.kind, self.params, self.seed = kind, params, seed
        self.model, self.x_scaler, self.y_scaler, self.best_iteration = model, x_scaler, y_scaler, best_iteration

    def predict(self, X):
        Xs = self.x_scaler.transform(X)
        if self.kind == "ANN":
            pred = _predict_ann(self.model, Xs)
            return self.y_scaler.inverse_transform(pred.reshape(-1, 1)).ravel()
        if self.kind == "XGB" and self.best_iteration is not None:
            return self.model.predict(Xs, iteration_range=(0, self.best_iteration + 1))
        return self.model.predict(Xs)


def _make_rf(p, seed):
    return RandomForestRegressor(
        n_estimators=p["n_estimators"], max_depth=p["max_depth"], max_features=p["max_features"],
        min_samples_split=p["min_samples_split"], min_samples_leaf=p["min_samples_leaf"],
        max_leaf_nodes=p["max_leaf_nodes"], bootstrap=p["bootstrap"],
        max_samples=p["max_samples"] if p["bootstrap"] else None, random_state=seed, n_jobs=1)


def _make_xgb(p, seed, es_rounds):
    from xgboost import XGBRegressor
    return XGBRegressor(
        tree_method="hist", objective=p["objective"], n_estimators=p["n_estimators"],
        learning_rate=p["learning_rate"], max_depth=p["max_depth"], min_child_weight=p["min_child_weight"],
        gamma=p["gamma"], subsample=p["subsample"], colsample_bytree=p["colsample_bytree"],
        max_leaves=p["max_leaves"], reg_alpha=p["reg_alpha"],        # grow_policy: mặc định của XGBoost (bài không có)
        reg_lambda=p["reg_lambda"], random_state=seed, n_jobs=1, verbosity=0, early_stopping_rounds=es_rounds)


def fit_model(kind, params, seed, X_train, y_train, X_es=None, y_es=None, es_frac=0.15, es_rounds=50):
    """Huấn luyện 1 mô hình học máy trên mục tiêu Δy.

    XGBoost dừng sớm trên (X_es, y_es) nếu có (tầng 1: validation), ngược lại trên 15% cuối của train.
    """
    x_scaler = StandardScaler().fit(X_train)
    Xs = x_scaler.transform(X_train)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if kind == "ANN":
            y_scaler = StandardScaler().fit(y_train.reshape(-1, 1))
            ys = y_scaler.transform(y_train.reshape(-1, 1)).ravel()
            return FittedModel(kind, params, seed, _train_ann(Xs, ys, params, seed), x_scaler, y_scaler)
        if kind == "RF":
            return FittedModel(kind, params, seed, _make_rf(params, seed).fit(Xs, y_train), x_scaler)
        if kind == "XGB":
            if X_es is None:
                fit_idx, es_idx = early_stop_split(len(Xs), es_frac)
                X_fit, y_fit, X_val, y_val = Xs[fit_idx], y_train[fit_idx], Xs[es_idx], y_train[es_idx]
            else:
                X_fit, y_fit, X_val, y_val = Xs, y_train, x_scaler.transform(X_es), y_es
            model = _make_xgb(params, seed, es_rounds).fit(X_fit, y_fit, eval_set=[(X_val, y_val)], verbose=False)
            return FittedModel(kind, params, seed, model, x_scaler, best_iteration=int(model.best_iteration))
    raise ValueError(kind)


def fit_predict(kind, params, seed, X, target, train_rows, pred_rows, es_rows=None, es_frac=0.15, es_rounds=50):
    """Hàm huấn luyện DUY NHẤT của pipeline. Trả về (Δŷ cho pred_rows, mô hình đã fit)."""
    model = fit_model(kind, params, seed, X[train_rows], target[train_rows],
                      None if es_rows is None else X[es_rows], None if es_rows is None else target[es_rows],
                      es_frac, es_rounds)
    return model.predict(X[pred_rows]), model


# ---------------------------------------------------------------- ARIMA (mục 6.1)

def _fit_arima(y, order, trend):
    from statsmodels.tsa.arima.model import ARIMA
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ARIMA(np.asarray(y, dtype=float), order=order, trend=trend).fit()


def arima_structures(y_dev, d, max_p, max_q, trend, on_step=None):
    """Ước lượng 25 cấu trúc (p, q ∈ 0..4) bằng hợp lý cực đại trên development. Trả về list đã sắp theo AIC."""
    out, total, i = [], (max_p + 1) * (max_q + 1), 0
    for p in range(max_p + 1):
        for q in range(max_q + 1):
            i += 1
            if on_step:
                on_step(i, total, (p, d, q))
            try:
                res = _fit_arima(y_dev, (p, d, q), trend)
                out.append({"order": (p, d, q), "trend": trend, "llf": float(res.llf), "aic": float(res.aic),
                            "bic": float(res.bic), "hqic": float(res.hqic), "nobs": int(res.nobs), "result": res})
            except Exception as e:                              # cấu trúc không hội tụ -> bỏ qua, ghi lại
                out.append({"order": (p, d, q), "trend": trend, "error": str(e), "aic": np.inf})
    return sorted(out, key=lambda r: r["aic"])


def arima_test_forecast(result, y, start, on_step=None):
    """Dự báo 1 ngày phía trước cho y[start..n-1], cập nhật quan sát thật từng ngày
    bằng results.append(new_obs, refit=False). Trả về (dự báo, cận dưới 95%, cận trên 95%)."""
    y = np.asarray(y, dtype=float)
    pred, lo, hi = [], [], []
    res = result
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for k, i in enumerate(range(start, len(y))):
            fc = res.get_forecast(1)
            ci = np.asarray(fc.conf_int(alpha=0.05))[0]
            pred.append(float(np.asarray(fc.predicted_mean)[0]))
            lo.append(float(ci[0]))
            hi.append(float(ci[1]))
            res = res.append(y[i:i + 1], refit=False)
            if on_step and k % 20 == 0:
                on_step(k + 1, len(y) - start)
    return np.array(pred), np.array(lo), np.array(hi)


def arima_forecast_after(result, y_new):
    """Giữ tham số đã ước lượng trên tập phát triển, cập nhật các quan sát thật sau đó (append, refit=False)
    rồi dự báo 1 bước. Trả về (dự báo, cận dưới 95%, cận trên 95%)."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = result.append(np.asarray(y_new, dtype=float), refit=False) if len(y_new) else result
        fc = res.get_forecast(1)
    ci = np.asarray(fc.conf_int(alpha=0.05))[0]
    return float(np.asarray(fc.predicted_mean)[0]), float(ci[0]), float(ci[1])


def arima_forecast_next(y, order, trend):
    """Refit (giữ bậc) trên toàn bộ lịch sử, dự báo 1 bước. Trả về (dự báo, cận dưới, cận trên)."""
    res = _fit_arima(y, order, trend)
    fc = res.get_forecast(1)
    ci = np.asarray(fc.conf_int(alpha=0.05))[0]
    return float(np.asarray(fc.predicted_mean)[0]), float(ci[0]), float(ci[1])
