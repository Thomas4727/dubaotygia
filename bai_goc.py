"""Số liệu của BÀI GỐC – chỉ để hiển thị ở cột "Bài gốc (tham chiếu)", KHÔNG dùng làm kết quả chạy.

Nguồn: bài NCKH "Dự báo tỷ giá hối đoái dựa trên các thuật toán học máy và tối ưu hóa siêu tham số" (Bảng 4.1, 4.4, 4.5;
dữ liệu tỷ giá chuyển khoản Vietcombank 03/01/2000–30/06/2026, 6.837 quan sát).
"""
NHAN = "Bài gốc – dữ liệu Vietcombank 2000–2026, không phải kết quả của lần chạy này"

BANG_4_1 = {"n_obs": 6837, "first": 14168, "last": 26070, "min": 14168, "max": 26230, "max_date": "25/09/2025",
            "mean": 19974, "median": 20950, "std": 3631, "change_abs": 11902, "change_pct": 84.01,
            "vnd_depreciation_pct": 45.65}

BANG_4_4 = {
    "ARIMA": {"n_runs": 30, "MAE": 26.66, "RMSE": 45.16, "MAPE": 0.1391, "MeanErr": 7.0809, "SdErr": 45.12},
    "ANN": {"n_runs": 30, "MAE": 22.92, "RMSE": 40.87, "MAPE": 0.0942, "MeanErr": 1.5631, "SdErr": 40.75},
    "RF": {"n_runs": 30, "MAE": 21.80, "RMSE": 40.39, "MAPE": 0.0897, "MeanErr": 0.8383, "SdErr": 40.40},
    "XGB": {"n_runs": 30, "MAE": 20.93, "RMSE": 38.51, "MAPE": 0.0702, "MeanErr": 0.8765, "SdErr": 38.46},
}

# (mô hình, chỉ tiêu) -> (Trước, Sau SA, Sau GA, SA cải thiện %, GA cải thiện %)
BANG_4_5 = {
    ("ANN", "MAE"): (25.3399, 23.2031, 22.5277, 8.43, 11.10),
    ("ANN", "RMSE"): (42.0507, 37.0827, 38.7437, 11.81, 7.86),
    ("ANN", "MAPE"): (0.1039, 0.0954, 0.0927, 8.22, 10.76),
    ("RF", "MAE"): (21.8913, 21.8459, 21.4986, 0.21, 1.79),
    ("RF", "RMSE"): (40.4895, 37.2890, 37.8804, 7.90, 6.44),
    ("RF", "MAPE"): (0.0901, 0.0899, 0.0890, 0.22, 1.21),
    ("XGB", "MAE"): (21.6437, 21.4795, 21.3483, 0.76, 1.36),
    ("XGB", "RMSE"): (40.3664, 36.4118, 37.7313, 9.80, 6.53),
    ("XGB", "MAPE"): (0.0890, 0.0889, 0.0886, 0.13, 0.49),
}
