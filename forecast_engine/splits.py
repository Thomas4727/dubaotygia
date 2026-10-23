"""Thiết kế thực nghiệm ba tầng (mục 3.3.2 của bài; đặc tả v3 mục 4). Không bao giờ xáo trộn.

Quy ước: "mẫu" t là dòng đặc trưng tại ngày t, mục tiêu là y[t+1].
Quan sát:  |<------------- development (80%) ------------->|<-- test (20%) -->|
           |<-- train (80% dev) -->|<-- validation (20%) -->|
"""
from dataclasses import dataclass

import numpy as np


@dataclass
class Split:
    n_obs: int
    n_dev: int          # số quan sát development
    n_train: int        # số quan sát train (tầng 1)
    first_row: int      # dòng mẫu đầu tiên đủ cửa sổ cho mọi cấu hình
    train_rows: np.ndarray      # tầng 1
    val_rows: np.ndarray        # tầng 1 (chỉ early stopping XGBoost)
    dev_rows: np.ndarray        # CV (tầng 2) và fit tầng 3
    test_rows: np.ndarray       # đánh giá (tầng 1 và 3)
    all_rows: np.ndarray        # refit toàn bộ lịch sử


def make_split(n_obs, test_ratio, val_ratio, first_row):
    n_test = int(round(n_obs * test_ratio))
    n_dev = n_obs - n_test
    n_train = n_dev - int(round(n_dev * val_ratio))
    if n_train - 1 - first_row < 20:
        raise ValueError("Không đủ dữ liệu để chia train/validation/test (cần thêm quan sát).")
    return Split(
        n_obs=n_obs, n_dev=n_dev, n_train=n_train, first_row=first_row,
        train_rows=np.arange(first_row, n_train - 1),          # mục tiêu y[first_row+1 .. n_train-1]
        val_rows=np.arange(n_train - 1, n_dev - 1),            # mục tiêu y[n_train .. n_dev-1]
        dev_rows=np.arange(first_row, n_dev - 1),
        test_rows=np.arange(n_dev - 1, n_obs - 1),             # mục tiêu y[n_dev .. n-1]
        all_rows=np.arange(first_row, n_obs - 1),
    )


def expanding_folds(n, k, first_train_frac=0.5):
    """K fold cửa sổ mở rộng trên n mẫu development: fold đầu train 50%, 50% còn lại chia đều K khối."""
    val_len = int(round(n * (1 - first_train_frac))) // k
    if val_len < 1:
        raise ValueError(f"Không đủ dữ liệu cho {k} fold.")
    start = n - k * val_len
    return [(np.arange(0, start + i * val_len), np.arange(start + i * val_len, start + (i + 1) * val_len))
            for i in range(k)]


def early_stop_split(n_train, frac):
    """15% cuối của phần train dùng để dừng sớm (luôn nằm trước tập đánh giá)."""
    n_es = max(1, int(round(n_train * frac)))
    return np.arange(0, n_train - n_es), np.arange(n_train - n_es, n_train)
