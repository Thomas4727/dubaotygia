"""run_pipeline(df, run_config, on_progress): tái lập quy trình dự báo T+1 của bài NCKH.

12 công đoạn hiển thị là cách web chia nhỏ quy trình ([WEB]); KHÔNG phải 12 bước GA/SA của Bảng 3.5, 3.7.
Hai chế độ gọi CÙNG các hàm dưới đây, chỉ khác tham số lấy từ run_config.py.

Lưu tiến độ để "Chạy tiếp": mỗi đơn vị việc (1 seed huấn luyện, 1 lần chạy GA/SA, 1 seed refit) được lưu vào
<thư mục phiên>/checkpoint ngay khi xong. Chạy lại với cùng dữ liệu và cấu hình sẽ bỏ qua phần đã xong; mọi bước
tổng hợp sắp theo khóa (mô hình, lần chạy, seed) nên kết quả giống hệt khi chạy một mạch.
"""
import hashlib
import json
import os
import queue as _queue
import re
import shutil
import threading
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from joblib import Parallel, delayed, effective_n_jobs

from . import search_space as ss
from .budget import Evaluator
from .data_io import clean
from .evaluate import alert, choose, direction, h3_inputs, hypotheses, metrics, summarize, table_4_5
from .features import build_features, to_level
from .ga import run_ga
from .models import arima_forecast_after, arima_structures, arima_test_forecast, fit_predict
from .progress import Cancelled, Progress, StepError
from .report_extras import enrich
from .run_config import MODEL_NAMES, ML_MODELS, MODE_NAMES, is_default_scope, normalize, seeds
from .sa import run_sa
from .splits import expanding_folds, make_split
from .stats_tests import descriptive, stationarity

EVAL_SEED_STRIDE = 1000        # seed phụ khi đánh giá 1 cấu hình nhiều lần: seed_lần_chạy + 1000·k  [WEB]


# ======================================================================== Ngữ cảnh dùng chung (gửi sang tiến trình con)

class Context:
    def __init__(self, y, cfg):
        self.y = np.asarray(y, dtype=float)
        self.cfg = cfg
        self.split = make_split(len(self.y), cfg["test_ratio"], cfg["val_ratio"],
                                first_row=max(cfg["max_lag"], cfg["max_window"]))
        self.folds = expanding_folds(len(self.split.dev_rows), cfg["n_folds"], cfg["cv_first_train_frac"])
        self._feat = {}

    def features(self, p, w=None):
        """w = None: chỉ p giá trị trễ (ANN – công thức 3.9). w có giá trị: đủ đặc trưng (RF, XGBoost)."""
        if (p, w) not in self._feat:
            self._feat[(p, w)] = build_features(self.y, p, w)
        return self._feat[(p, w)]

    def run(self, kind, params, seed, train_rows, pred_rows, es_rows=None):
        """Huấn luyện + dự báo, trả về mức tỷ giá dự báo cho pred_rows (và mô hình)."""
        X, target, _ = self.features(params["p"], params.get("w"))
        model_params = {k: v for k, v in params.items() if k not in ("p", "w")}
        delta, model = fit_predict(kind, model_params, seed, X, target, train_rows, pred_rows, es_rows,
                                   self.cfg["es_frac"], self.cfg["es_rounds"])
        return to_level(self.y, pred_rows, delta), model

    def cv_scores(self, kind, params, seed, cancel=None):
        """RMSE trên từng cửa sổ xác thực của expanding-window CV (công thức 3.34)."""
        dev = self.split.dev_rows
        scores = []
        for tr, va in self.folds:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            pred, _ = self.run(kind, params, seed, dev[tr], dev[va])
            scores.append(float(np.sqrt(np.mean((self.y[dev[va] + 1] - pred) ** 2))))
        return scores

    def cv_objective(self, kind, params, seed, cancel=None):
        """J(ω) = (1/K) Σ_k RMSE_k(ω) trên các fold cửa sổ mở rộng của development (công thức 3.32–3.34)."""
        return float(np.mean(self.cv_scores(kind, params, seed, cancel)))


# ======================================================================== Tác vụ chạy trong tiến trình con

def _quiet():
    warnings.filterwarnings("ignore")


def _task_eval(ctx, tag, kind, params, seed, tier):
    """Tầng 1: fit trên train (XGB dừng sớm trên validation). Tầng 3: fit trên toàn bộ development."""
    _quiet()
    t0 = time.time()
    s = ctx.split
    if tier == 1:
        pred, _ = ctx.run(kind, params, seed, s.train_rows, s.test_rows, es_rows=s.val_rows if kind == "XGB" else None)
    else:
        pred, _ = ctx.run(kind, params, seed, s.dev_rows, s.test_rows)
    return tag, seed, pred, time.time() - t0


def _task_hpo(ctx, kind, algo, run_idx, seed, chan, cancel):
    """Một lần chạy độc lập của GA hoặc SA (vòng ngoài), vòng trong là huấn luyện mô hình trên các fold."""
    _quiet()
    cfg, caps = ctx.cfg, ctx.cfg["caps"]
    t0 = time.time()
    rng = np.random.default_rng(seed)
    state = {"gen": 0, "T": None}
    fold_scores = {}                     # khóa cấu hình -> RMSE từng fold (để đo độ ổn định qua các lần đánh giá)

    def send(**kw):
        if chan is not None:
            chan.put({"algo": algo, "model": kind, "run": run_idx, **kw})

    class _Evaluator(Evaluator):
        """Báo tiến độ sau MỖI lần đánh giá (thế hệ / nhiệt độ hiện tại, J tốt nhất)."""
        def __call__(self, vector):
            j = super().__call__(vector)
            send(evals=self.n_evals, best=self.best_j, gen=state["gen"], T=state["T"])
            return j

    def objective(v):
        params = ss.decode(kind, v, caps)
        sc = ctx.cv_scores(kind, params, seed, cancel)
        fold_scores[ss.params_key(params)] = sc
        return float(np.mean(sc))

    evaluator = _Evaluator(objective, cfg["budget"], key_fn=lambda v: ss.params_key(ss.decode(kind, v, caps)))
    common = dict(evaluator=evaluator, dim=ss.dim(kind, caps), categorical=ss.categorical_mask(kind, caps), rng=rng,
                  init_vector=ss.encode(kind, ss.baseline(kind), caps))
    send(evals=0, best=float("nan"), gen=0, T=None)

    if algo == "GA":
        def on_gen(g, b, n):
            state["gen"] = min(g + 1, cfg["ga_max_generations"])    # thế hệ tiếp theo đang được tạo
        res = run_ga(**common, pop_size=cfg["ga_pop_size"], max_generations=cfg["ga_max_generations"],
                     tournament_k=cfg["ga_tournament_k"], p_crossover=cfg["ga_p_crossover"],
                     p_mutation=cfg["ga_p_mutation"], sigma=cfg["ga_sigma"], elitism=cfg["ga_elitism"],
                     patience=cfg["ga_patience"], on_generation=on_gen)
    else:
        def on_step(n, T, b):
            state["T"] = T
        res = run_sa(**common, t0_samples=cfg["sa_t0_samples"], accept0=cfg["sa_accept0"], cooling=cfg["sa_cooling"],
                     moves_per_temp=cfg["sa_moves_per_temp"], sigma=cfg["sa_sigma"],
                     t_min_ratio=cfg["sa_t_min_ratio"], patience=cfg["sa_patience"], on_step=on_step)
    send(done=True, best=res["best_j"], evals=res["n_evals"])
    best_params = ss.decode(kind, res["best_vector"], caps)
    # Thông tin để kiểm tra GA và SA dùng cùng không gian, cùng J, cùng fold, cùng ngân sách (mục 3.3.5)
    parity = {"space": [p.name for p in ss.space(kind, caps)], "budget": cfg["budget"],
              "folds": [[int(tr[0]), int(tr[-1]), int(va[0]), int(va[-1])] for tr, va in ctx.folds],
              "objective": "J = mean RMSE over K expanding-window validation folds (3.33, 3.34)"}
    return {"model": kind, "algo": algo, "run": run_idx, "seed": seed, "parity": parity,
            "params": best_params, "J": res["best_j"], "fold_rmse": fold_scores.get(ss.params_key(best_params)),
            "n_evals": res["n_evals"], "n_trained": evaluator.n_trained, "stop_reason": res["stop_reason"],
            "generations": res.get("generations"), "T0": res.get("T0"), "T_final": res.get("T_final"),
            "history": evaluator.history, "seconds": round(time.time() - t0, 1)}


def _task_refit(ctx, key, kind, params, seed, keep_model=True):
    """Huấn luyện lại trên TOÀN BỘ TẬP PHÁT TRIỂN (mục 3.3.5 của bài), rồi dự báo ngày làm việc kế tiếp từ đặc trưng
    của ngày quan sát cuối cùng (đặc trưng chỉ dùng dữ liệu đến hết ngày đó)."""
    _quiet()
    last = np.array([len(ctx.y) - 1])
    pred, model = ctx.run(kind, params, seed, ctx.split.dev_rows, last)
    return key, seed, float(pred[0]), model if keep_model else None     # chỉ giữ mô hình của ứng viên được chọn


def _unit(key, fn, args):
    """Một đơn vị việc: trả về (khóa, kết quả) để lưu tiến độ."""
    return key, fn(*args)


# ======================================================================== Lưu tiến độ ("Chạy tiếp")

class _Store:
    """Kết quả từng đơn vị việc. Có thư mục: lưu ra đĩa ngay khi xong (ghi tệp tạm rồi đổi tên). Không có: chỉ trong bộ nhớ."""

    def __init__(self, folder, fingerprint):
        self.folder = Path(folder) if folder else None
        self.mem = {}
        self.reused = 0
        if self.folder is not None:
            stamp = self.folder / "fingerprint.txt"
            if self.folder.exists() and (not stamp.exists() or stamp.read_text(encoding="utf-8") != fingerprint):
                shutil.rmtree(self.folder)            # dữ liệu hoặc cấu hình khác -> không dùng lại tiến độ cũ
            self.folder.mkdir(parents=True, exist_ok=True)
            stamp.write_text(fingerprint, encoding="utf-8")

    def _path(self, key):
        return self.folder / (re.sub(r"[^A-Za-z0-9_.-]", "_", key) + ".joblib")

    def has(self, key):
        return key in self.mem or (self.folder is not None and self._path(key).exists())

    def get(self, key):
        if key not in self.mem:
            import joblib
            self.mem[key] = joblib.load(self._path(key))
        return self.mem[key]

    def put(self, key, value):
        self.mem[key] = value
        if self.folder is not None:
            import joblib
            tmp = self._path(key).with_suffix(".tmp")
            joblib.dump(value, tmp)
            os.replace(tmp, self._path(key))


def _fingerprint(y, cfg):
    keep = {k: v for k, v in cfg.items() if k not in ("n_jobs",)}
    h = hashlib.sha256(np.asarray(y, dtype=float).tobytes())
    h.update(json.dumps(keep, sort_keys=True, default=str).encode())
    return h.hexdigest()


def _run_units(par, store, units, on_result):
    """units: list (khóa, hàm, tham số). Đơn vị đã có trong store không chạy lại. on_result(khóa, kết quả, i, n, từ_trước)."""
    n, i = len(units), 0
    for key, _, _ in units:
        if store.has(key):
            i += 1
            store.reused += 1
            on_result(key, store.get(key), i, n, True)
    pending = [u for u in units if not store.has(u[0])]
    if pending:
        for key, val in par(delayed(_unit)(k, f, a) for k, f, a in pending):
            store.put(key, val)
            i += 1
            on_result(key, val, i, n, False)


# ======================================================================== Tiện ích

def _next_business_day(last):
    day = pd.Timestamp(last).normalize() + pd.Timedelta(days=1)
    while day.weekday() >= 5:
        day += pd.Timedelta(days=1)
    return day


def _clean_params(p):
    return {k: (v.item() if isinstance(v, np.generic) else v) for k, v in p.items()}


def _label(model, variant=None):
    return MODEL_NAMES[model] if not variant else f"{MODEL_NAMES[model]} – {variant}"


class _Channel:
    """Kênh tiến độ từ tiến trình con về + cờ hủy. Dùng Manager khi chạy song song nhiều tiến trình."""

    def __init__(self, n_jobs):
        if n_jobs == 1:
            self.manager, self.queue, self.cancel = None, _queue.Queue(), threading.Event()
        else:
            import multiprocessing as mp
            self.manager = mp.Manager()
            self.queue, self.cancel = self.manager.Queue(), self.manager.Event()

    def close(self):
        if self.manager is not None:
            self.manager.shutdown()


def hpo_parity(hpo_runs, need_hpo):
    """Kiểm tra tự động cho mỗi phiên (mục 3.3.5): với mỗi mô hình chạy cả GA và SA, hai thuật toán có cùng không gian
    tìm kiếm, cùng hàm mục tiêu J, cùng các fold xác thực và cùng ngân sách đánh giá hay không."""
    out = []
    for m in sorted({m for m, _ in need_hpo}):
        runs = {a: [r for r in hpo_runs if r["model"] == m and r["algo"] == a] for a in ("GA", "SA")}
        if not runs["GA"] or not runs["SA"]:
            out.append({"model": m, "applicable": False, "ok": None,
                        "note": "Chỉ chạy một trong hai thuật toán – không cần đối chiếu"})
            continue
        p = {a: [r["parity"] for r in rs] for a, rs in runs.items()}
        checks = {k: all(x[k] == p["GA"][0][k] for a in ("GA", "SA") for x in p[a])
                  for k in ("space", "objective", "folds", "budget")}
        out.append({"model": m, "applicable": True, "ok": all(checks.values()), "checks": checks,
                    "space": p["GA"][0]["space"], "budget": p["GA"][0]["budget"], "n_folds": len(p["GA"][0]["folds"]),
                    "evals_used": {a: [r["n_evals"] for r in rs] for a, rs in runs.items()}})
    return out


def final_config(runs, tie_tolerance):
    """Cấu hình cuối của (mô hình × GA/SA) qua các lần chạy độc lập. Bài (mục 3.3.4.1): "cấu hình có RMSE thấp nhất
    trong đa số lần chạy và có hiệu quả tốt và ổn định qua nhiều lần đánh giá" – bài không cho công thức.
    [WEB – cách hiểu] J (RMSE trung bình CV) thấp nhất; các cấu hình chênh < tie_tolerance coi là ngang nhau, khi đó chọn
    cấu hình có RMSE ổn định nhất qua các cửa sổ xác thực (SD nhỏ nhất). Chỉ dùng dữ liệu trước tập kiểm tra, vì tập
    kiểm tra phải tách biệt hoàn toàn khỏi quá trình xây dựng và lựa chọn mô hình (mục 3.3.5)."""
    j_min = min(r["J"] for r in runs)
    tied = [r for r in runs if r["J"] <= j_min * (1 + tie_tolerance)]
    sd = lambda r: float(np.std(r["fold_rmse"], ddof=1)) if r.get("fold_rmse") and len(r["fold_rmse"]) > 1 else 0.0
    return min(tied, key=lambda r: (sd(r), r["J"], r["run"]))


def _parallel(cfg):
    return Parallel(n_jobs=cfg["n_jobs"], return_as="generator_unordered")


# ======================================================================== Hàm chính

def run_pipeline(df, run_config, on_progress=None, output_dir=None, meta=None, estimate=None, checkpoint_dir=None):
    """df: DataFrame (date, rate) hoặc (Ngay, GiaTri). run_config: {"mode","models","variants"}.

    on_progress(snapshot) được gọi khi tiến độ thay đổi; trả về True để yêu cầu hủy.
    checkpoint_dir: thư mục lưu tiến độ (mặc định <output_dir>/checkpoint nếu có output_dir).
    Trả về dict kết quả (các Bảng 4.1–4.6, hình, so sánh với thực tế, kết luận H1–H3).
    """
    cfg = normalize(run_config)
    meta = meta or {}
    weights = (estimate or {}).get("weights")
    prog = Progress(cfg, on_progress, weights=weights, estimate_seconds=(estimate or {}).get("total_seconds"))
    ml = [m for m in cfg["models"] if m in ML_MODELS]
    V = cfg["variants"]
    need_hpo = [(m, a) for m in ml for a in ("GA", "SA") if a in V]
    t_start = time.time()
    step = 1
    chan = None
    result = {}
    if checkpoint_dir is None and output_dir is not None:
        checkpoint_dir = Path(output_dir) / "checkpoint"
    try:
        # ------------------------------------------------------------ 1. Tiếp nhận dữ liệu
        prog.start(1, f"{meta.get('filename', 'dữ liệu')}: {len(df)} dòng đọc được")
        df = df.rename(columns={"Ngay": "date", "GiaTri": "rate"})[["date", "rate"]].copy()
        cols = (f" · cột ngày '{meta['date_column']}', cột tỷ giá '{meta['rate_column']}'"
                if meta.get("date_column") else " · đã nhận dạng cột ngày và tỷ giá khi tải lên")
        prog.done(1, f"{meta.get('filename', 'dữ liệu')}: {len(df)} dòng đọc được{cols}")

        # ------------------------------------------------------------ 2. Làm sạch
        step = 2
        prog.start(2)
        df, clean_log, clean_stats = clean(df, cfg)
        prog.done(2, f"Còn {clean_stats['rows_out']} dòng, loại {clean_stats['rows_removed']} "
                     f"(dị thường {clean_stats['anomalies']}); {clean_stats['missing_business_days']} ngày làm việc trống")
        y = df["rate"].to_numpy(dtype=float)
        dates = pd.DatetimeIndex(df["date"])
        store = _Store(checkpoint_dir, _fingerprint(y, cfg))

        # ------------------------------------------------------------ 3. Thống kê mô tả + tính dừng
        step = 3
        prog.start(3, "Chỉ số mô tả, kiểm định ADF và Phillips–Perron cho tỷ giá và mức thay đổi")
        t41 = descriptive(df)
        t42, t42_conclusion = stationarity(y)
        prog.done(3, t42_conclusion["text"])

        # ------------------------------------------------------------ 4. Đặc trưng + chia dữ liệu
        step = 4
        prog.start(4)
        ctx = Context(y, cfg)
        s = ctx.split
        d_ = lambda i: f"{dates[i]:%d/%m/%Y}"
        split_info = {
            "n_obs": s.n_obs, "n_dev": s.n_dev, "n_train_obs": s.n_train, "n_test": s.n_obs - s.n_dev,
            "train_samples": len(s.train_rows), "val_samples": len(s.val_rows), "test_samples": len(s.test_rows),
            "dev_samples": len(s.dev_rows), "first_row": s.first_row,
            "dev_start": d_(0), "dev_end": d_(s.n_dev - 1), "train_end": d_(s.n_train - 1),
            "val_start": d_(s.n_train), "test_start": d_(s.n_dev), "test_end": d_(s.n_obs - 1),
            "folds": [{"train": len(tr), "val": len(va)} for tr, va in ctx.folds],
        }
        prog.done(4, f"train {len(s.train_rows)} · validation {len(s.val_rows)} · test {len(s.test_rows)} mẫu; "
                     f"cắt test từ {split_info['test_start']}; CV {cfg['n_folds']} fold")
        test_targets = s.test_rows + 1
        actual = y[test_targets]
        test_dates = [f"{dates[i]:%Y-%m-%d}" for i in test_targets]
        rw_pred = y[s.test_rows]                            # Random walk: ŷ_{t+1} = y_t
        latest = float(y[-1])
        next_day = _next_business_day(dates[-1])

        candidates = {}
        t43, arima_fig, arima_t1 = [], None, None

        # ------------------------------------------------------------ 5. ARIMA (chuẩn đối chiếu)
        step = 5
        if "ARIMA" in cfg["models"]:
            prog.start(5, "Cấu trúc 0/25")
            if store.has("arima"):
                a = store.get("arima")
                store.reused += 1
            else:
                t_arima = time.time()
                structs = arima_structures(y[:s.n_dev], t42_conclusion["d"], cfg["arima_max_p"], cfg["arima_max_q"],
                                           cfg["arima_trend"],
                                           on_step=lambda i, n, o: prog.update(5, f"Cấu trúc đang thử {i}/{n}: ARIMA{o}", 0.6 * i / n))
                ok = [r for r in structs if "error" not in r]
                if not ok:
                    raise StepError(5, "Không ước lượng được cấu trúc ARIMA nào.", "Kiểm tra dữ liệu có đủ dài và không có giá trị bất thường.")
                best = ok[0]
                prog.update(5, f"Chọn ARIMA{best['order']} (AIC {best['aic']:.2f}); dự báo tập test...", 0.6)
                a_pred, a_lo, a_hi = arima_test_forecast(best["result"], y, s.n_dev,
                                                         on_step=lambda k, n: prog.update(5, None, 0.6 + 0.4 * k / n))
                # T+1: tham số ước lượng trên development, cập nhật quan sát thật đến ngày cuối (refit=False)
                a = {"t43": [{"order": list(r["order"]), "trend": r["trend"], "nobs": r["nobs"],
                              "dev_start": split_info["dev_start"], "dev_end": split_info["dev_end"],
                              "llf": r["llf"], "aic": r["aic"], "bic": r["bic"], "hqic": r["hqic"]}
                             for r in ok[:cfg["arima_top"]]],
                     "order": list(best["order"]), "pred": a_pred, "lo": a_lo, "hi": a_hi,
                     "t1": arima_forecast_after(best["result"], y[s.n_dev:]), "seconds": round(time.time() - t_arima, 1)}
                store.put("arima", a)
            t43 = a["t43"]
            arima_fig = {"dates": test_dates, "actual": actual.tolist(), "pred": np.asarray(a["pred"]).tolist(),
                         "lo": np.asarray(a["lo"]).tolist(), "hi": np.asarray(a["hi"]).tolist(), "order": a["order"]}
            m = metrics(actual, a["pred"])
            # ARIMA là CHUẨN ĐỐI CHIẾU (mục 3.3.5): hiển thị trong bảng xếp hạng nhưng không bao giờ được chọn
            candidates["ARIMA"] = {"model": "ARIMA", "variant": None, "label": f"ARIMA{tuple(a['order'])}",
                                   "summary": {**m, "SD_RMSE": 0.0, "CV_RMSE": 0.0, "n_runs": cfg["n_baseline_seeds"]},
                                   "pred": np.asarray(a["pred"]).tolist(),
                                   "params": {"order": a["order"], "trend": cfg["arima_trend"]},
                                   "in_selection": False, "benchmark": True, "cost_seconds": a["seconds"]}
            arima_t1 = a["t1"]
            prog.done(5, f"Chọn ARIMA{tuple(a['order'])}, trend='n'; RMSE test {m['RMSE']:.3f}")

        par = _parallel(cfg)
        reuse_txt = lambda cached: " – lấy từ lần chạy trước" if cached else ""

        # ------------------------------------------------------------ 6. Baseline tầng 1 (Bảng 4.4)
        step = 6
        tier1, tier1_pred = {}, {}
        if not prog.is_skipped(6):
            prog.start(6)
            per1 = {m: {} for m in ml}
            units = [(f"t1|{m}|{sd}", _task_eval, (ctx, m, m, ss.baseline(m), sd, 1))
                     for m in ml for sd in seeds(cfg, cfg["n_baseline_seeds"])]

            def got1(key, val, i, n, cached):
                m, sd, pred, _ = val
                per1[m][sd] = pred
                prog.update(6, f"{MODEL_NAMES[m]} · seed {sd} xong ({i}/{n} lần chạy, {cfg['n_baseline_seeds']} seed mỗi mô hình)"
                               f"{reuse_txt(cached)}", i / n)
                prog.check_cancel()
            _run_units(par, store, units, got1)
            for m in ml:
                preds = [per1[m][sd] for sd in sorted(per1[m])]
                tier1[m] = summarize([metrics(actual, p) for p in preds])
                tier1_pred[m] = np.mean(preds, axis=0)
            prog.done(6, " · ".join(f"{MODEL_NAMES[m]} RMSE {tier1[m]['RMSE']:.3f}" for m in ml))

        # ------------------------------------------------------------ 7–8. GA và SA (tầng 2)
        step = 7
        hpo_by_key = {}
        if need_hpo:
            chan = _Channel(cfg["n_jobs"])
            run_seeds = seeds(cfg, cfg["n_hpo_runs"])
            tasks = [(m, a, i + 1, sd) for m, a in need_hpo for i, sd in enumerate(run_seeds)]
            for a in ("GA", "SA"):
                if any(t[1] == a for t in tasks):
                    prog.start(7 if a == "GA" else 8, "Khởi động...")
            live = {}
            total = {a: sum(1 for t in tasks if t[1] == a) for a in ("GA", "SA")}
            stop_drain = threading.Event()

            def describe(a):
                parts = []
                for (aa, m, r), msg in sorted(live.items()):
                    if aa != a or (msg.get("done") and len(live) > 3):
                        continue
                    best = msg.get("best")
                    best_txt = f"RMSE tốt nhất {best:.3f}" if best is not None and best == best else "đang đánh giá P₀"
                    head = f"{MODEL_NAMES[m]} lần chạy {r}/{cfg['n_hpo_runs']}"
                    if msg.get("done"):
                        parts.append(f"{head} · xong · {best_txt}{reuse_txt(msg.get('cached'))}")
                    elif a == "GA":
                        parts.append(f"{head} · thế hệ {msg.get('gen', 0)}/{cfg['ga_max_generations']} · "
                                     f"đánh giá {msg.get('evals', 0)}/{cfg['budget']} · {best_txt}")
                    else:
                        T = msg.get("T")
                        t_txt = f" · nhiệt độ T = {T:.4g}" if T is not None else " · đang hiệu chỉnh T0"
                        parts.append(f"{head} · đánh giá {msg.get('evals', 0)}/{cfg['budget']}{t_txt} · {best_txt}")
                return " | ".join(parts[-6:])

            def frac(a):
                return sum(min(1.0, v.get("evals", 0) / cfg["budget"]) if not v.get("done") else 1.0
                           for (aa, _, _), v in live.items() if aa == a) / max(1, total[a])

            def drain():
                while not stop_drain.is_set():
                    try:
                        msg = chan.queue.get(timeout=0.3)
                    except Exception:
                        msg = None
                    if prog.cancel_requested:
                        chan.cancel.set()
                    if msg is None:
                        continue
                    key = (msg["algo"], msg["model"], msg["run"])
                    live[key] = {**live.get(key, {}), **msg}
                    a = msg["algo"]
                    prog.update(7 if a == "GA" else 8, describe(a), frac(a))

            def gothpo(key, res, i, n, cached):
                hpo_by_key[(res["model"], res["algo"], res["run"])] = res
                live[(res["algo"], res["model"], res["run"])] = {"done": True, "best": res["J"], "evals": res["n_evals"],
                                                                  "cached": cached}
                a = res["algo"]
                prog.log(f"{a} · {MODEL_NAMES[res['model']]} lần chạy {res['run']}: J = {res['J']:.4f} "
                         f"({res['n_evals']} đánh giá, {res['stop_reason']}, {res['seconds']} s){reuse_txt(cached)}")
                prog.update(7 if a == "GA" else 8, describe(a), frac(a))
                if sum(1 for k in hpo_by_key if k[1] == a) == total[a]:
                    best = {m: min(r["J"] for k, r in hpo_by_key.items() if k[0] == m and k[1] == a)
                            for m in ml if (m, a) in need_hpo}
                    prog.done(7 if a == "GA" else 8, " · ".join(f"{MODEL_NAMES[m]} J tốt nhất {j:.3f}" for m, j in best.items()))
                prog.check_cancel()

            drainer = threading.Thread(target=drain, daemon=True)
            drainer.start()
            try:
                _run_units(par, store, [(f"hpo|{m}|{a}|{r}", _task_hpo, (ctx, m, a, r, sd, chan.queue, chan.cancel))
                                        for m, a, r, sd in tasks], gothpo)
            finally:
                stop_drain.set()
                drainer.join(timeout=2)
        hpo_runs = [hpo_by_key[k] for k in sorted(hpo_by_key)]           # thứ tự cố định: mô hình, thuật toán, lần chạy

        # ------------------------------------------------------------ 9. Đánh giá trên tập kiểm tra (tầng 3, Bảng 4.5)
        step = 9
        tier3_base, tier3_hpo, final_cfg, cand_eval, cost = {}, {}, {}, {}, {}
        if ml:
            prog.start(9)
            # 9a. Bảng 4.5: "Before" = cấu hình định sẵn × n seed; "After" = mỗi lần chạy GA/SA × n_eval_seeds_per_config
            units = [(f"t3|{m}|Baseline|0|{sd}", _task_eval, (ctx, (m, "Baseline", 0), m, ss.baseline(m), sd, 3))
                     for m in ml for sd in seeds(cfg, cfg["n_test_seeds_baseline"])]
            units += [(f"t3|{r['model']}|{r['algo']}|{r['run']}|{r['seed'] + EVAL_SEED_STRIDE * k}", _task_eval,
                       (ctx, (r["model"], r["algo"], r["run"]), r["model"], r["params"], r["seed"] + EVAL_SEED_STRIDE * k, 3))
                      for r in hpo_runs for k in range(cfg["n_eval_seeds_per_config"])]
            per3 = {}

            def got3(key, val, i, n, cached):
                tag, sd, pred, sec = val
                per3.setdefault(tuple(tag), {})[sd] = (pred, sec)
                prog.update(9, f"Trước/sau tối ưu · {MODEL_NAMES[tag[0]]} – {tag[1]}{f' (lần chạy {tag[2]})' if tag[2] else ''} · "
                               f"seed {sd} ({i}/{n} lượt){reuse_txt(cached)}", 0.7 * i / n)
                prog.check_cancel()
            _run_units(par, store, units, got3)
            for m in ml:
                runs = per3[(m, "Baseline", 0)]
                tier3_base[m] = summarize([metrics(actual, runs[sd][0]) for sd in sorted(runs)])
                final_cfg[(m, "Baseline")] = ss.baseline(m)
                cost[(m, "Baseline")] = sum(v[1] for v in runs.values())
            for m, a in need_hpo:
                rs = [r for r in hpo_runs if r["model"] == m and r["algo"] == a]
                evals = [per3[(m, a, r["run"])][sd][0] for r in rs for sd in sorted(per3[(m, a, r["run"])])]
                tier3_hpo[(m, a)] = summarize([metrics(actual, p) for p in evals])
                chosen_run = final_config(rs, cfg["config_tie_tolerance"])
                final_cfg[(m, a)] = chosen_run["params"]
                tier3_hpo[(m, a)]["final_run"] = chosen_run["run"]
                tier3_hpo[(m, a)]["final_J"] = chosen_run["J"]
                cost[(m, a)] = sum(r["seconds"] for r in rs)

            # 9b. Đánh giá lặp lại các ứng viên trên tập kiểm tra (mục 4.5): cấu hình cuối của GA/SA × n seed
            units = [(f"cand|{m}|{a}|{sd}", _task_eval, (ctx, (m, a), m, final_cfg[(m, a)], sd, 3))
                     for m, a in need_hpo for sd in seeds(cfg, cfg["n_test_seeds_baseline"])]
            perc = {}

            def gotc(key, val, i, n, cached):
                tag, sd, pred, sec = val
                perc.setdefault(tuple(tag), {})[sd] = (pred, sec)
                prog.update(9, f"Đánh giá lại {MODEL_NAMES[tag[0]]} – {tag[1]} (cấu hình tốt nhất) · lần {sd} "
                               f"({i}/{n} lượt){reuse_txt(cached)}", 0.7 + 0.3 * i / n)
                prog.check_cancel()
            _run_units(par, store, units, gotc)
            for m in ml:
                runs = per3[(m, "Baseline", 0)]
                cand_eval[(m, "Baseline")] = (tier3_base[m], np.mean([runs[sd][0] for sd in sorted(runs)], axis=0))
            for m, a in need_hpo:
                runs = perc[(m, a)]
                preds = [runs[sd][0] for sd in sorted(runs)]
                cand_eval[(m, a)] = (summarize([metrics(actual, p) for p in preds]), np.mean(preds, axis=0))
                cost[(m, a)] += sum(v[1] for v in runs.values())
            prog.done(9, " · ".join(f"{m}-{a} RMSE {cand_eval[(m, a)][0]['RMSE']:.3f}" for m, a in need_hpo)
                      or " · ".join(f"{m} Baseline RMSE {tier3_base[m]['RMSE']:.3f}" for m in ml))
        else:
            prog.update(9, "Chỉ chọn ARIMA – ARIMA đã được đánh giá trên test ở bước 5")

        # Tập ứng viên được chọn (mục 3.3.5, 4.5): CHỈ ANN, RF, XGBoost × Baseline/GA/SA
        for m in ml:
            for v in V:
                summ, pred = cand_eval[(m, v)]
                candidates[f"{m}|{v}"] = {"model": m, "variant": v, "label": _label(m, v), "summary": summ,
                                          "pred": np.asarray(pred).tolist(), "params": _clean_params(final_cfg[(m, v)]),
                                          "in_selection": True, "benchmark": False, "cost_seconds": round(cost[(m, v)], 1)}

        # ------------------------------------------------------------ 10. Chọn mô hình
        step = 10
        selectable = {k: c["summary"] for k, c in candidates.items() if c["in_selection"]}
        if not prog.is_skipped(10):
            prog.start(10)
        chosen_key = choose(selectable)
        ranking = sorted(candidates, key=lambda k: (candidates[k]["summary"]["RMSE"], k))   # hiển thị, gồm ARIMA đối chiếu
        selection = [{"key": k, "label": candidates[k]["label"], "RMSE": selectable[k]["RMSE"], "SD_RMSE": selectable[k]["SD_RMSE"],
                      "CV_RMSE": selectable[k]["CV_RMSE"], "n_runs": selectable[k]["n_runs"],
                      "cost_seconds": candidates[k]["cost_seconds"]}
                     for k in sorted(selectable, key=lambda k: (selectable[k]["RMSE"], k))]
        if not prog.is_skipped(10):
            prog.done(10, "Xếp hạng (chỉ ANN/RF/XGBoost): " + " < ".join(f"{r['label']} ({r['RMSE']:.3f})" for r in selection[:5]))
        elif chosen_key is not None:
            prog.update(10, f"Chỉ có một mô hình học máy – dùng luôn {candidates[chosen_key]['label']}")
        else:
            prog.update(10, "Không có mô hình học máy – ARIMA chỉ để so sánh nên không có dự báo chính")

        # ------------------------------------------------------------ 11. Huấn luyện lại trên tập phát triển + dự báo T+1
        step = 11
        prog.start(11)
        forecasts, models_by_key = {}, {}
        if arima_t1 is not None:
            forecasts["ARIMA"] = {sd: arima_t1[0] for sd in seeds(cfg, cfg["n_refit_seeds"])}   # ARIMA xác định
            candidates["ARIMA"]["pi95"] = [arima_t1[1], arima_t1[2]]

        def gotr(key, val, i, n, cached):
            k, sd, f, model = val
            forecasts.setdefault(k, {})[sd] = f
            models_by_key.setdefault(k, {})[sd] = model
            prog.update(11, f"{candidates[k]['label']} · seed {sd} ({i}/{n}); dự báo tạm {f:,.2f}{reuse_txt(cached)}", i / max(1, n))
            prog.check_cancel()
        _run_units(par, store, [(f"refit|{k}|{sd}", _task_refit,
                                 (ctx, k, c["model"], final_cfg[(c["model"], c["variant"])], sd, k == chosen_key))
                                for k, c in candidates.items() if c["model"] in ML_MODELS
                                for sd in seeds(cfg, cfg["n_refit_seeds"])], gotr)
        for k, by_seed in forecasts.items():
            vals = np.array([by_seed[sd] for sd in sorted(by_seed)])
            chg = (vals - latest) / latest * 100
            candidates[k]["t1"] = {
                "date": f"{next_day:%Y-%m-%d}", "mean": float(vals.mean()),
                "sd": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
                "p05": float(np.quantile(vals, 0.05)), "p95": float(np.quantile(vals, 0.95)),
                "change_pct_mean": float(chg.mean()), "change_abs_mean": float(vals.mean() - latest), "n_seeds": len(vals),
                "direction": direction(float(vals.mean() - latest)),
                "alert": alert(float(chg.mean()), cfg["alert_watch_pct"]),
                "trained_on": "development",
            }
        chosen_models = [models_by_key[chosen_key][sd] for sd in sorted(models_by_key[chosen_key])] if chosen_key else []
        prog.done(11, (f"{candidates[chosen_key]['label']}: dự báo {next_day:%d/%m/%Y} = {candidates[chosen_key]['t1']['mean']:,.2f}"
                       if chosen_key else "Đã dự báo T+1 cho ARIMA (đối chiếu); không có mô hình chính"))

        # ------------------------------------------------------------ 12. Cảnh báo + xuất báo cáo
        step = 12
        prog.start(12)
        ch = candidates[chosen_key] if chosen_key else None
        t46, outputs_335 = None, None
        if ch:
            # Bảng 4.6: đúng 16 trường như bài
            t46 = {
                "Latest_Observed_Date": f"{dates[-1]:%Y-%m-%d}", "Latest_Observed_Rate": latest,
                "Chosen_Model": MODEL_NAMES[ch["model"]], "Chosen_Variant": ch["variant"] or "—",
                "Chosen_Selection_Basis": (f"Minimum Mean RMSE across {ch['summary']['n_runs']} repeated Test runs"
                                           if len(selectable) > 1 else "Only one machine-learning candidate in the selected scope"),
                "Chosen_Mean_RMSE": ch["summary"]["RMSE"], "Chosen_SD_RMSE": ch["summary"]["SD_RMSE"],
                "Chosen_Mean_MAE": ch["summary"]["MAE"], "Chosen_Mean_MAPE_Percent": ch["summary"]["MAPE"],
                "Next_Forecast_Date": ch["t1"]["date"], "Next_Forecast_Rate_Mean": ch["t1"]["mean"],
                "Next_Forecast_Rate_SD": ch["t1"]["sd"], "Next_Forecast_P05": ch["t1"]["p05"],
                "Next_Forecast_P95": ch["t1"]["p95"], "Next_Forecast_Change_Percent_Mean": ch["t1"]["change_pct_mean"],
                "Management_Alert": ch["t1"]["alert"],
            }
            # Đầu ra quản lý theo mục 3.3.5 / Hình 3.3 nằm ngoài 16 trường của Bảng 4.6
            outputs_335 = {"change_abs": ch["t1"]["change_abs_mean"], "hyperparameters": ch["params"]}
        for k, c in candidates.items():
            c["chosen"] = k == chosen_key

        t44 = []
        if "ARIMA" in candidates:
            t44.append({"model": "ARIMA", **candidates["ARIMA"]["summary"]})
        for m in ml:
            if m in tier1:
                t44.append({"model": m, **tier1[m]})
        rw_metrics = metrics(actual, rw_pred)
        t45 = table_4_5(tier3_base, tier3_hpo)
        hyp = hypotheses(t44, t45, completed=True, cfg=cfg, ml_selected=ml,
                         h3=h3_inputs(candidates, chosen_key, rw_metrics, t46, report_saved=t46 is not None))
        ref = candidates.get("ARIMA", {}).get("summary")
        for c in candidates.values():
            smy = c["summary"]
            c["vs_arima_pct"] = None if ref is None else 100 * (smy["RMSE"] - ref["RMSE"]) / ref["RMSE"]
            c["vs_rw_pct"] = 100 * (smy["RMSE"] - rw_metrics["RMSE"]) / rw_metrics["RMSE"]
        # Hình 4.2 của bài: thực tế, ARIMA và ANN, RF, XGBoost (cấu hình định sẵn, dự báo trung bình các lần chạy)
        fig42 = [{"key": "ARIMA", "label": candidates["ARIMA"]["label"], "model": "ARIMA",
                  "pred": candidates["ARIMA"]["pred"]}] if "ARIMA" in candidates else []
        fig42 += [{"key": f"tier1|{m}", "label": MODEL_NAMES[m], "model": m, "pred": tier1_pred[m].tolist()} for m in tier1_pred]

        result = {
            "version": 4,
            "mode": cfg["mode"], "mode_name": MODE_NAMES[cfg["mode"]],
            "scope": {"models": cfg["models"], "variants": cfg["variants"], "default": is_default_scope(cfg)},
            "data": {"filename": meta.get("filename"), "clean_log": clean_log, "clean_stats": clean_stats, "split": split_info},
            "table_4_1": t41, "table_4_2": t42, "table_4_2_conclusion": t42_conclusion,
            "table_4_3": t43, "figure_4_1": arima_fig, "figure_4_2": fig42,
            "table_4_4": t44, "random_walk": {"model": "RW", **rw_metrics, "n_runs": 1},
            "table_4_5": t45, "table_4_6": t46, "outputs_335": outputs_335,
            "tier3_baseline": tier3_base, "hypotheses": hyp,
            "test": {"dates": test_dates, "actual": actual.tolist(), "random_walk": rw_pred.tolist()},
            "candidates": candidates, "chosen_key": chosen_key, "ranking": ranking, "selection": selection,
            "trained_on": "development", "hpo_parity": hpo_parity(hpo_runs, need_hpo),
            "hpo_runs": [{k: (_clean_params(v) if k == "params" else v) for k, v in r.items()} for r in hpo_runs],
            "settings": {k: cfg[k] for k in cfg if k not in ("models", "variants")},
            "estimate": estimate, "checkpoint_reused": store.reused,
        }
        enrich(result)                       # khoảng ±1,96×RMSE, kiểm tra ngưỡng cảnh báo trên test (bổ sung ngoài bài)
        result["elapsed_seconds"] = round(time.time() - t_start, 1)
        if output_dir is not None:
            from .outputs import save_outputs
            save_outputs(result, output_dir, chosen_models, cfg)
        prog.done(12, (f"Cảnh báo: {t46['Management_Alert']}" if t46 else "Không có mô hình học máy nên không có dự báo chính")
                  + (f" · lưu tại {output_dir}" if output_dir else ""))
        result["progress"] = prog.snapshot()
        return result
    except Cancelled:
        prog.cancel()
        raise
    except StepError as e:
        prog.fail(e.step, str(e), e.hint)
        raise
    except Exception as e:
        hints = {1: "Kiểm tra định dạng file (cột Ngày, Tỷ giá).", 2: "Kiểm tra dữ liệu còn đủ dòng sau khi làm sạch.",
                 3: "Chuỗi quá ngắn hoặc hằng số – cần thêm dữ liệu.", 4: "Cần thêm quan sát để chia train/validation/test.",
                 5: "Thử lại; nếu vẫn lỗi, chuỗi có thể quá ngắn cho ARIMA.",
                 6: "Kiểm tra thư viện torch/scikit-learn/xgboost đã cài đúng (cai_dat.bat)."}
        prog.fail(step, f"{type(e).__name__}: {e}", hints.get(step, "Bấm \"Chạy tiếp\" để chạy lại từ phần đã xong; "
                                                                     "nếu lỗi lặp lại, gửi nhật ký cho người phát triển."))
        raise
    finally:
        if chan is not None:
            chan.close()


# ======================================================================== Ước tính thời gian

def estimate(df, run_config):
    """Đo 1 lần huấn luyện mỗi mô hình trên dữ liệu thật rồi nhân với số lần cần chạy.
    Trả về {"total_seconds", "phases": {...}, "weights": {bước: trọng số}}."""
    _quiet()
    cfg = normalize(run_config)
    df = df.rename(columns={"Ngay": "date", "GiaTri": "rate"})[["date", "rate"]].copy()
    df, _, _ = clean(df, cfg)
    y = df["rate"].to_numpy(dtype=float)
    ctx = Context(y, cfg)
    s = ctx.split
    cores = max(1, effective_n_jobs(cfg["n_jobs"]))
    ml = [m for m in cfg["models"] if m in ML_MODELS]
    V = cfg["variants"]
    ph = {}
    measured = {}
    if "ARIMA" in cfg["models"]:
        from .models import _fit_arima
        t = time.time()
        res = _fit_arima(y[:s.n_dev], (1, 1, 1), "n")
        one = time.time() - t
        t = time.time()
        arima_test_forecast(res, y[:s.n_dev + 10], s.n_dev)
        per_append = (time.time() - t) / 10
        ph["arima"] = 25 * one * 1.3 + (s.n_obs - s.n_dev) * per_append
        measured["ARIMA"] = round(one, 3)
    for m in ml:
        t = time.time()
        ctx.run(m, ss.baseline(m), 1, s.train_rows, s.test_rows, es_rows=s.val_rows if m == "XGB" else None)
        measured[m] = time.time() - t
    # Hệ số quy đổi từ cấu hình baseline sang cấu hình trung bình trong không gian tìm kiếm
    caps = cfg["caps"]
    factor = {"ANN": ((50 + caps["ANN_epochs"]) / 2) / 200, "RF": ((100 + caps["RF_n_estimators"]) / 2) / 500, "XGB": 1.0}
    cv_size = 0.75
    if ml and "Baseline" in V:
        ph["tier1"] = sum(measured[m] for m in ml) * cfg["n_baseline_seeds"] / min(cores, len(ml) * cfg["n_baseline_seeds"])
    for a in ("GA", "SA"):
        if ml and a in V:
            per_task = {m: cfg["budget"] * cfg["n_folds"] * measured[m] * factor[m] * cv_size for m in ml}
            n_tasks = len(ml) * cfg["n_hpo_runs"]
            ph[a] = max(max(per_task.values()), sum(per_task.values()) * cfg["n_hpo_runs"] / min(cores, n_tasks))
    if "GA" in ph and "SA" in ph:          # GA và SA chạy đồng thời trên cùng các lõi
        both = max(ph["GA"], ph["SA"], (ph["GA"] + ph["SA"]) * min(cores, len(ml) * cfg["n_hpo_runs"]) /
                   min(cores, 2 * len(ml) * cfg["n_hpo_runs"]))
        ph["GA"] = ph["SA"] = both / 2
    if ml:
        n_hv = sum(1 for a in ("GA", "SA") if a in V)
        n_eval = (cfg["n_test_seeds_baseline"] + n_hv * cfg["n_hpo_runs"] * cfg["n_eval_seeds_per_config"]
                  + n_hv * cfg["n_test_seeds_baseline"])                    # Bảng 4.5 + đánh giá ứng viên
        ph["tier3"] = sum(measured[m] * 1.25 * n_eval for m in ml) / min(cores, len(ml) * n_eval)
        ph["refit"] = sum(measured[m] * 1.25 * cfg["n_refit_seeds"] * len(V) for m in ml) / min(cores, len(ml) * len(V) * cfg["n_refit_seeds"])
    overhead = 1.35                                     # chạy song song làm mỗi lõi chậm đi
    total = sum(ph.values()) * overhead + 10
    weights = {5: ph.get("arima", 0), 6: ph.get("tier1", 0), 7: ph.get("GA", 0), 8: ph.get("SA", 0),
               9: ph.get("tier3", 0), 11: ph.get("refit", 0)}
    weights = {k: max(0.5, v) for k, v in weights.items()}
    return {"total_seconds": round(total), "phases": {k: round(v * overhead, 1) for k, v in ph.items()},
            "measured_fit_seconds": {k: round(v, 3) for k, v in measured.items()}, "cores": cores,
            "weights": weights, "mode": cfg["mode"], "n_obs": int(len(y))}
