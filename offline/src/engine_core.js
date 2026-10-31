/* Bộ máy dự báo chạy trong trình duyệt – phần 1: tiện ích, đọc và làm sạch dữ liệu, thống kê, kiểm định tính dừng.
   Chuyển từ forecast_engine/ (Python). Mọi tham số lấy từ CONFIG bên dưới (= forecast_engine/run_config.py). */
var E = (typeof E !== "undefined") ? E : {};
(function (E) {
"use strict";

// ======================================================================== Cấu hình (run_config.py)

E.MODELS = ["ARIMA", "ANN", "RF", "XGB"];
E.ML_MODELS = ["ANN", "RF", "XGB"];
E.VARIANTS = ["Baseline", "GA", "SA"];
E.MODEL_NAMES = { ARIMA: "ARIMA", ANN: "ANN", RF: "Random Forest", XGB: "XGBoost", RW: "Random walk" };
E.MODE_NAMES = { chay_thu: "Chạy dự báo", chay_day_du: "Chạy đầy đủ" };

E.MODES = {
  chay_thu: {
    n_baseline_seeds: 3, n_hpo_runs: 1, budget: 30, ga_pop_size: 6, ga_max_generations: 5,
    sa_t0_samples: 5, sa_moves_per_temp: 5, n_folds: 3, n_test_seeds_baseline: 3,
    n_eval_seeds_per_config: 3, n_refit_seeds: 3,
    caps: { ANN_epochs: 150, RF_n_estimators: 300, XGB_n_estimators: 500 },
  },
  chay_day_du: {
    n_baseline_seeds: 30, n_hpo_runs: 30, budget: 300, ga_pop_size: 20, ga_max_generations: 15,
    sa_t0_samples: 20, sa_moves_per_temp: 10, n_folds: 5, n_test_seeds_baseline: 30,
    n_eval_seeds_per_config: 1, n_refit_seeds: 30,
    caps: { ANN_epochs: 500, RF_n_estimators: 800, XGB_n_estimators: 1500 },
  },
};

E.COMMON = {
  min_rows: 60, anomaly_jump: 0.01, anomaly_revert: 0.002,
  test_ratio: 0.20, val_ratio: 0.20, cv_first_train_frac: 0.50, es_frac: 0.15, es_rounds: 50,
  max_lag: 30, max_window: 30,
  arima_max_p: 4, arima_max_q: 4, arima_trend: "n", arima_top: 3,
  ga_tournament_k: 3, ga_p_crossover: 0.9, ga_p_mutation: 0.15, ga_sigma: 0.1, ga_elitism: 2, ga_patience: 5,
  sa_accept0: 0.8, sa_cooling: 0.9, sa_sigma: 0.1, sa_t_min_ratio: 1e-3, sa_patience: 100,
  config_tie_tolerance: 0.005,
  alert_watch_pct: 0.10,
  seed_start: 1,
};

E.buildConfig = function (mode, models, variants, overrides) {
  if (!E.MODES[mode]) throw new Error("Chế độ không hợp lệ: " + mode);
  models = E.MODELS.filter(m => (models || E.MODELS).includes(m));
  if (!models.length) throw new Error("Phải chọn ít nhất 1 thuật toán.");
  variants = E.VARIANTS.filter(v => (variants || E.VARIANTS).includes(v));
  if (models.some(m => E.ML_MODELS.includes(m)) && !variants.length)
    throw new Error("Phải chọn ít nhất 1 cách cấu hình siêu tham số cho ANN/RF/XGBoost.");
  const cfg = Object.assign({ mode, models, variants }, clone(E.COMMON), clone(E.MODES[mode]));
  for (const k in (overrides || {})) {
    if (!(k in cfg)) throw new Error("Tham số không tồn tại: " + k);
    cfg[k] = overrides[k];
  }
  return cfg;
};
E.isDefaultScope = cfg => cfg.models.join() === E.MODELS.join() && cfg.variants.join() === E.VARIANTS.join();
E.seeds = (cfg, count, offset) => Array.from({ length: count }, (_, i) => cfg.seed_start + (offset || 0) + i);

function clone(o) { return JSON.parse(JSON.stringify(o)); }
E.clone = clone;

// ======================================================================== Số học cơ bản

const mean = a => { let s = 0; for (let i = 0; i < a.length; i++) s += a[i]; return s / a.length; };
function std(a, ddof) {
  const m = mean(a); let s = 0;
  for (let i = 0; i < a.length; i++) s += (a[i] - m) ** 2;
  return Math.sqrt(s / (a.length - (ddof || 0)));
}
function quantile(a, q) {                      // numpy mặc định (nội suy tuyến tính)
  const s = Array.from(a).sort((x, y) => x - y);
  const pos = (s.length - 1) * q, lo = Math.floor(pos), hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}
const median = a => quantile(a, 0.5);
E.mean = mean; E.std = std; E.quantile = quantile; E.median = median;

// Phân phối chuẩn: Φ(x) qua erfc (sai số ~1e-7)
function erfc(x) {
  const z = Math.abs(x), t = 1 / (1 + 0.5 * z);
  const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 +
    t * (-0.18628806 + t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
  return x >= 0 ? r : 2 - r;
}
E.normCdf = x => 0.5 * erfc(-x / Math.SQRT2);

// ======================================================================== Số ngẫu nhiên có seed (sfc32)

E.makeRng = function (seed) {
  let s = ((seed >>> 0) ^ 0x9E3779B9) >>> 0;
  function sm() {
    s = (s + 0x9E3779B9) | 0;
    let z = s;
    z = Math.imul(z ^ (z >>> 16), 0x85EBCA6B);
    z = Math.imul(z ^ (z >>> 13), 0xC2B2AE35);
    return (z ^ (z >>> 16)) >>> 0;
  }
  let a = sm(), b = sm(), c = sm(), d = sm();
  function next() {
    const t = (((a + b) | 0) + d) | 0;
    d = (d + 1) | 0;
    a = b ^ (b >>> 9);
    b = (c + (c << 3)) | 0;
    c = (c << 21) | (c >>> 11);
    c = (c + t) | 0;
    return (t >>> 0) / 4294967296;
  }
  for (let i = 0; i < 15; i++) next();
  let spare = null;
  return {
    random: next,
    normal(mu, sd) {
      mu = mu || 0; sd = sd === undefined ? 1 : sd;
      if (spare !== null) { const v = spare; spare = null; return mu + sd * v; }
      let u, v, r;
      do { u = 2 * next() - 1; v = 2 * next() - 1; r = u * u + v * v; } while (r >= 1 || r === 0);
      const f = Math.sqrt(-2 * Math.log(r) / r);
      spare = v * f;
      return mu + sd * u * f;
    },
    int(lo, hi) { return lo + Math.floor(next() * (hi - lo)); },          // [lo, hi)
    choice(n, k) {                                                         // k chỉ số khác nhau trong 0..n-1
      const arr = Array.from({ length: n }, (_, i) => i);
      for (let i = 0; i < k; i++) { const j = i + Math.floor(next() * (n - i)); const t = arr[i]; arr[i] = arr[j]; arr[j] = t; }
      return arr.slice(0, k);
    },
    permutation(n) {
      const arr = new Int32Array(n);
      for (let i = 0; i < n; i++) arr[i] = i;
      for (let i = n - 1; i > 0; i--) { const j = Math.floor(next() * (i + 1)); const t = arr[i]; arr[i] = arr[j]; arr[j] = t; }
      return arr;
    },
  };
};

// ======================================================================== Ngày (số ngày kể từ 1970-01-01, UTC)

E.dayFromYMD = (y, m, d) => Math.round(Date.UTC(y, m - 1, d) / 864e5);
E.weekday = day => ((day % 7) + 7 + 3) % 7;                 // Thứ hai = 0 (như Python)
function ymd(day) { const t = new Date(day * 864e5); return [t.getUTCFullYear(), t.getUTCMonth() + 1, t.getUTCDate()]; }
const p2 = n => String(n).padStart(2, "0");
E.fmtISO = day => { const [y, m, d] = ymd(day); return `${y}-${p2(m)}-${p2(d)}`; };
E.fmtVN = day => { const [y, m, d] = ymd(day); return `${p2(d)}/${p2(m)}/${y}`; };
E.nextBusinessDay = day => { let d = day + 1; while (E.weekday(d) >= 5) d++; return d; };

// ======================================================================== Đọc file (data_io.py)

const DATE_COLUMNS = ["ngay", "date", "thoigian", "time", "day"];
const RATE_COLUMNS = ["tygia", "giatri", "close", "price", "giaban", "ban", "sell", "rate", "gia", "value"];

class DataError extends Error {}
E.DataError = DataError;

E.normName = s => String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[đĐ]/g, "d")
  .toLowerCase().replace(/[^a-z]/g, "");

E.parseCSV = function (text) {
  text = text.replace(/^﻿/, "");
  const first = text.split(/\r?\n/, 1)[0];
  const seps = [",", ";", "\t"];
  const counts = seps.map(s => first.split(s).length - 1);
  const sep = seps[counts.indexOf(Math.max(...counts))];
  const rows = [];
  let row = [], field = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (q) {
      if (ch === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else q = false; }
      else field += ch;
    } else if (ch === '"') q = true;
    else if (ch === sep) { row.push(field); field = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && text[i + 1] === "\n") i++;
      row.push(field); field = "";
      if (row.some(c => c.trim() !== "")) rows.push(row);
      row = [];
    } else field += ch;
  }
  row.push(field);
  if (row.some(c => c.trim() !== "")) rows.push(row);
  if (!rows.length) throw new DataError("File trống.");
  return { header: rows[0].map(c => c.trim()), rows: rows.slice(1) };
};

function findColumn(columns, priority) {
  const norm = columns.map(E.normName);
  for (const key of priority) { const i = norm.indexOf(key); if (i >= 0) return i; }
  for (const key of priority) { const i = norm.findIndex(n => n.startsWith(key)); if (i >= 0) return i; }
  return -1;
}
function findRateColumn(columns, skip) {
  // File Vietcombank: dùng cột MUA chuyển khoản (giống bản Python)
  const norm = columns.map(E.normName);
  for (let i = 0; i < norm.length; i++)
    if (i !== skip && norm[i].includes("chuyenkhoan") && !norm[i].replace("chuyenkhoan", "").includes("ban")) return i;
  const rest = columns.map((c, i) => (i === skip ? "\u0000" : c));
  return findColumn(rest, RATE_COLUMNS);
}

E.parseNumber = function (x) {
  let s = String(x).replace(/[^\d.,\-]/g, "");
  if (!s) return NaN;
  if (s.includes(",") && s.includes(".")) {
    s = s.lastIndexOf(",") > s.lastIndexOf(".") ? s.replace(/\./g, "").replace(",", ".") : s.replace(/,/g, "");
  } else if (s.includes(",")) {
    s = /^-?\d{1,3}(,\d{3})+$/.test(s) ? s.replace(/,/g, "") : s.replace(",", ".");
  } else if (/^-?\d{1,3}(\.\d{3})+$/.test(s)) {
    s = s.replace(/\./g, "");
  }
  const v = Number(s);
  return Number.isFinite(v) ? v : NaN;
};

const MONTHS = { jan: 1, feb: 2, mar: 3, apr: 4, may: 5, jun: 6, jul: 7, aug: 8, sep: 9, oct: 10, nov: 11, dec: 12 };
function validDay(y, m, d) {
  if (!(m >= 1 && m <= 12 && d >= 1 && d <= 31)) return null;
  const day = E.dayFromYMD(y, m, d);
  const [yy, mm, dd] = ymd(day);
  return yy === y && mm === m && dd === d ? day : null;
}
function monotonic(days) {
  const v = days.filter(d => d !== null);
  if (v.length < 2) return false;
  let inc = true, dec = true;
  for (let i = 1; i < v.length; i++) { if (v[i] < v[i - 1]) inc = false; if (v[i] > v[i - 1]) dec = false; }
  return inc || dec;
}

E.parseDates = function (values) {
  const s = values.map(v => String(v).trim());
  const re = /^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})/;
  const parts = s.map(v => v.match(re));
  if (parts.filter(Boolean).length > 0.9 * s.length) {
    const fixYear = y => (y.length <= 2 ? 2000 + Number(y) : Number(y));
    const cands = [["dd/mm", (a, b, y) => validDay(fixYear(y), Number(b), Number(a))],
                   ["mm/dd", (a, b, y) => validDay(fixYear(y), Number(a), Number(b))]].map(([label, f]) => {
      const days = parts.map(p => (p ? f(p[1], p[2], p[3]) : null));
      return { label, days, key: [days.filter(d => d !== null).length, monotonic(days) ? 1 : 0, label === "dd/mm" ? 1 : 0] };
    });
    cands.sort((x, y) => y.key[0] - x.key[0] || y.key[1] - x.key[1] || y.key[2] - x.key[2]);
    return { days: cands[0].days, format: cands[0].label };
  }
  const days = s.map(v => {
    let m = v.match(/^(\d{4})[/\-.](\d{1,2})[/\-.](\d{1,2})/);
    if (m) return validDay(Number(m[1]), Number(m[2]), Number(m[3]));
    m = v.match(/^([A-Za-z]{3})[a-z]*\.?\s+(\d{1,2}),?\s+(\d{4})/);        // "Oct 28, 2026" (Investing.com)
    if (m && MONTHS[m[1].toLowerCase()]) return validDay(Number(m[3]), MONTHS[m[1].toLowerCase()], Number(m[2]));
    const t = Date.parse(v);
    if (!Number.isFinite(t)) return null;
    const dt = new Date(t);
    return E.dayFromYMD(dt.getFullYear(), dt.getMonth() + 1, dt.getDate());
  });
  return { days, format: "tự nhận diện" };
};

/** Bảng CSV -> {rows: [{day, rate}] theo thứ tự trong file, info}. */
E.parseTable = function (table) {
  if (table.header.length < 2) throw new DataError("File cần ít nhất 2 cột: Ngày và Tỷ giá.");
  const di = findColumn(table.header, DATE_COLUMNS);
  const ri = findRateColumn(table.header, di);
  if (di < 0 || ri < 0) {
    const thieu = [["cột Ngày", di], ["cột Tỷ giá", ri]].filter(x => x[1] < 0).map(x => x[0]).join(" và ");
    throw new DataError(`Không tìm thấy ${thieu} trong dòng tiêu đề của file. Dòng đầu tiên phải là tên cột, ví dụ ` +
      "Ngay,TyGia (mặc định), Date,Price (Investing.com) hoặc Date,Close (Yahoo Finance).");
  }
  const raw = table.rows.filter(r => r.some(c => String(c).trim() !== ""));
  const { days, format } = E.parseDates(raw.map(r => r[di] ?? ""));
  if (days.filter(d => d !== null).length < 0.8 * raw.length)
    throw new DataError(`Cột '${table.header[di]}' không đúng định dạng ngày (dd/mm/yyyy, yyyy-mm-dd hoặc mm/dd/yyyy).`);
  const rates = raw.map(r => E.parseNumber(r[ri] ?? ""));
  if (rates.filter(Number.isFinite).length < 0.8 * raw.length)
    throw new DataError(`Cột '${table.header[ri]}' không phải số tỷ giá (ví dụ 26345 hoặc 26.345,50).`);
  return { rows: raw.map((_, i) => ({ day: days[i], rate: rates[i] })),
           info: { date_column: table.header[di], rate_column: table.header[ri], date_format: format } };
};

// ======================================================================== Làm sạch 6 bước (data_io.clean)

const fmtNum = (x, nd) => new Intl.NumberFormat("en-US", { minimumFractionDigits: nd, maximumFractionDigits: nd }).format(x);
E.vn = (x, nd) => new Intl.NumberFormat("vi-VN", { minimumFractionDigits: nd, maximumFractionDigits: nd }).format(x);

E.clean = function (rows, cfg) {
  const log = [], n0 = rows.length;
  const badDate = rows.filter(r => r.day === null).length;
  log.push(`Bước 1 – Chuẩn hóa định dạng ngày: ${n0 - badDate} dòng đọc được ngày` +
           (badDate ? `, bỏ ${badDate} dòng không đọc được ngày.` : "."));
  let df = rows.filter(r => r.day !== null).map((r, i) => ({ day: r.day, rate: r.rate, i }));
  df.sort((a, b) => a.day - b.day || a.i - b.i);              // sắp xếp ổn định
  log.push("Bước 2 – Sắp xếp tăng dần theo thời gian" +
           (df.length ? `: ${E.fmtVN(df[0].day)} → ${E.fmtVN(df[df.length - 1].day)}.` : "."));
  const kept = [];
  let dup = 0;
  for (let i = 0; i < df.length; i++) {
    if (i + 1 < df.length && df[i + 1].day === df[i].day) { dup++; continue; }  // giữ dòng cuối
    kept.push(df[i]);
  }
  log.push(`Bước 3 – Loại trùng lặp: ${dup} dòng trùng ngày` + (dup ? " (giữ dòng cuối)." : "."));
  df = kept;
  const bad = df.filter(r => !Number.isFinite(r.rate) || r.rate <= 0).length;
  log.push(`Bước 4 – Kiểm tra giá trị âm hoặc bằng 0: ${bad} dòng tỷ giá trống, âm hoặc bằng 0` + (bad ? " (đã loại)." : "."));
  df = df.filter(r => Number.isFinite(r.rate) && r.rate > 0);
  if (n0 && df.length < 0.8 * n0) throw new DataError(`Chỉ ${df.length}/${n0} dòng hợp lệ. Hãy kiểm tra cột ngày và cột tỷ giá.`);

  // Bước 5: dị thường
  const y = df.map(r => r.rate), drop = new Set();
  for (let i = 1; i < y.length - 1; i++)
    if (Math.abs(y[i] / y[i - 1] - 1) > cfg.anomaly_jump && Math.abs(y[i + 1] / y[i - 1] - 1) <= cfg.anomaly_revert) drop.add(i);
  const removed = df.filter((_, i) => drop.has(i));
  df = df.filter((_, i) => !drop.has(i));
  log.push(`Bước 5 – Kiểm tra điểm dị thường bằng thay đổi phần trăm liên tiếp (|%Δ| > ${Math.round(cfg.anomaly_jump * 100)}% ` +
           `rồi hôm sau quay về trong ${(cfg.anomaly_revert * 100).toFixed(1)}%): ${removed.length} điểm` + (removed.length ? " (đã loại):" : "."));
  for (const r of removed) log.push(`    · ${E.fmtVN(r.day)}: ${fmtNum(r.rate, 2)}`);

  // Bước 6: lịch ngày làm việc, không nội suy
  const weekend = df.filter(r => E.weekday(r.day) >= 5).length;
  df = df.filter(r => E.weekday(r.day) < 5);
  let missing = 0;
  if (df.length > 1) {
    let full = 0;
    for (let d = df[0].day; d <= df[df.length - 1].day; d++) if (E.weekday(d) < 5) full++;
    missing = full - df.length;
  }
  log.push(`Bước 6 – Đối chiếu tính liên tục của lịch quan sát: bỏ ${weekend} dòng rơi vào thứ 7/chủ nhật; ` +
           `${missing} ngày làm việc không có quan sát (lễ, nghỉ) – không nội suy thêm.`);
  if (df.length < cfg.min_rows) throw new DataError(`Chỉ còn ${df.length} dòng hợp lệ, cần ít nhất ${cfg.min_rows}.`);
  const stats = { rows_in: n0, rows_out: df.length, rows_removed: n0 - df.length, anomalies: removed.length,
                  missing_business_days: missing };
  return { days: df.map(r => r.day), y: df.map(r => r.rate), log, stats };
};

// ======================================================================== OLS (QR Householder)

/** X: mảng cột (k cột, mỗi cột n phần tử). Trả về {beta, se, ssr, n, k, llf, aic, resid}. */
E.ols = function (cols, yv) {
  const k = cols.length, n = yv.length;
  const A = cols.map(c => Float64Array.from(c));
  const b = Float64Array.from(yv);
  const R = Array.from({ length: k }, () => new Float64Array(k));
  for (let j = 0; j < k; j++) {
    const a = A[j];
    let norm = 0;
    for (let i = j; i < n; i++) norm += a[i] * a[i];
    norm = Math.sqrt(norm);
    const alpha = a[j] > 0 ? -norm : norm;
    const v = new Float64Array(n);
    v[j] = a[j] - alpha;
    for (let i = j + 1; i < n; i++) v[i] = a[i];
    let vv = 0;
    for (let i = j; i < n; i++) vv += v[i] * v[i];
    if (vv === 0) continue;
    for (let c = j; c < k; c++) {
      const col = A[c]; let dot = 0;
      for (let i = j; i < n; i++) dot += v[i] * col[i];
      const f = 2 * dot / vv;
      for (let i = j; i < n; i++) col[i] -= f * v[i];
    }
    let dot = 0;
    for (let i = j; i < n; i++) dot += v[i] * b[i];
    const f = 2 * dot / vv;
    for (let i = j; i < n; i++) b[i] -= f * v[i];
  }
  for (let i = 0; i < k; i++) for (let j = i; j < k; j++) R[i][j] = A[j][i];
  const beta = new Float64Array(k);
  for (let i = k - 1; i >= 0; i--) {
    let s = b[i];
    for (let j = i + 1; j < k; j++) s -= R[i][j] * beta[j];
    beta[i] = s / R[i][i];
  }
  let ssr = 0;
  for (let i = k; i < n; i++) ssr += b[i] * b[i];
  // (R'R)^-1 = R^-1 R^-T
  const Ri = Array.from({ length: k }, () => new Float64Array(k));
  for (let i = k - 1; i >= 0; i--) {
    Ri[i][i] = 1 / R[i][i];
    for (let j = i + 1; j < k; j++) {
      let s = 0;
      for (let l = i + 1; l <= j; l++) s += R[i][l] * Ri[l][j];
      Ri[i][j] = -s / R[i][i];
    }
  }
  const s2 = ssr / (n - k), se = new Float64Array(k);
  for (let i = 0; i < k; i++) { let s = 0; for (let j = i; j < k; j++) s += Ri[i][j] * Ri[i][j]; se[i] = Math.sqrt(s * s2); }
  const resid = new Float64Array(n);
  for (let i = 0; i < n; i++) { let f = 0; for (let j = 0; j < k; j++) f += cols[j][i] * beta[j]; resid[i] = yv[i] - f; }
  const llf = -n / 2 * (Math.log(2 * Math.PI) + Math.log(ssr / n) + 1);
  return { beta, se, ssr, n, k, llf, aic: -2 * llf + 2 * k, resid };
};

// ======================================================================== Bảng 4.1

E.flatDays = function (y) {
  let n = 0;
  for (let i = 1; i < y.length; i++) if (y[i] === y[i - 1]) n++;
  return { flat_days: n, flat_days_pct: y.length > 1 ? 100 * n / (y.length - 1) : null };
};

E.descriptive = function (days, y) {
  const first = y[0], last = y[y.length - 1];
  let iMax = 0;
  for (let i = 1; i < y.length; i++) if (y[i] > y[iMax]) iMax = i;
  return Object.assign({
    n_obs: y.length, start_date: E.fmtISO(days[0]), end_date: E.fmtISO(days[days.length - 1]),
    first, last, min: Math.min(...y), max: Math.max(...y), max_date: E.fmtISO(days[iMax]),
    mean: mean(y), median: median(y), std: std(y, 1),
    change_abs: last - first, change_pct: (last / first - 1) * 100, vnd_depreciation_pct: (1 - first / last) * 100,
  }, E.flatDays(y));
};

// ======================================================================== ADF + Phillips–Perron (Bảng 4.2)
// Bảng MacKinnon (1994, 2010) – giống statsmodels.tsa.adfvalues và arch.

const MK = {
  star: { c: -1.61, ct: -2.89 }, min: { c: -18.83, ct: -16.18 }, max: { c: 2.74, ct: 0.7 },
  small: { c: [2.1659, 1.4412, 3.8269e-2], ct: [3.2512, 1.6047, 4.9588e-2] },
  large: { c: [1.7339, 9.3202e-1, -1.2745e-1, -1.0368e-2], ct: [2.5261, 6.1654e-1, -3.7956e-1, -6.0285e-2] },
  crit: {
    c: [[-3.43035, -6.5393, -16.786, -79.433], [-2.86154, -2.8903, -4.234, -40.04], [-2.56677, -1.5384, -2.809, 0]],
    ct: [[-3.95877, -9.0531, -28.428, -134.155], [-3.41049, -4.3904, -9.036, -45.374], [-3.12705, -2.5856, -3.925, -22.38]],
  },
};
function mackinnonp(stat, reg) {
  if (stat > MK.max[reg]) return 1;
  if (stat < MK.min[reg]) return 0;
  const c = stat <= MK.star[reg] ? MK.small[reg] : MK.large[reg];
  let v = 0;
  for (let i = c.length - 1; i >= 0; i--) v = v * stat + c[i];
  return E.normCdf(v);
}
function mackinnoncrit(reg, nobs) {
  const out = {};
  ["1%", "5%", "10%"].forEach((lv, i) => {
    const c = MK.crit[reg][i];
    out[lv] = c[0] + c[1] / nobs + c[2] / nobs ** 2 + c[3] / nobs ** 3;
  });
  return out;
}

function trendCols(reg, n) {
  const cols = [new Float64Array(n).fill(1)];
  if (reg === "ct") cols.push(Float64Array.from({ length: n }, (_, i) => i + 1));
  return cols;
}

/** statsmodels.adfuller(x, regression, autolag="AIC") */
E.adf = function (x, reg) {
  const n = x.length, ntrend = reg.length;
  const xd = new Float64Array(n - 1);
  for (let i = 1; i < n; i++) xd[i - 1] = x[i] - x[i - 1];
  let maxlag = Math.ceil(12 * Math.pow(n / 100, 0.25));
  maxlag = Math.min(Math.floor(n / 2) - ntrend - 1, maxlag);
  const design = lag => {                                  // các hàng t = lag..n-2 của xd
    const nobs = xd.length - lag;
    const level = new Float64Array(nobs), lags = [];
    for (let i = 0; i < nobs; i++) level[i] = x[n - nobs - 1 + i];
    for (let j = 1; j <= lag; j++) {
      const c = new Float64Array(nobs);
      for (let i = 0; i < nobs; i++) c[i] = xd[lag + i - j];
      lags.push(c);
    }
    return { nobs, level, lags, yv: xd.subarray(xd.length - nobs) };
  };
  // Chọn độ trễ theo AIC trên cùng mẫu (cắt maxlag dòng đầu)
  const full = design(maxlag);
  const tc = trendCols(reg, full.nobs);
  let best = null;
  for (let lag = 0; lag <= maxlag; lag++) {
    const r = E.ols([...tc, full.level, ...full.lags.slice(0, lag)], full.yv);
    if (!best || r.aic < best.aic) best = { aic: r.aic, lag };
  }
  const d = design(best.lag);
  const r = E.ols([d.level, ...d.lags, ...trendCols(reg, d.nobs)], d.yv);
  const stat = r.beta[0] / r.se[0];
  return { stat, pvalue: mackinnonp(stat, reg), crit: mackinnoncrit(reg, d.nobs), lags: best.lag, nobs: d.nobs };
};

/** arch.unitroot.PhillipsPerron(x, trend, test_type="tau") */
E.pp = function (x, reg) {
  const n0 = x.length, lags = Math.ceil(12 * Math.pow(n0 / 100, 0.25));
  const lhs = x.slice(1), rhs = x.slice(0, -1), n = lhs.length;
  const cols = [Float64Array.from(rhs), ...trendCols(reg, n)];
  const r = E.ols(cols, Float64Array.from(lhs));
  const u = r.resid, k = cols.length;
  let lam2 = 0;
  for (let i = 0; i < n; i++) lam2 += u[i] * u[i];
  for (let j = 1; j <= lags; j++) {
    let g = 0;
    for (let i = j; i < n; i++) g += u[i] * u[i - j];
    lam2 += 2 * (1 - j / (lags + 1)) * g;
  }
  lam2 /= n;
  const lam = Math.sqrt(lam2), s2 = r.ssr / (n - k), s = Math.sqrt(s2), gamma0 = s2 * (n - k) / n;
  const sigma = r.se[0], rho = r.beta[0];
  const stat = Math.sqrt(gamma0 / lam2) * ((rho - 1) / sigma) - 0.5 * ((lam2 - gamma0) / lam) * (n * sigma / s);
  return { stat, pvalue: mackinnonp(stat, reg), crit: mackinnoncrit(reg, n), lags };
};

const LEVELS = [["a", "1%"], ["b", "5%"], ["c", "10%"]];
const mark = (stat, crit) => { for (const [m, lv] of LEVELS) if (stat < crit[lv]) return m; return ""; };

E.stationarity = function (y) {
  const dy = [];
  for (let i = 1; i < y.length; i++) dy.push(y[i] - y[i - 1]);
  const rows = [];
  for (const [name, x] of [["EXR", y], ["D.EXR", dy]])
    for (const [test, fn] of [["ADF", E.adf], ["PP", E.pp]])
      for (const [trend, label] of [["c", "Intercept"], ["ct", "Intercept & trend"]]) {
        const r = fn(Float64Array.from(x), trend);
        rows.push({ series: name, test, form: label, trend, stat: r.stat, pvalue: r.pvalue, mark: mark(r.stat, r.crit), crit: r.crit });
      }
  const stationary = name => ["a", "b"].includes(rows.find(r => r.series === name && r.test === "ADF" && r.trend === "c").mark);
  const d = stationary("EXR") ? 0 : stationary("D.EXR") ? 1 : 2;
  const text = { 0: "Chuỗi dừng ở bậc gốc: I(0).", 1: "Chuỗi không dừng ở bậc gốc nhưng dừng ở sai phân bậc 1: I(1).",
                 2: "Chuỗi chưa dừng ở sai phân bậc 1 (d = 2)." }[d];
  return { rows, conclusion: { d, text } };
};

})(E);
if (typeof module !== "undefined") module.exports = E;
