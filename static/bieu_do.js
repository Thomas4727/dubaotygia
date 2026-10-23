/* Biểu đồ so sánh "Thực tế và dự báo" – component Chart.js hiện có của web, tách ra để dùng chung.
   GIỮ NGUYÊN kiểu vẽ, màu, bố cục (đặc tả v3 mục 0.4): thực tế nét liền màu chữ; mô hình được chọn nét liền
   màu chính; ứng viên khác nét đứt theo màu mô hình; dự báo T+1 nét đứt + điểm hình thoi; vùng mờ = khoảng 95%.
   Chỉ nhận thêm dữ liệu (nhiều đường, dải 95% trên tập test cho ARIMA). */
(function () {
  const KHOA_MAU = { ARIMA: "ARIMA", ANN: "ANN", RF: "RF", XGB: "XGBoost", RW: "RandomWalk" };
  const vnd = (v, so = 1) => v.toLocaleString("vi-VN", { maximumFractionDigits: so });
  const ngayVN = s => s.slice(8, 10) + "/" + s.slice(5, 7) + "/" + s.slice(0, 4);
  const danhSach = [];      // {canvas, cauHinh, chart} – vẽ lại khi đổi giao diện sáng/tối

  function mau() {
    const css = getComputedStyle(document.documentElement);
    const v = k => css.getPropertyValue(k).trim();
    const sang = document.documentElement.dataset.theme === "light";
    return {
      chu: v("--text"), phu: v("--text-muted"), luoi: v("--border-soft"), chinh: sang ? "#1E40AF" : "#3B82F6",
      mo: sang ? "rgba(30,64,175,.15)" : "rgba(59,130,246,.18)",
      chuoi: sang ? { RandomWalk: "#64748B", ARIMA: "#B45309", ANN: "#0E7490", RF: "#047857", XGBoost: "#BE123C" }
                  : { RandomWalk: "#94A3B8", ARIMA: "#F59E0B", ANN: "#22D3EE", RF: "#34D399", XGBoost: "#FB7185" },
    };
  }

  function caiMacDinh(m) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.font.size = 12;
    Chart.defaults.color = m.phu;
    Chart.defaults.borderColor = m.luoi;
    Chart.defaults.plugins.tooltip.titleFont = { weight: "600" };
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
    Chart.defaults.plugins.legend.labels.boxWidth = 8;
  }

  function taoChart(canvas, c) {
    const m = mau();
    caiMacDinh(m);
    const n = c.dates.length;
    const coT1 = !!c.t1;
    const nhan = (coT1 ? [...c.dates, c.t1.date] : c.dates).map(ngayVN);
    const them = coT1 ? [null] : [];
    const rong = () => Array(nhan.length).fill(null);
    const bo = [{ label: "Thực tế", data: [...c.actual, ...them], borderColor: m.chu, backgroundColor: m.chu,
                  borderWidth: 2, pointRadius: 0, order: 1 }];
    for (const s of c.series) {
      const mauMH = m.chuoi[KHOA_MAU[s.model] || s.model];
      bo.push({ label: s.label + (s.chosen ? " (được chọn)" : ""), data: [...s.values, ...them],
                borderColor: s.chosen ? m.chinh : mauMH, backgroundColor: s.chosen ? m.chinh : mauMH,
                borderWidth: s.chosen ? 2 : 1.3, borderDash: s.chosen ? [] : [5, 4], pointRadius: 0,
                hidden: s.hidden !== undefined ? s.hidden : !s.chosen, order: s.chosen ? 2 : 5 });
    }
    if (c.band) {                                  // dải 95% trên tập test (Hình 4.1) – cùng kiểu vùng tô
      bo.push({ label: c.band.label || "Khoảng dự báo 95%", data: [...c.band.hi, ...them], borderColor: "transparent",
                backgroundColor: m.mo, pointRadius: 0, fill: "+1", order: 3 });
      bo.push({ label: "_duoi_dai", data: [...c.band.lo, ...them], borderColor: "transparent", backgroundColor: m.mo,
                pointRadius: 0, order: 3 });
    }
    if (coT1) {
      const cuoi = c.actual[n - 1];
      const duBao = rong(); duBao[n - 1] = cuoi; duBao[n] = c.t1.value;
      bo.push({ label: "Dự báo T+1", data: duBao, borderColor: m.chinh, backgroundColor: m.chinh, borderWidth: 2,
                borderDash: [6, 4], pointRadius: ctx => (ctx.dataIndex === n ? 6 : 0), pointStyle: "rectRot", order: 0 });
      if (c.t1.lo !== undefined && c.t1.lo !== null) {
        const tren = rong(); tren[n - 1] = cuoi; tren[n] = c.t1.hi;
        const duoi = rong(); duoi[n - 1] = cuoi; duoi[n] = c.t1.lo;
        bo.push({ label: "Khoảng 95%", data: tren, borderColor: "transparent", backgroundColor: m.mo, pointRadius: 0,
                  fill: "+1", order: 3 });
        bo.push({ label: "_duoi", data: duoi, borderColor: "transparent", backgroundColor: m.mo, pointRadius: 0, order: 3 });
      }
    }
    const khoang = c.khoang || 40;
    return new Chart(canvas, {
      type: "line", data: { labels: nhan, datasets: bo },
      options: {
        responsive: true, maintainAspectRatio: false, animation: false, spanGaps: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { min: Math.max(0, n - khoang), ticks: { maxTicksLimit: 8, maxRotation: 0 }, grid: { display: false } },
          y: { ticks: { callback: v => vnd(v, 0) } },
        },
        plugins: {
          legend: { labels: { filter: i => !i.text.startsWith("_"), sort: (a, b) => a.datasetIndex - b.datasetIndex } },
          tooltip: {
            filter: i => i.raw !== null && !i.dataset.label.startsWith("_"),
            callbacks: {
              title: i => coT1 && i[0].dataIndex === n ? i[0].label + " · dự báo T+1" : i[0].label,
              label: i => {
                if (i.dataset.label === "Khoảng 95%") return ` Khoảng 95%: ${vnd(c.t1.lo)} – ${vnd(c.t1.hi)}`;
                if (c.band && i.dataset.label === (c.band.label || "Khoảng dự báo 95%"))
                  return ` ${i.dataset.label}: ${vnd(c.band.lo[i.dataIndex])} – ${vnd(c.band.hi[i.dataIndex])}`;
                return ` ${i.dataset.label}: ${vnd(i.raw)}`;
              },
            },
          },
        },
      },
    });
  }

  function ve(canvas, cauHinh) {
    const muc = { canvas, cauHinh, chart: taoChart(canvas, cauHinh) };
    danhSach.push(muc);
    return muc;
  }

  function huy(muc) {
    if (!muc) return;
    muc.chart.destroy();
    const i = danhSach.indexOf(muc);
    if (i >= 0) danhSach.splice(i, 1);
  }

  function doiKhoang(muc, khoang) {
    muc.cauHinh.khoang = khoang;
    muc.chart.options.scales.x.min = Math.max(0, muc.cauHinh.dates.length - khoang);
    muc.chart.update();
  }

  document.addEventListener("doi-giao-dien", () => {
    for (const muc of danhSach) { muc.chart.destroy(); muc.chart = taoChart(muc.canvas, muc.cauHinh); }
  });

  window.BieuDoSoSanh = { ve, huy, doiKhoang, mau, vnd, ngayVN };
})();
