/* Giới thiệu công cụ trong lúc chạy: mỗi thẻ giải thích một phần của quy trình, tự chuyển theo bước đang chạy
   (thay cho slide giới thiệu công cụ khi thuyết trình). Người xem có thể tự bấm trước / sau. */
(function () {
"use strict";

const CARDS = [
  { steps: [1], tag: "Tổng quan", title: "Công cụ dự báo tỷ giá USD/VND ngày làm việc tiếp theo",
    lead: "Một quy trình khép kín: nhận dữ liệu tỷ giá, tự kiểm tra, huấn luyện và tối ưu các mô hình, chọn mô hình tốt nhất rồi đưa ra dự báo kèm cảnh báo.",
    cols: [["Đầu vào", ["Chuỗi tỷ giá USD/VND theo ngày (file .csv)", "Chọn chế độ chạy, mô hình, cách tối ưu", "Ngưỡng cảnh báo biến động"]],
           ["Xử lý lõi", ["Làm sạch dữ liệu, kiểm định tính dừng", "Tạo đặc trưng: trễ, lợi suất, trung bình trượt", "Huấn luyện ARIMA, ANN, Random Forest, XGBoost; tối ưu bằng GA và SA", "Đánh giá lặp lại, chọn mô hình tốt nhất"]],
           ["Đầu ra quản lý", ["Tỷ giá dự báo ngày làm việc tiếp theo", "Cảnh báo Tăng / Giảm / Ổn định", "Bảng 4.1 – 4.6, biểu đồ, kết luận giả thuyết"]]] },
  { steps: [2], tag: "Bước 2", title: "Làm sạch dữ liệu",
    lead: "Dữ liệu bẩn làm mô hình học sai. Công cụ tự làm 6 bước, không cần sửa tay.",
    cols: [["Chuẩn hóa", ["Đọc nhiều định dạng ngày: 28/10/2026, 2026-10-28…", "Sắp xếp theo thời gian tăng dần", "Bỏ dòng trùng ngày (giữ dòng cuối)"]],
           ["Kiểm tra giá trị", ["Bỏ tỷ giá trống, âm hoặc bằng 0", "Điểm dị thường: nhảy hơn 1% rồi hôm sau quay lại → loại", "Chỉ giữ ngày làm việc, không tự bịa số cho ngày nghỉ"]]] },
  { steps: [3], tag: "Bước 3", title: "Thống kê mô tả và kiểm định tính dừng",
    lead: "Chuỗi “dừng” là chuỗi có trung bình và độ dao động không đổi theo thời gian. Tỷ giá thường không dừng vì có xu hướng tăng dần.",
    cols: [["Kiểm định ADF và Phillips–Perron", ["Giả thuyết H0: chuỗi có nghiệm đơn vị (không dừng)", "Bác bỏ H0 ở mức 1%, 5%, 10% → đánh dấu a, b, c", "Kiểm cho cả tỷ giá và mức thay đổi hằng ngày"]],
           ["Vì sao quan trọng", ["Tỷ giá không dừng nhưng mức thay đổi thì dừng → I(1)", "Vì vậy mô hình dự báo MỨC THAY ĐỔI, rồi cộng vào tỷ giá hôm nay", "Bậc sai phân d này cũng dùng cho ARIMA"]]] },
  { steps: [4], tag: "Bước 4", title: "Tạo đặc trưng và chia dữ liệu theo thời gian",
    lead: "Mô hình học máy cần “gợi ý” để học. Mỗi ngày được mô tả bằng các con số chỉ dùng thông tin đến hết ngày đó.",
    cols: [["Đặc trưng", ["Trễ: mức thay đổi của p ngày gần nhất", "Lợi suất: thay đổi so với hôm trước (%)", "Trung bình và độ lệch chuẩn trượt w ngày", "Khoảng cách tới trung bình trượt, động lượng"]],
           ["Chia dữ liệu", ["80% đầu: xây dựng mô hình; 20% cuối: kiểm tra", "Không xáo trộn: tương lai không được lọt vào quá khứ", "Kiểm tra chéo cửa sổ mở rộng để chấm điểm cấu hình"]]] },
  { steps: [5], tag: "Bước 5", title: "ARIMA – mô hình kinh tế lượng để đối chứng",
    lead: "ARIMA dự báo dựa trên các giá trị và sai số trong quá khứ. Đây là thước đo để xem học máy có thật sự tốt hơn cách truyền thống không.",
    cols: [["Cách làm", ["Thử 25 cấu trúc ARIMA(p, d, q) với p, q từ 0 đến 4", "Chọn cấu trúc có AIC thấp nhất (vừa khớp dữ liệu, vừa gọn)", "Dự báo từng ngày trên 20% dữ liệu kiểm tra"]],
           ["Lưu ý", ["ARIMA chỉ để so sánh, không được chọn làm mô hình chính", "Có khoảng dự báo 95% (vùng mờ trên biểu đồ)"]]] },
  { steps: [6], tag: "Bước 6", title: "Ba mô hình học máy",
    lead: "Mỗi mô hình được huấn luyện nhiều lần với cấu hình mặc định để đo độ chính xác và độ ổn định.",
    cols: [["ANN – mạng nơ-ron", ["Nhiều lớp “nơ-ron” học quan hệ phi tuyến", "Nhạy với cách khởi tạo ban đầu"]],
           ["Random Forest", ["Hàng trăm cây quyết định, lấy trung bình", "Thường ổn định giữa các lần chạy"]],
           ["XGBoost", ["Cây sau sửa sai số của cây trước", "Có dừng sớm để tránh học thuộc lòng"]]] },
  { steps: [7], tag: "Bước 7", title: "Tối ưu siêu tham số bằng GA – thuật toán di truyền",
    lead: "Siêu tham số là các “nút vặn” của mô hình (số cây, độ sâu, tốc độ học…). GA mô phỏng chọn lọc tự nhiên để tìm bộ nút vặn tốt.",
    cols: [["Cách hoạt động", ["Quần thể: nhiều cấu hình cùng lúc", "Chọn lọc: cấu hình sai số thấp được giữ", "Lai ghép và đột biến tạo cấu hình mới", "Lặp qua nhiều thế hệ"]],
           ["Chấm điểm", ["Điểm J = RMSE trung bình trên các giai đoạn kiểm tra chéo", "Chỉ dùng dữ liệu trước phần kiểm tra – không “nhìn trộm” đáp án"]]] },
  { steps: [8], tag: "Bước 8", title: "Tối ưu siêu tham số bằng SA – mô phỏng luyện kim",
    lead: "SA giống làm nguội kim loại: lúc đầu “nóng” nên dám thử cả cấu hình kém hơn để không bị kẹt, càng về sau càng chỉ nhận cấu hình tốt hơn.",
    cols: [["Cách hoạt động", ["Bắt đầu từ cấu hình mặc định", "Thử cấu hình lân cận (đổi 1–2 nút vặn)", "Nhiệt độ T giảm dần sau mỗi vòng"]],
           ["So sánh công bằng với GA", ["Cùng không gian tìm kiếm", "Cùng hàm điểm J và cùng các giai đoạn kiểm tra", "Cùng ngân sách số lần thử"]]] },
  { steps: [9], tag: "Bước 9", title: "Đánh giá trên 20% dữ liệu cuối",
    lead: "Mọi mô hình được chạy lại nhiều lần trên phần dữ liệu chưa từng dùng khi xây dựng, để đo cả độ chính xác lẫn độ ổn định.",
    cols: [["Chỉ tiêu", ["RMSE: sai số bình phương trung bình, phạt nặng sai số lớn (đơn vị VND)", "MAE: sai số tuyệt đối trung bình", "MAPE: sai số theo phần trăm"]],
           ["Mốc so sánh", ["ARIMA: mô hình truyền thống", "Random walk: “ngày mai bằng hôm nay” – mốc khó vượt qua (Meese–Rogoff)", "Trước và sau tối ưu: GA, SA cải thiện bao nhiêu"]]] },
  { steps: [10], tag: "Bước 10", title: "Chọn mô hình",
    lead: "Mô hình được chọn là ứng viên có RMSE trung bình thấp nhất qua các lần chạy lặp trên dữ liệu kiểm tra.",
    cols: [["Ứng viên", ["ANN, Random Forest, XGBoost", "Mỗi mô hình 3 cách cấu hình: mặc định, GA, SA → tối đa 9 ứng viên"]],
           ["Không được chọn", ["ARIMA và Random walk chỉ dùng để đối chiếu"]]] },
  { steps: [11, 12], tag: "Bước 11 – 12", title: "Dự báo ngày tiếp theo và cảnh báo",
    lead: "Mô hình được chọn được huấn luyện lại rồi dự báo tỷ giá ngày làm việc kế tiếp, kèm cảnh báo cho người quản lý.",
    cols: [["Dự báo", ["Lặp nhiều lần, lấy trung bình", "Khoảng dao động P05 – P95 giữa các lần", "Khoảng theo sai số lịch sử: dự báo ± 1,96 × RMSE"]],
           ["Cảnh báo", ["Ổn định: thay đổi dự báo nhỏ hơn ngưỡng (mặc định 0,10%)", "Tăng / Giảm: vượt ngưỡng theo chiều tương ứng", "Kết quả, bảng và biểu đồ hiện ngay bên dưới"]]] },
];
const MIN_DWELL = 9000, ROTATE = 14000;
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

let idx = 0, shownAt = 0, auto = true, lastSnap = null, timer = null;

function render() {
  const c = CARDS[idx], box = $("#gt-the");
  box.innerHTML = `
    <div class="gt-dau"><span class="nhan nhan-chon">${esc(c.tag)}</span><span class="muted">${idx + 1} / ${CARDS.length}</span></div>
    <h3 class="gt-tieu-de">${esc(c.title)}</h3>
    <p class="gt-mo-dau">${esc(c.lead)}</p>
    <div class="gt-cot gt-cot-${c.cols.length}">${c.cols.map(([h, items]) => `<div><b>${esc(h)}</b><ul>${items.map(i => `<li>${esc(i)}</li>`).join("")}</ul></div>`).join("")}</div>
    <div class="gt-dang" id="gt-dang"></div>`;
  $("#gt-cham").innerHTML = CARDS.map((_, i) => `<button type="button" aria-label="Thẻ ${i + 1}" aria-current="${i === idx}" data-i="${i}"></button>`).join("");
  $("#gt-cham").querySelectorAll("button").forEach(b => b.addEventListener("click", () => go(Number(b.dataset.i), true)));
  shownAt = Date.now();
  live();
}
function live() {
  const el = $("#gt-dang");
  if (!el || !lastSnap) return;
  const st = lastSnap.steps.filter(s => CARDS[idx].steps.includes(s.id) && (s.status === "dang_chay" || s.status === "xong"));
  el.innerHTML = st.map(s => `<span class="nhan ${s.status === "xong" ? "tt-xong" : "tt-dang_chay"}">${s.status === "xong" ? "Xong" : "Đang chạy"}</span> ${esc(s.detail || "")}`).join("<br>");
  el.hidden = !st.length;
}
function go(i, manual) {
  idx = (i + CARDS.length) % CARDS.length;
  if (manual) setAuto(false);
  render();
}
function setAuto(on) {
  auto = on;
  $("#gt-tu-dong").checked = on;
  if (on) follow(true);
}
/** Chọn thẻ theo bước đang chạy; giữ mỗi thẻ đủ lâu để đọc. Nhiều bước chạy cùng lúc (GA, SA) thì luân phiên. */
function follow(force) {
  if (!auto || !lastSnap) return;
  const running = lastSnap.steps.filter(s => s.status === "dang_chay").map(s => s.id);
  const done = lastSnap.steps.filter(s => s.status === "xong").map(s => s.id);
  let targets = CARDS.map((c, i) => (c.steps.some(s => running.includes(s)) ? i : -1)).filter(i => i >= 0);
  if (!targets.length && done.length) targets = [CARDS.findIndex(c => c.steps.includes(Math.max(...done)))];
  if (!targets.length) return;
  const since = Date.now() - shownAt;
  if (!force && since < MIN_DWELL) return;
  let next;
  if (targets.includes(idx)) {
    if (targets.length < 2 || since < ROTATE) return;
    next = targets[(targets.indexOf(idx) + 1) % targets.length];
  } else {
    // đi lần lượt, không nhảy cóc qua thẻ chưa xem khi các bước đầu chạy quá nhanh
    next = targets[0] > idx && !force ? Math.min(targets[0], idx + 1) : targets[0];
  }
  if (next !== idx) go(next, false);
}

window.Intro = {
  start() {
    $("#the-gioi-thieu").hidden = false;
    lastSnap = null;
    setAuto(true);
    go(0, false);
    clearInterval(timer);
    timer = setInterval(() => follow(false), 1000);
  },
  update(snap) { lastSnap = snap; live(); follow(false); },
  stop() { clearInterval(timer); timer = null; },
};

document.addEventListener("DOMContentLoaded", () => {});
$("#gt-truoc").addEventListener("click", () => go(idx - 1, true));
$("#gt-sau").addEventListener("click", () => go(idx + 1, true));
$("#gt-tu-dong").addEventListener("change", e => setAuto(e.target.checked));
$("#nut-xem-gioi-thieu").addEventListener("click", () => {
  $("#the-gioi-thieu").hidden = false;
  if (!timer) { setAuto(false); go(0, true); }
  $("#the-gioi-thieu").scrollIntoView({ behavior: "smooth", block: "start" });
});
document.addEventListener("keydown", e => {
  if ($("#the-gioi-thieu").hidden || /INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) return;
  if (e.key === "ArrowRight") go(idx + 1, true);
  if (e.key === "ArrowLeft") go(idx - 1, true);
});
})();
