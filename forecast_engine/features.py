"""Tạo đặc trưng (mục 3.3.1, 3.3.3, 4.5 của bài; đặc tả v3 mục 5).

MỘT hàm build_features duy nhất cho train, test và dự báo thật.
Dòng t chỉ dùng y[0..t] (cửa sổ lùi). Mục tiêu tại dòng t là Δy_{t+1} = y_{t+1} − y_t.
"""
import numpy as np
import pandas as pd


def build_features(series, p, w=None):
    """series: tỷ giá y[0..n-1]; p: số trễ; w: độ dài cửa sổ trượt.

    w = None (ANN): CHỈ p giá trị trễ, đúng công thức 3.3 / 3.9 và Bảng 3.1 của bài (chỉ có p), ở dạng sai phân bậc 1
    theo mục 4.1.2: d_t, ..., d_{t-p+1}.

    Đặc trưng nội sinh theo bài (mục 3.3.1, 4.5: Lag, Return, MA, STD, Momentum), dạng sai phân bậc 1 (mục 4.1.2):
      - Lag:      d_t, d_{t-1}, ..., d_{t-p+1}     (trễ của sai phân bậc 1; d_t cũng là "thay đổi tỷ giá")
      - Return:   r_t = d_t / y_{t-1}              (lợi suất)
      - MA, STD:  trung bình trượt và độ lệch chuẩn trượt của d trên w phiên;
                  y_t − trung bình trượt của y trên w phiên (khoảng cách tới MA)
      - Momentum: y_t − y_{t-w}                    [WEB: bài nêu Momentum nhưng không ghi công thức; web dùng định nghĩa
                                                    phổ biến, cùng độ dài cửa sổ w]
    Mọi cửa sổ là cửa sổ lùi kết thúc tại t; mục tiêu là Δy_{t+1}, nên thông tin của ngày dự báo không nằm trong X.
    Trả về (X: ndarray n×k, target: ndarray n, NaN ở dòng cuối, tên cột).
    """
    y = pd.Series(np.asarray(series, dtype=float))
    d = y.diff()
    cols = {f"d_lag{k}": d.shift(k) for k in range(p)}
    if w is None:                                   # ANN: chỉ các giá trị trễ (Bảng 3.1, công thức 3.9)
        X = pd.DataFrame(cols)
        return X.to_numpy(), (y.shift(-1) - y).to_numpy(), list(X.columns)
    cols["r"] = d / y.shift(1)
    cols[f"d_mean_{w}"] = d.rolling(w).mean()
    cols[f"d_std_{w}"] = d.rolling(w).std()
    cols[f"y_minus_ma_{w}"] = y - y.rolling(w).mean()
    cols[f"momentum_{w}"] = y - y.shift(w)
    X = pd.DataFrame(cols)
    target = (y.shift(-1) - y).to_numpy()
    return X.to_numpy(), target, list(X.columns)


def to_level(series, rows, delta_pred):
    """Khôi phục mức tỷ giá: ŷ_{t+1} = y_t + Δŷ_{t+1}."""
    return np.asarray(series, dtype=float)[rows] + np.asarray(delta_pred, dtype=float)
