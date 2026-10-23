"""Tiến trình 12 công đoạn hiển thị cho người dùng (cách web chia nhỏ quy trình chạy)."""
import threading
import time

from .run_config import MODE_NAMES, MODEL_NAMES, ML_MODELS

STEPS = [
    (1, "Tiếp nhận dữ liệu", "Đọc file, nhận dạng cột ngày và cột tỷ giá"),
    (2, "Kiểm tra và làm sạch dữ liệu", "Chuẩn hóa ngày, sắp xếp, bỏ trùng, bỏ giá trị không hợp lệ và điểm bất thường"),
    (3, "Thống kê và kiểm tra tính dừng", "Chỉ số mô tả; kiểm định ADF và Phillips–Perron"),
    (4, "Tạo đặc trưng và chia dữ liệu", "Mức thay đổi hằng ngày, giá trị trễ, thống kê trượt; chia 80% xây dựng / 20% kiểm tra theo thời gian"),
    (5, "Mô hình so sánh ARIMA", "Thử 25 cấu trúc, chọn theo AIC, dự báo từng ngày trên phần kiểm tra"),
    (6, "Huấn luyện ANN, Random Forest, XGBoost (mặc định)", "Cấu hình mặc định, lặp nhiều lần để đo độ ổn định"),
    (7, "Tìm cấu hình bằng GA", "Thuật toán di truyền: quần thể, chọn lọc, lai ghép, đột biến"),
    (8, "Tìm cấu hình bằng SA", "Mô phỏng luyện kim: thử cấu hình lân cận, nhiệt độ giảm dần"),
    (9, "Đánh giá trên phần kiểm tra", "Chạy lại mọi mô hình nhiều lần trên 20% dữ liệu cuối"),
    (10, "Chọn mô hình", "Sai số RMSE trung bình thấp nhất trong ANN, Random Forest, XGBoost"),
    (11, "Huấn luyện lại và dự báo", "Huấn luyện lại mô hình được chọn, dự báo ngày làm việc tiếp theo"),
    (12, "Cảnh báo và lưu kết quả", "Báo Tăng / Giảm / Ổn định theo ngưỡng, lưu kết quả"),
]
DEFAULT_WEIGHTS = {1: 1, 2: 1, 3: 2, 4: 1, 5: 8, 6: 8, 7: 30, 8: 30, 9: 10, 10: 1, 11: 6, 12: 2}


class Cancelled(Exception):
    """Người dùng bấm Hủy."""


class StepError(Exception):
    def __init__(self, step, message, hint):
        super().__init__(message)
        self.step, self.hint = step, hint


def skip_reasons(cfg):
    """Bước nào nằm ngoài phạm vi đã chọn -> lý do 'Bỏ qua'."""
    ml = [m for m in cfg["models"] if m in ML_MODELS]
    v = cfg["variants"]
    out = {}
    if "ARIMA" not in cfg["models"]:
        out[5] = "Không chọn ARIMA"
    if not ml:
        for s in (6, 7, 8, 9):
            out[s] = "Không chọn ANN / Random Forest / XGBoost"
    else:
        if "Baseline" not in v:
            out[6] = "Không chọn cấu hình mặc định (vẫn chạy ở bước 9 làm mốc so sánh cho GA/SA)"
        if "GA" not in v:
            out[7] = "Không chọn GA"
        if "SA" not in v:
            out[8] = "Không chọn SA"
    n_candidates = len(ml) * len(v)                 # ARIMA không phải ứng viên được chọn (chuẩn đối chiếu)
    if n_candidates == 1:
        out[10] = "Chỉ có một ứng viên học máy – dùng luôn ứng viên đó"
    elif n_candidates == 0:
        out[10] = "Không có mô hình học máy – ARIMA chỉ để so sánh"
    return out


def scope_text(cfg):
    models = ", ".join(MODEL_NAMES[m] for m in cfg["models"])
    ml = any(m in ML_MODELS for m in cfg["models"])
    ten = {"Baseline": "mặc định", "GA": "GA", "SA": "SA"}
    return models + (f" · cấu hình: {', '.join(ten[v] for v in cfg['variants'])}" if ml else "")


class Progress:
    def __init__(self, cfg, on_progress=None, weights=None, estimate_seconds=None):
        self.cfg, self.on_progress = cfg, on_progress
        # Trọng số % theo thời gian ước tính của từng bước (khóa có thể là chuỗi nếu đi qua JSON)
        self.weights = {**DEFAULT_WEIGHTS, **{int(k): float(v) for k, v in (weights or {}).items()}}
        self.estimate_seconds = estimate_seconds
        reasons = skip_reasons(cfg)
        self.steps = [{"id": i, "name": n, "caption": c, "status": "bo_qua" if i in reasons else "cho",
                       "detail": reasons.get(i, ""), "frac": 0.0, "started": None, "seconds": None}
                      for i, n, c in STEPS]
        self.log_lines = []
        self.t0 = time.time()
        self.cancel_requested = False
        self.error = None
        self._lock = threading.Lock()
        self._emit_lock = threading.Lock()
        self._last_emit = 0.0

    # ---------------------------------------------------------------- cập nhật
    def _step(self, i):
        return self.steps[i - 1]

    def is_skipped(self, i):
        return self._step(i)["status"] == "bo_qua"

    def log(self, line):
        with self._lock:
            self.log_lines.append(f"{time.strftime('%H:%M:%S')}  {line}")
        self.emit()

    def start(self, i, detail=""):
        s = self._step(i)
        s.update(status="dang_chay", detail=detail, frac=0.0, started=time.time())
        self.log(f"[Bước {i}] {s['name']}: bắt đầu. {detail}")
        self.emit(force=True)

    def update(self, i, detail=None, frac=None):
        s = self._step(i)
        if detail is not None:
            s["detail"] = detail
        if frac is not None:
            s["frac"] = max(0.0, min(1.0, frac))
        self.emit()

    def done(self, i, detail=None):
        s = self._step(i)
        s.update(status="xong", frac=1.0, seconds=round(time.time() - (s["started"] or time.time()), 1))
        if detail is not None:
            s["detail"] = detail
        self.log(f"[Bước {i}] xong ({s['seconds']} s). {s['detail']}")
        self.emit(force=True)

    def fail(self, i, message, hint):
        s = self._step(i)
        s.update(status="loi", detail=f"{message} — Cách khắc phục: {hint}")
        self.error = {"step": i, "step_name": s["name"], "message": message, "hint": hint}
        self.log(f"[Bước {i}] LỖI: {message}")
        self.emit(force=True)

    def cancel(self):
        for s in self.steps:
            if s["status"] == "dang_chay":
                s["status"], s["detail"] = "huy", "Đã hủy theo yêu cầu"
        self.log("Đã hủy theo yêu cầu người dùng.")
        self.emit(force=True)

    def current_step(self):
        running = [s["id"] for s in self.steps if s["status"] == "dang_chay"]
        return running[0] if running else None

    # ---------------------------------------------------------------- tổng hợp
    def percent(self):
        total = sum(self.weights[s["id"]] for s in self.steps if s["status"] != "bo_qua")
        got = sum(self.weights[s["id"]] * (1.0 if s["status"] == "xong" else s["frac"])
                  for s in self.steps if s["status"] != "bo_qua")
        return 100.0 * got / total if total else 0.0

    def snapshot(self):
        elapsed = time.time() - self.t0
        pct = self.percent()
        if pct >= 3:
            eta = elapsed * (100 - pct) / pct
        elif self.estimate_seconds:
            eta = max(0.0, self.estimate_seconds - elapsed)
        else:
            eta = None
        with self._lock:
            log = list(self.log_lines[-300:])
        return {"mode": self.cfg["mode"], "mode_name": MODE_NAMES[self.cfg["mode"]], "scope": scope_text(self.cfg),
                "steps": [{k: v for k, v in s.items() if k != "started"} for s in self.steps],
                "percent": round(pct, 1), "elapsed": round(elapsed, 1), "eta": None if eta is None else round(eta),
                "log": log, "error": self.error}

    def emit(self, force=False):
        """Gửi trạng thái ra ngoài (tối đa ~2 lần/giây). on_progress trả về True nghĩa là người dùng bấm Hủy."""
        if not self.on_progress:
            return
        now = time.time()
        if not force and now - self._last_emit < 0.5:
            return
        # Luồng chính và luồng đọc tiến độ của tiến trình con cùng gọi emit: chỉ một luồng gửi mỗi lúc
        if not self._emit_lock.acquire(blocking=force):
            return
        try:
            self._last_emit = now
            if self.on_progress(self.snapshot()):
                self.cancel_requested = True
        finally:
            self._emit_lock.release()

    def check_cancel(self):
        if self.cancel_requested:
            raise Cancelled()
