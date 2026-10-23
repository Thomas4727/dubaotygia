# Đối chiếu web với bài NCKH gốc

Bài: "Dự báo tỷ giá hối đoái dựa trên các thuật toán học máy và tối ưu hóa siêu tham số" (file `đề tài mẫu.pdf`,
107 trang; số trang dưới đây là số in trên trang). Đối chiếu trực tiếp với văn bản, các bảng và Hình 3.1–3.3, 4.2 của bài.

Nguyên tắc: bài quy định thì làm đúng như bài; bài chỉ nêu tên mà không cho giá trị thì giữ giá trị hiện tại và ghi
**"lựa chọn của web, bài không quy định"** (trong code: `[WEB]`); phần web tự thêm gắn nhãn **"bổ sung ngoài bài"**;
khi prompt và bài khác nhau thì **làm theo bài** (người dùng xác nhận). Không thêm phương pháp bài không dùng
(không Diebold–Mariano – bài để ở hướng nghiên cứu tiếp theo, tr. 82–83).

Trạng thái: **ĐÃ SỬA**. Cột "Trước" là hiện trạng lúc lập bảng (bước 0), cột "Sau" là sau khi sửa.

## 1. Hai chế độ chạy

| Yêu cầu | Bài | Trước | Sau (file, hàm) | Đạt |
|---|---|---|---|---|
| Hai chế độ dùng chung một pipeline | – | Đạt: `pipeline.run_pipeline`, tham số ở `run_config.MODES` | Giữ nguyên; test `test_hai_che_do_goi_cung_mot_ham` | Đạt |
| Chạy đầy đủ không cắt giảm | 30 lần chạy (tr. 51, 64, 72) | Đạt | Giữ nguyên; thêm bước đánh giá lặp lại ứng viên 30 lần (mục 7.5) | Đạt |
| Chạy thử: cùng hàm, giảm lần lặp; nhãn "kết quả Chạy thử, không dùng để so với bài" | – | Nhãn "Chạy thử" chung | Nhãn trên mọi bảng/hình (`nckh.html` macro `nhan_thu`) và trong H1–H3 (`evaluate.hypotheses`); mô tả nút theo yêu cầu | Đạt |
| Khung "Thiết lập bài không quy định, lựa chọn của web" | – | Không có | `run_config.WEB_SETTINGS`, `settings_table`; `search_space.space_table`; `templates/_thiet_lap.html` ở form chạy và trang kết quả | Đạt |

## 2. Dữ liệu và làm sạch (mục 3.2, 3.3.1 – tr. 29–30)

| Yêu cầu | Bài | Trước | Sau | Đạt |
|---|---|---|---|---|
| Đơn biến, ngày làm việc, không nội suy | "giữ nguyên tần suất ngày làm việc" | Đạt | Giữ nguyên (`data_io.clean`) | Đạt |
| 6 bước đúng thứ tự, ghi nhật ký | 6 bước tr. 29–30 | Đạt (sửa ở lần trước) | Giữ nguyên | Đạt |
| File Vietcombank chuyển khoản | "Tỷ giá VND/USD chuyển khoản … Vietcombank" | Đạt (ưu tiên "Mua chuyển khoản") | Giữ nguyên; ghi chú không so trực tiếp với bài cho file khác | Đạt |

## 3. Đặc trưng, tính dừng, chống rò rỉ (mục 3.3.1, 4.1.2, 4.5)

| Yêu cầu | Bài | Trước | Sau | Đạt |
|---|---|---|---|---|
| Lag, Return, MA, STD, Momentum; cửa sổ lùi | Hình 3.3: "Lag • Return • MA • STD • Momentum"; tr. 72 "đặc trưng trượt được dịch lùi" | Đạt | Giữ (`features.build_features`); công thức Momentum `[WEB]` | Đạt |
| **ANN chỉ dùng p giá trị trễ** | Công thức 3.3, 3.9 và Bảng 3.1 chỉ có p | ANN có w và đủ đặc trưng | `features.build_features(p, w=None)` → chỉ trễ của Δy; `search_space.space("ANN")` bỏ w; `Context.run` dùng `params.get("w")` | Đạt |
| Scaler fit trên train của từng lượt | tr. 30 | Đạt | Giữ; test (b) | Đạt |
| ADF, PP (c, ct) cho EXR, D.EXR | Bảng 4.2 | Đạt | Bảng 4.2 trình bày theo bố cục của bài (dòng EXR/D.EXR, 4 cột) | Đạt |
| Sai phân bậc 1, cộng lại về mức | tr. 61 | Đạt | Giữ | Đạt |

## 4. Chia mẫu và ba tầng (mục 3.3.2 – tr. 30)

Đạt từ trước, giữ nguyên: `splits.make_split` (80/20), tầng 1 `_task_eval(tier=1)`, tầng 2 `Context.cv_scores` trên vùng
trước test, tầng 3 `_task_eval(tier=3)`; early stopping XGBoost trên validation / 15% cuối phần train.

## 5. Mô hình và không gian siêu tham số (mục 3.3.3, Bảng 3.1–3.3)

| Yêu cầu | Bài | Trước | Sau | Đạt |
|---|---|---|---|---|
| ARIMA: d theo nghiệm đơn vị, 25 cấu trúc, AIC, 3 cấu trúc tốt nhất, khoảng 95% | tr. 45–46, Bảng 4.3, Hình 4.1 | Đạt | Bảng 4.3 trình bày theo bài (chỉ tiêu theo dòng, 3 mô hình theo cột) | Đạt |
| ANN: MLP, ReLU, đầu ra tuyến tính, dropout | tr. 33 "Nghiên cứu này dùng hàm ReLU" | Đạt | Bỏ w (mục 3) | Đạt |
| RF: 8 siêu tham số + p, w | Bảng 3.2; tr. 39 | Đạt | Giữ | Đạt |
| XGBoost: Bảng 3.3 + reg_alpha, reg_lambda, w; không grow_policy; lr và n_estimators tối ưu đồng thời | Bảng 3.3; tr. 41–42 | Đạt | Giữ | Đạt |
| Random walk chỉ đối chiếu | tr. 57 | Đạt | Giữ | Đạt |

## 6. Hàm mục tiêu, GA, SA (mục 3.3.4, Bảng 3.4–3.7, Hình 3.1–3.2)

Đạt từ trước (`Context.cv_objective` = công thức 3.33, `ga.run_ga`, `sa.run_sa`, `pipeline._task_hpo`), kiểm tra GA/SA
cùng điều kiện mỗi phiên (`pipeline.hpo_parity`). Giá trị tham số GA/SA: `[WEB]` (bảng ở mục "Lựa chọn của web").

## 7. 30 lần chạy và chọn mô hình (mục 3.3.4.1, 4.3, 4.4, 4.5)

| Yêu cầu | Bài | Trước | Sau | Đạt |
|---|---|---|---|---|
| Bảng 4.4: 30 lần mỗi mô hình | tr. 64 "120 lần chạy" | Đạt | Giữ; thêm SD, CV RMSE (bài thảo luận ở tr. 65–66) | Đạt |
| GA, SA: 30 lần độc lập mỗi mô hình | tr. 51 | Đạt | Giữ | Đạt |
| Cấu hình cuối GA/SA | "cấu hình có RMSE thấp nhất trong đa số lần chạy và có hiệu quả tốt và ổn định qua nhiều lần đánh giá" (tr. 51) – không có công thức | J thấp nhất; hòa (< 0,5%) thì so độ ổn định RMSE **trên tập kiểm tra** | `pipeline.final_config`: J thấp nhất; hòa thì chọn RMSE ổn định nhất **qua các cửa sổ xác thực**; không dùng tập kiểm tra vì "tập kiểm tra cuối cùng được tách biệt hoàn toàn khỏi quá trình xây dựng và lựa chọn mô hình" (tr. 56–57). Hiển thị "cách hiểu của web" | Đạt |
| Bảng 4.5: Before/After = trung bình 30 lần; 18 phép so sánh; "RMSE is the objective function" | Bảng 4.5 | Thiếu ghi chú | Thêm ghi chú, tiêu đề cột theo bài | Đạt |
| Chọn mô hình: 9 ứng viên ANN/RF/XGB × 3, mỗi ứng viên đánh giá lặp lại 30 lần trên test, Mean RMSE thấp nhất, kèm ổn định và chi phí | tr. 57, 72–73: "các ứng viên mới được đánh giá lặp lại trên tập kiểm tra" | Ứng viên GA/SA = trung bình 30 cấu hình của 30 lần chạy (chính là cột After của Bảng 4.5) | Thêm bước 9b: cấu hình cuối của GA/SA × 30 seed trên tập kiểm tra; Baseline × 30 seed; ARIMA, RW không được chọn | Đạt |
| Refit trên toàn bộ tập phát triển, 30 seed, lưu tiền xử lý, đặc trưng, siêu tham số, phiên bản | tr. 57 ("toàn bộ tập phát triển"); **tr. 75 lại ghi "refit trên toàn bộ lịch sử"** – bài không thống nhất | Đạt (theo tr. 57, người dùng chọn) | Giữ; ghi chú mâu thuẫn ở đây | Đạt |

## 8. Đầu ra, cảnh báo, vòng phản hồi (mục 3.3.5, Bảng 4.6, Hình 3.3, mục 5.2.2)

| Yêu cầu | Bài | Trước | Sau | Đạt |
|---|---|---|---|---|
| Bảng 4.6 đúng 16 trường; Selection_Basis "Minimum Mean RMSE across 30 repeated Test runs" | Bảng 4.6 tr. 74 | Có thêm 2 trường, câu Basis có thêm chữ | Đúng 16 trường và câu của bài (`pipeline`, `evaluate.FIELDS_46`) | Đạt |
| Bỏ Expected_Direction | Bài: "chiều biến động dự kiến" (tr. 57) = tín hiệu tăng/giảm/ổn định (tr. 81) | Có | Bỏ khỏi Bảng 4.6; chiều biến động thể hiện qua Management_Alert | Đạt |
| Mức thay đổi tuyệt đối | tr. 57 "mức thay đổi tuyệt đối", tr. 81 "mức thay đổi dự kiến" – **đầu ra của bài**, nhưng không có trong Bảng 4.6 | Trường trong Bảng 4.6, nhãn "bổ sung ngoài bài" | Hiển thị ở khối "Đầu ra quản lý khác" với ghi chú "đầu ra theo mục 3.3.5, ngoài 16 trường của Bảng 4.6" (không gắn nhãn bổ sung vì bài có nêu) | Đạt |
| Cảnh báo Tăng / Giảm / Ổn định theo ngưỡng người dùng đặt | Hình 3.3 | Đạt | Giữ | Đạt |
| ±1,96 × RMSE, kiểm tra ngưỡng trên test | – | Có, có nhãn | Giữ nhãn "bổ sung ngoài bài" | Đạt |
| Vòng phản hồi 3 mức | tr. 57–58; tr. 85 | Đạt | Giữ; ranh giới các mức `[WEB]` | Đạt |

## 9. Giả thuyết (mục 3.1.2, 4.3, chương 5)

H1 so MAE, RMSE, MAPE từng mô hình với ARIMA; H2 đủ 18 phép so sánh, Chạy thử ghi "Chưa đủ căn cứ"; H3 ba tiêu chí
(tr. 28): chính xác, tự động hóa, hữu ích quản lý; ngưỡng "đạt" của tiêu chí chính xác: lựa chọn của web. Đạt từ lần sửa
trước, giữ nguyên; thêm nhãn "kết quả Chạy thử, không dùng để so với bài".

## 10. Nhãn, tên bảng

| Bảng / hình | Tên theo bài | Mục |
|---|---|---|
| Bảng 4.1 | Thống kê mô tả giá trị của chuỗi VND/USD | 4.1.1 |
| Bảng 4.2 | Kết quả kiểm định tính dừng | 4.1.2 |
| Bảng 4.3 | Mô hình ARIMA độ trễ tối ưu (chỉ tiêu theo dòng, 3 mô hình theo cột) | 4.2.1 |
| Hình 4.1 | Kết quả dự báo trên tập kiểm tra của mô hình ARIMA(p,d,q) – lấy cấu trúc thật | 4.2.2 |
| Hình 4.2 | Kết quả dự báo trên tập kiểm tra của các mô hình học máy và ARIMA – vẽ đúng như bài: thực tế, ARIMA, ANN, RF, XGBoost cấu hình định sẵn (trung bình các lần chạy) | 4.3 |
| Bảng 4.4 | Kết quả kiểm định trên tập kiểm tra của các mô hình nghiên cứu | 4.3 |
| Bảng 4.5 | Kết quả tối ưu hóa tham số các thuật toán học máy theo SA và GA | 4.4 |
| Bảng 4.6 | Kết quả chu trình tự động | 4.5 |

Bảng 4.1 có cột "Bài gốc" (`bai_goc.BANG_4_1`). Không còn nhãn mục ngoài 5 chương của bài.

## 11. Chạy đầy đủ không bị mất công (không đổi thuật toán)

| Yêu cầu | Sau |
|---|---|
| Lưu kết quả sau mỗi đơn vị việc | `pipeline._Store`, `_run_units`: mỗi seed Bảng 4.4, mỗi lần chạy GA/SA, mỗi seed Bảng 4.5 / đánh giá ứng viên, mỗi seed refit, kết quả ARIMA → `artifacts/nckh_<id>/checkpoint/*.joblib` (ghi tệp tạm rồi đổi tên). Dữ liệu hoặc cấu hình khác thì bỏ tiến độ cũ (`fingerprint.txt`). Phiên xong thì xóa thư mục tiến độ. Chỉ lưu mô hình refit của ứng viên được chọn. |
| Nút "Chạy tiếp" | `app.chay_tiep`, `hoc_may.chay_tiep`; hiện khi phiên lỗi / bị hủy / web khởi động lại. Kết quả giống hệt khi chạy một mạch (mọi bước tổng hợp sắp theo khóa; test (h)). |
| Song song nhiều tiến trình, seed cố định theo chỉ số lần chạy | `joblib` loky (đã có); seed = 1..30 theo lần chạy |
| Thanh tiến độ: bước, số phần xong / tổng, thời gian còn lại, nút hủy | Đã có; thêm "lấy từ lần chạy trước" khi chạy tiếp |
| Ước tính thời gian trước Chạy đầy đủ, yêu cầu xác nhận | Đã có (`pipeline.estimate`, trạng thái `cho_xac_nhan`); ước tính tính cả bước đánh giá ứng viên mới |

## Lựa chọn của web (bài không quy định)

Xem khung "Thiết lập bài không quy định, lựa chọn của web" trên web (`run_config.WEB_SETTINGS`): số fold K, ngân sách
đánh giá, tham số GA (N, số thế hệ, tournament k, xác suất lai ghép / đột biến, elitism, patience), tham số SA (số bước
hiệu chỉnh T0, xác suất chấp nhận ban đầu, tốc độ làm nguội, số nghiệm mỗi mức nhiệt, Tmin, patience), miền giá trị
siêu tham số và cấu hình baseline (`search_space`), trần epoch / số cây, early stopping XGBoost, ngưỡng dị thường,
ngưỡng cảnh báo mặc định, tham số vòng phản hồi, công thức Momentum, cách chọn cấu hình cuối GA/SA, cách đo chi phí
tính toán, quy tắc gắn nhãn H1–H3. Optimizer Adam cho ANN.

## Chỗ bài không thống nhất (web chọn một cách, có ghi chú)

- Refit mô hình chính: tr. 57 "toàn bộ tập phát triển" ↔ tr. 75 "toàn bộ lịch sử" → web theo tr. 57.
- Bảng 3.1 liệt kê "Hàm kích hoạt" là siêu tham số ↔ tr. 33 "Nghiên cứu này dùng hàm ReLU" → web cố định ReLU.
- ARIMA: tr. 46 "tìm kiếm theo thuật toán từng bước" ↔ tr. 61 "25 cấu trúc ARIMA" → web xét đủ 25 cấu trúc.
- Bảng 4.6 chọn XGBoost – Baseline (Mean RMSE 40,18) dù Bảng 4.5 có XGBoost – SA 36,41 → web áp dụng đúng quy tắc
  "Minimum Mean RMSE" cho mọi ứng viên.
- Mục 3.1.1 nêu "MAE, MRE và RMSE" ↔ phần còn lại dùng MAE, RMSE, MAPE → web dùng MAE, RMSE, MAPE.
