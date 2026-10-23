"""MỌI tham số của hai chế độ chạy nằm ở đây (đặc tả v3, mục 12.2). Không rải số trong code khác.

Hai chế độ gọi CÙNG các hàm của pipeline; chỉ khác bộ số dưới đây.
Các giá trị đánh dấu [CHỐT] lấy từ đặc tả; [TỰ QUYẾT] là chỗ đặc tả không nói, xem README/báo cáo.
[WEB] = lựa chọn của web, bài NCKH không quy định (xem docs/doi-chieu-bai-goc.md). "30 lần chạy" là của bài.
"""
from copy import deepcopy

MODELS = ["ARIMA", "ANN", "RF", "XGB"]            # thứ tự hiển thị
ML_MODELS = ["ANN", "RF", "XGB"]
VARIANTS = ["Baseline", "GA", "SA"]
MODEL_NAMES = {"ARIMA": "ARIMA", "ANN": "ANN", "RF": "Random Forest", "XGB": "XGBoost", "RW": "Random walk"}
MODE_NAMES = {"chay_thu": "Chạy thử", "chay_day_du": "Chạy đầy đủ"}

MODES = {
    "chay_thu": {
        "n_baseline_seeds": 3,            # Bảng 4.4 (tầng 1)
        "n_hpo_runs": 1,                  # số lần chạy độc lập GA/SA mỗi mô hình (mục 7.4)
        "budget": 30,                     # ngân sách đánh giá mỗi lần GA/SA
        "ga_pop_size": 6, "ga_max_generations": 5,
        "sa_t0_samples": 5, "sa_moves_per_temp": 5,
        "n_folds": 3,                     # expanding-window CV
        "n_test_seeds_baseline": 3,       # cột "Trước" Bảng 4.5 (tầng 3)
        "n_eval_seeds_per_config": 3,     # quyết định của người dùng: 1 lần chạy × 3 seed = 3 giá trị
        "n_refit_seeds": 3,               # refit + dự báo T+1 (Bảng 4.6)
        "caps": {"ANN_epochs": 150, "RF_n_estimators": 300, "XGB_n_estimators": 500},
    },
    "chay_day_du": {
        "n_baseline_seeds": 30,
        "n_hpo_runs": 30,
        "budget": 300,                    # [WEB] bài không quy định ngân sách
        "ga_pop_size": 20, "ga_max_generations": 15,
        "sa_t0_samples": 20, "sa_moves_per_temp": 10,
        "n_folds": 5,                      # [WEB] bài không quy định số fold
        "n_test_seeds_baseline": 30,
        "n_eval_seeds_per_config": 1,     # quyết định của người dùng: 30 lần chạy × 1 seed (seed của lần chạy)
        "n_refit_seeds": 30,
        "caps": {"ANN_epochs": 500, "RF_n_estimators": 800, "XGB_n_estimators": 1500},   # = miền mục 7.1
    },
}

COMMON = {
    # Dữ liệu (mục 2)
    "min_rows": 60,
    "anomaly_jump": 0.01,                 # [CHỐT] |%Δ| > 1% ...
    "anomaly_revert": 0.002,              # [CHỐT] ... và hôm sau quay về trong 0,2%
    # Thiết kế thực nghiệm (mục 4)
    "test_ratio": 0.20,                   # development 80% / test 20%
    "val_ratio": 0.20,                    # trong development: train 80% / validation 20% (tầng 1)
    "cv_first_train_frac": 0.50,          # [CHỐT] fold đầu dùng 50% development
    "es_frac": 0.15,                      # [CHỐT] early stopping XGB: 15% cuối phần train (CV, tầng 3, refit)
    "es_rounds": 50,                      # [TỰ QUYẾT] số vòng chờ của early stopping
    "max_lag": 30, "max_window": 30,      # trần p, w (mục 7.1) -> mọi cấu hình dùng chung dòng bắt đầu
    # ARIMA (mục 6.1)
    "arima_max_p": 4, "arima_max_q": 4, "arima_trend": "n", "arima_top": 3,
    # GA (mục 7.2) [CHỐT]
    "ga_tournament_k": 3, "ga_p_crossover": 0.9, "ga_p_mutation": 0.15, "ga_sigma": 0.1,
    "ga_elitism": 2, "ga_patience": 5,
    # SA (mục 7.3) [CHỐT]
    "sa_accept0": 0.8, "sa_cooling": 0.9, "sa_sigma": 0.1, "sa_t_min_ratio": 1e-3, "sa_patience": 100,
    # Chọn cấu hình cuối (mục 7.4) [CHỐT]
    "config_tie_tolerance": 0.005,
    # Cảnh báo Tăng / Giảm / Ổn định (Hình 3.3): |%Δ dự báo| < alert_watch_pct -> Ổn định. Bài để người dùng tự đặt
    # ngưỡng; mặc định 0,10% là [WEB]. alert_strong_pct không còn dùng (giữ để tương thích cột NguongManh trong SQL Server).
    "alert_watch_pct": 0.10, "alert_strong_pct": 0.30,
    # Vòng phản hồi (mục 3.3.5, 5.2.2): cửa sổ cuốn chiếu, hệ số và số phiên liên tiếp là [WEB] – bài không nêu con số
    "monitor_window": 20, "monitor_factor": 1.25, "monitor_consecutive": 5,
    # Chạy
    "n_jobs": -1,
    "seed_start": 1,                      # seed 1..N như bài
}


def build_run_config(mode="chay_thu", models=None, variants=None, **overrides):
    """Trả về dict run_config đầy đủ: {"mode", "models", "variants", ...tham số}. Kiểm tra hợp lệ."""
    if mode not in MODES:
        raise ValueError(f"Chế độ không hợp lệ: {mode}")
    models = [m for m in MODELS if m in (models or MODELS)]
    if not models:
        raise ValueError("Phải chọn ít nhất 1 thuật toán.")
    variants = [v for v in VARIANTS if v in (variants or VARIANTS)]
    if any(m in ML_MODELS for m in models) and not variants:
        raise ValueError("Phải chọn ít nhất 1 cách cấu hình siêu tham số cho ANN/RF/XGBoost.")
    cfg = {"mode": mode, "models": models, "variants": variants, **deepcopy(COMMON), **deepcopy(MODES[mode])}
    for k, v in overrides.items():
        if k not in cfg:
            raise KeyError(f"Tham số không tồn tại: {k}")
        cfg[k] = v
    return cfg


def normalize(run_config):
    """Nhận dict tối thiểu {"mode","models","variants"} (như mục 11) và bổ sung đủ tham số."""
    if "budget" in run_config:
        return run_config
    extra = {k: v for k, v in run_config.items() if k not in ("mode", "models", "variants")}
    return build_run_config(run_config.get("mode", "chay_thu"), run_config.get("models"),
                            run_config.get("variants"), **extra)


def is_default_scope(cfg):
    return cfg["models"] == MODELS and cfg["variants"] == VARIANTS


def seeds(cfg, count, offset=0):
    """Seed 1..N (mục 4). offset để tách các nhóm seed phụ khi cần."""
    return [cfg["seed_start"] + offset + i for i in range(count)]


# ======================================================================== Thiết lập bài không quy định (hiển thị)

# (nhóm, nhãn, khóa trong run_config). Bài chỉ nêu tên/thành phần (Bảng 3.4, 3.6) mà không cho giá trị -> lựa chọn
# của web. Chạy đầy đủ dùng nguyên các giá trị dưới đây, không cắt giảm; Chạy thử chỉ giảm số lần lặp.
WEB_SETTINGS = [
    ("Kiểm tra chéo", "Số giai đoạn lịch sử dùng để chấm điểm mỗi cấu hình (fold)", "n_folds"),
    ("Kiểm tra chéo", "Phần dữ liệu xây dựng dùng cho giai đoạn đầu tiên", "cv_first_train_frac"),
    ("Kiểm tra chéo", "Phần dữ liệu xây dựng dùng để kiểm định (mô hình mặc định)", "val_ratio"),
    ("Kiểm tra chéo", "XGBoost dừng sớm: phần cuối dữ liệu học / số vòng chờ", ("es_frac", "es_rounds")),
    ("GA và SA", "Số cấu hình tối đa được thử mỗi lần chạy", "budget"),
    ("GA và SA", "Hai cấu hình chênh ít hơn mức này coi là ngang nhau", "config_tie_tolerance"),
    ("GA", "Kích thước quần thể N", "ga_pop_size"),
    ("GA", "Số thế hệ tối đa", "ga_max_generations"),
    ("GA", "Tournament k", "ga_tournament_k"),
    ("GA", "Xác suất lai ghép / đột biến mỗi gene", ("ga_p_crossover", "ga_p_mutation")),
    ("GA", "Độ lệch đột biến (thang [0, 1])", "ga_sigma"),
    ("GA", "Elitism (số cá thể giữ lại)", "ga_elitism"),
    ("GA", "Patience (số thế hệ không cải thiện)", "ga_patience"),
    ("SA", "Số bước thử để hiệu chỉnh T0", "sa_t0_samples"),
    ("SA", "Xác suất chấp nhận ban đầu mong muốn", "sa_accept0"),
    ("SA", "Tốc độ làm nguội (T ← α·T)", "sa_cooling"),
    ("SA", "Số nghiệm lân cận mỗi mức nhiệt", "sa_moves_per_temp"),
    ("SA", "Tmin (tỷ lệ so với T0)", "sa_t_min_ratio"),
    ("SA", "Độ lệch bước lân cận (thang [0, 1])", "sa_sigma"),
    ("SA", "Patience (số lần đánh giá không cải thiện)", "sa_patience"),
    ("Mô hình", "Tối đa epoch ANN / số cây Random Forest / số cây XGBoost",
     ("caps.ANN_epochs", "caps.RF_n_estimators", "caps.XGB_n_estimators")),
    ("Làm sạch, cảnh báo", "Điểm bất thường: nhảy quá / rồi quay về trong", ("anomaly_jump", "anomaly_revert")),
    ("Làm sạch, cảnh báo", "Ngưỡng Ổn định mặc định (% thay đổi dự báo)", "alert_watch_pct"),
    ("Làm sạch, cảnh báo", "Theo dõi sai số: số phiên gần nhất / hệ số vượt / số kỳ liên tiếp",
     ("monitor_window", "monitor_factor", "monitor_consecutive")),
]
# Thông số bài CÓ quy định (hiển thị để đối chiếu): số lần chạy độc lập
PAPER_SETTINGS = [
    ("Số lần huấn luyện mỗi mô hình cấu hình mặc định", "n_baseline_seeds"),
    ("Số lần chạy GA và SA độc lập cho mỗi mô hình", "n_hpo_runs"),
    ("Số lần đánh giá lại mỗi mô hình trên phần kiểm tra", "n_test_seeds_baseline"),
    ("Số lần huấn luyện lại để dự báo ngày tiếp theo", "n_refit_seeds"),
]


def _get(cfg, key):
    if isinstance(key, tuple):
        return " / ".join(str(_get(cfg, k)) for k in key)
    v = cfg
    for part in key.split("."):
        v = v[part]
    return v


def settings_table(rows=None):
    """[(nhóm, nhãn, giá trị Chạy thử, giá trị Chạy đầy đủ)] cho khung "Thiết lập bài không quy định"."""
    thu, du = build_run_config("chay_thu"), build_run_config("chay_day_du")
    return [(g, label, _get(thu, k), _get(du, k)) for g, label, k in (rows or WEB_SETTINGS)]


def paper_settings_table():
    thu, du = build_run_config("chay_thu"), build_run_config("chay_day_du")
    return [(label, _get(thu, k), _get(du, k)) for label, k in PAPER_SETTINGS]
