/* Phần 4: không gian tìm kiếm (search_space.py), bộ đếm ngân sách (budget.py), GA (ga.py), SA (sa.py),
   ngữ cảnh dùng chung và các "đơn vị việc" chạy trong Web Worker (pipeline.py: _task_eval, _task_hpo, _task_refit). */
var E = (typeof E !== "undefined") ? E : {};
(function (E) {
"use strict";

const SPECIAL_WIDTH = 0.1;
const P = (name, kind, low, high, opt) => Object.assign({ name, kind, low, high, log: false, choices: null, specials: [] }, opt || {});

function numDecode(p, u) {
  let v = p.log ? Math.exp(Math.log(p.low) + u * (Math.log(p.high) - Math.log(p.low))) : p.low + u * (p.high - p.low);
  v = Math.min(Math.max(v, p.low), p.high);
  return p.kind === "int" ? Math.round(v) : Number(v.toPrecision(6));
}
function numEncode(p, v) {
  v = Math.min(Math.max(v, p.low), p.high);
  return p.log ? (Math.log(v) - Math.log(p.low)) / (Math.log(p.high) - Math.log(p.low)) : (v - p.low) / (p.high - p.low);
}
function decodeParam(p, u) {
  u = Math.min(Math.max(Number(u), 0), 1);
  if (p.kind === "cat") return p.choices[Math.min(Math.floor(u * p.choices.length), p.choices.length - 1)];
  const region = p.specials.length * SPECIAL_WIDTH;
  if (u < region) return p.specials[Math.floor(u / SPECIAL_WIDTH)];
  return numDecode(p, region ? (u - region) / (1 - region) : u);
}
function encodeParam(p, v) {
  if (p.kind === "cat") return (p.choices.indexOf(v) + 0.5) / p.choices.length;
  const si = p.specials.indexOf(v);
  if (si >= 0) return (si + 0.5) * SPECIAL_WIDTH;
  const region = p.specials.length * SPECIAL_WIDTH;
  return region + (1 - region) * numEncode(p, v);
}

/** Miền giá trị: giống hệt bản Python (lựa chọn của web, bài không nêu miền). */
E.space = function (model, caps) {
  const common = [P("p", "int", 3, 30), P("w", "int", 5, 30)];
  if (model === "ANN") return [common[0],
    P("n_layers", "int", 1, 3), P("units", "int", 8, 128, { log: true }), P("learning_rate", "float", 1e-4, 1e-2, { log: true }),
    P("epochs", "int", 50, caps.ANN_epochs), P("batch_size", "cat", null, null, { choices: [16, 32, 64, 128] }),
    P("dropout", "float", 0, 0.5)];
  if (model === "RF") return common.concat([
    P("n_estimators", "int", 100, caps.RF_n_estimators), P("max_depth", "int", 3, 30, { specials: [null] }),
    P("max_features", "float", 0.3, 1.0, { specials: ["sqrt", "log2"] }), P("min_samples_split", "int", 2, 20),
    P("min_samples_leaf", "int", 1, 20), P("max_leaf_nodes", "int", 16, 512, { specials: [null] }),
    P("bootstrap", "cat", null, null, { choices: [true, false] }), P("max_samples", "float", 0.5, 1.0)]);
  if (model === "XGB") return common.concat([
    P("n_estimators", "int", 100, caps.XGB_n_estimators), P("learning_rate", "float", 0.005, 0.3, { log: true }),
    P("max_depth", "int", 2, 10), P("min_child_weight", "float", 1, 20), P("gamma", "float", 0, 5),
    P("subsample", "float", 0.5, 1.0), P("colsample_bytree", "float", 0.5, 1.0), P("max_leaves", "int", 8, 256, { specials: [0] }),
    P("reg_alpha", "float", 1e-4, 10, { log: true }), P("reg_lambda", "float", 1e-2, 10, { log: true }),
    P("objective", "cat", null, null, { choices: ["reg:squarederror", "reg:pseudohubererror"] })]);
  throw new Error(model);
};

E.BASELINES = {
  ANN: { p: 10, n_layers: 1, units: 64, learning_rate: 1e-3, epochs: 200, batch_size: 32, dropout: 0.1 },
  RF: { p: 10, w: 10, n_estimators: 500, max_depth: null, max_features: 1.0, min_samples_split: 2, min_samples_leaf: 1,
        max_leaf_nodes: null, bootstrap: true, max_samples: null },
  XGB: { p: 10, w: 10, n_estimators: 500, learning_rate: 0.05, max_depth: 4, subsample: 0.8, colsample_bytree: 0.8,
         min_child_weight: 1.0, gamma: 0.0, max_leaves: 0, reg_alpha: 0.0, reg_lambda: 1.0, objective: "reg:squarederror" },
};
function repair(model, params) {
  params = Object.assign({}, params);
  if (model === "RF" && params.bootstrap === false) params.max_samples = null;
  return params;
}
E.baseline = model => repair(model, E.BASELINES[model]);
E.decode = (model, vec, caps) => {
  const out = {};
  E.space(model, caps).forEach((p, i) => { out[p.name] = decodeParam(p, vec[i]); });
  return repair(model, out);
};
E.encode = (model, params, caps) => E.space(model, caps).map(p => {
  let v = params[p.name];
  if ((v === null || v === undefined) && p.name === "max_samples") v = 1.0;
  return encodeParam(p, v);
});
E.dim = (model, caps) => E.space(model, caps).length;
E.categoricalMask = (model, caps) => E.space(model, caps).map(p => p.kind === "cat");
E.paramsKey = params => JSON.stringify(Object.keys(params).sort().map(k => [k, params[k]]));
E.describeParam = p => {
  if (p.kind === "cat") return "{" + p.choices.join(", ") + "}";
  const rng = `[${p.low}, ${p.high}]` + (p.log ? " (log)" : "");
  return (p.specials.length ? "{" + p.specials.map(s => (s === null ? "None" : s)).join(", ") + "} ∪ " : "") + rng;
};

// ======================================================================== Ngân sách + cache (budget.py)

class BudgetExhausted extends Error {}
class StopSearch extends Error {}

function makeEvaluator(objective, budget, keyFn, onEval) {
  const ev = {
    cache: new Map(), n_evals: 0, n_trained: 0, best_j: Infinity, best_vector: null, history: [],
    call(vec) {
      if (ev.n_evals >= budget) throw new BudgetExhausted();
      ev.n_evals++;
      const key = keyFn(vec);
      if (!ev.cache.has(key)) { ev.cache.set(key, Number(objective(vec))); ev.n_trained++; }
      const j = ev.cache.get(key);
      if (j < ev.best_j) { ev.best_j = j; ev.best_vector = Array.from(vec); }
      ev.history.push(ev.best_j);
      if (onEval) onEval(ev);
      return j;
    },
  };
  return ev;
}

// ======================================================================== GA (ga.py)

const clip01 = v => Math.min(Math.max(v, 0), 1);

E.runGA = function (ev, dim, cat, rng, init, o, onGen) {
  let pop = [init.map(clip01)];
  for (let i = 1; i < o.pop_size; i++) pop.push(Array.from({ length: dim }, () => rng.random()));
  const tournament = fit => {
    const idx = rng.choice(fit.length, Math.min(o.tournament_k, fit.length));
    let b = idx[0];
    for (const i of idx) if (fit[i] < fit[b]) b = i;
    return b;
  };
  const mutate = c => c.map((v, g) => (rng.random() < o.p_mutation ? (cat[g] ? rng.random() : clip01(v + rng.normal(0, o.sigma))) : v));
  let generation = 0, stall = 0, stop = `đủ ${o.max_generations} thế hệ`, fitness = [];
  try {
    for (const ind of pop) fitness.push(ev.call(ind));
    let best = Math.min(...fitness);
    if (onGen) onGen(0);
    while (generation < o.max_generations) {
      generation++;
      const order = fitness.map((_, i) => i).sort((a, b) => fitness[a] - fitness[b]);
      const np = order.slice(0, o.elitism).map(i => pop[i]), nf = order.slice(0, o.elitism).map(i => fitness[i]);
      while (np.length < o.pop_size) {
        const a = pop[tournament(fitness)], b = pop[tournament(fitness)];
        let child = rng.random() < o.p_crossover ? a.map((v, g) => (rng.random() < 0.5 ? v : b[g])) : a.slice();
        child = mutate(child);
        nf.push(ev.call(child));
        np.push(child);
      }
      pop = np; fitness = nf;
      const mn = Math.min(...fitness);
      if (mn < best) { best = mn; stall = 0; } else stall++;
      if (onGen) onGen(generation);
      if (stall >= o.patience) { stop = `${o.patience} thế hệ liên tiếp không cải thiện`; break; }
    }
  } catch (e) {
    if (!(e instanceof BudgetExhausted)) throw e;
    stop = "hết ngân sách đánh giá";
  }
  return { best_vector: ev.best_vector, best_j: ev.best_j, n_evals: ev.n_evals, generations: generation, stop_reason: stop };
};

// ======================================================================== SA (sa.py)

function neighbor(x, cat, rng, sigma) {
  const y = x.slice();
  for (const g of rng.choice(x.length, Math.min(x.length, rng.int(1, 3))))
    y[g] = cat[g] ? rng.random() : clip01(y[g] + rng.normal(0, sigma));
  return y;
}

E.runSA = function (ev, dim, cat, rng, init, o, onStep) {
  let current = init.map(clip01), T0 = null, T = null, stop = "hết ngân sách đánh giá";
  try {
    let jCur = ev.call(current);
    const deltas = [];
    for (let i = 0; i < o.t0_samples; i++) {
      const j = ev.call(neighbor(current, cat, rng, o.sigma));
      if (j > jCur) deltas.push(j - jCur);
    }
    const meanUp = deltas.length ? E.mean(deltas) : Math.max(Math.abs(jCur) * 1e-3, 1e-9);
    T0 = T = -meanUp / Math.log(o.accept0);
    if (onStep) onStep(T);
    let since = 0;
    for (;;) {
      for (let i = 0; i < o.moves_per_temp; i++) {
        if (T < o.t_min_ratio * T0) throw new StopSearch("nhiệt độ dưới ngưỡng T_min");
        if (since >= o.patience) throw new StopSearch(`${o.patience} lần đánh giá liên tiếp không cải thiện`);
        const cand = neighbor(current, cat, rng, o.sigma);
        const before = ev.best_j;
        const j = ev.call(cand), delta = j - jCur;
        if (delta <= 0 || rng.random() < Math.exp(-delta / T)) { current = cand; jCur = j; }
        since = ev.best_j < before ? 0 : since + 1;
        if (onStep) onStep(T);
      }
      T *= o.cooling;
    }
  } catch (e) {
    if (e instanceof StopSearch) stop = e.message;
    else if (!(e instanceof BudgetExhausted)) throw e;
  }
  return { best_vector: ev.best_vector, best_j: ev.best_j, n_evals: ev.n_evals, T0, T_final: T, stop_reason: stop };
};

// ======================================================================== Ngữ cảnh (pipeline.Context)

E.Context = function (y, cfg) {
  this.y = Float64Array.from(y);
  this.cfg = cfg;
  this.split = E.makeSplit(y.length, cfg.test_ratio, cfg.val_ratio, Math.max(cfg.max_lag, cfg.max_window));
  this.folds = E.expandingFolds(this.split.dev_rows.length, cfg.n_folds, cfg.cv_first_train_frac);
  this._feat = new Map();
};
E.Context.prototype.features = function (p, w) {
  const key = p + "|" + w;
  if (!this._feat.has(key)) {
    if (this._feat.size > 40) this._feat.clear();
    this._feat.set(key, E.buildFeatures(this.y, p, w));
  }
  return this._feat.get(key);
};
/** Huấn luyện + dự báo, trả về MỨC tỷ giá dự báo cho predRows: ŷ_{t+1} = y_t + Δŷ_{t+1}. */
E.Context.prototype.run = function (kind, params, seed, trainRows, predRows, esRows) {
  const F = this.features(params.p, kind === "ANN" ? null : params.w);
  const mp = Object.assign({}, params); delete mp.p; delete mp.w;
  const delta = E.fitPredict(kind, mp, seed, F, trainRows, predRows, esRows || null, this.cfg.es_frac, this.cfg.es_rounds);
  const out = new Array(predRows.length);
  for (let i = 0; i < predRows.length; i++) out[i] = this.y[predRows[i]] + delta[i];
  return out;
};
const sub = (arr, idx) => Int32Array.from(idx, i => arr[i]);
E.Context.prototype.cvScores = function (kind, params, seed) {
  const dev = this.split.dev_rows, out = [];
  for (const [tr, va] of this.folds) {
    const vr = sub(dev, va), pred = this.run(kind, params, seed, sub(dev, tr), vr);
    let s = 0;
    for (let i = 0; i < vr.length; i++) s += (this.y[vr[i] + 1] - pred[i]) ** 2;
    out.push(Math.sqrt(s / vr.length));
  }
  return out;
};

// ======================================================================== Đơn vị việc

E.tasks = {
  /** Tầng 1: fit trên train (XGB dừng sớm trên validation). Tầng 3: fit trên toàn bộ development. */
  eval(ctx, a) {
    const t0 = Date.now(), s = ctx.split;
    const pred = a.tier === 1
      ? ctx.run(a.kind, a.params, a.seed, s.train_rows, s.test_rows, a.kind === "XGB" ? s.val_rows : null)
      : ctx.run(a.kind, a.params, a.seed, s.dev_rows, s.test_rows);
    return { tag: a.tag, seed: a.seed, pred, seconds: (Date.now() - t0) / 1000 };
  },
  /** Một lần chạy độc lập của GA hoặc SA. send(msg) báo tiến độ sau mỗi lần đánh giá. */
  hpo(ctx, a, send) {
    const cfg = ctx.cfg, caps = cfg.caps, kind = a.kind, t0 = Date.now();
    const rng = E.makeRng(a.seed), state = { gen: 0, T: null }, foldScores = new Map();
    const objective = v => {
      const params = E.decode(kind, v, caps), sc = ctx.cvScores(kind, params, a.seed);
      foldScores.set(E.paramsKey(params), sc);
      return E.mean(sc);
    };
    const ev = makeEvaluator(objective, cfg.budget, v => E.paramsKey(E.decode(kind, v, caps)),
      e => send && send({ evals: e.n_evals, best: e.best_j, gen: state.gen, T: state.T }));
    const dim = E.dim(kind, caps), cat = E.categoricalMask(kind, caps), init = E.encode(kind, E.baseline(kind), caps);
    if (send) send({ evals: 0, best: null, gen: 0, T: null });
    const res = a.algo === "GA"
      ? E.runGA(ev, dim, cat, rng, init, { pop_size: cfg.ga_pop_size, max_generations: cfg.ga_max_generations,
          tournament_k: cfg.ga_tournament_k, p_crossover: cfg.ga_p_crossover, p_mutation: cfg.ga_p_mutation,
          sigma: cfg.ga_sigma, elitism: cfg.ga_elitism, patience: cfg.ga_patience },
          g => { state.gen = Math.min(g + 1, cfg.ga_max_generations); })
      : E.runSA(ev, dim, cat, rng, init, { t0_samples: cfg.sa_t0_samples, accept0: cfg.sa_accept0, cooling: cfg.sa_cooling,
          moves_per_temp: cfg.sa_moves_per_temp, sigma: cfg.sa_sigma, t_min_ratio: cfg.sa_t_min_ratio, patience: cfg.sa_patience },
          T => { state.T = T; });
    const best = E.decode(kind, res.best_vector, caps);
    const parity = { space: E.space(kind, caps).map(p => p.name), budget: cfg.budget,
                     folds: ctx.folds.map(([tr, va]) => [tr[0], tr[tr.length - 1], va[0], va[va.length - 1]]),
                     objective: "J = mean RMSE over K expanding-window validation folds (3.33, 3.34)" };
    return { model: kind, algo: a.algo, run: a.run, seed: a.seed, parity, params: best, J: res.best_j,
             fold_rmse: foldScores.get(E.paramsKey(best)) || null, n_evals: res.n_evals, n_trained: ev.n_trained,
             stop_reason: res.stop_reason, generations: res.generations ?? null, T0: res.T0 ?? null, T_final: res.T_final ?? null,
             history: ev.history, seconds: Math.round((Date.now() - t0) / 100) / 10 };
  },
  /** Huấn luyện lại trên toàn bộ tập phát triển, dự báo ngày làm việc kế tiếp từ đặc trưng của ngày cuối. */
  refit(ctx, a) {
    const last = Int32Array.of(ctx.y.length - 1);
    return { key: a.key, seed: a.seed, f: ctx.run(a.kind, a.params, a.seed, ctx.split.dev_rows, last)[0] };
  },
  /** 25 cấu trúc ARIMA trên tập phát triển + dự báo tập kiểm tra + T+1. */
  arima(ctx, a, send) {
    const t0 = Date.now(), s = ctx.split, cfg = ctx.cfg;
    const structs = E.arimaStructures(Array.from(ctx.y.subarray(0, s.n_dev)), a.d, cfg.arima_max_p, cfg.arima_max_q,
      (i, n, o) => send && send({ i, n, order: o }));
    const ok = structs.filter(r => !r.error);
    if (!ok.length) throw new Error("Không ước lượng được cấu trúc ARIMA nào.");
    const best = ok[0], fc = E.arimaForecast(best, ctx.y, s.n_dev);
    return { t43: ok.slice(0, cfg.arima_top).map(r => ({ order: r.order, trend: r.trend, nobs: r.nobs, llf: r.llf, aic: r.aic, bic: r.bic, hqic: r.hqic })),
             order: best.order, pred: fc.pred, lo: fc.lo, hi: fc.hi, t1: fc.t1, seconds: Math.round((Date.now() - t0) / 100) / 10 };
  },
  /** Đo thời gian 1 lần huấn luyện mặc định mỗi mô hình (ước tính thời gian chạy). */
  measure(ctx, a) {
    const t0 = Date.now(), s = ctx.split;
    ctx.run(a.kind, E.baseline(a.kind), 1, s.train_rows, s.test_rows, a.kind === "XGB" ? s.val_rows : null);
    return { kind: a.kind, seconds: (Date.now() - t0) / 1000 };
  },
};

})(E);
if (typeof module !== "undefined") module.exports = E;
