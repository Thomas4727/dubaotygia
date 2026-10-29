/* Phần 3: đặc trưng (features.py), chia dữ liệu (splits.py) và ba mô hình học máy (models.py):
   ANN (MLP, ReLU, Adam, dropout – như PyTorch), Random Forest (CART, như scikit-learn), XGBoost (hist, như xgboost).
   Ma trận lưu dạng Float64Array theo hàng: X[i * k + j]. */
var E = (typeof E !== "undefined") ? E : {};
(function (E) {
"use strict";

// ======================================================================== Đặc trưng (features.py)

/** w = null (ANN): chỉ p trễ của sai phân. Có w (RF, XGB): Lag, Return, MA, STD, khoảng cách tới MA, Momentum.
    Mục tiêu tại dòng t là Δy_{t+1}. */
E.buildFeatures = function (y, p, w) {
  const n = y.length, d = new Float64Array(n);
  d[0] = NaN;
  for (let t = 1; t < n; t++) d[t] = y[t] - y[t - 1];
  const names = [];
  for (let l = 0; l < p; l++) names.push("d_lag" + l);
  if (w !== null && w !== undefined) names.push("r", "d_mean_" + w, "d_std_" + w, "y_minus_ma_" + w, "momentum_" + w);
  const k = names.length, X = new Float64Array(n * k).fill(NaN), target = new Float64Array(n);
  for (let t = 0; t < n; t++) {
    target[t] = t + 1 < n ? y[t + 1] - y[t] : NaN;
    const o = t * k;
    for (let l = 0; l < p; l++) X[o + l] = t - l >= 1 ? d[t - l] : NaN;
    if (k === p) continue;
    X[o + p] = t >= 1 ? d[t] / y[t - 1] : NaN;
    if (t >= w) {                                   // cửa sổ d[t−w+1..t] đều có giá trị khi t ≥ w
      let s = 0, s2 = 0, sy = 0;
      for (let i = t - w + 1; i <= t; i++) { s += d[i]; sy += y[i]; }
      const m = s / w;
      for (let i = t - w + 1; i <= t; i++) s2 += (d[i] - m) ** 2;
      X[o + p + 1] = m;
      X[o + p + 2] = Math.sqrt(s2 / (w - 1));
      X[o + p + 3] = y[t] - sy / w;
      X[o + p + 4] = y[t] - y[t - w];
    } else if (t >= w - 1) {
      let sy = 0;
      for (let i = t - w + 1; i <= t; i++) sy += y[i];
      X[o + p + 3] = y[t] - sy / w;
    }
  }
  return { X, k, target, names };
};

// ======================================================================== Chia dữ liệu (splits.py)

const range = (a, b) => { const r = new Int32Array(Math.max(0, b - a)); for (let i = 0; i < r.length; i++) r[i] = a + i; return r; };
E.range = range;
const pyRound = x => { const r = Math.round(x); return (Math.abs(x % 1) === 0.5 && r % 2 !== 0) ? r - 1 : r; };  // làm tròn kiểu Python
E.pyRound = pyRound;

E.makeSplit = function (nObs, testRatio, valRatio, firstRow) {
  const nTest = pyRound(nObs * testRatio), nDev = nObs - nTest, nTrain = nDev - pyRound(nDev * valRatio);
  if (nTrain - 1 - firstRow < 20) throw new E.DataError("Không đủ dữ liệu để chia train/validation/test (cần thêm quan sát).");
  return { n_obs: nObs, n_dev: nDev, n_train: nTrain, first_row: firstRow,
           train_rows: range(firstRow, nTrain - 1), val_rows: range(nTrain - 1, nDev - 1), dev_rows: range(firstRow, nDev - 1),
           test_rows: range(nDev - 1, nObs - 1), all_rows: range(firstRow, nObs - 1) };
};
E.expandingFolds = function (n, k, firstFrac) {
  const valLen = Math.floor(pyRound(n * (1 - firstFrac)) / k);
  if (valLen < 1) throw new E.DataError(`Không đủ dữ liệu cho ${k} fold.`);
  const start = n - k * valLen, out = [];
  for (let i = 0; i < k; i++) out.push([range(0, start + i * valLen), range(start + i * valLen, start + (i + 1) * valLen)]);
  return out;
};
function earlyStopSplit(nTrain, frac) {
  const nEs = Math.max(1, pyRound(nTrain * frac));
  return [range(0, nTrain - nEs), range(nTrain - nEs, nTrain)];
}

// ======================================================================== Chuẩn hóa (StandardScaler)

function take(X, k, rows) {
  const out = new Float64Array(rows.length * k);
  for (let r = 0; r < rows.length; r++) out.set(X.subarray(rows[r] * k, rows[r] * k + k), r * k);
  return out;
}
function scalerFit(X, n, k) {
  const mu = new Float64Array(k), sd = new Float64Array(k);
  for (let i = 0; i < n; i++) for (let j = 0; j < k; j++) mu[j] += X[i * k + j];
  for (let j = 0; j < k; j++) mu[j] /= n;
  for (let i = 0; i < n; i++) for (let j = 0; j < k; j++) sd[j] += (X[i * k + j] - mu[j]) ** 2;
  for (let j = 0; j < k; j++) { sd[j] = Math.sqrt(sd[j] / n); if (!(sd[j] > 1e-300)) sd[j] = 1; }
  return { mu, sd };
}
function scalerApply(sc, X, n, k) {
  const out = new Float64Array(n * k);
  for (let i = 0; i < n; i++) for (let j = 0; j < k; j++) out[i * k + j] = (X[i * k + j] - sc.mu[j]) / sc.sd[j];
  return out;
}

// ======================================================================== ANN: MLP (ReLU, dropout, Adam, MSE)

function trainANN(X, n, k, yv, prm, seed) {
  const rng = E.makeRng(seed);
  const dims = [k];
  for (let l = 0; l < prm.n_layers; l++) dims.push(prm.units);
  dims.push(1);
  const L = dims.length - 1, W = [], b = [], mW = [], vW = [], mb = [], vb = [], gW = [], gb = [];
  for (let l = 0; l < L; l++) {
    const fin = dims[l], fout = dims[l + 1], bound = 1 / Math.sqrt(fin);       // khởi tạo mặc định của PyTorch
    const w = new Float64Array(fout * fin), bb = new Float64Array(fout);
    for (let i = 0; i < w.length; i++) w[i] = (2 * rng.random() - 1) * bound;
    for (let i = 0; i < fout; i++) bb[i] = (2 * rng.random() - 1) * bound;
    W.push(w); b.push(bb);
    mW.push(new Float64Array(w.length)); vW.push(new Float64Array(w.length)); gW.push(new Float64Array(w.length));
    mb.push(new Float64Array(fout)); vb.push(new Float64Array(fout)); gb.push(new Float64Array(fout));
  }
  const bs = prm.batch_size, pdrop = prm.dropout, keep = 1 / (1 - pdrop), lr = prm.learning_rate;
  const b1 = 0.9, b2 = 0.999, eps = 1e-8;
  // Bộ nhớ đệm cho 1 mini-batch: A[l] = đầu vào của lớp l (sau ReLU và dropout), R[l] = ReLU trước dropout
  const A = dims.map(d => new Float64Array(bs * d)), Rl = dims.map(d => new Float64Array(bs * d)), M = dims.map(d => new Float64Array(bs * d));
  const D = dims.map(d => new Float64Array(bs * d));
  let step = 0;
  for (let ep = 0; ep < prm.epochs; ep++) {
    const order = rng.permutation(n);
    for (let s0 = 0; s0 < n; s0 += bs) {
      const B = Math.min(bs, n - s0);
      for (let r = 0; r < B; r++) A[0].set(X.subarray(order[s0 + r] * k, order[s0 + r] * k + k), r * k);
      // Lan truyền xuôi
      for (let l = 0; l < L; l++) {
        const fin = dims[l], fout = dims[l + 1], w = W[l], bb = b[l], ain = A[l], aout = A[l + 1];
        const hidden = l < L - 1;
        for (let r = 0; r < B; r++) {
          const ro = r * fin, oo = r * fout;
          for (let o = 0; o < fout; o++) {
            let z = bb[o];
            const wo = o * fin;
            for (let i = 0; i < fin; i++) z += w[wo + i] * ain[ro + i];
            if (hidden) {
              const rr = z > 0 ? z : 0;
              Rl[l + 1][oo + o] = rr;
              let m = 1;
              if (pdrop > 0) m = rng.random() < pdrop ? 0 : keep;
              M[l + 1][oo + o] = m;
              aout[oo + o] = rr * m;
            } else aout[oo + o] = z;
          }
        }
      }
      // Lan truyền ngược (MSE trung bình trên mini-batch)
      const out = A[L], dl = D[L];
      for (let r = 0; r < B; r++) dl[r] = 2 * (out[r] - yv[order[s0 + r]]) / B;
      for (let l = L - 1; l >= 0; l--) {
        const fin = dims[l], fout = dims[l + 1], w = W[l], gw = gW[l], gbb = gb[l], ain = A[l], dout = D[l + 1], din = D[l];
        gw.fill(0); gbb.fill(0);
        if (l > 0) din.fill(0, 0, B * fin);
        for (let r = 0; r < B; r++) {
          const ro = r * fin, oo = r * fout;
          for (let o = 0; o < fout; o++) {
            const g = dout[oo + o];
            if (g === 0) continue;
            gbb[o] += g;
            const wo = o * fin;
            for (let i = 0; i < fin; i++) gw[wo + i] += g * ain[ro + i];
            if (l > 0) for (let i = 0; i < fin; i++) din[ro + i] += g * w[wo + i];
          }
        }
        if (l > 0) {
          const R = Rl[l], Mm = M[l];
          for (let i = 0; i < B * fin; i++) din[i] = R[i] > 0 ? din[i] * Mm[i] : 0;
        }
      }
      // Adam
      step++;
      const c1 = 1 - Math.pow(b1, step), c2 = 1 - Math.pow(b2, step);
      for (let l = 0; l < L; l++) {
        adam(W[l], gW[l], mW[l], vW[l]);
        adam(b[l], gb[l], mb[l], vb[l]);
      }
      function adam(p, g, m, v) {
        for (let i = 0; i < p.length; i++) {
          m[i] = b1 * m[i] + (1 - b1) * g[i];
          v[i] = b2 * v[i] + (1 - b2) * g[i] * g[i];
          p[i] -= lr * (m[i] / c1) / (Math.sqrt(v[i] / c2) + eps);
        }
      }
    }
  }
  return { dims, W, b };
}
function predictANN(net, X, n) {
  const { dims, W, b } = net, L = dims.length - 1, out = new Float64Array(n);
  let cur = new Float64Array(dims[0]), nxt;
  for (let r = 0; r < n; r++) {
    cur = X.subarray(r * dims[0], (r + 1) * dims[0]);
    for (let l = 0; l < L; l++) {
      const fin = dims[l], fout = dims[l + 1];
      nxt = new Float64Array(fout);
      for (let o = 0; o < fout; o++) {
        let z = b[l][o];
        for (let i = 0; i < fin; i++) z += W[l][o * fin + i] * cur[i];
        nxt[o] = l < L - 1 ? (z > 0 ? z : 0) : z;
      }
      cur = nxt;
    }
    out[r] = cur[0];
  }
  return out;
}

// ======================================================================== Random Forest (CART hồi quy, MSE)

function maxFeatures(mf, k) {
  if (mf === "sqrt") return Math.max(1, Math.floor(Math.sqrt(k)));
  if (mf === "log2") return Math.max(1, Math.floor(Math.log2(k)));
  if (mf === null || mf === undefined) return k;
  return Math.max(1, Math.floor(mf * k));
}

function fitRF(X, n, k, yv, prm, seed) {
  const rng = E.makeRng(seed);
  const order = [];
  for (let j = 0; j < k; j++) {
    const o = Array.from({ length: n }, (_, i) => i);
    o.sort((a, b) => X[a * k + j] - X[b * k + j]);
    order.push(Int32Array.from(o));
  }
  const nFeat = maxFeatures(prm.max_features, k);
  const nDraw = prm.bootstrap ? (prm.max_samples === null || prm.max_samples === undefined ? n : Math.max(1, pyRound(prm.max_samples * n))) : n;
  const minSplit = prm.min_samples_split, minLeaf = prm.min_samples_leaf;
  const maxDepth = prm.max_depth === null || prm.max_depth === undefined ? Infinity : prm.max_depth;
  const maxLeaves = prm.max_leaf_nodes === null || prm.max_leaf_nodes === undefined ? Infinity : prm.max_leaf_nodes;
  const trees = [], w = new Float64Array(n), goLeft = new Uint8Array(n);
  for (let t = 0; t < prm.n_estimators; t++) {
    w.fill(0);
    if (prm.bootstrap) for (let i = 0; i < nDraw; i++) w[rng.int(0, n)] += 1;
    else w.fill(1);
    let m = 0;
    for (let i = 0; i < n; i++) if (w[i] > 0) m++;
    const idx = order.map(o => { const a = new Int32Array(m); let c = 0; for (let i = 0; i < n; i++) if (w[o[i]] > 0) a[c++] = o[i]; return a; });
    const tmp = new Int32Array(m);
    const feat = [], thr = [], left = [], right = [], val = [];
    const newNode = () => { feat.push(-1); thr.push(0); left.push(-1); right.push(-1); val.push(0); return feat.length - 1; };

    function stats(start, end) {
      const a = idx[0];
      let W = 0, S = 0, S2 = 0;
      for (let p = start; p < end; p++) { const s = a[p], ws = w[s]; W += ws; S += ws * yv[s]; S2 += ws * yv[s] * yv[s]; }
      return { W, S, S2 };
    }
    function findSplit(nd) {
      const cnt = nd.end - nd.start;
      if (nd.depth >= maxDepth || cnt < minSplit || cnt < 2 * minLeaf) return null;
      if (nd.S2 / nd.W - (nd.S / nd.W) ** 2 <= 1e-7 * Math.max(1, Math.abs(nd.S2 / nd.W))) return null;
      const perm = rng.permutation(k);
      let visited = 0, best = null, bestProxy = -Infinity;
      for (let fi = 0; fi < k; fi++) {
        if (visited >= nFeat && best) break;
        const j = perm[fi], a = idx[j];
        if (X[a[nd.end - 1] * k + j] <= X[a[nd.start] * k + j] + 1e-7) continue;     // đặc trưng hằng số trong nút
        visited++;
        let wl = 0, sl = 0, cl = 0;
        for (let p = nd.start; p < nd.end - 1; p++) {
          const s = a[p];
          wl += w[s]; sl += w[s] * yv[s]; cl++;
          const xv = X[s * k + j], xn = X[a[p + 1] * k + j];
          if (xn <= xv + 1e-7) continue;
          if (cl < minLeaf) continue;
          if (cnt - cl < minLeaf) break;
          const wr = nd.W - wl, sr = nd.S - sl;
          const proxy = sl * sl / wl + sr * sr / wr;
          if (proxy > bestProxy) {
            bestProxy = proxy;
            let th = xv / 2 + xn / 2;
            if (th === xn) th = xv;
            best = { j, thr: th, pos: p, cl, wl, sl };
          }
        }
      }
      if (best) best.gain = bestProxy - nd.S * nd.S / nd.W;
      return best;
    }
    function makeChild(start, end, depth) {
      const st = stats(start, end);
      const nd = { id: newNode(), start, end, depth, W: st.W, S: st.S, S2: st.S2 };
      val[nd.id] = st.S / st.W;
      nd.split = findSplit(nd);
      return nd;
    }
    const frontier = [makeChild(0, m, 0)];
    let leaves = 1;
    while (frontier.length) {
      let pick = frontier.length - 1;
      if (maxLeaves !== Infinity) {
        for (let i = 0; i < frontier.length; i++) {
          const g = frontier[i].split ? frontier[i].split.gain : -Infinity;
          const gb = frontier[pick].split ? frontier[pick].split.gain : -Infinity;
          if (g > gb) pick = i;
        }
      }
      const nd = frontier.splice(pick, 1)[0];
      if (!nd.split || leaves >= maxLeaves) continue;               // giữ làm lá
      const sp = nd.split, aj = idx[sp.j];
      for (let p = nd.start; p < nd.end; p++) goLeft[aj[p]] = p <= sp.pos ? 1 : 0;
      for (let j = 0; j < k; j++) {
        const a = idx[j];
        let l = nd.start, r = 0;
        for (let p = nd.start; p < nd.end; p++) { const s = a[p]; if (goLeft[s]) a[l++] = s; else tmp[r++] = s; }
        a.set(tmp.subarray(0, r), l);
      }
      feat[nd.id] = sp.j; thr[nd.id] = sp.thr;
      const mid = nd.start + sp.cl;
      const L = makeChild(nd.start, mid, nd.depth + 1), R = makeChild(mid, nd.end, nd.depth + 1);
      left[nd.id] = L.id; right[nd.id] = R.id;
      leaves++;
      frontier.push(R, L);
    }
    trees.push({ feat: Int32Array.from(feat), thr: Float64Array.from(thr), left: Int32Array.from(left), right: Int32Array.from(right), val: Float64Array.from(val) });
  }
  return trees;
}
function predictTree(tr, X, k, r) {
  let nd = 0;
  while (tr.feat[nd] >= 0) nd = X[r * k + tr.feat[nd]] <= tr.thr[nd] ? tr.left[nd] : tr.right[nd];
  return tr.val[nd];
}
function predictRF(trees, X, n, k) {
  const out = new Float64Array(n);
  for (let r = 0; r < n; r++) { let s = 0; for (const t of trees) s += predictTree(t, X, k, r); out[r] = s / trees.length; }
  return out;
}

// ======================================================================== XGBoost (tree_method = "hist", depthwise)

const MAX_BIN = 256;
function makeCuts(X, n, k) {
  const cuts = [];
  for (let j = 0; j < k; j++) {
    const col = new Float64Array(n);
    for (let i = 0; i < n; i++) col[i] = X[i * k + j];
    col.sort();
    const uniq = [];
    for (let i = 0; i < n; i++) if (!uniq.length || col[i] !== uniq[uniq.length - 1]) uniq.push(col[i]);
    let th = [];
    if (uniq.length <= MAX_BIN) for (let i = 0; i + 1 < uniq.length; i++) th.push(uniq[i] / 2 + uniq[i + 1] / 2);
    else {
      for (let b = 1; b < MAX_BIN; b++) { const v = col[Math.floor(b * n / MAX_BIN)]; if (!th.length || v > th[th.length - 1]) th.push(v); }
      if (th[th.length - 1] >= uniq[uniq.length - 1]) th.pop();
    }
    cuts.push(Float64Array.from(th));
  }
  return cuts;
}
function binOf(th, x) {                       // số ngưỡng < x  (x ≤ th[b] ⇔ bin ≤ b)
  let lo = 0, hi = th.length;
  while (lo < hi) { const m = (lo + hi) >> 1; if (th[m] < x) lo = m + 1; else hi = m; }
  return lo;
}

function fitXGB(X, n, k, yv, Xes, nes, yes, prm, seed, esRounds) {
  const rng = E.makeRng(seed);
  const cuts = makeCuts(X, n, k), nb = cuts.map(c => c.length + 1);
  const B = new Uint16Array(n * k);
  for (let i = 0; i < n; i++) for (let j = 0; j < k; j++) B[i * k + j] = binOf(cuts[j], X[i * k + j]);
  const huber = prm.objective === "reg:pseudohubererror";
  const base = huber ? E.median(yv) : E.mean(yv);
  const mtr = new Float64Array(n).fill(base), mes = new Float64Array(nes).fill(base);
  const g = new Float64Array(n), h = new Float64Array(n);
  const lam = prm.reg_lambda, alpha = prm.reg_alpha, gamma = prm.gamma, mcw = prm.min_child_weight, eta = prm.learning_rate;
  const maxLeaves = prm.max_leaves > 0 ? prm.max_leaves : Infinity;
  const nCol = Math.max(1, Math.floor(prm.colsample_bytree * k));
  const thr1 = G => (G > alpha ? G - alpha : G < -alpha ? G + alpha : 0);
  const score = (G, H) => { const t = thr1(G); return t * t / (H + lam); };
  const leafW = (G, H) => -thr1(G) / (H + lam) * eta;
  const maxNb = Math.max(...nb);
  const hg = new Float64Array(maxNb), hh = new Float64Array(maxNb);
  const metric = () => {
    let s = 0;
    for (let i = 0; i < nes; i++) { const z = mes[i] - yes[i]; s += huber ? Math.sqrt(1 + z * z) - 1 : z * z; }
    return huber ? s / nes : Math.sqrt(s / nes);
  };
  const trees = [];
  let best = Infinity, bestIt = -1;

  function bestSplit(rows, G, H, cols) {
    let bestG = -Infinity, res = null;
    const parent = score(G, H), r = rows.length;
    for (const j of cols) {
      const nbj = nb[j];
      if (nbj < 2) continue;
      let gl = 0, hl = 0;
      if (r >= 64) {
        for (let p = 0; p < r; p++) { const s = rows[p], bb = B[s * k + j]; hg[bb] += g[s]; hh[bb] += h[s]; }
        for (let bb = 0; bb < nbj - 1; bb++) {
          gl += hg[bb]; hl += hh[bb];
          const gr = G - gl, hr = H - hl;
          if (hl >= mcw && hr >= mcw) {
            const gain = score(gl, hl) + score(gr, hr) - parent;
            if (gain > bestG) { bestG = gain; res = { j, bin: bb }; }
          }
        }
        hg.fill(0, 0, nbj); hh.fill(0, 0, nbj);
      } else {
        const tmp = Array.from(rows).sort((a, c) => B[a * k + j] - B[c * k + j]);
        for (let p = 0; p < r - 1; p++) {
          const s = tmp[p];
          gl += g[s]; hl += h[s];
          const bb = B[s * k + j];
          if (B[tmp[p + 1] * k + j] === bb) continue;
          const gr = G - gl, hr = H - hl;
          if (hl >= mcw && hr >= mcw) {
            const gain = score(gl, hl) + score(gr, hr) - parent;
            if (gain > bestG) { bestG = gain; res = { j, bin: bb }; }
          }
        }
      }
    }
    if (!res || !(bestG > 1e-6) || bestG < gamma) return null;
    res.gain = bestG;
    return res;
  }

  for (let it = 0; it < prm.n_estimators; it++) {
    for (let i = 0; i < n; i++) {
      const z = mtr[i] - yv[i];
      if (huber) { const q = 1 + z * z; g[i] = z / Math.sqrt(q); h[i] = 1 / (q * Math.sqrt(q)); }
      else { g[i] = z; h[i] = 1; }
    }
    const rowsArr = [];
    for (let i = 0; i < n; i++) if (prm.subsample >= 1 || rng.random() < prm.subsample) rowsArr.push(i);
    const cols = nCol >= k ? Array.from({ length: k }, (_, i) => i) : rng.choice(k, nCol);
    const feat = [], thr = [], left = [], right = [], val = [];
    const node = (rows) => {
      let G = 0, H = 0;
      for (const s of rows) { G += g[s]; H += h[s]; }
      feat.push(-1); thr.push(0); left.push(-1); right.push(-1); val.push(leafW(G, H));
      return { id: feat.length - 1, rows, G, H };
    };
    let level = [node(Int32Array.from(rowsArr))], leaves = 1;
    for (let depth = 0; depth < prm.max_depth && level.length; depth++) {
      const next = [];
      for (const nd of level) {
        if (leaves >= maxLeaves) break;
        const sp = bestSplit(nd.rows, nd.G, nd.H, cols);
        if (!sp) continue;
        const L = [], R = [];
        for (const s of nd.rows) (B[s * k + sp.j] <= sp.bin ? L : R).push(s);
        feat[nd.id] = sp.j; thr[nd.id] = cuts[sp.j][sp.bin];
        const ln = node(Int32Array.from(L)), rn = node(Int32Array.from(R));
        left[nd.id] = ln.id; right[nd.id] = rn.id;
        leaves++;
        next.push(ln, rn);
      }
      level = next;
    }
    const tr = { feat: Int32Array.from(feat), thr: Float64Array.from(thr), left: Int32Array.from(left), right: Int32Array.from(right), val: Float64Array.from(val) };
    trees.push(tr);
    for (let i = 0; i < n; i++) mtr[i] += predictTree(tr, X, k, i);
    for (let i = 0; i < nes; i++) mes[i] += predictTree(tr, Xes, k, i);
    const mv = metric();
    if (mv < best) { best = mv; bestIt = it; }
    else if (it - bestIt >= esRounds) break;
  }
  return { base, trees: trees.slice(0, bestIt + 1), best_iteration: bestIt };
}
function predictXGB(model, X, n, k) {
  const out = new Float64Array(n).fill(model.base);
  for (const t of model.trees) for (let r = 0; r < n; r++) out[r] += predictTree(t, X, k, r);
  return out;
}

// ======================================================================== fit_predict: hàm huấn luyện DUY NHẤT

/** Huấn luyện trên trainRows, dự báo Δy cho predRows. XGBoost dừng sớm trên esRows nếu có, ngược lại 15% cuối train. */
E.fitPredict = function (kind, prm, seed, F, trainRows, predRows, esRows, esFrac, esRounds) {
  const k = F.k, ntr = trainRows.length;
  const Xtr = take(F.X, k, trainRows), ytr = new Float64Array(ntr);
  for (let i = 0; i < ntr; i++) ytr[i] = F.target[trainRows[i]];
  const sc = scalerFit(Xtr, ntr, k);
  const Xs = scalerApply(sc, Xtr, ntr, k);
  const Xp = scalerApply(sc, take(F.X, k, predRows), predRows.length, k), np_ = predRows.length;
  if (kind === "ANN") {
    const my = E.mean(ytr);
    let sy = Math.sqrt(ytr.reduce((s, v) => s + (v - my) ** 2, 0) / ntr);
    if (!(sy > 1e-300)) sy = 1;
    const ys = ytr.map(v => (v - my) / sy);
    const net = trainANN(Xs, ntr, k, ys, prm, seed);
    return predictANN(net, Xp, np_).map(v => v * sy + my);
  }
  if (kind === "RF") return predictRF(fitRF(Xs, ntr, k, ytr, prm, seed), Xp, np_, k);
  if (kind === "XGB") {
    let Xf, yf, Xv, yvv, nf, nv;
    if (!esRows) {
      const [fi, ei] = earlyStopSplit(ntr, esFrac);
      Xf = take(Xs, k, fi); yf = Float64Array.from(fi, i => ytr[i]); nf = fi.length;
      Xv = take(Xs, k, ei); yvv = Float64Array.from(ei, i => ytr[i]); nv = ei.length;
    } else {
      Xf = Xs; yf = ytr; nf = ntr; nv = esRows.length;
      Xv = scalerApply(sc, take(F.X, k, esRows), nv, k); yvv = Float64Array.from(esRows, i => F.target[i]);
    }
    const model = fitXGB(Xf, nf, k, yf, Xv, nv, yvv, prm, seed, esRounds);
    return predictXGB(model, Xp, np_, k);
  }
  throw new Error(kind);
};

})(E);
if (typeof module !== "undefined") module.exports = E;
