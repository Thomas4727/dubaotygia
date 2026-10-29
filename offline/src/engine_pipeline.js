/* Phần 5: chỉ tiêu, bảng kết quả, kết luận H1–H3 (evaluate.py, report_extras.py), tiến trình 12 bước (progress.py)
   và hàm điều phối runPipeline (pipeline.py). Các đơn vị việc nặng được giao cho `runner` (nhóm Web Worker). */
var E = (typeof E !== "undefined") ? E : {};
(function (E) {
"use strict";

const ML = E.ML_MODELS;

// ======================================================================== Chỉ tiêu (evaluate.py)

E.metrics = function (actual, pred) {
  const n = actual.length, e = actual.map((a, i) => a - pred[i]);
  return { MAE: E.mean(e.map(Math.abs)), RMSE: Math.sqrt(E.mean(e.map(v => v * v))),
           MAPE: E.mean(e.map((v, i) => Math.abs(v / actual[i]))) * 100, MeanErr: E.mean(e), SdErr: n > 1 ? E.std(e, 1) : 0 };
};
E.summarize = function (perRun) {
  const out = {};
  for (const k of ["MAE", "RMSE", "MAPE", "MeanErr", "SdErr"]) out[k] = E.mean(perRun.map(m => m[k]));
  const rmse = perRun.map(m => m.RMSE);
  out.SD_RMSE = rmse.length > 1 ? E.std(rmse, 1) : 0;
  out.CV_RMSE = out.RMSE ? out.SD_RMSE / out.RMSE : null;
  out.n_runs = perRun.length;
  return out;
};
const improvement = (b, a) => (b === null || b === undefined || b === 0 || a === null || a === undefined ? null : 100 * (b - a) / b);
E.ALERTS = ["Tăng", "Giảm", "Ổn định"];
E.FIELDS_46 = ["Latest_Observed_Date", "Latest_Observed_Rate", "Chosen_Model", "Chosen_Variant", "Chosen_Selection_Basis",
  "Chosen_Mean_RMSE", "Chosen_SD_RMSE", "Chosen_Mean_MAE", "Chosen_Mean_MAPE_Percent", "Next_Forecast_Date",
  "Next_Forecast_Rate_Mean", "Next_Forecast_Rate_SD", "Next_Forecast_P05", "Next_Forecast_P95",
  "Next_Forecast_Change_Percent_Mean", "Management_Alert"];
E.alert = (chg, thr) => (Math.abs(chg) < thr ? "Ổn định" : chg > 0 ? "Tăng" : "Giảm");
const direction = c => (c > 0 ? "Tăng" : c < 0 ? "Giảm" : "Không đổi");
const choose = c => { const ks = Object.keys(c); return ks.length ? ks.reduce((a, b) => (c[b].RMSE < c[a].RMSE ? b : a)) : null; };

E.table45 = function (before, after) {
  const rows = [];
  for (const m of Object.keys(before)) {
    const b = before[m], sa = after[m + "|SA"], ga = after[m + "|GA"];
    if (!sa && !ga) continue;
    for (const met of ["MAE", "RMSE", "MAPE"]) rows.push({
      model: m, metric: met, before: b[met], after_sa: sa ? sa[met] : null, after_ga: ga ? ga[met] : null,
      impr_sa: sa ? improvement(b[met], sa[met]) : null, impr_ga: ga ? improvement(b[met], ga[met]) : null,
      sd_before: met === "RMSE" ? b.SD_RMSE : null, sd_sa: sa && met === "RMSE" ? sa.SD_RMSE : null,
      sd_ga: ga && met === "RMSE" ? ga.SD_RMSE : null });
  }
  return rows;
};

const METRIC_TEXT = { MAE: "MAE", RMSE: "RMSE", MAPE: "MAPE (%)" };
const vn = E.vn;

E.hypotheses = function (t44, t45, cfg, h3) {
  const label = cfg.mode === "chay_thu" ? " (kết quả Chạy thử, không dùng để so với bài)" : "";
  const out = {};
  const arima = t44.find(r => r.model === "ARIMA"), ml = t44.filter(r => ML.includes(r.model));
  if (!arima || !ml.length) {
    const need = [["ARIMA", !!arima], ["ít nhất một mô hình học máy ở cấu hình Baseline", ml.length > 0]].filter(x => !x[1]).map(x => x[0]);
    out.H1 = { status: "Chưa đủ dữ liệu", text: "Chưa đủ dữ liệu để kết luận – cần chạy thêm " + need.join(" và ") + "." };
  } else {
    let lower = 0, total = 0;
    const detail = ml.map(r => {
      const parts = [], low = [], high = [];
      for (const met of ["MAE", "RMSE", "MAPE"]) {
        const nd = met === "MAPE" ? 4 : 2, isLow = r[met] < arima[met];
        lower += isLow; total++;
        (isLow ? low : high).push(met);
        parts.push(`${METRIC_TEXT[met]} ${vn(r[met], nd)} ${isLow ? "<" : r[met] === arima[met] ? "=" : ">"} ${vn(arima[met], nd)} (${isLow ? "thấp hơn" : "không thấp hơn"})`);
      }
      const tt = !high.length ? "thấp hơn ARIMA ở cả 3 chỉ tiêu" : !low.length ? "không thấp hơn ARIMA ở chỉ tiêu nào"
        : `thấp hơn ARIMA ở ${low.join(", ")}; không thấp hơn ở ${high.join(", ")}`;
      return `${E.MODEL_NAMES[r.model]}: ${parts.join("; ")} → ${tt}`;
    });
    out.H1 = { status: lower === total ? "Được ủng hộ" : lower ? "Ủng hộ một phần" : "Không được ủng hộ",
               text: `${lower}/${total} phép so sánh (mô hình × MAE, RMSE, MAPE) có sai số trung bình thấp hơn ARIMA${label}.`, detail };
  }
  const comps = [];
  for (const r of t45) for (const a of ["GA", "SA"]) if (r["after_" + a.toLowerCase()] !== null) comps.push([r.model, r.metric, a, r["impr_" + a.toLowerCase()]]);
  if (!comps.length) out.H2 = { status: "Chưa đủ dữ liệu", text: "Chưa đủ dữ liệu để kết luận – cần chạy thêm tối ưu GA hoặc SA cho ít nhất một mô hình học máy." };
  else {
    const down = comps.filter(c => c[3] !== null && c[3] > 0).length;
    const note = comps.length === 18 ? "" : ` (phạm vi chạy có ${comps.length}/18 phép so sánh)`;
    let text = `${down}/${comps.length} phép so sánh có sai số giảm sau tối ưu${note}${label}.`, status;
    if (cfg.mode === "chay_thu") {
      status = "Chưa đủ căn cứ (Chạy thử)";
      text = `Bảng 4.5 ở chế độ Chạy thử chỉ có ${cfg.n_hpo_runs} lần chạy GA/SA × ${cfg.n_eval_seeds_per_config} seed mỗi ô, chưa đủ căn cứ để kết luận. Thông tin phụ: ${text}`;
    } else status = down === comps.length ? "Được ủng hộ" : down ? "Ủng hộ một phần" : "Không được ủng hộ";
    out.H2 = { status, text, detail: comps.map(([m, met, a, v]) => `${E.MODEL_NAMES[m]} · ${met} · ${a}: ${v > 0 ? "giảm" : "không giảm"} (${v > 0 ? "+" : ""}${vn(v, 2)}%)`) };
  }
  if (!h3 || !h3.accuracy) out.H3 = { status: "Chưa đủ dữ liệu", text: "Chưa đủ dữ liệu để kết luận – cần chạy ít nhất một mô hình học máy để có mô hình tích hợp (mô hình chính)." };
  else {
    const a = h3.accuracy, m = h3.management, accOk = a.RMSE <= a.reference_RMSE;
    const crit = [
      ["Tính chính xác", accOk, `Mô hình tích hợp (${a.label}): MAE ${vn(a.MAE, 2)}, RMSE ${vn(a.RMSE, 2)}, MAPE ${vn(a.MAPE, 4)}% trên tập kiểm tra; ` +
        `RMSE ${accOk ? "≤" : ">"} ${a.reference} (${vn(a.reference_RMSE, 2)}). (Ngưỡng 'đạt' – lựa chọn của web, bài không quy định: RMSE không cao hơn chuẩn đối chiếu ${a.reference}.)`],
      ["Tính tự động hóa", !!h3.automation, h3.automation ? "Chạy tuần tự từ dữ liệu tải lên đến dự báo T+1 không cần can thiệp thủ công" : "Quy trình cần can thiệp thủ công"],
      ["Tính hữu ích quản lý", Object.values(m).every(Boolean), "Có dự báo T+1 (Bảng 4.6): " + (m.forecast ? "có" : "không") +
        "; cảnh báo Tăng/Giảm/Ổn định: " + (m.alert ? "có" : "không") + "; báo cáo (bảng, biểu đồ, file kết quả): " + (m.report ? "có" : "không")],
    ];
    const met = crit.filter(c => c[1]).length;
    out.H3 = { status: met === 3 ? "Được ủng hộ" : met ? "Ủng hộ một phần" : "Không được ủng hộ",
               text: `Đạt ${met}/3 tiêu chí của mục 3.1.1 (chính xác, tự động hóa, hữu ích quản lý)${label}.`,
               detail: crit.map(([n, ok, t]) => `${n}: ${ok ? "đạt" : "chưa đạt"} – ${t}`) };
  }
  return out;
};

function h3Inputs(cands, key, rw, t46) {
  if (!key) return null;
  const ch = cands[key].summary, ref = cands.ARIMA;
  return { accuracy: { label: cands[key].label, MAE: ch.MAE, RMSE: ch.RMSE, MAPE: ch.MAPE, reference: ref ? "ARIMA" : "Random walk",
                       reference_RMSE: ref ? ref.summary.RMSE : rw.RMSE },
           automation: true,
           management: { forecast: !!(t46 && t46.Next_Forecast_Rate_Mean !== null), alert: !!(t46 && t46.Management_Alert), report: !!t46 } };
}

function thresholdCheck(actual, previous, thr) {
  const chg = actual.map((a, i) => (a - previous[i]) / previous[i] * 100), labels = chg.map(c => E.alert(c, thr));
  const ab = chg.map(Math.abs), n = chg.length, count = {}, share = {};
  for (const k of E.ALERTS) { count[k] = labels.filter(x => x === k).length; share[k] = count[k] / n * 100; }
  return { n_days: n, threshold_pct: thr, dist: { min: Math.min(...ab), median: E.median(ab), p90: E.quantile(ab, 0.9), p95: E.quantile(ab, 0.95), max: Math.max(...ab) },
           share_pct: share, count, mostly_stable: share["Ổn định"] > 95 };
}

function hpoParity(runs, needHpo) {
  const out = [];
  for (const m of [...new Set(needHpo.map(x => x[0]))].sort()) {
    const by = { GA: runs.filter(r => r.model === m && r.algo === "GA"), SA: runs.filter(r => r.model === m && r.algo === "SA") };
    if (!by.GA.length || !by.SA.length) { out.push({ model: m, applicable: false, ok: null, note: "Chỉ chạy một trong hai thuật toán – không cần đối chiếu" }); continue; }
    const ref = by.GA[0].parity, checks = {};
    for (const k of ["space", "objective", "folds", "budget"])
      checks[k] = [...by.GA, ...by.SA].every(r => JSON.stringify(r.parity[k]) === JSON.stringify(ref[k]));
    out.push({ model: m, applicable: true, ok: Object.values(checks).every(Boolean), checks, space: ref.space, budget: ref.budget,
               n_folds: ref.folds.length, evals_used: { GA: by.GA.map(r => r.n_evals), SA: by.SA.map(r => r.n_evals) } });
  }
  return out;
}

/** Cấu hình cuối qua các lần chạy độc lập: J thấp nhất; ngang nhau (< tie) thì chọn RMSE ổn định nhất qua các fold. */
function finalConfig(runs, tie) {
  const jmin = Math.min(...runs.map(r => r.J));
  const tied = runs.filter(r => r.J <= jmin * (1 + tie));
  const sd = r => (r.fold_rmse && r.fold_rmse.length > 1 ? E.std(r.fold_rmse, 1) : 0);
  return tied.sort((a, b) => sd(a) - sd(b) || a.J - b.J || a.run - b.run)[0];
}

// ======================================================================== Tiến trình 12 bước (progress.py)

E.STEPS = [
  [1, "Tiếp nhận dữ liệu", "Đọc file, nhận dạng cột ngày và cột tỷ giá"],
  [2, "Kiểm tra và làm sạch dữ liệu", "Chuẩn hóa ngày, sắp xếp, bỏ trùng, bỏ giá trị không hợp lệ và điểm bất thường"],
  [3, "Thống kê và kiểm tra tính dừng", "Chỉ số mô tả; kiểm định ADF và Phillips–Perron"],
  [4, "Tạo đặc trưng và chia dữ liệu", "Mức thay đổi hằng ngày, giá trị trễ, thống kê trượt; chia 80% xây dựng / 20% kiểm tra theo thời gian"],
  [5, "Mô hình so sánh ARIMA", "Thử 25 cấu trúc, chọn theo AIC, dự báo từng ngày trên phần kiểm tra"],
  [6, "Huấn luyện ANN, Random Forest, XGBoost (mặc định)", "Cấu hình mặc định, lặp nhiều lần để đo độ ổn định"],
  [7, "Tìm cấu hình bằng GA", "Thuật toán di truyền: quần thể, chọn lọc, lai ghép, đột biến"],
  [8, "Tìm cấu hình bằng SA", "Mô phỏng luyện kim: thử cấu hình lân cận, nhiệt độ giảm dần"],
  [9, "Đánh giá trên phần kiểm tra", "Chạy lại mọi mô hình nhiều lần trên 20% dữ liệu cuối"],
  [10, "Chọn mô hình", "Sai số RMSE trung bình thấp nhất trong ANN, Random Forest, XGBoost"],
  [11, "Huấn luyện lại và dự báo", "Huấn luyện lại mô hình được chọn, dự báo ngày làm việc tiếp theo"],
  [12, "Cảnh báo và lưu kết quả", "Báo Tăng / Giảm / Ổn định theo ngưỡng, lưu kết quả"],
];
const DEFAULT_WEIGHTS = { 1: 1, 2: 1, 3: 2, 4: 1, 5: 8, 6: 8, 7: 30, 8: 30, 9: 10, 10: 1, 11: 6, 12: 2 };

function skipReasons(cfg) {
  const ml = cfg.models.filter(m => ML.includes(m)), v = cfg.variants, out = {};
  if (!cfg.models.includes("ARIMA")) out[5] = "Không chọn ARIMA";
  if (!ml.length) for (const s of [6, 7, 8, 9]) out[s] = "Không chọn ANN / Random Forest / XGBoost";
  else {
    if (!v.includes("Baseline")) out[6] = "Không chọn cấu hình mặc định (vẫn chạy ở bước 9 làm mốc so sánh cho GA/SA)";
    if (!v.includes("GA")) out[7] = "Không chọn GA";
    if (!v.includes("SA")) out[8] = "Không chọn SA";
  }
  const nc = ml.length * v.length;
  if (nc === 1) out[10] = "Chỉ có một ứng viên học máy – dùng luôn ứng viên đó";
  else if (nc === 0) out[10] = "Không có mô hình học máy – ARIMA chỉ để so sánh";
  return out;
}
E.scopeText = cfg => cfg.models.map(m => E.MODEL_NAMES[m]).join(", ") +
  (cfg.models.some(m => ML.includes(m)) ? " · cấu hình: " + cfg.variants.map(v => ({ Baseline: "mặc định", GA: "GA", SA: "SA" })[v]).join(", ") : "");

class Cancelled extends Error {}
E.Cancelled = Cancelled;
class StepError extends Error { constructor(step, msg, hint) { super(msg); this.step = step; this.hint = hint; } }

E.Progress = function (cfg, onProgress, weights, estimateSeconds) {
  const reasons = skipReasons(cfg);
  this.cfg = cfg; this.onProgress = onProgress; this.estimateSeconds = estimateSeconds || null;
  this.weights = Object.assign({}, DEFAULT_WEIGHTS, weights || {});
  this.steps = E.STEPS.map(([id, name, caption]) => ({ id, name, caption, status: reasons[id] ? "bo_qua" : "cho", detail: reasons[id] || "", frac: 0, started: null, seconds: null }));
  this.log_lines = []; this.t0 = Date.now(); this.error = null; this._last = 0;
};
const nowTime = () => new Date().toTimeString().slice(0, 8);
Object.assign(E.Progress.prototype, {
  step(i) { return this.steps[i - 1]; },
  isSkipped(i) { return this.step(i).status === "bo_qua"; },
  log(line) { this.log_lines.push(`${nowTime()}  ${line}`); this.emit(); },
  start(i, detail) { const s = this.step(i); Object.assign(s, { status: "dang_chay", detail: detail || "", frac: 0, started: Date.now() }); this.log(`[Bước ${i}] ${s.name}: bắt đầu. ${detail || ""}`); this.emit(true); },
  update(i, detail, frac) { const s = this.step(i); if (detail !== null && detail !== undefined) s.detail = detail; if (frac !== null && frac !== undefined) s.frac = Math.max(0, Math.min(1, frac)); this.emit(); },
  done(i, detail) { const s = this.step(i); Object.assign(s, { status: "xong", frac: 1, seconds: Math.round((Date.now() - (s.started || Date.now())) / 100) / 10 }); if (detail !== undefined) s.detail = detail; this.log(`[Bước ${i}] xong (${s.seconds} s). ${s.detail}`); this.emit(true); },
  fail(i, message, hint) { const s = this.step(i); s.status = "loi"; s.detail = `${message} — Cách khắc phục: ${hint}`; this.error = { step: i, step_name: s.name, message, hint }; this.log(`[Bước ${i}] LỖI: ${message}`); this.emit(true); },
  cancel() { for (const s of this.steps) if (s.status === "dang_chay") { s.status = "huy"; s.detail = "Đã hủy theo yêu cầu"; } this.log("Đã hủy theo yêu cầu người dùng."); this.emit(true); },
  percent() {
    let tot = 0, got = 0;
    for (const s of this.steps) if (s.status !== "bo_qua") { tot += this.weights[s.id]; got += this.weights[s.id] * (s.status === "xong" ? 1 : s.frac); }
    return tot ? 100 * got / tot : 0;
  },
  snapshot() {
    const elapsed = (Date.now() - this.t0) / 1000, pct = this.percent();
    const eta = pct >= 3 ? elapsed * (100 - pct) / pct : this.estimateSeconds ? Math.max(0, this.estimateSeconds - elapsed) : null;
    return { mode: this.cfg.mode, mode_name: E.MODE_NAMES[this.cfg.mode], scope: E.scopeText(this.cfg),
             steps: this.steps.map(s => Object.assign({}, s)), percent: Math.round(pct * 10) / 10, elapsed: Math.round(elapsed),
             eta: eta === null ? null : Math.round(eta), log: this.log_lines.slice(-300), error: this.error };
  },
  emit(force) {
    if (!this.onProgress) return;
    const now = Date.now();
    if (!force && now - this._last < 400) return;
    this._last = now;
    this.onProgress(this.snapshot());
  },
});

// ======================================================================== Điều phối (pipeline.run_pipeline)

const EVAL_SEED_STRIDE = 1000;
const meanRows = preds => preds[0].map((_, i) => E.mean(preds.map(p => p[i])));
const label = (m, v) => (v ? `${E.MODEL_NAMES[m]} – ${v}` : E.MODEL_NAMES[m]);
const f2 = x => x.toFixed(3);

/**
 * rows: [{day, rate}] đọc từ file; meta: {filename, date_column, rate_column}; cfg: E.buildConfig(...).
 * runner: {init(y, cfg), run(units, onResult, onMessage) -> Promise, cancelled}.
 * store: {get(key) -> Promise, put(key, value) -> Promise} để "Chạy tiếp" (có thể null).
 */
E.runPipeline = async function (rows, meta, cfg, runner, onProgress, opts) {
  opts = opts || {};
  const prog = new E.Progress(cfg, onProgress, opts.weights, opts.estimateSeconds);
  const ml = cfg.models.filter(m => ML.includes(m)), V = cfg.variants;
  const needHpo = [];
  for (const m of ml) for (const a of ["GA", "SA"]) if (V.includes(a)) needHpo.push([m, a]);
  const tStart = Date.now();
  let step = 1, reused = 0;
  const store = opts.store || null;
  const check = () => { if (runner.cancelled) throw new Cancelled(); };
  const reuseTxt = c => (c ? " – lấy từ lần chạy trước" : "");

  // Chạy các đơn vị việc: phần đã có trong store không chạy lại
  async function runUnits(units, onResult, onMessage) {
    let i = 0;
    const pending = [];
    for (const u of units) {
      const v = store ? await store.get(u.key) : undefined;
      if (v !== undefined) { i++; reused++; onResult(u.key, v, i, units.length, true); }
      else pending.push(u);
    }
    check();
    if (pending.length) await runner.run(pending, (key, val) => {
      if (store) store.put(key, val);
      i++;
      onResult(key, val, i, units.length, false);
    }, onMessage);
    check();
  }

  try {
    // 1. Tiếp nhận dữ liệu
    prog.start(1, `${meta.filename || "dữ liệu"}: ${rows.length} dòng đọc được`);
    prog.done(1, `${meta.filename || "dữ liệu"}: ${rows.length} dòng đọc được` +
      (meta.date_column ? ` · cột ngày '${meta.date_column}', cột tỷ giá '${meta.rate_column}'` : ""));

    // 2. Làm sạch
    step = 2; prog.start(2);
    const cl = E.clean(rows, cfg), y = cl.y, days = cl.days, cs = cl.stats;
    prog.done(2, `Còn ${cs.rows_out} dòng, loại ${cs.rows_removed} (dị thường ${cs.anomalies}); ${cs.missing_business_days} ngày làm việc trống`);
    if (store && store.open) await store.open(E.fingerprint(y, cfg));

    // 3. Thống kê + tính dừng
    step = 3; prog.start(3, "Chỉ số mô tả, kiểm định ADF và Phillips–Perron cho tỷ giá và mức thay đổi");
    const t41 = E.descriptive(days, y), st = E.stationarity(y), t42 = st.rows, t42c = st.conclusion;
    prog.done(3, t42c.text);

    // 4. Đặc trưng + chia dữ liệu
    step = 4; prog.start(4);
    const ctx = new E.Context(y, cfg), s = ctx.split, dv = i => E.fmtVN(days[i]);
    const split = {
      n_obs: s.n_obs, n_dev: s.n_dev, n_train_obs: s.n_train, n_test: s.n_obs - s.n_dev,
      train_samples: s.train_rows.length, val_samples: s.val_rows.length, test_samples: s.test_rows.length,
      dev_samples: s.dev_rows.length, first_row: s.first_row, dev_start: dv(0), dev_end: dv(s.n_dev - 1),
      train_end: dv(s.n_train - 1), val_start: dv(s.n_train), test_start: dv(s.n_dev), test_end: dv(s.n_obs - 1),
      folds: ctx.folds.map(([tr, va]) => ({ train: tr.length, val: va.length })) };
    prog.done(4, `train ${split.train_samples} · validation ${split.val_samples} · test ${split.test_samples} mẫu; cắt test từ ${split.test_start}; CV ${cfg.n_folds} fold`);
    await runner.init(y, cfg);
    const testT = Array.from(s.test_rows, i => i + 1), actual = testT.map(i => y[i]);
    const testDates = testT.map(i => E.fmtISO(days[i])), rwPred = Array.from(s.test_rows, i => y[i]);
    const latest = y[y.length - 1], nextDay = E.nextBusinessDay(days[days.length - 1]);
    const candidates = {};
    let t43 = [], arimaFig = null, arimaT1 = null;

    // 5. ARIMA
    step = 5;
    if (cfg.models.includes("ARIMA")) {
      prog.start(5, "Cấu trúc 0/25");
      let a;
      await runUnits([{ key: "arima", type: "arima", args: { d: t42c.d } }], (k, v, i, n, c) => { a = v; if (c) prog.update(5, "Lấy từ lần chạy trước", 1); },
        (u, msg) => prog.update(5, `Cấu trúc đang thử ${msg.i}/${msg.n}: ARIMA(${msg.order.join(", ")})`, 0.95 * msg.i / msg.n));
      t43 = a.t43.map(r => Object.assign({ dev_start: split.dev_start, dev_end: split.dev_end }, r));
      arimaFig = { dates: testDates, actual, pred: a.pred, lo: a.lo, hi: a.hi, order: a.order };
      const m = E.metrics(actual, a.pred);
      candidates.ARIMA = { model: "ARIMA", variant: null, label: `ARIMA(${a.order.join(", ")})`,
        summary: Object.assign({}, m, { SD_RMSE: 0, CV_RMSE: 0, n_runs: cfg.n_baseline_seeds }), pred: a.pred,
        params: { order: a.order, trend: cfg.arima_trend }, in_selection: false, benchmark: true, cost_seconds: a.seconds };
      arimaT1 = a.t1;
      prog.done(5, `Chọn ARIMA(${a.order.join(", ")}), trend='n'; RMSE test ${f2(m.RMSE)}`);
    }

    // 6. Baseline tầng 1
    step = 6;
    const tier1 = {}, tier1Pred = {};
    if (!prog.isSkipped(6)) {
      prog.start(6);
      const per = {};
      ml.forEach(m => { per[m] = {}; });
      const units = [];
      for (const m of ml) for (const sd of E.seeds(cfg, cfg.n_baseline_seeds))
        units.push({ key: `t1|${m}|${sd}`, type: "eval", args: { tag: m, kind: m, params: E.baseline(m), seed: sd, tier: 1 } });
      await runUnits(units, (k, v, i, n, c) => {
        per[v.tag][v.seed] = v.pred;
        prog.update(6, `${E.MODEL_NAMES[v.tag]} · seed ${v.seed} xong (${i}/${n} lần chạy, ${cfg.n_baseline_seeds} seed mỗi mô hình)${reuseTxt(c)}`, i / n);
      });
      for (const m of ml) {
        const preds = Object.keys(per[m]).sort((a, b) => a - b).map(sd => per[m][sd]);
        tier1[m] = E.summarize(preds.map(p => E.metrics(actual, p)));
        tier1Pred[m] = meanRows(preds);
      }
      prog.done(6, ml.map(m => `${E.MODEL_NAMES[m]} RMSE ${f2(tier1[m].RMSE)}`).join(" · "));
    }

    // 7–8. GA, SA
    step = 7;
    const hpoBy = {};
    if (needHpo.length) {
      const runSeeds = E.seeds(cfg, cfg.n_hpo_runs), tasks = [];
      for (const [m, a] of needHpo) runSeeds.forEach((sd, i) => tasks.push([m, a, i + 1, sd]));
      for (const a of ["GA", "SA"]) if (tasks.some(t => t[1] === a)) prog.start(a === "GA" ? 7 : 8, "Khởi động...");
      const live = {}, total = { GA: tasks.filter(t => t[1] === "GA").length, SA: tasks.filter(t => t[1] === "SA").length };
      const describe = a => {
        const parts = [];
        for (const key of Object.keys(live).sort()) {
          const [aa, m, r] = key.split("|"), msg = live[key];
          if (aa !== a || (msg.done && Object.keys(live).length > 3)) continue;
          const best = msg.best, bt = best !== null && best !== undefined && Number.isFinite(best) ? `RMSE tốt nhất ${f2(best)}` : "đang đánh giá P₀";
          const head = `${E.MODEL_NAMES[m]} lần chạy ${r}/${cfg.n_hpo_runs}`;
          if (msg.done) parts.push(`${head} · xong · ${bt}${reuseTxt(msg.cached)}`);
          else if (a === "GA") parts.push(`${head} · thế hệ ${msg.gen || 0}/${cfg.ga_max_generations} · đánh giá ${msg.evals || 0}/${cfg.budget} · ${bt}`);
          else parts.push(`${head} · đánh giá ${msg.evals || 0}/${cfg.budget}${msg.T !== null && msg.T !== undefined ? ` · nhiệt độ T = ${msg.T.toPrecision(4)}` : " · đang hiệu chỉnh T0"} · ${bt}`);
        }
        return parts.slice(-6).join(" | ");
      };
      const frac = a => Object.entries(live).filter(([k]) => k.startsWith(a + "|"))
        .reduce((acc, [, v]) => acc + (v.done ? 1 : Math.min(1, (v.evals || 0) / cfg.budget)), 0) / Math.max(1, total[a]);
      await runUnits(tasks.map(([m, a, r, sd]) => ({ key: `hpo|${m}|${a}|${r}`, type: "hpo", args: { kind: m, algo: a, run: r, seed: sd } })),
        (key, res, i, n, c) => {
          hpoBy[`${res.model}|${res.algo}|${res.run}`] = res;
          live[`${res.algo}|${res.model}|${res.run}`] = { done: true, best: res.J, evals: res.n_evals, cached: c };
          const a = res.algo;
          prog.log(`${a} · ${E.MODEL_NAMES[res.model]} lần chạy ${res.run}: J = ${res.J.toFixed(4)} (${res.n_evals} đánh giá, ${res.stop_reason}, ${res.seconds} s)${reuseTxt(c)}`);
          prog.update(a === "GA" ? 7 : 8, describe(a), frac(a));
          if (Object.keys(hpoBy).filter(k => k.split("|")[1] === a).length === total[a]) {
            const parts = ml.filter(m => needHpo.some(x => x[0] === m && x[1] === a)).map(m =>
              `${E.MODEL_NAMES[m]} J tốt nhất ${f2(Math.min(...Object.values(hpoBy).filter(r => r.model === m && r.algo === a).map(r => r.J)))}`);
            prog.done(a === "GA" ? 7 : 8, parts.join(" · "));
          }
        },
        (unit, msg) => {
          const a = unit.args;
          live[`${a.algo}|${a.kind}|${a.run}`] = Object.assign(live[`${a.algo}|${a.kind}|${a.run}`] || {}, msg);
          prog.update(a.algo === "GA" ? 7 : 8, describe(a.algo), frac(a.algo));
        });
    }
    const hpoRuns = Object.keys(hpoBy).sort().map(k => hpoBy[k]);

    // 9. Đánh giá trên tập kiểm tra (tầng 3, Bảng 4.5)
    step = 9;
    const tier3Base = {}, tier3Hpo = {}, finalCfg = {}, candEval = {}, cost = {};
    if (ml.length) {
      prog.start(9);
      let units = [];
      for (const m of ml) for (const sd of E.seeds(cfg, cfg.n_test_seeds_baseline))
        units.push({ key: `t3|${m}|Baseline|0|${sd}`, type: "eval", args: { tag: [m, "Baseline", 0], kind: m, params: E.baseline(m), seed: sd, tier: 3 } });
      for (const r of hpoRuns) for (let k = 0; k < cfg.n_eval_seeds_per_config; k++) {
        const sd = r.seed + EVAL_SEED_STRIDE * k;
        units.push({ key: `t3|${r.model}|${r.algo}|${r.run}|${sd}`, type: "eval", args: { tag: [r.model, r.algo, r.run], kind: r.model, params: r.params, seed: sd, tier: 3 } });
      }
      const per3 = {};
      await runUnits(units, (key, v, i, n, c) => {
        const t = v.tag.join("|");
        (per3[t] = per3[t] || {})[v.seed] = v;
        prog.update(9, `Trước/sau tối ưu · ${E.MODEL_NAMES[v.tag[0]]} – ${v.tag[1]}${v.tag[2] ? ` (lần chạy ${v.tag[2]})` : ""} · seed ${v.seed} (${i}/${n} lượt)${reuseTxt(c)}`, 0.7 * i / n);
      });
      const sortedVals = o => Object.keys(o).sort((a, b) => a - b).map(k => o[k]);
      for (const m of ml) {
        const runs = sortedVals(per3[`${m}|Baseline|0`]);
        tier3Base[m] = E.summarize(runs.map(v => E.metrics(actual, v.pred)));
        finalCfg[`${m}|Baseline`] = E.baseline(m);
        cost[`${m}|Baseline`] = runs.reduce((a, v) => a + v.seconds, 0);
      }
      for (const [m, a] of needHpo) {
        const rs = hpoRuns.filter(r => r.model === m && r.algo === a);
        const evals = [];
        for (const r of rs) for (const v of sortedVals(per3[`${m}|${a}|${r.run}`])) evals.push(v.pred);
        const k = `${m}|${a}`;
        tier3Hpo[k] = E.summarize(evals.map(p => E.metrics(actual, p)));
        const ch = finalConfig(rs, cfg.config_tie_tolerance);
        finalCfg[k] = ch.params; tier3Hpo[k].final_run = ch.run; tier3Hpo[k].final_J = ch.J;
        cost[k] = rs.reduce((acc, r) => acc + r.seconds, 0);
      }
      units = [];
      for (const [m, a] of needHpo) for (const sd of E.seeds(cfg, cfg.n_test_seeds_baseline))
        units.push({ key: `cand|${m}|${a}|${sd}`, type: "eval", args: { tag: [m, a], kind: m, params: finalCfg[`${m}|${a}`], seed: sd, tier: 3 } });
      const perc = {};
      await runUnits(units, (key, v, i, n, c) => {
        const t = v.tag.join("|");
        (perc[t] = perc[t] || {})[v.seed] = v;
        prog.update(9, `Đánh giá lại ${E.MODEL_NAMES[v.tag[0]]} – ${v.tag[1]} (cấu hình tốt nhất) · lần ${v.seed} (${i}/${n} lượt)${reuseTxt(c)}`, 0.7 + 0.3 * i / n);
      });
      for (const m of ml) candEval[`${m}|Baseline`] = [tier3Base[m], meanRows(sortedVals(per3[`${m}|Baseline|0`]).map(v => v.pred))];
      for (const [m, a] of needHpo) {
        const vs = sortedVals(perc[`${m}|${a}`]), preds = vs.map(v => v.pred);
        candEval[`${m}|${a}`] = [E.summarize(preds.map(p => E.metrics(actual, p))), meanRows(preds)];
        cost[`${m}|${a}`] += vs.reduce((acc, v) => acc + v.seconds, 0);
      }
      prog.done(9, needHpo.map(([m, a]) => `${m}-${a} RMSE ${f2(candEval[`${m}|${a}`][0].RMSE)}`).join(" · ") ||
        ml.map(m => `${m} Baseline RMSE ${f2(tier3Base[m].RMSE)}`).join(" · "));
    } else prog.update(9, "Chỉ chọn ARIMA – ARIMA đã được đánh giá trên test ở bước 5");

    for (const m of ml) for (const v of V) {
      const [summ, pred] = candEval[`${m}|${v}`];
      candidates[`${m}|${v}`] = { model: m, variant: v, label: label(m, v), summary: summ, pred, params: finalCfg[`${m}|${v}`],
                                  in_selection: true, benchmark: false, cost_seconds: Math.round(cost[`${m}|${v}`] * 10) / 10 };
    }

    // 10. Chọn mô hình
    step = 10;
    const selectable = {};
    for (const [k, c] of Object.entries(candidates)) if (c.in_selection) selectable[k] = c.summary;
    if (!prog.isSkipped(10)) prog.start(10);
    const chosenKey = choose(selectable);
    const byRmse = (o, f) => Object.keys(o).sort((a, b) => f(a) - f(b) || (a < b ? -1 : 1));
    const ranking = byRmse(candidates, k => candidates[k].summary.RMSE);
    const selection = byRmse(selectable, k => selectable[k].RMSE).map(k => ({ key: k, label: candidates[k].label, RMSE: selectable[k].RMSE,
      SD_RMSE: selectable[k].SD_RMSE, CV_RMSE: selectable[k].CV_RMSE, n_runs: selectable[k].n_runs, cost_seconds: candidates[k].cost_seconds }));
    if (!prog.isSkipped(10)) prog.done(10, "Xếp hạng (chỉ ANN/RF/XGBoost): " + selection.slice(0, 5).map(r => `${r.label} (${f2(r.RMSE)})`).join(" < "));
    else if (chosenKey) prog.update(10, `Chỉ có một mô hình học máy – dùng luôn ${candidates[chosenKey].label}`);
    else prog.update(10, "Không có mô hình học máy – ARIMA chỉ để so sánh nên không có dự báo chính");

    // 11. Huấn luyện lại + dự báo T+1
    step = 11; prog.start(11);
    const forecasts = {};
    if (arimaT1) {
      forecasts.ARIMA = {};
      for (const sd of E.seeds(cfg, cfg.n_refit_seeds)) forecasts.ARIMA[sd] = arimaT1[0];
      candidates.ARIMA.pi95 = [arimaT1[1], arimaT1[2]];
    }
    const refitUnits = [];
    for (const [k, c] of Object.entries(candidates)) if (ML.includes(c.model))
      for (const sd of E.seeds(cfg, cfg.n_refit_seeds))
        refitUnits.push({ key: `refit|${k}|${sd}`, type: "refit", args: { key: k, kind: c.model, params: finalCfg[`${c.model}|${c.variant}`], seed: sd } });
    await runUnits(refitUnits, (key, v, i, n, c) => {
      (forecasts[v.key] = forecasts[v.key] || {})[v.seed] = v.f;
      prog.update(11, `${candidates[v.key].label} · seed ${v.seed} (${i}/${n}); dự báo tạm ${v.f.toLocaleString("en-US", { maximumFractionDigits: 2 })}${reuseTxt(c)}`, i / Math.max(1, n));
    });
    for (const [k, bySeed] of Object.entries(forecasts)) {
      const vals = Object.keys(bySeed).sort((a, b) => a - b).map(sd => bySeed[sd]);
      const chg = vals.map(v => (v - latest) / latest * 100), mu = E.mean(vals);
      candidates[k].t1 = { date: E.fmtISO(nextDay), mean: mu, sd: vals.length > 1 ? E.std(vals, 1) : 0,
        p05: E.quantile(vals, 0.05), p95: E.quantile(vals, 0.95), change_pct_mean: E.mean(chg), change_abs_mean: mu - latest,
        n_seeds: vals.length, direction: direction(mu - latest), alert: E.alert(E.mean(chg), cfg.alert_watch_pct), trained_on: "development" };
    }
    prog.done(11, chosenKey ? `${candidates[chosenKey].label}: dự báo ${E.fmtVN(nextDay)} = ${candidates[chosenKey].t1.mean.toLocaleString("en-US", { maximumFractionDigits: 2 })}`
      : "Đã dự báo T+1 cho ARIMA (đối chiếu); không có mô hình chính");

    // 12. Cảnh báo + kết quả
    step = 12; prog.start(12);
    const ch = chosenKey ? candidates[chosenKey] : null;
    let t46 = null, out335 = null;
    if (ch) {
      t46 = { Latest_Observed_Date: E.fmtISO(days[days.length - 1]), Latest_Observed_Rate: latest,
        Chosen_Model: E.MODEL_NAMES[ch.model], Chosen_Variant: ch.variant || "—",
        Chosen_Selection_Basis: Object.keys(selectable).length > 1 ? `Minimum Mean RMSE across ${ch.summary.n_runs} repeated Test runs`
          : "Only one machine-learning candidate in the selected scope",
        Chosen_Mean_RMSE: ch.summary.RMSE, Chosen_SD_RMSE: ch.summary.SD_RMSE, Chosen_Mean_MAE: ch.summary.MAE,
        Chosen_Mean_MAPE_Percent: ch.summary.MAPE, Next_Forecast_Date: ch.t1.date, Next_Forecast_Rate_Mean: ch.t1.mean,
        Next_Forecast_Rate_SD: ch.t1.sd, Next_Forecast_P05: ch.t1.p05, Next_Forecast_P95: ch.t1.p95,
        Next_Forecast_Change_Percent_Mean: ch.t1.change_pct_mean, Management_Alert: ch.t1.alert };
      out335 = { change_abs: ch.t1.change_abs_mean, hyperparameters: ch.params };
    }
    for (const [k, c] of Object.entries(candidates)) c.chosen = k === chosenKey;
    const t44 = [];
    if (candidates.ARIMA) t44.push(Object.assign({ model: "ARIMA" }, candidates.ARIMA.summary));
    for (const m of ml) if (tier1[m]) t44.push(Object.assign({ model: m }, tier1[m]));
    const rw = E.metrics(actual, rwPred), t45 = E.table45(tier3Base, tier3Hpo);
    const hyp = E.hypotheses(t44, t45, cfg, h3Inputs(candidates, chosenKey, rw, t46));
    const ref = candidates.ARIMA ? candidates.ARIMA.summary : null;
    for (const c of Object.values(candidates)) {
      c.vs_arima_pct = ref ? 100 * (c.summary.RMSE - ref.RMSE) / ref.RMSE : null;
      c.vs_rw_pct = 100 * (c.summary.RMSE - rw.RMSE) / rw.RMSE;
    }
    const fig42 = (candidates.ARIMA ? [{ key: "ARIMA", label: candidates.ARIMA.label, model: "ARIMA", pred: candidates.ARIMA.pred }] : [])
      .concat(Object.keys(tier1Pred).map(m => ({ key: "tier1|" + m, label: E.MODEL_NAMES[m], model: m, pred: tier1Pred[m] })));
    const settings = {};
    for (const k of Object.keys(cfg)) if (!["models", "variants"].includes(k)) settings[k] = cfg[k];
    const result = {
      version: 4, engine: "html", mode: cfg.mode, mode_name: E.MODE_NAMES[cfg.mode],
      scope: { models: cfg.models, variants: cfg.variants, default: E.isDefaultScope(cfg) },
      data: { filename: meta.filename, date_column: meta.date_column, rate_column: meta.rate_column, clean_log: cl.log, clean_stats: cs, split,
              series: { dates: days.map(E.fmtISO), rate: y } },
      table_4_1: t41, table_4_2: t42, table_4_2_conclusion: t42c, table_4_3: t43, figure_4_1: arimaFig, figure_4_2: fig42,
      table_4_4: t44, random_walk: Object.assign({ model: "RW", n_runs: 1 }, rw), table_4_5: t45, table_4_6: t46, outputs_335: out335,
      tier3_baseline: tier3Base, hypotheses: hyp,
      test: { dates: testDates, actual, random_walk: rwPred },
      candidates, chosen_key: chosenKey, ranking, selection, trained_on: "development",
      hpo_parity: hpoParity(hpoRuns, needHpo), hpo_runs: hpoRuns, settings, checkpoint_reused: reused,
    };
    if (t46) result.error_interval = { lo: t46.Next_Forecast_Rate_Mean - 1.96 * t46.Chosen_Mean_RMSE, hi: t46.Next_Forecast_Rate_Mean + 1.96 * t46.Chosen_Mean_RMSE, z: 1.96, rmse: t46.Chosen_Mean_RMSE };
    result.alert_check = thresholdCheck(actual, rwPred, cfg.alert_watch_pct);
    result.elapsed_seconds = Math.round((Date.now() - tStart) / 100) / 10;
    prog.done(12, t46 ? `Cảnh báo: ${t46.Management_Alert}` : "Không có mô hình học máy nên không có dự báo chính");
    result.progress = prog.snapshot();
    result.finished_at = new Date().toISOString();
    return result;
  } catch (e) {
    if (e instanceof Cancelled || runner.cancelled) { prog.cancel(); throw new Cancelled(); }
    const hints = { 1: "Kiểm tra định dạng file (cột Ngày, Tỷ giá).", 2: "Kiểm tra dữ liệu còn đủ dòng sau khi làm sạch.",
                    3: "Chuỗi quá ngắn hoặc hằng số – cần thêm dữ liệu.", 4: "Cần thêm quan sát để chia train/validation/test.",
                    5: "Thử lại; nếu vẫn lỗi, chuỗi có thể quá ngắn cho ARIMA." };
    prog.fail(step, e.message || String(e), hints[step] || "Bấm \"Chạy\" lại để chạy tiếp từ phần đã xong; nếu lỗi lặp lại, gửi nhật ký cho người phát triển.");
    e.progress = prog.snapshot();
    throw e;
  }
};

/** Dấu vân tay của (dữ liệu, cấu hình): đổi dữ liệu hoặc cấu hình thì không dùng lại tiến độ cũ. */
E.fingerprint = function (y, cfg) {
  const s = JSON.stringify([Array.from(y), cfg]);
  let h1 = 0x811c9dc5, h2 = 0x01000193;
  for (let i = 0; i < s.length; i++) { const c = s.charCodeAt(i); h1 = Math.imul(h1 ^ c, 16777619); h2 = Math.imul(h2 ^ c, 2246822519) + (h2 >>> 13); }
  return (h1 >>> 0).toString(16) + (h2 >>> 0).toString(16) + s.length.toString(16);
};

/** Ước tính thời gian (pipeline.estimate): đo 1 lần huấn luyện mỗi mô hình rồi nhân số lần cần chạy. */
E.estimate = function (cfg, measured, nObs, nDev, cores) {
  const ml = cfg.models.filter(m => ML.includes(m)), V = cfg.variants, ph = {};
  if (cfg.models.includes("ARIMA")) ph.arima = (measured.ARIMA || 5);
  const caps = cfg.caps, factor = { ANN: ((50 + caps.ANN_epochs) / 2) / 200, RF: ((100 + caps.RF_n_estimators) / 2) / 500, XGB: 1.0 };
  if (ml.length && V.includes("Baseline")) ph.tier1 = ml.reduce((a, m) => a + measured[m], 0) * cfg.n_baseline_seeds / Math.min(cores, ml.length * cfg.n_baseline_seeds);
  for (const a of ["GA", "SA"]) if (ml.length && V.includes(a)) {
    const per = ml.map(m => cfg.budget * cfg.n_folds * measured[m] * factor[m] * 0.75);
    const nt = ml.length * cfg.n_hpo_runs;
    ph[a] = Math.max(Math.max(...per), per.reduce((x, y) => x + y, 0) * cfg.n_hpo_runs / Math.min(cores, nt));
  }
  if (ph.GA && ph.SA) {
    const both = Math.max(ph.GA, ph.SA, (ph.GA + ph.SA) * Math.min(cores, ml.length * cfg.n_hpo_runs) / Math.min(cores, 2 * ml.length * cfg.n_hpo_runs));
    ph.GA = ph.SA = both / 2;
  }
  if (ml.length) {
    const nhv = ["GA", "SA"].filter(a => V.includes(a)).length;
    const ne = cfg.n_test_seeds_baseline + nhv * cfg.n_hpo_runs * cfg.n_eval_seeds_per_config + nhv * cfg.n_test_seeds_baseline;
    ph.tier3 = ml.reduce((a, m) => a + measured[m] * 1.25 * ne, 0) / Math.min(cores, ml.length * ne);
    ph.refit = ml.reduce((a, m) => a + measured[m] * 1.25 * cfg.n_refit_seeds * V.length, 0) / Math.min(cores, ml.length * V.length * cfg.n_refit_seeds);
  }
  const overhead = 1.25, total = Object.values(ph).reduce((a, b) => a + b, 0) * overhead + 5;
  const w = { 5: ph.arima || 0, 6: ph.tier1 || 0, 7: ph.GA || 0, 8: ph.SA || 0, 9: ph.tier3 || 0, 11: ph.refit || 0 };
  for (const k of Object.keys(w)) w[k] = Math.max(0.5, w[k]);
  return { total_seconds: Math.round(total), phases: ph, weights: w, cores };
};

})(E);
if (typeof module !== "undefined") module.exports = E;
