/* Phần 2: ARIMA(p, d, q), trend = "n" (models.py mục 6.1).
   Hợp lý cực đại chính xác qua bộ lọc Kalman trên chuỗi sai phân bậc d (giống statsmodels khi khởi tạo khuếch tán
   phần tích hợp). Tham số ràng buộc dừng / khả nghịch như statsmodels; σ² được "cô đặc" khỏi hàm hợp lý. */
var E = (typeof E !== "undefined") ? E : {};
(function (E) {
"use strict";

// Tự tương quan riêng phần -> hệ số (Levinson–Durbin): luôn cho đa thức 1 − Σφ z^j ổn định
function pacfToCoef(x) {
  let phi = [];
  for (let k = 0; k < x.length; k++) {
    const r = x[k] / Math.sqrt(1 + x[k] * x[k]);
    const nw = new Array(k + 1);
    for (let i = 0; i < k; i++) nw[i] = phi[i] - r * phi[k - 1 - i];
    nw[k] = r;
    phi = nw;
  }
  return phi;
}
function unpack(theta, p, q) {
  return { ar: pacfToCoef(theta.slice(0, p)), ma: pacfToCoef(theta.slice(p, p + q)).map(v => -v) };
}

// Ma trận hiệp phương sai dừng P = T P T' + R R' (giải hệ tuyến tính m² ẩn)
function lyapunov(T, R, m) {
  const N = m * m, A = Array.from({ length: N }, () => new Float64Array(N + 1));
  for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) {
    const row = A[i * m + j];
    row[i * m + j] += 1;
    for (let k = 0; k < m; k++) for (let l = 0; l < m; l++) row[k * m + l] -= T[i][k] * T[j][l];
    row[N] = R[i] * R[j];
  }
  for (let c = 0; c < N; c++) {
    let piv = c;
    for (let r = c + 1; r < N; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r;
    const t = A[c]; A[c] = A[piv]; A[piv] = t;
    const d = A[c][c];
    if (Math.abs(d) < 1e-300) return null;
    for (let r = 0; r < N; r++) {
      if (r === c) continue;
      const f = A[r][c] / d;
      if (f !== 0) for (let k = c; k <= N; k++) A[r][k] -= f * A[c][k];
    }
  }
  const P = Array.from({ length: m }, () => new Float64Array(m));
  for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) P[i][j] = A[i * m + j][N] / A[i * m + j][i * m + j];
  return P;
}

/** Bộ lọc Kalman cho ARMA (σ² = 1). Trả về trạng thái để dự báo / cập nhật tiếp. */
function makeFilter(ar, ma) {
  const p = ar.length, q = ma.length, m = Math.max(p, q + 1);
  const T = Array.from({ length: m }, () => new Float64Array(m));
  for (let i = 0; i < m; i++) { if (i < p) T[i][0] = ar[i]; if (i + 1 < m) T[i][i + 1] = 1; }
  const R = new Float64Array(m);
  R[0] = 1;
  for (let j = 1; j < m; j++) R[j] = j - 1 < q ? ma[j - 1] : 0;
  const P = lyapunov(T, R, m);
  if (!P) return null;
  return { m, T, R, a: new Float64Array(m), P, steady: false, sumLogF: 0, sumV2F: 0, n: 0 };
}
function filterStep(f, yt) {
  const { m, T, R, a, P } = f;
  const F = P[0][0];
  const v = yt - a[0];
  f.sumLogF += Math.log(F); f.sumV2F += v * v / F; f.n++;
  if (f.steady) {
    const au = new Float64Array(m);
    for (let i = 0; i < m; i++) au[i] = a[i] + f.K[i] * v;
    predictState(f, au);
    return;
  }
  const au = new Float64Array(m), Pu = Array.from({ length: m }, () => new Float64Array(m));
  for (let i = 0; i < m; i++) au[i] = a[i] + P[i][0] * v / F;
  for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) Pu[i][j] = P[i][j] - P[i][0] * P[0][j] / F;
  predictState(f, au);
  // P = T Pu T' + R R'
  const TP = Array.from({ length: m }, () => new Float64Array(m));
  for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) { let s = 0; for (let k = 0; k < m; k++) s += T[i][k] * Pu[k][j]; TP[i][j] = s; }
  let diff = 0;
  for (let i = 0; i < m; i++) for (let j = 0; j < m; j++) {
    let s = R[i] * R[j];
    for (let k = 0; k < m; k++) s += TP[i][k] * T[j][k];
    diff = Math.max(diff, Math.abs(s - P[i][j]));
    P[i][j] = s;
  }
  if (diff < 1e-11) {                                     // hội tụ về trạng thái ổn định
    f.steady = true;
    f.K = new Float64Array(m);
    for (let i = 0; i < m; i++) f.K[i] = P[i][0] / P[0][0];
  }
}
function predictState(f, au) {
  const { m, T, a } = f;
  for (let i = 0; i < m; i++) { let s = 0; for (let k = 0; k < m; k++) s += T[i][k] * au[k]; a[i] = s; }
}
function cloneFilter(f) {
  return Object.assign({}, f, { a: Float64Array.from(f.a), P: f.P.map(r => Float64Array.from(r)), K: f.K && Float64Array.from(f.K) });
}

function diffSeries(y, d) {
  let x = Array.from(y);
  for (let k = 0; k < d; k++) x = x.slice(1).map((v, i) => v - x[i]);
  return x;
}

function negLogLik(theta, x, p, q) {
  const { ar, ma } = unpack(theta, p, q);
  const f = makeFilter(ar, ma);
  if (!f) return Infinity;
  for (let t = 0; t < x.length; t++) filterStep(f, x[t]);
  const n = f.n, s2 = f.sumV2F / n;
  const llf = -0.5 * n * (Math.log(2 * Math.PI) + 1 + Math.log(s2)) - 0.5 * f.sumLogF;
  return Number.isFinite(llf) ? -llf : Infinity;
}

// Nelder–Mead
function nelderMead(fn, x0, step, maxIter, tol) {
  const n = x0.length;
  let pts = [x0.slice()];
  for (let i = 0; i < n; i++) { const p = x0.slice(); p[i] += step; pts.push(p); }
  let vals = pts.map(fn);
  for (let it = 0; it < maxIter; it++) {
    const ord = vals.map((v, i) => i).sort((a, b) => vals[a] - vals[b]);
    pts = ord.map(i => pts[i]); vals = ord.map(i => vals[i]);
    if (Math.abs(vals[n] - vals[0]) <= tol * (Math.abs(vals[0]) + 1e-12)) {
      let spread = 0;
      for (let i = 1; i <= n; i++) for (let j = 0; j < n; j++) spread = Math.max(spread, Math.abs(pts[i][j] - pts[0][j]));
      if (spread < 1e-6) break;
    }
    const c = new Array(n).fill(0);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) c[j] += pts[i][j] / n;
    const at = t => c.map((cj, j) => cj + t * (pts[n][j] - cj));
    const xr = at(-1), fr = fn(xr);
    if (fr < vals[0]) {
      const xe = at(-2), fe = fn(xe);
      if (fe < fr) { pts[n] = xe; vals[n] = fe; } else { pts[n] = xr; vals[n] = fr; }
    } else if (fr < vals[n - 1]) { pts[n] = xr; vals[n] = fr; }
    else {
      const xc = fr < vals[n] ? at(-0.5) : at(0.5), fc = fn(xc);
      if (fc < Math.min(fr, vals[n])) { pts[n] = xc; vals[n] = fc; }
      else {
        for (let i = 1; i <= n; i++) { pts[i] = pts[i].map((v, j) => pts[0][j] + 0.5 * (v - pts[0][j])); vals[i] = fn(pts[i]); }
      }
    }
  }
  let b = 0;
  for (let i = 1; i <= n; i++) if (vals[i] < vals[b]) b = i;
  return { x: pts[b], f: vals[b] };
}

/** Ước lượng ARIMA(p,d,q) trên y (mức tỷ giá). */
E.fitArima = function (y, p, d, q, starts) {
  const x = diffSeries(y, d), k = p + q;
  let theta = new Array(k).fill(0), nll;
  if (k === 0) nll = negLogLik([], x, 0, 0);
  else {
    // Nhiều điểm xuất phát (0 và nghiệm của các cấu trúc nhỏ hơn) để tránh cực trị địa phương
    let res = null;
    for (const s0 of [theta].concat(starts || [])) {
      const r = nelderMead(t => negLogLik(t, x, p, q), s0, s0 === theta ? 0.5 : 0.2, 400 * k, 1e-10);
      if (!res || r.f < res.f) res = r;
    }
    for (let r = 0; r < 3; r++) {
      const again = nelderMead(t => negLogLik(t, x, p, q), res.x, 0.1, 400 * k, 1e-12);
      const gain = res.f - again.f;
      res = again.f <= res.f ? again : res;
      if (gain < 1e-7) break;
    }
    theta = res.x; nll = res.f;
  }
  if (!Number.isFinite(nll)) throw new Error("Không hội tụ");
  const { ar, ma } = unpack(theta, p, q);
  // σ² MLE
  const f = makeFilter(ar, ma);
  for (const v of x) filterStep(f, v);
  const sigma2 = f.sumV2F / f.n, llf = -nll, kp = p + q + 1, neff = x.length;
  return { order: [p, d, q], theta, ar, ma, sigma2, llf, aic: -2 * llf + 2 * kp, bic: -2 * llf + kp * Math.log(neff),
           hqic: -2 * llf + 2 * kp * Math.log(Math.log(neff)), nobs: y.length };
};

/** 25 cấu trúc (p, q ∈ 0..max) trên tập phát triển, sắp theo AIC (arima_structures). */
E.arimaStructures = function (yDev, d, maxP, maxQ, onStep) {
  const fits = {}, out = [], total = (maxP + 1) * (maxQ + 1);
  let i = 0;
  for (let p = 0; p <= maxP; p++) for (let q = 0; q <= maxQ; q++) {
    i++;
    if (onStep) onStep(i, total, [p, d, q]);
    const starts = [];
    const pad = (f, pp, qq) => f && starts.push(f.theta.slice(0, f.order[0]).concat(new Array(p - pp).fill(0),
      f.theta.slice(f.order[0]), new Array(q - qq).fill(0)));
    if (p > 0) pad(fits[(p - 1) + "," + q], p - 1, q);
    if (q > 0) pad(fits[p + "," + (q - 1)], p, q - 1);
    try {
      const f = E.fitArima(yDev, p, d, q, starts);
      fits[p + "," + q] = f;
      out.push(Object.assign({ trend: "n" }, f));
    } catch (e) {
      out.push({ order: [p, d, q], trend: "n", error: String(e.message || e), aic: Infinity });
    }
  }
  return out.sort((a, b) => a.aic - b.aic);
};

// y_i từ Δ^d y_i và các mức trước đó: y_i = Δ^d y_i − Σ_{k=1..d} (−1)^k C(d,k) y_{i−k}
function integrate(fcDiff, y, i, d) {
  const C = [[1], [1, 1], [1, 2, 1]][d];
  let s = fcDiff;
  for (let k = 1; k <= d; k++) s -= ((k % 2) ? -1 : 1) * C[k] * y[i - k];
  return s;
}

/** Dự báo 1 bước cho y[start..n−1], cập nhật quan sát thật từng ngày (append, refit=False), và dự báo sau quan sát
    cuối (T+1). Trả về {pred, lo, hi, t1: [dự báo, cận dưới, cận trên]}. */
E.arimaForecast = function (fit, y, start) {
  const d = fit.order[1], x = diffSeries(y, d);
  const f = makeFilter(fit.ar, fit.ma);
  const z = 1.959963984540054, pred = [], lo = [], hi = [];
  // x[j] = Δ^d y[j + d]
  for (let j = 0; j < start - d; j++) filterStep(f, x[j]);
  const one = i => {
    const mu = integrate(f.a[0], y, i, d), sd = Math.sqrt(fit.sigma2 * f.P[0][0]);
    return [mu, mu - z * sd, mu + z * sd];
  };
  for (let i = start; i < y.length; i++) {
    const [mu, l, h] = one(i);
    pred.push(mu); lo.push(l); hi.push(h);
    filterStep(f, x[i - d]);
  }
  return { pred, lo, hi, t1: one(y.length) };
};

})(E);
if (typeof module !== "undefined") module.exports = E;
