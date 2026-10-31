/* Giao diện: chọn file, thiết lập, chạy (nhóm Web Worker), tiến trình 12 bước, kết quả (bảng 4.1–4.6, biểu đồ, H1–H3),
   lưu tiến độ / kết quả trong IndexedDB của trình duyệt, tải kết quả. */
(function () {
"use strict";

const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
const esc = s => String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const icon = (id, cls) => `<svg class="icon ${cls || ""}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
const ok = x => x !== null && x !== undefined && Number.isFinite(x);
const fmt = (x, nd) => (ok(x) ? E.vn(x, nd === undefined ? 2 : nd) : "—");
const fmtPct = (x, nd) => (ok(x) ? (x > 0 ? "+" : "") + E.vn(x, nd === undefined ? 2 : nd) + "%" : "—");
const ngayVN = s => (s ? s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4) : "—");
function fmtTime(sec) {
  if (!ok(sec)) return "—";
  sec = Math.max(0, Math.round(sec));
  if (sec < 60) return sec + " giây";
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  if (h) return `${h} giờ ${m} phút`;
  return `${m} phút ${s ? s + " giây" : ""}`.trim();
}

const state = { data: null, result: null, running: false, pool: null };

// ======================================================================== Giao diện sáng / tối

// Không đặt data-theme thì theo cài đặt sáng/tối của máy
const sysLight = () => window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
const currentTheme = () => document.documentElement.dataset.theme || (sysLight() ? "light" : "dark");
function syncThemeIcon() { $("#nut-giao-dien use").setAttribute("href", currentTheme() === "light" ? "#i-moon" : "#i-sun"); }
function setTheme(t) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("dbtg-theme", t); } catch (e) {}
  syncThemeIcon();
  Charts.redrawAll();
}
$("#nut-giao-dien").addEventListener("click", () => setTheme(currentTheme() === "light" ? "dark" : "light"));
if (window.matchMedia) window.matchMedia("(prefers-color-scheme: light)").addEventListener("change", () => { syncThemeIcon(); Charts.redrawAll(); });

// Hộp xác nhận ngay trên trang (không dùng window.confirm: một số khung nhúng chặn hộp thoại của trình duyệt)
function askConfirm(html, okLabel) {
  const dlg = $("#hop-xac-nhan");
  $("#hop-tieu-de").textContent = "Xác nhận";
  $("#hop-noi-dung").innerHTML = `<p>${html}</p>`;
  $("#hop-ok").textContent = okLabel || "Đồng ý";
  return openDialog(dlg);
}
function openDialog(dlg) {
  if (typeof dlg.showModal !== "function") return Promise.resolve(true);
  return new Promise(res => {
    dlg.addEventListener("close", () => res(dlg.returnValue === "ok"), { once: true });
    dlg.returnValue = "";
    dlg.showModal();
  });
}

// ======================================================================== IndexedDB: tiến độ tạm + kết quả

const DB = (function () {
  let dbp = null;
  function open() {
    if (dbp) return dbp;
    dbp = new Promise((res, rej) => {
      try {
        const r = indexedDB.open("du_bao_ty_gia", 1);
        r.onupgradeneeded = () => { r.result.createObjectStore("units"); r.result.createObjectStore("results", { keyPath: "id" }); };
        r.onsuccess = () => res(r.result);
        r.onerror = () => rej(r.error);
      } catch (e) { rej(e); }
    }).catch(() => null);
    return dbp;
  }
  async function tx(store, mode, fn) {
    const db = await open();
    if (!db) return undefined;
    return new Promise(res => {
      try {
        const t = db.transaction(store, mode), s = t.objectStore(store), r = fn(s);
        t.oncomplete = () => res(r && r.result);
        t.onerror = t.onabort = () => res(undefined);
      } catch (e) { res(undefined); }
    });
  }
  return {
    get: (store, key) => tx(store, "readonly", s => s.get(key)),
    put: (store, val, key) => tx(store, "readwrite", s => (key === undefined ? s.put(val) : s.put(val, key))),
    del: (store, key) => tx(store, "readwrite", s => s.delete(key)),
    all: store => tx(store, "readonly", s => s.getAll()),
    clear: store => tx(store, "readwrite", s => s.clear()),
  };
})();

function unitStore() {
  let prefix = "";
  return {
    open(fp) { prefix = fp + "|"; return Promise.resolve(); },
    async get(key) { const v = await DB.get("units", prefix + key); return v === null ? undefined : v; },
    put(key, val) { DB.put("units", val, prefix + key); },
  };
}

// ======================================================================== Nhóm Web Worker

const CORES = Math.max(1, navigator.hardwareConcurrency || 2);

function makePool(n) {
  const src = $("#worker-src").textContent;
  const url = URL.createObjectURL(new Blob([src], { type: "text/javascript" }));
  let workers = [], seq = 0;
  const call = (w, msg, onMsg) => new Promise((res, rej) => {
    const id = ++seq;
    w.onmessage = e => {
      const m = e.data;
      if (m.id !== id) return;
      if (m.type === "msg") { if (onMsg) onMsg(m.msg); return; }
      if (m.type === "error") rej(new Error(m.message)); else res(m.value);
    };
    w.onerror = e => { e.preventDefault(); rej(new Error(e.message || "Lỗi trong Web Worker")); };
    w.postMessage(Object.assign({ id }, msg));
  });
  const pool = {
    cancelled: false, size: n,
    async init(y, cfg) {
      if (!workers.length) workers = Array.from({ length: n }, () => new Worker(url));
      await Promise.all(workers.map(w => call(w, { type: "init", y: Array.from(y), cfg })));
    },
    run(units, onResult, onMessage) {
      return new Promise((resolve, reject) => {
        let next = 0, active = 0, failed = false;
        pool._reject = reject;
        const pump = () => {
          if (failed || pool.cancelled) return;
          if (next >= units.length && active === 0) { resolve(); return; }
          for (const w of workers) {
            if (w._busy || next >= units.length) continue;
            const u = units[next++];
            w._busy = true; active++;
            call(w, { type: "task", task: u.type, args: u.args }, m => onMessage && onMessage(u, m)).then(v => {
              w._busy = false; active--;
              try { onResult(u.key, v); } catch (e) { failed = true; reject(e); return; }
              pump();
            }, e => { failed = true; reject(e); });
          }
        };
        pump();
      });
    },
    cancel() {
      pool.cancelled = true;
      workers.forEach(w => w.terminate());
      workers = [];
      if (pool._reject) pool._reject(new E.Cancelled());
    },
    dispose() { workers.forEach(w => w.terminate()); workers = []; },
  };
  return pool;
}

/** Dự phòng khi trình duyệt không cho tạo Web Worker: chạy ngay trên trang (giao diện có thể khựng). */
function makeInline() {
  let ctx = null;
  const r = {
    cancelled: false, size: 1,
    init(y, cfg) { ctx = new E.Context(y, cfg); return Promise.resolve(); },
    async run(units, onResult, onMessage) {
      for (const u of units) {
        await new Promise(res => setTimeout(res, 0));
        if (r.cancelled) throw new E.Cancelled();
        onResult(u.key, JSON.parse(JSON.stringify(E.tasks[u.type](ctx, u.args, m => onMessage && onMessage(u, m)))));
      }
    },
    cancel() { r.cancelled = true; }, dispose() {},
  };
  return r;
}

let workerOK = null;
async function checkWorker() {
  if (workerOK !== null) return workerOK;
  try {
    const p = makePool(1);
    await Promise.race([p.init([1, 2, 3].concat(Array.from({ length: 80 }, (_, i) => 3 + i)), E.buildConfig("chay_thu")),
                        new Promise((_, rej) => setTimeout(() => rej(new Error("timeout")), 4000))]);
    p.dispose();
    workerOK = true;
  } catch (e) { workerOK = false; }
  return workerOK;
}

// ======================================================================== Biểu đồ (canvas, không cần thư viện)

const Charts = (function () {
  const list = new Set();
  const tip = () => $("#o-goi-y");
  const cssVar = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  function niceTicks(lo, hi, n) {
    if (lo === hi) { lo -= 1; hi += 1; }
    const span = hi - lo, step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map(f => f * mag).find(s => s >= step0);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(v);
    return { ticks: out, step };
  }
  /** opt: {labels, series:[{name, data, color, dash, width, hidden, band:{lo,hi}, point}], yFmt, xFmt, tipFmt} */
  function line(el, opt) {
    el.innerHTML = `<div class="bieu-do"><div class="chu-giai"></div><div class="khung-bieu-do ${opt.size || ""}"><canvas role="img"></canvas></div></div>`;
    const legend = $(".chu-giai", el), box = $(".khung-bieu-do", el), cv = $("canvas", el);
    cv.setAttribute("aria-label", opt.aria || "Biểu đồ");
    opt.series.forEach((s, i) => {
      if (s.legend === false) return;
      const b = document.createElement("button");
      b.type = "button";
      b.setAttribute("aria-pressed", s.hidden ? "false" : "true");
      b.innerHTML = `<i class="${s.dash ? "dut" : ""}" style="border-color:${cssVar(s.color) || s.color}"></i>${esc(s.name)}`;
      b.addEventListener("click", () => { s.hidden = !s.hidden; b.setAttribute("aria-pressed", s.hidden ? "false" : "true"); draw(); });
      s._btn = b;
      legend.appendChild(b);
    });
    let geom = null;
    function draw() {
      const W = box.clientWidth, H = box.clientHeight, dpr = window.devicePixelRatio || 1;
      if (!W || !H) return;
      cv.width = W * dpr; cv.height = H * dpr; cv.style.width = W + "px"; cv.style.height = H + "px";
      const g = cv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, W, H);
      opt.series.forEach(s => { if (s._btn) s._btn.querySelector("i").style.borderColor = cssVar(s.color) || s.color; });
      const vis = opt.series.filter(s => !s.hidden);
      let lo = Infinity, hi = -Infinity;
      for (const s of vis) for (const arr of [s.data, s.band && s.band.lo, s.band && s.band.hi]) if (arr) for (const v of arr) if (ok(v)) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
      if (!ok(lo)) { lo = 0; hi = 1; }
      const pad = (hi - lo) * 0.06 || 1;
      const { ticks } = niceTicks(lo - pad, hi + pad, H < 200 ? 3 : 5);
      const yMin = Math.min(lo - pad, ticks[0]), yMax = Math.max(hi + pad, ticks[ticks.length - 1]);
      g.font = `12px ${getComputedStyle(document.body).fontFamily}`;
      const yFmt = opt.yFmt || (v => E.vn(v, 0));
      const left = opt.compact ? 6 : Math.max(...ticks.map(t => g.measureText(yFmt(t)).width)) + 14, right = 12, top = 8, bottom = opt.compact ? 6 : 26;
      const n = opt.labels.length, pw = W - left - right, ph = H - top - bottom;
      const X = i => left + (n > 1 ? i * pw / (n - 1) : pw / 2), Y = v => top + (yMax - v) / (yMax - yMin) * ph;
      geom = { X, Y, left, right, top, bottom, n, pw, ph, W, H };
      const muted = cssVar("--text-muted"), grid = cssVar("--border-soft");
      if (!opt.compact) {
        g.strokeStyle = grid; g.lineWidth = 1; g.fillStyle = muted; g.textAlign = "right"; g.textBaseline = "middle";
        for (const t of ticks) { if (t < yMin || t > yMax) continue; const y = Math.round(Y(t)) + 0.5; g.beginPath(); g.moveTo(left, y); g.lineTo(W - right, y); g.stroke(); g.fillText(yFmt(t), left - 8, y); }
        g.textAlign = "center"; g.textBaseline = "top";
        const nl = Math.max(2, Math.min(n, Math.floor(pw / 90)));
        for (let k = 0; k < nl; k++) {
          const i = Math.round(k * (n - 1) / (nl - 1));
          let x = X(i);
          const txt = (opt.xFmt || (s => s))(opt.labels[i]);
          const w = g.measureText(txt).width / 2;
          x = Math.min(Math.max(x, left + w), W - right - w);
          g.fillText(txt, x, H - bottom + 8);
        }
      }
      for (const s of vis) if (s.band) {
        g.fillStyle = cssVar(s.bandColor || "--band"); g.beginPath();
        let started = false;
        s.band.hi.forEach((v, i) => { if (!ok(v)) return; started ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v)); started = true; });
        for (let i = s.band.lo.length - 1; i >= 0; i--) if (ok(s.band.lo[i])) g.lineTo(X(i), Y(s.band.lo[i]));
        g.closePath(); g.fill();
      }
      for (const s of vis.slice().reverse()) {
        if (!s.data) continue;
        g.strokeStyle = cssVar(s.color) || s.color; g.lineWidth = s.width || 1.5; g.setLineDash(s.dash || []);
        g.beginPath();
        let pen = false;
        s.data.forEach((v, i) => { if (!ok(v)) { pen = false; return; } pen ? g.lineTo(X(i), Y(v)) : g.moveTo(X(i), Y(v)); pen = true; });
        g.stroke(); g.setLineDash([]);
        if (s.point !== undefined) {
          const i = s.point, v = s.data[i];
          g.fillStyle = cssVar(s.color) || s.color;
          g.beginPath(); g.moveTo(X(i), Y(v) - 6); g.lineTo(X(i) + 6, Y(v)); g.lineTo(X(i), Y(v) + 6); g.lineTo(X(i) - 6, Y(v)); g.closePath(); g.fill();
        }
      }
      if (geom.hover !== undefined) {
        const x = Math.round(X(geom.hover)) + 0.5;
        g.strokeStyle = muted; g.setLineDash([3, 3]); g.beginPath(); g.moveTo(x, top); g.lineTo(x, H - bottom); g.stroke(); g.setLineDash([]);
      }
    }
    function hover(ev) {
      if (!geom || opt.compact) return;
      const r = cv.getBoundingClientRect(), x = ev.clientX - r.left;
      if (x < geom.left - 10 || x > geom.W - geom.right + 10) return leave();
      const i = Math.max(0, Math.min(geom.n - 1, Math.round((x - geom.left) / geom.pw * (geom.n - 1))));
      geom.hover = i; draw();
      const t = tip(), vis = opt.series.filter(s => !s.hidden && s.data && ok(s.data[i]) && s.legend !== false);
      t.innerHTML = `<b>${esc((opt.tipX || opt.xFmt || (s => s))(opt.labels[i]))}</b>` + vis.map(s =>
        `<div><i style="background:${cssVar(s.color) || s.color}"></i>${esc(s.name)}: ${(opt.tipFmt || (v => E.vn(v, 2)))(s.data[i])}</div>`).join("");
      t.hidden = false;
      const tw = t.offsetWidth, th = t.offsetHeight;
      let lx = ev.clientX + 14, ly = ev.clientY - th - 10;
      if (lx + tw > window.innerWidth - 8) lx = ev.clientX - tw - 14;
      if (ly < 8) ly = ev.clientY + 16;
      t.style.left = lx + "px"; t.style.top = ly + "px";
    }
    function leave() { if (geom) { delete geom.hover; draw(); } tip().hidden = true; }
    cv.addEventListener("mousemove", hover);
    cv.addEventListener("touchstart", e => hover(e.touches[0]), { passive: true });
    cv.addEventListener("touchmove", e => hover(e.touches[0]), { passive: true });
    cv.addEventListener("mouseleave", leave);
    cv.addEventListener("touchend", () => setTimeout(leave, 1500));
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => draw()) : null;
    if (ro) ro.observe(box); else window.addEventListener("resize", draw);
    const item = { draw, el };
    list.add(item);
    requestAnimationFrame(draw);
    return item;
  }
  return {
    line,
    redrawAll() { for (const it of list) { if (!document.body.contains(it.el)) list.delete(it); else it.draw(); } },
    clear() { list.clear(); },
  };
})();
const COLOR = { ARIMA: "--c-arima", ANN: "--c-ann", RF: "--c-rf", XGB: "--c-xgb", RW: "--c-rw" };

// ======================================================================== Bước 1: đọc file

const fileInput = $("#file-du-lieu"), drop = $("#vung-tha");
fileInput.addEventListener("change", () => fileInput.files[0] && loadFile(fileInput.files[0]));
["dragenter", "dragover"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.add("keo"); }));
["dragleave", "drop"].forEach(ev => drop.addEventListener(ev, e => { e.preventDefault(); drop.classList.remove("keo"); }));
drop.addEventListener("drop", e => { const f = e.dataTransfer.files[0]; if (f) { if (/\.json$/i.test(f.name)) openResultFile(f); else loadFile(f); } });

function decode(buf) {
  for (const enc of ["utf-8", "windows-1258", "windows-1252"]) {
    try { return new TextDecoder(enc, { fatal: enc === "utf-8" }).decode(buf); } catch (e) {}
  }
  return new TextDecoder().decode(buf);
}

async function loadFile(file) {
  const box = $("#thong-tin-file");
  box.hidden = false;
  state.data = null;
  updateRunButton();
  if (/\.xlsx?$/i.test(file.name)) {
    box.innerHTML = `<div class="thong-bao thong-bao-loi" role="alert">${icon("x")}<div><b>Chưa đọc được file Excel trực tiếp.</b> Mở file trong Excel, chọn <b>File → Save As → CSV UTF-8 (*.csv)</b> rồi chọn file .csv đó.</div></div>`;
    return;
  }
  try {
    const text = decode(await file.arrayBuffer());
    const tb = E.parseTable(E.parseCSV(text));
    const cl = E.clean(tb.rows, E.buildConfig("chay_thu"));
    state.data = { rows: tb.rows, info: tb.info, filename: file.name, clean: cl };
    drop.classList.add("da-chon");
    $("#vung-tha-chu").textContent = file.name;
    $("#vung-tha-phu").textContent = "Bấm để chọn file khác";
    const s = cl.stats;
    box.innerHTML = `
      <div class="thong-bao thong-bao-ok">${icon("check")}<div>Đọc được <b>${s.rows_in}</b> dòng · cột ngày <code>${esc(tb.info.date_column)}</code>, cột tỷ giá <code>${esc(tb.info.rate_column)}</code>
        · sau khi làm sạch còn <b>${s.rows_out}</b> quan sát từ <b>${E.fmtVN(cl.days[0])}</b> đến <b>${E.fmtVN(cl.days[cl.days.length - 1])}</b>
        · tỷ giá cuối <b>${fmt(cl.y[cl.y.length - 1], 0)}</b>.</div></div>
      <div id="bd-xem-truoc"></div>`;
    Charts.line($("#bd-xem-truoc"), { labels: cl.days.map(E.fmtISO), size: "nho", aria: "Chuỗi tỷ giá trong file",
      series: [{ name: "Tỷ giá", data: cl.y, color: "--primary", width: 1.5, legend: false }], xFmt: ngayVN, tipFmt: v => E.vn(v, 0) });
  } catch (e) {
    box.innerHTML = `<div class="thong-bao thong-bao-loi" role="alert">${icon("x")}<div><b>Không dùng được file này.</b> ${esc(e.message || e)}</div></div>`;
  }
  updateRunButton();
}

// Dữ liệu mẫu nhúng sẵn trong trang
const sampleEl = $("#du-lieu-mau");
const sampleFile = () => new File([sampleEl.textContent.trim() + "\n"], sampleEl.dataset.ten, { type: "text/csv" });
$("#nut-du-lieu-mau").addEventListener("click", () => loadFile(sampleFile()));
$("#nut-tai-mau").addEventListener("click", () => save(sampleEl.dataset.ten, "\uFEFF" + sampleEl.textContent.trim() + "\n", "text/csv"));
if (window.__ARTIFACT__) $("#nut-tai-mau").hidden = true;

// ======================================================================== Bước 2: thiết lập

const form = $("#form-chay");
(function initThreads() {
  const sel = $("#chon-luong"), def = Math.max(1, Math.min(CORES - 1, 8)) || 1;
  for (let i = 1; i <= Math.max(1, Math.min(CORES, 16)); i++) {
    const o = document.createElement("option");
    o.value = i; o.textContent = i + (i === def ? " (khuyên dùng)" : "");
    if (i === def) o.selected = true;
    sel.appendChild(o);
  }
  $("#so-luong-cpu").textContent = `Máy này có ${CORES} luồng CPU. Dùng nhiều luồng thì chạy nhanh hơn nhưng máy sẽ nóng và chậm khi làm việc khác.`;
})();

function readForm() {
  const fd = new FormData(form);
  const mode = fd.get("mode"), models = fd.getAll("models"), variants = fd.getAll("variants");
  const alertPct = Number(String(fd.get("alert")).replace(",", "."));
  if (!(alertPct >= 0)) throw new Error("Ngưỡng Ổn định phải là số không âm, ví dụ 0.10.");
  const cfg = E.buildConfig(mode, models, variants, { alert_watch_pct: alertPct });
  return { cfg, threads: Number(fd.get("threads")) || 1 };
}
function updateRunButton() {
  const b = $("#nut-chay"), hint = $("#goi-y-chay");
  let msg = "";
  if (state.running) msg = "Đang chạy…";
  else if (!state.data) msg = "Chọn file dữ liệu ở Bước 1 trước.";
  else { try { readForm(); } catch (e) { msg = e.message; } }
  b.disabled = !!msg;
  hint.textContent = msg || "Sẵn sàng.";
}
form.addEventListener("change", updateRunButton);
form.addEventListener("input", updateRunButton);

// ======================================================================== Chạy

let wakeLock = null;
async function keepAwake(on) {
  try {
    if (on && "wakeLock" in navigator) wakeLock = await navigator.wakeLock.request("screen");
    else if (!on && wakeLock) { await wakeLock.release(); wakeLock = null; }
  } catch (e) {}
}
document.addEventListener("visibilitychange", () => { if (state.running && document.visibilityState === "visible") keepAwake(true); });
window.addEventListener("beforeunload", e => { if (state.running) { e.preventDefault(); e.returnValue = ""; } });

form.addEventListener("submit", async e => {
  e.preventDefault();
  if (state.running || !state.data) return;
  let cfg, threads;
  try { ({ cfg, threads } = readForm()); } catch (err) { showFormError(err.message); return; }
  showFormError(null);
  state.running = true;
  updateRunButton();
  const useWorkers = await checkWorker();
  const runner = useWorkers ? makePool(Math.max(1, threads)) : makeInline();
  state.pool = runner;
  if (!useWorkers) showEnvWarning("Trình duyệt này không cho chạy luồng nền (Web Worker) khi mở file trực tiếp, nên web chạy ngay trên trang: có thể bị khựng. Nên dùng Chrome hoặc Edge bản mới.");

  // Ước tính thời gian: đo 1 lần huấn luyện mặc định mỗi mô hình
  let est = null;
  try {
    const ml = cfg.models.filter(m => E.ML_MODELS.includes(m));
    const cl = E.clean(state.data.rows, cfg);
    await runner.init(cl.y, cfg);
    const measured = { ARIMA: 6 };
    if (ml.length) await runner.run(ml.map(m => ({ key: "measure|" + m, type: "measure", args: { kind: m } })), (k, v) => { measured[v.kind] = v.seconds; });
    est = E.estimate(cfg, measured, cl.y.length, 0, runner.size);
  } catch (err) { est = null; }
  if (cfg.mode === "chay_day_du") {
    const okRun = await confirmFull(est, runner.size);
    if (!okRun) { runner.dispose(); state.running = false; updateRunButton(); return; }
  }
  await startRun(cfg, runner, est);
});

function showFormError(msg) {
  const el = $("#loi-form");
  el.hidden = !msg;
  el.innerHTML = msg ? `<div class="thong-bao thong-bao-loi" role="alert">${icon("x")}<div>${esc(msg)}</div></div>` : "";
}
function showEnvWarning(msg) {
  const el = $("#canh-bao-moi-truong");
  el.hidden = false;
  el.innerHTML = `<div class="thong-bao thong-bao-canh-bao">${icon("alert")}<div>${esc(msg)}</div></div>`;
}

function confirmFull(est, threads) {
  const dlg = $("#hop-xac-nhan");
  $("#hop-noi-dung").innerHTML = `
    <p>Ước tính trên máy này với <b>${threads}</b> luồng: khoảng <b>${est ? fmtTime(est.total_seconds) : "nhiều giờ"}</b> (con số chỉ là ước lượng).</p>
    <ul class="danh-sach">
      <li>Giữ tab này mở, cắm sạc, tắt chế độ ngủ của máy.</li>
      <li>Có thể làm việc khác trong tab khác, nhưng đừng đóng tab này.</li>
      <li>Nếu lỡ đóng tab: mở lại file, chọn đúng file dữ liệu và cùng thiết lập rồi bấm Chạy – phần đã xong được giữ lại.</li>
    </ul>`;
  $("#hop-tieu-de").textContent = "Chạy đầy đủ mất nhiều thời gian";
  $("#hop-ok").textContent = "Bắt đầu chạy";
  return openDialog(dlg);
}

async function startRun(cfg, runner, est) {
  const card = $("#the-tien-trinh");
  card.hidden = false;
  tm.follow = true;
  $("#tt-luu-y").hidden = false;
  $("#nut-huy").hidden = false;
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  keepAwake(true);
  if (window.Intro) Intro.start();
  const d = state.data;
  try {
    const result = await E.runPipeline(d.rows, { filename: d.filename, date_column: d.info.date_column, rate_column: d.info.rate_column },
      cfg, runner, renderProgress, { store: unitStore(), weights: est && est.weights, estimateSeconds: est && est.total_seconds });
    result.threads = runner.size;
    renderProgress(result.progress);
    $("#td-tien-trinh").previousElementSibling.textContent = "Đã xong";
    $("#tt-luu-y").hidden = true;
    $("#nut-huy").hidden = true;
    const id = Date.now();
    result.id = id;
    await DB.put("results", { id, saved: new Date().toISOString(), result });
    showResult(result);
    refreshHistory();
  } catch (e) {
    if (e.progress) renderProgress(e.progress);
    $("#nut-huy").hidden = true;
    if (!(e instanceof E.Cancelled)) {
      const box = document.createElement("div");
      box.className = "thong-bao thong-bao-loi"; box.setAttribute("role", "alert");
      box.innerHTML = `${icon("x")}<div><b>Quy trình dừng vì lỗi.</b> ${esc(e.message || e)}</div>`;
      $("#tt-cac-buoc").before(box);
    }
  } finally {
    runner.dispose();
    state.running = false;
    keepAwake(false);
    updateRunButton();
  }
}
$("#nut-huy").addEventListener("click", async () => {
  if (!state.pool || !state.running) return;
  if (!(await askConfirm("Dừng quy trình? Phần đã xong vẫn được lưu để chạy tiếp lần sau.", "Dừng"))) return;
  state.pool.cancel();
});

// Thuyết minh từng bước (đọc to khi trình bày trong lúc web chạy)
const STEP_INFO = {
  1: { p: ["Người dùng chỉ cần đưa vào một file tỷ giá. Công cụ tự nhận ra đâu là cột ngày, đâu là cột tỷ giá, kể cả khi tên cột khác nhau."],
       li: ["Đọc được file Vietcombank, Investing.com (Date, Price), Yahoo Finance (Date, Close).", "Ngày viết kiểu 28/10/2026, 2026-10-28 hay 10/28/2026 đều được."] },
  2: { p: ["Dữ liệu thật thường có lỗi. Công cụ làm sạch theo 6 bước của bài trước khi đưa vào mô hình."],
       li: ["Chuẩn hóa ngày, sắp xếp theo thời gian, bỏ dòng trùng ngày.", "Bỏ giá trị trống, âm hoặc bằng 0.",
            "Bỏ điểm bất thường: nhảy hơn 1% rồi hôm sau quay về chỗ cũ (thường là lỗi nhập liệu).", "Ngày lễ, cuối tuần không có giao dịch thì để trống, không tự bịa số."] },
  3: { p: ["Trước khi dự báo cần biết chuỗi tỷ giá có \"dừng\" hay không, tức là có dao động quanh một mức cố định hay không."],
       li: ["Kiểm định ADF và Phillips–Perron (Bảng 4.2).", "Tỷ giá USD/VND thường không dừng nhưng mức thay đổi hằng ngày thì dừng: chuỗi I(1).",
            "Vì vậy các mô hình dự báo mức thay đổi Δy rồi cộng lại vào tỷ giá hôm nay."] },
  4: { p: ["Biến chuỗi tỷ giá thành bảng dữ liệu cho học máy, rồi chia dữ liệu theo thời gian."],
       li: ["Đặc trưng: các mức thay đổi trễ (lag), lợi suất, trung bình trượt, độ lệch chuẩn trượt, momentum.",
            "80% đầu để xây dựng mô hình, 20% cuối để kiểm tra. Không xáo trộn: mô hình không được \"nhìn thấy tương lai\".",
            "Phần xây dựng lại chia thành các fold kiểm tra chéo cửa sổ mở rộng để chấm điểm cấu hình."] },
  5: { p: ["ARIMA là mô hình kinh tế lượng truyền thống, dùng làm mốc để so sánh với học máy."],
       li: ["Thử 25 cấu trúc ARIMA(p, d, q) với p, q từ 0 đến 4.", "Chọn cấu trúc có AIC nhỏ nhất (vừa khớp dữ liệu, vừa không quá phức tạp).",
            "Dự báo từng ngày trên 20% dữ liệu cuối, kèm khoảng dự báo 95%."] },
  6: { p: ["Ba mô hình học máy chạy với cấu hình mặc định để có mốc \"trước tối ưu\"."],
       li: ["ANN: mạng nơ-ron nhiều lớp, học quan hệ phi tuyến.", "Random Forest: trung bình của hàng trăm cây quyết định.",
            "XGBoost: các cây được xây nối tiếp, cây sau sửa sai số của cây trước.", "Mỗi mô hình chạy lặp nhiều lần với hạt giống ngẫu nhiên khác nhau để đo độ ổn định."] },
  7: { p: ["Kết quả của học máy phụ thuộc nhiều vào siêu tham số (số cây, độ sâu, tốc độ học…). Thuật toán di truyền GA tự tìm bộ siêu tham số tốt."],
       li: ["Mỗi cấu hình là một \"cá thể\"; cả nhóm cá thể là một quần thể.", "Chọn lọc cá thể tốt, lai ghép, đột biến để tạo thế hệ mới.",
            "Điểm của mỗi cá thể = RMSE trung bình trên các fold kiểm tra chéo, chỉ dùng dữ liệu trước phần kiểm tra."] },
  8: { p: ["Mô phỏng luyện kim SA tìm cấu hình theo cách khác: đi từng bước từ cấu hình mặc định."],
       li: ["Mỗi bước thử một cấu hình \"lân cận\" (đổi 1–2 siêu tham số).", "Tốt hơn thì nhận; kém hơn vẫn có thể nhận với một xác suất, để không bị kẹt ở lời giải chưa tốt.",
            "Xác suất đó giảm dần theo \"nhiệt độ\", giống kim loại nguội dần.", "GA và SA dùng cùng không gian tìm kiếm, cùng hàm mục tiêu và cùng số lần đánh giá, nên so sánh công bằng."] },
  9: { p: ["Đến lúc này mới dùng 20% dữ liệu cuối mà mô hình chưa từng thấy để chấm điểm thật."],
       li: ["So sánh trước và sau tối ưu cho từng mô hình (Bảng 4.5).", "Mỗi ứng viên chạy lặp nhiều lần, lấy RMSE, MAE, MAPE trung bình và độ lệch chuẩn."] },
  10: { p: ["Chọn mô hình có RMSE trung bình thấp nhất trong các ứng viên ANN, Random Forest, XGBoost (mặc định, GA, SA)."],
        li: ["RMSE: sai số trung bình tính bằng VND/USD, phạt nặng các lần dự báo sai nhiều.", "ARIMA và Random walk (\"ngày mai bằng hôm nay\") chỉ để đối chiếu, không được chọn."] },
  11: { p: ["Mô hình được chọn được huấn luyện lại, rồi dự báo tỷ giá ngày làm việc tiếp theo (T+1)."],
        li: ["Chạy nhiều lần với hạt giống khác nhau, lấy trung bình làm dự báo.", "Kèm khoảng P05–P95 giữa các lần chạy và khoảng ±1,96 × RMSE theo sai số lịch sử."] },
  12: { p: ["Biến con số dự báo thành thông tin quản trị dễ dùng."],
        li: ["Nếu thay đổi dự báo nhỏ hơn ngưỡng người dùng đặt: Ổn định; ngược lại: Tăng hoặc Giảm.", "Xuất Bảng 4.6 (16 trường), biểu đồ, kết luận giả thuyết H1–H3 và file kết quả."] },
};
const tm = { follow: true, view: 1, last: null };
function renderNarration(s) {
  if (s) tm.last = s;
  s = tm.last;
  if (!s) return;
  const running = s.steps.filter(x => x.status === "dang_chay").map(x => x.id);
  const done = s.steps.filter(x => x.status === "xong").map(x => x.id);
  const cur = running.length ? running[0] : (done.length ? done[done.length - 1] : 1);
  if (tm.follow) tm.view = cur;
  const st = s.steps[tm.view - 1], info = STEP_INFO[tm.view];
  $("#tm-nhan").textContent = tm.view === cur && running.includes(cur) ? `Bước ${tm.view} / 12 · đang chạy` : `Bước ${tm.view} / 12 · ${STATUS_TEXT[st.status] || ""}`;
  $("#tm-tieu-de").textContent = st.name;
  $("#tm-noi-dung").innerHTML = info.p.map(t => `<p>${esc(t)}</p>`).join("") + `<ul>${info.li.map(t => `<li>${esc(t)}</li>`).join("")}</ul>` +
    (st.detail && st.status !== "cho" ? `<div class="so-lieu-song">${esc(st.detail)}</div>` : "");
  $("#tm-truoc").disabled = tm.view <= 1;
  $("#tm-sau").disabled = tm.view >= 12;
  $("#tm-theo").hidden = tm.follow;
  $$("#tt-cac-buoc .buoc").forEach(li => li.classList.toggle("dang-xem", Number(li.dataset.buoc) === tm.view));
}
const tmGo = v => { tm.follow = false; tm.view = Math.max(1, Math.min(12, v)); renderNarration(); };
$("#tm-truoc").addEventListener("click", () => tmGo(tm.view - 1));
$("#tm-sau").addEventListener("click", () => tmGo(tm.view + 1));
$("#tm-theo").addEventListener("click", () => { tm.follow = true; renderNarration(); });
$("#tt-cac-buoc").addEventListener("click", e => { const li = e.target.closest("[data-buoc]"); if (li) tmGo(Number(li.dataset.buoc)); });

const STATUS_TEXT = { cho: "Chờ", dang_chay: "Đang chạy", xong: "Xong", bo_qua: "Bỏ qua", loi: "Lỗi", huy: "Đã dừng" };
function renderProgress(s) {
  if (window.Intro) Intro.update(s);
  $("#tt-pham-vi").textContent = `${s.mode_name} · ${s.scope}`;
  $("#tt-phan-tram").textContent = E.vn(s.percent, 1) + "%";
  $("#tt-da-chay").textContent = fmtTime(s.elapsed);
  $("#tt-con-lai").textContent = s.percent >= 100 ? "0 giây" : fmtTime(s.eta);
  $("#tt-thanh > div").style.width = s.percent + "%";
  $("#tt-thanh").setAttribute("aria-valuenow", Math.round(s.percent));
  $("#tt-cac-buoc").innerHTML = s.steps.map(st => `
    <li class="buoc buoc-${st.status}" data-buoc="${st.id}" title="Bấm để xem giải thích bước này">
      <span class="buoc-so">${st.status === "xong" ? icon("check", "nho") : st.status === "loi" ? "!" : st.id}</span>
      <div class="buoc-noi-dung">
        <div class="buoc-dau"><b>${esc(st.name)}</b><span class="nhan tt-${st.status === "huy" ? "loi" : st.status}">${STATUS_TEXT[st.status] || st.status}${st.seconds !== null && st.status === "xong" ? " · " + fmtTime(st.seconds) : ""}</span></div>
        <span class="muted" style="font-size:13px">${esc(st.caption)}</span>
        ${st.detail ? `<div class="buoc-chi-tiet">${esc(st.detail)}</div>` : ""}
        ${st.status === "dang_chay" && st.frac > 0 ? `<div class="thanh-tien-do" style="height:4px;margin-top:6px"><div style="width:${st.frac * 100}%"></div></div>` : ""}
      </div>
    </li>`).join("");
  const log = $("#tt-nhat-ky"), atEnd = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
  log.textContent = s.log.join("\n");
  if (atEnd) log.scrollTop = log.scrollHeight;
  renderNarration(s);
}

// ======================================================================== Kết quả

function badgeAlert(a) {
  const ic = { "Ổn định": "flat", "Tăng": "up", "Giảm": "down" }[a] || "info";
  return `<span class="nhan nhan-lon ${a === "Ổn định" ? "cb-on-dinh" : "cb-theo-doi"}">${icon(ic)}${esc(a)}</span>`;
}
function badgeHyp(st) {
  const cls = st === "Được ủng hộ" ? "tt-xong" : st === "Không được ủng hộ" ? "tt-loi" : st === "Chưa đủ dữ liệu" ? "" : "tt-dang_cho";
  return `<span class="nhan ${cls}" style="${cls ? "" : "border-color:var(--border)"}">${esc(st)}</span>`;
}
const paramsText = p => (p ? Object.entries(p).map(([k, v]) => `${k}=${v === null ? "None" : Array.isArray(v) ? "(" + v.join(", ") + ")" : v}`).join(", ") : "—");
const table = (head, rows, cls) => `<div class="cuon-ngang"><table class="bang ${cls || ""}"><thead><tr>${head.map(h => (typeof h === "string" ? `<th>${h}</th>` : `<th class="so">${h[0]}</th>`)).join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
const section = (id, tag, title, sub, body, extraCls) => `
  <section class="the ${extraCls || ""}" aria-labelledby="${id}">
    <div class="the-dau"><div>${tag ? `<span class="nhan-muc">${tag}</span>` : ""}<h2 id="${id}">${title}</h2>${sub ? `<p class="muted">${sub}</p>` : ""}</div></div>
    ${body}
  </section>`;
const fold = (title, body, open) => `<details class="the" ${open ? "open" : ""}><summary>${icon("chevron")} ${title}</summary><div style="margin-top:12px" class="xep-doc">${body}</div></details>`;

function showResult(r) {
  state.result = r;
  Charts.clear();
  const el = $("#ket-qua");
  const c = r.candidates, ch = r.chosen_key ? c[r.chosen_key] : null, t46 = r.table_4_6, t41 = r.table_4_1;
  const latest = t41.last, H = r.hypotheses;
  let html = "";

  // ---------------------------------------------------------------- Thẻ dự báo
  if (ch) {
    const t1 = ch.t1;
    html += `
    <section class="the the-du-bao" aria-labelledby="td-du-bao">
      <div class="the-dau">
        <div><span class="nhan-muc">Kết quả · ${esc(r.mode_name)} · ${esc(r.data.filename || "")}</span>
          <h2 id="td-du-bao">Dự báo ngày ${ngayVN(t1.date)}</h2>
          <p class="muted">Quan sát cuối ${ngayVN(t46.Latest_Observed_Date)}: ${fmt(latest, 0)} VND/USD · chạy xong lúc ${esc(new Date(r.finished_at || Date.now()).toLocaleString("vi-VN"))}${r.elapsed_seconds >= 1 ? " · mất " + fmtTime(r.elapsed_seconds) : ""}</p></div>
        <div class="hang-tai khong-in">
          <span class="chi-link muted" style="font-size:13px">Bản mở qua link không tải file được. Muốn tải kết quả .json/.csv hoặc in: dùng bản file du_bao_ty_gia.html.</span>
          <button class="nut nut-vien nut-nho" type="button" data-tai="json">${icon("download")} Tải kết quả (.json)</button>
          <button class="nut nut-vien nut-nho" type="button" data-tai="csv">${icon("download")} Dự báo tập kiểm tra (.csv)</button>
          <button class="nut nut-vien nut-nho" type="button" data-tai="t46">${icon("download")} Bảng 4.6 (.csv)</button>
          <button class="nut nut-vien nut-nho" type="button" data-tai="in">${icon("file")} In / lưu PDF</button>
        </div>
      </div>
      <div class="luoi-kpi">
        <div class="kpi kpi-chinh"><span class="nhan-muc">Tỷ giá dự báo</span><span class="kpi-so">${fmt(t1.mean, 2)}</span>
          <span class="kpi-phu">${fmtPct(t1.change_pct_mean, 3)} · ${t1.change_abs_mean >= 0 ? "+" : ""}${fmt(t1.change_abs_mean, 2)} VND so với ${fmt(latest, 0)}</span></div>
        <div class="kpi"><span class="nhan-muc">Cảnh báo</span><span>${badgeAlert(t1.alert)}</span>
          <span class="kpi-phu">Ngưỡng Ổn định: |thay đổi| &lt; ${fmt(r.settings.alert_watch_pct, 2)}%</span></div>
        <div class="kpi"><span class="nhan-muc">Mô hình được chọn</span><span class="kpi-so vua">${esc(ch.label)}</span>
          <span class="kpi-phu">RMSE ${fmt(ch.summary.RMSE, 2)} · MAPE ${fmt(ch.summary.MAPE, 4)}% trên tập kiểm tra</span></div>
        <div class="kpi"><span class="nhan-muc">Khoảng theo sai số lịch sử</span><span class="kpi-so nho">${fmt(r.error_interval.lo, 0)} – ${fmt(r.error_interval.hi, 0)}</span>
          <span class="kpi-phu">Dự báo ± 1,96 × RMSE (≈ 95%) · P05–P95 qua ${t1.n_seeds} seed: ${fmt(t1.p05, 1)} – ${fmt(t1.p95, 1)}</span></div>
      </div>
      ${r.alert_check && r.alert_check.mostly_stable ? `<p class="ghi-chu">${icon("info", "nho")}<span>Trên tập kiểm tra, ${fmt(r.alert_check.share_pct["Ổn định"], 1)}% số ngày có thay đổi thực tế nhỏ hơn ngưỡng – cảnh báo "Ổn định" là phổ biến; có thể giảm ngưỡng nếu cần nhạy hơn.</span></p>` : ""}
    </section>`;
  } else {
    html += section("td-du-bao", "Kết quả", "Không có mô hình học máy", "Chỉ chạy ARIMA (chuẩn đối chiếu) nên không có dự báo chính. ARIMA dự báo: " +
      (c.ARIMA && c.ARIMA.t1 ? fmt(c.ARIMA.t1.mean, 2) : "—"), `<div class="hang-tai khong-in"><button class="nut nut-vien nut-nho" type="button" data-tai="json">${icon("download")} Tải kết quả (.json)</button></div>`);
  }

  // ---------------------------------------------------------------- Biểu đồ test + xếp hạng
  html += `<div class="luoi">
    <section class="the c-8" aria-labelledby="td-bd"><div class="the-dau"><div><span class="nhan-muc">Tập kiểm tra (20% cuối)</span>
      <h2 id="td-bd">Thực tế và dự báo</h2><p class="muted">Bấm vào chú giải để bật/tắt đường. Điểm hình thoi: dự báo T+1.</p></div></div>
      <div id="bd-test"></div></section>
    <section class="the c-4" aria-labelledby="td-rmse"><div class="the-dau"><div><span class="nhan-muc">Sai số trung bình</span>
      <h2 id="td-rmse">RMSE trên tập kiểm tra</h2><p class="muted">Càng ngắn càng tốt. Random walk: ŷ(t+1) = y(t).</p></div></div>
      ${rmseBars(r)}</section>
  </div>`;

  // ---------------------------------------------------------------- Bảng xếp hạng
  const rw = r.random_walk;
  const rowsRank = r.ranking.map(k => {
    const x = c[k], s = x.summary;
    return `<tr class="${x.chosen ? "dong-chon" : ""}"><td class="tieu-de-o">${esc(x.label)} ${x.chosen ? '<span class="nhan nhan-chon">Được chọn</span>' : ""}${x.benchmark ? ' <span class="nhan-bo-sung">đối chiếu</span>' : ""}</td>
      <td class="so">${fmt(s.RMSE, 3)}</td><td class="so">${fmt(s.MAE, 3)}</td><td class="so">${fmt(s.MAPE, 4)}</td><td class="so">${fmt(s.SD_RMSE, 3)}</td>
      <td class="so">${s.n_runs}</td><td class="so">${fmtPct(x.vs_arima_pct)}</td><td class="so">${fmtPct(x.vs_rw_pct)}</td>
      <td class="so">${x.t1 ? fmt(x.t1.mean, 2) : "—"}</td><td class="so">${x.cost_seconds !== undefined ? fmtTime(x.cost_seconds) : "—"}</td></tr>`;
  });
  rowsRank.push(`<tr class="dong-rw"><td>Random walk (chuẩn ngây thơ)</td><td class="so">${fmt(rw.RMSE, 3)}</td><td class="so">${fmt(rw.MAE, 3)}</td><td class="so">${fmt(rw.MAPE, 4)}</td><td class="so">—</td><td class="so">1</td><td class="so">—</td><td class="so">—</td><td class="so">${fmt(latest, 2)}</td><td class="so">—</td></tr>`);
  html += section("td-xh", "Bước 10", `Bảng xếp hạng ${r.ranking.length} ứng viên`,
    "Chọn theo RMSE trung bình thấp nhất qua các lần chạy lặp trên tập kiểm tra, chỉ trong ANN / Random Forest / XGBoost. ARIMA và Random walk chỉ để đối chiếu.",
    table(["Mô hình", ["RMSE"], ["MAE"], ["MAPE (%)"], ["SD RMSE"], ["Số lần chạy"], ["So với ARIMA"], ["So với RW"], ["Dự báo T+1"], ["Thời gian"]], rowsRank));

  // ---------------------------------------------------------------- Giả thuyết
  html += section("td-gt", "Kết luận", "Giả thuyết H1 – H3", "Tự động rút ra từ số liệu của lần chạy này.",
    `<div class="xep-doc">${["H1", "H2", "H3"].map(h => `<div class="gia-thuyet"><div class="buoc-dau"><b>${h}</b>${badgeHyp(H[h].status)}</div><p>${esc(H[h].text)}</p>
      ${H[h].detail ? `<details><summary>${icon("chevron")} Chi tiết</summary><ul class="danh-sach">${H[h].detail.map(d => `<li>${esc(d)}</li>`).join("")}</ul></details>` : ""}</div>`).join("")}</div>`);

  // ---------------------------------------------------------------- Bảng 4.1 – 4.6
  html += fold("Bảng 4.1 – Thống kê mô tả tỷ giá", table(["Chỉ tiêu", ["Giá trị"]], [
    ["Số quan sát", t41.n_obs], ["Từ ngày", ngayVN(t41.start_date)], ["Đến ngày", ngayVN(t41.end_date)], ["Đầu kỳ", fmt(t41.first, 2)], ["Cuối kỳ", fmt(t41.last, 2)],
    ["Thấp nhất", fmt(t41.min, 2)], ["Cao nhất", `${fmt(t41.max, 2)} (${ngayVN(t41.max_date)})`], ["Trung bình", fmt(t41.mean, 2)], ["Trung vị", fmt(t41.median, 2)],
    ["Độ lệch chuẩn", fmt(t41.std, 2)], ["Thay đổi cả kỳ", `${fmt(t41.change_abs, 2)} (${fmtPct(t41.change_pct)})`], ["Mức mất giá VND (1 − đầu/cuối)", fmt(t41.vnd_depreciation_pct, 2) + "%"],
    ["Số ngày tỷ giá không đổi so với hôm trước", `${t41.flat_days} (${fmt(t41.flat_days_pct, 1)}%)`],
  ].map(([a, b]) => `<tr><td>${a}</td><td class="so">${b}</td></tr>`), "bang-gon"));

  html += fold("Bảng 4.2 – Kiểm định tính dừng ADF và Phillips–Perron", table(["Chuỗi", "Kiểm định", "Dạng", ["Thống kê"], ["p-value"], ["Giá trị tới hạn 1% / 5% / 10%"]],
    r.table_4_2.map(x => `<tr><td>${x.series}</td><td>${x.test}</td><td>${x.form}</td><td class="so">${fmt(x.stat, 4)}<sup>${x.mark}</sup></td><td class="so">${fmt(x.pvalue, 4)}</td>
      <td class="so">${fmt(x.crit["1%"], 3)} / ${fmt(x.crit["5%"], 3)} / ${fmt(x.crit["10%"], 3)}</td></tr>`)) +
    `<p class="ghi-chu">${icon("info", "nho")}<span>a, b, c: bác bỏ giả thuyết có nghiệm đơn vị ở mức 1%, 5%, 10%. Kết luận: ${esc(r.table_4_2_conclusion.text)}</span></p>`);

  if (r.table_4_3.length) html += fold("Bảng 4.3 – ARIMA: 3 cấu trúc có AIC thấp nhất (ước lượng trên tập phát triển)",
    table(["Cấu trúc", ["Số quan sát"], ["Log-likelihood"], ["AIC"], ["BIC"], ["HQIC"]], r.table_4_3.map(x =>
      `<tr><td>ARIMA(${x.order.join(", ")})</td><td class="so">${x.nobs}</td><td class="so">${fmt(x.llf, 3)}</td><td class="so">${fmt(x.aic, 3)}</td><td class="so">${fmt(x.bic, 3)}</td><td class="so">${fmt(x.hqic, 3)}</td></tr>`)) +
    `<div id="bd-arima"></div><p class="ghi-chu">${icon("info", "nho")}<span>Hình 4.1: dự báo 1 ngày của ARIMA trên tập kiểm tra, vùng mờ là khoảng dự báo 95%.</span></p>`);

  html += fold("Bảng 4.4 – Sai số trên tập kiểm tra, cấu hình mặc định (tầng 1)", table(["Mô hình", ["MAE"], ["RMSE"], ["MAPE (%)"], ["Sai số TB"], ["SD RMSE"], ["Số lần chạy"]],
    r.table_4_4.concat([r.random_walk]).map(x => `<tr class="${x.model === "RW" ? "dong-rw" : ""}"><td>${E.MODEL_NAMES[x.model]}</td><td class="so">${fmt(x.MAE, 3)}</td><td class="so">${fmt(x.RMSE, 3)}</td><td class="so">${fmt(x.MAPE, 4)}</td>
      <td class="so">${fmt(x.MeanErr, 3)}</td><td class="so">${fmt(x.SD_RMSE, 3)}</td><td class="so">${x.n_runs}</td></tr>`)) +
    (r.figure_4_2.length ? `<div id="bd-42"></div><p class="ghi-chu">${icon("info", "nho")}<span>Hình 4.2: thực tế so với ARIMA và ba mô hình học máy ở cấu hình mặc định (trung bình các seed).</span></p>` : ""));

  if (r.table_4_5.length) html += fold("Bảng 4.5 – Trước và sau tối ưu siêu tham số (GA, SA)", table(["Mô hình", "Chỉ tiêu", ["Trước"], ["Sau SA"], ["Cải thiện SA"], ["Sau GA"], ["Cải thiện GA"]],
    r.table_4_5.map(x => `<tr><td>${E.MODEL_NAMES[x.model]}</td><td>${x.metric}</td><td class="so">${fmt(x.before, x.metric === "MAPE" ? 4 : 3)}</td>
      <td class="so">${fmt(x.after_sa, x.metric === "MAPE" ? 4 : 3)}</td><td class="so ${x.impr_sa > 0 ? "duong" : x.impr_sa < 0 ? "am" : ""}">${fmtPct(x.impr_sa)}</td>
      <td class="so">${fmt(x.after_ga, x.metric === "MAPE" ? 4 : 3)}</td><td class="so ${x.impr_ga > 0 ? "duong" : x.impr_ga < 0 ? "am" : ""}">${fmtPct(x.impr_ga)}</td></tr>`)) +
    `<p class="ghi-chu">${icon("info", "nho")}<span>Cải thiện = 100 × (trước − sau) / trước. Số dương: sai số giảm sau tối ưu.</span></p>`);

  if (t46) html += fold("Bảng 4.6 – Dự báo ngày tiếp theo (16 trường)", table(["Trường", ["Giá trị"]], E.FIELDS_46.map(f => {
    const v = t46[f];
    return `<tr><td><code>${f}</code></td><td class="so">${typeof v === "number" ? fmt(v, f.includes("Percent") ? 4 : 3) : esc(v)}</td></tr>`;
  }), "bang-gon") + (r.outputs_335 ? `<p class="ghi-chu">${icon("info", "nho")}<span>Siêu tham số của mô hình được chọn: <code>${esc(paramsText(r.outputs_335.hyperparameters))}</code></span></p>` : ""), true);

  // ---------------------------------------------------------------- GA / SA
  if (r.hpo_runs.length) {
    html += fold("GA và SA – quá trình tìm cấu hình", `<div id="bd-hoi-tu"></div>
      <p class="ghi-chu">${icon("info", "nho")}<span>J = RMSE trung bình trên ${r.settings.n_folds} fold kiểm tra chéo cửa sổ mở rộng (chỉ dùng dữ liệu trước tập kiểm tra). Đường: J tốt nhất sau mỗi lần đánh giá, lần chạy 1 của mỗi cặp.</span></p>` +
      table(["Mô hình", "Thuật toán", ["Lần chạy"], ["J tốt nhất"], ["Số đánh giá"], ["Huấn luyện thật"], "Lý do dừng", ["Thời gian"], "Cấu hình tốt nhất"],
        r.hpo_runs.map(x => `<tr><td>${E.MODEL_NAMES[x.model]}</td><td>${x.algo}</td><td class="so">${x.run}</td><td class="so">${fmt(x.J, 4)}</td><td class="so">${x.n_evals}</td><td class="so">${x.n_trained}</td>
          <td>${esc(x.stop_reason)}</td><td class="so">${fmtTime(x.seconds)}</td><td class="o-tham-so">${esc(paramsText(x.params))}</td></tr>`)) +
      (r.hpo_parity && r.hpo_parity.length ? `<p class="ghi-chu">${icon("shield", "nho")}<span>Kiểm tra công bằng GA – SA: ${r.hpo_parity.map(p => `${E.MODEL_NAMES[p.model]}: ${p.applicable ? (p.ok ? "cùng không gian, cùng hàm mục tiêu, cùng fold, cùng ngân sách" : "KHÔNG khớp") : p.note}`).join(" · ")}.</span></p>` : ""));
  }

  // ---------------------------------------------------------------- Dữ liệu và thiết lập
  const sp = r.data.split;
  html += fold("Dữ liệu, làm sạch và chia tập", `
    <dl class="muc-thong-tin">
      <div><dt>Tập phát triển (80%)</dt><dd>${sp.dev_start} – ${sp.dev_end}</dd></div>
      <div><dt>Huấn luyện / kiểm định</dt><dd>${sp.train_samples} / ${sp.val_samples} mẫu</dd></div>
      <div><dt>Tập kiểm tra (20%)</dt><dd>${sp.test_start} – ${sp.test_end} · ${sp.test_samples} mẫu</dd></div>
      <div><dt>Kiểm tra chéo</dt><dd>${sp.folds.length} fold · ${sp.folds.map(f => f.train + "/" + f.val).join(", ")}</dd></div>
    </dl>
    <pre class="nhat-ky">${esc(r.data.clean_log.join("\n"))}</pre>
    <p class="ghi-chu">${icon("info", "nho")}<span>Thiết lập: ${esc(r.mode_name)} · ngân sách ${r.settings.budget} · ${r.settings.n_hpo_runs} lần chạy GA/SA · ${r.settings.n_baseline_seeds} seed mặc định · ${r.settings.n_refit_seeds} seed dự báo${r.threads ? " · " + r.threads + " luồng" : ""}${r.checkpoint_reused ? ` · ${r.checkpoint_reused} phần việc lấy lại từ lần chạy trước` : ""}.</span></p>`);

  html += `<p class="ghi-chu">${icon("info", "nho")}<span>Bản HTML dùng bộ máy viết lại bằng JavaScript (ARIMA, ANN, Random Forest, XGBoost, GA, SA) theo đúng quy trình của bản Python; vì bộ sinh số ngẫu nhiên khác nhau nên số liệu của các mô hình học máy có thể lệch nhẹ so với bản Python, nhưng cùng phương pháp.</span></p>`;
  el.innerHTML = html;

  // ---------------------------------------------------------------- Vẽ biểu đồ
  const n = r.test.dates.length, labels = r.test.dates.concat(ch ? [ch.t1.date] : []), pad = a => a.concat(ch ? [null] : []);
  const series = [{ name: "Thực tế", data: pad(r.test.actual), color: "--c-actual", width: 2 }];
  if (ch) series.push({ name: ch.label + " (được chọn)", data: pad(ch.pred), color: "--primary", width: 2 });
  for (const k of r.ranking) if (k !== r.chosen_key) {
    const x = c[k];
    series.push({ name: x.label, data: pad(x.pred), color: COLOR[x.model], dash: [5, 4], width: 1.3, hidden: k !== "ARIMA" });
  }
  series.push({ name: "Random walk", data: pad(r.test.random_walk), color: "--c-rw", dash: [2, 3], width: 1.2, hidden: true });
  if (ch) { const d = new Array(n + 1).fill(null); d[n - 1] = r.test.actual[n - 1]; d[n] = ch.t1.mean; series.push({ name: "Dự báo T+1", data: d, color: "--primary", dash: [6, 4], width: 2, point: n }); }
  Charts.line($("#bd-test"), { labels, series, xFmt: ngayVN, aria: "Thực tế và dự báo trên tập kiểm tra" });
  if (r.figure_4_1 && $("#bd-arima")) {
    const f = r.figure_4_1;
    Charts.line($("#bd-arima"), { labels: f.dates, size: "vua", xFmt: ngayVN, aria: "Hình 4.1 ARIMA",
      series: [{ name: "Thực tế", data: f.actual, color: "--c-actual", width: 2 },
               { name: `ARIMA(${f.order.join(", ")})`, data: f.pred, color: "--c-arima", width: 1.5, band: { lo: f.lo, hi: f.hi } }] });
  }
  if ($("#bd-42")) Charts.line($("#bd-42"), { labels: r.test.dates, size: "vua", xFmt: ngayVN, aria: "Hình 4.2",
    series: [{ name: "Thực tế", data: r.test.actual, color: "--c-actual", width: 2 }].concat(r.figure_4_2.map(f => ({ name: f.label, data: f.pred, color: COLOR[f.model], dash: [5, 4], width: 1.3 }))) });
  if ($("#bd-hoi-tu")) {
    const firsts = r.hpo_runs.filter(x => x.run === 1), len = Math.max(...firsts.map(x => x.history.length));
    Charts.line($("#bd-hoi-tu"), { labels: Array.from({ length: len }, (_, i) => String(i + 1)), size: "vua", aria: "Hội tụ GA/SA",
      xFmt: s => s, tipX: s => "Lần đánh giá " + s, yFmt: v => E.vn(v, 2), tipFmt: v => E.vn(v, 4),
      series: firsts.map(x => ({ name: `${E.MODEL_NAMES[x.model]} – ${x.algo}`, data: x.history, color: COLOR[x.model], dash: x.algo === "SA" ? [5, 4] : null, width: 1.6 })) });
  }
  $$("[data-tai]", el).forEach(b => b.addEventListener("click", () => download(b.dataset.tai)));
  el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function rmseBars(r) {
  const items = r.ranking.map(k => ({ label: r.candidates[k].label, v: r.candidates[k].summary.RMSE, chosen: r.candidates[k].chosen }))
    .concat([{ label: "Random walk", v: r.random_walk.RMSE }]).sort((a, b) => a.v - b.v);
  const max = Math.max(...items.map(x => x.v)), min = Math.min(...items.map(x => x.v)), base = Math.max(0, min - (max - min) * 1.5);
  return `<div class="thanh-so-sanh">${items.map(x => `<div class="dong ${x.chosen ? "chon" : ""}"><span>${esc(x.label)}</span>
    <div class="ray"><div style="width:${Math.max(4, (x.v - base) / (max - base) * 100)}%"></div></div><span class="so">${fmt(x.v, 2)}</span></div>`).join("")}</div>
    <p class="ghi-chu">${icon("info", "nho")}<span>Thanh bắt đầu từ ${fmt(base, 1)} để thấy rõ chênh lệch.</span></p>`;
}

// ======================================================================== Tải xuống

function save(name, text, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
const csvCell = v => (typeof v === "number" ? String(v) : `"${String(v === null || v === undefined ? "" : v).replace(/"/g, '""')}"`);
function download(kind) {
  const r = state.result;
  if (!r) return;
  const stamp = (r.finished_at || new Date().toISOString()).slice(0, 16).replace(/[-:T]/g, "");
  if (kind === "json") save(`ket_qua_du_bao_${r.mode}_${stamp}.json`, JSON.stringify(r), "application/json");
  if (kind === "in") window.print();
  if (kind === "csv") {
    const keys = r.ranking;
    const head = ["Ngay", "Thuc_te", "Random_walk"].concat(keys.map(k => r.candidates[k].label));
    const lines = [head.map(csvCell).join(",")];
    r.test.dates.forEach((d, i) => lines.push([d, r.test.actual[i], r.test.random_walk[i]].concat(keys.map(k => r.candidates[k].pred[i])).map(csvCell).join(",")));
    save(`du_bao_tap_kiem_tra_${stamp}.csv`, "﻿" + lines.join("\n"), "text/csv");
  }
  if (kind === "t46" && r.table_4_6) {
    const lines = [E.FIELDS_46.map(csvCell).join(","), E.FIELDS_46.map(f => csvCell(r.table_4_6[f])).join(",")];
    save(`bang_4_6_${stamp}.csv`, "﻿" + lines.join("\n"), "text/csv");
  }
}

// ======================================================================== Mở kết quả đã lưu, lịch sử

$("#file-ket-qua").addEventListener("change", e => e.target.files[0] && openResultFile(e.target.files[0]));
async function openResultFile(f) {
  try {
    const r = JSON.parse(await f.text());
    if (!r || !r.candidates || !r.table_4_1) throw new Error("File không phải kết quả của web này.");
    showResult(r);
  } catch (e) {
    showEnvWarning("Không mở được file kết quả: " + (e.message || e));
  }
}

async function refreshHistory() {
  const all = (await DB.all("results")) || [];
  const card = $("#the-lich-su");
  card.hidden = !all.length;
  all.sort((a, b) => b.id - a.id);
  $("#ds-lich-su").innerHTML = all.slice(0, 20).map(x => {
    const r = x.result, ch = r.chosen_key ? r.candidates[r.chosen_key] : null;
    return `<tr><td>${esc(new Date(x.saved).toLocaleString("vi-VN"))}</td><td>${esc(r.data.filename || "")}</td><td>${esc(r.mode_name)}</td>
      <td>${ch ? esc(ch.label) : "—"}</td><td class="so">${ch ? fmt(ch.t1.mean, 2) + " (" + ngayVN(ch.t1.date) + ")" : "—"}</td>
      <td class="so"><button class="nut nut-vien nut-nho" data-mo="${x.id}" type="button">Xem</button>
        <button class="nut nut-icon nguy" data-xoa="${x.id}" type="button" aria-label="Xóa kết quả này">${icon("trash")}</button></td></tr>`;
  }).join("");
  $$("[data-mo]").forEach(b => b.addEventListener("click", async () => { const x = await DB.get("results", Number(b.dataset.mo)); if (x) showResult(x.result); }));
  $$("[data-xoa]").forEach(b => b.addEventListener("click", async () => {
    if (!(await askConfirm("Xóa kết quả này khỏi trình duyệt?", "Xóa"))) return;
    await DB.del("results", Number(b.dataset.xoa)); refreshHistory();
  }));
}
$("#nut-xoa-tam").addEventListener("click", async () => {
  if (!(await askConfirm("Xóa tiến độ tạm (phần việc đã chạy dở để chạy tiếp)? Kết quả đã chạy xong vẫn giữ.", "Xóa"))) return;
  await DB.clear("units");
  showEnvWarning("Đã xóa tiến độ tạm.");
});

// ======================================================================== Khởi động

syncThemeIcon();
if (window.__ARTIFACT__) document.body.classList.add("ban-link");
updateRunButton();
refreshHistory();
if (location.protocol === "file:" && !window.indexedDB) showEnvWarning("Trình duyệt không cho lưu tiến độ khi mở file trực tiếp: nếu đóng tab giữa chừng sẽ phải chạy lại từ đầu.");
window.__app = { state, showResult, loadFile };
})();
