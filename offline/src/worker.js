/* Web Worker: giữ ngữ cảnh dữ liệu và chạy từng đơn vị việc nặng (huấn luyện, GA/SA, ARIMA) ngoài luồng giao diện. */
(function () {
  "use strict";
  let ctx = null, lastSend = 0;
  self.onmessage = function (e) {
    const m = e.data;
    try {
      if (m.type === "init") {
        ctx = new E.Context(m.y, m.cfg);
        self.postMessage({ type: "ready", id: m.id });
        return;
      }
      if (m.type === "task") {
        const send = msg => {
          const now = Date.now();
          if (now - lastSend < 250) return;               // tối đa ~4 tin/giây
          lastSend = now;
          self.postMessage({ type: "msg", id: m.id, msg });
        };
        const value = E.tasks[m.task](ctx, m.args, send);
        self.postMessage({ type: "done", id: m.id, value });
      }
    } catch (err) {
      self.postMessage({ type: "error", id: m.id, message: String((err && err.message) || err) });
    }
  };
})();
