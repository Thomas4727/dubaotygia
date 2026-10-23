# Web Dự báo tỷ giá VND/USD T+1 – tái lập quy trình bài NCKH

Theo file đặc tả `DAC_TA_THUAT_TOAN_TY_GIA_T1_v3.md`. Người dùng tải file tỷ giá lên, dữ liệu được lưu vào
**SQL Server**, rồi quy trình 12 công đoạn của bài chạy nền. Kết quả gồm Bảng 4.1–4.6, Hình 4.1–4.2,
kết luận H1–H3 và phần "So sánh với thực tế" cho từng thuật toán.

Chỉ dùng các thuật toán trong bài: **ARIMA, ANN (MLP, PyTorch), Random Forest, XGBoost**; tối ưu siêu tham số
bằng **GA** và **SA**; **Random walk** chỉ để đối chiếu.

## Cách chạy

- **Lần đầu:** bấm đúp `cai_dat.bat`. File này cài thư viện (có PyTorch bản CPU) và tạo các bảng trong SQL Server.
- **Mỗi lần dùng:** bấm đúp `chay_web.bat`, rồi mở http://localhost:5000.
  1. Chọn file (hoặc tải file mẫu ở mục "Định dạng file được hỗ trợ").
  2. Chọn **Chế độ chạy**, **Thuật toán**, **Cách cấu hình siêu tham số** và (tùy chọn) ngưỡng cảnh báo.
  3. Bấm **Tải lên & Dự báo**. Web đo thời gian ước tính trước khi chạy. Với **Chạy đầy đủ**, bạn phải bấm
     **Xác nhận** thêm một lần.
  4. Trang phiên hiển thị tiến trình 12 công đoạn (có nút **Hủy**). Chạy xong thì trang tự hiện kết quả.
- **Dòng lệnh** (không cần web):

  ```bash
  .venv\Scripts\python.exe -m forecast_engine.cli --data data/tygia_mau.csv --mode chay_thu
  ```

- **Test:**

  ```bash
  .venv\Scripts\python.exe -m pytest tests
  ```

## Chia sẻ cho người khác dùng

1. Cài `cloudflared` (một lần, để có link công khai): `winget install --id Cloudflare.cloudflared`.
2. Bấm đúp **`chia_se_web.bat`**. Lần đầu, web hỏi đặt **mật khẩu Quản trị** (chỉ của bạn).
   - **Người dùng** vào web **không cần mật khẩu**: xem kết quả, tải file, chạy mô hình (Chạy thử hoặc Chạy đầy đủ), xác nhận / hủy / chạy tiếp phiên của chính mình.
   - **Quản trị**: bấm **biểu tượng ổ khóa** ở góc trên, nhập mật khẩu để xóa phiên, xác nhận hoặc hủy phiên bất kỳ;
     bấm ổ khóa lần nữa để khóa lại.
3. Windows hỏi quyền mạng thì chọn cho phép **Private / Riêng tư**.
4. Cửa sổ hiện 2 địa chỉ:
   - `http://192.168.x.x:5000` cho người cùng Wi-Fi.
   - `https://....trycloudflare.com` cho người ở bất kỳ đâu. Link này đổi mỗi lần chạy lại và được lưu vào `link_chia_se.txt`.
5. Đóng cửa sổ là ngừng chia sẻ. Máy phải bật trong suốt thời gian chia sẻ.

Tùy chọn: `chia_se_web.bat --chi-noi-bo` (chỉ Wi-Fi), `--chi-link` (chỉ link công khai), `--chi-may-nay` (không chia sẻ).
Thêm `--chi-xem` (hoặc đặt biến môi trường `PUBLIC_READONLY=1`): người dùng chỉ xem lịch sử và trang kết quả,
không tải lên, không chạy, không hủy; Quản trị (mở ổ khóa) vẫn làm được mọi thao tác.
Đổi mật khẩu Quản trị: `.venv\Scripts\python.exe dat_mat_khau.py`.

Bảo mật khi chia sẻ (các con số đặt trong `config.py`):
- Máy chủ `waitress`, chế độ debug tắt. Người dùng qua trình duyệt không thể sửa code hay file trên máy.
- Chống giả mạo form (CSRF); sai mật khẩu Quản trị 5 lần thì khóa 5 phút.
- Mọi người chọn được Chạy thử và Chạy đầy đủ; người tạo phiên tự xác nhận, hủy, chạy tiếp phiên của mình. Chỉ Quản trị được xóa phiên và hủy phiên của người khác.
- Chỉ **1 phiên** được ước tính/chờ/chạy cùng lúc; phiên thứ hai báo "Hệ thống đang bận, thử lại sau"
  (`PHIEN_CHAY_DONG_THOI`). Phiên Chạy đầy đủ chờ xác nhận quá 30 phút thì không còn tính là đang bận.
- Mỗi địa chỉ IP tối đa **5 phiên Chạy thử trong 1 giờ** (`CHAY_THU_MOI_IP_MOI_GIO`, Quản trị không bị giới hạn).
- File tải lên phải có dòng tiêu đề với cột Ngày và cột Tỷ giá đúng định dạng. Không giới hạn dung lượng file.

## Đọc kết quả

Đối chiếu từng yêu cầu với bài gốc và các lựa chọn của web: [docs/doi-chieu-bai-goc.md](docs/doi-chieu-bai-goc.md).

- **Mô hình chính** chỉ chọn trong ANN, Random Forest, XGBoost × Baseline/GA/SA (Mean RMSE thấp nhất); ARIMA và
  random walk là chuẩn đối chiếu (mục 3.3.5). Mô hình chính được huấn luyện lại trên toàn bộ tập phát triển rồi dự báo T+1.
  Mục "Chọn mô hình chính" ghi kèm độ ổn định (SD, CV RMSE), chi phí tính toán và kiểm tra GA/SA cùng điều kiện.
- **Cảnh báo** theo Hình 3.3: Tăng / Giảm / Ổn định với một ngưỡng % do người dùng đặt (mặc định 0,10%).
- **ANN** chỉ dùng p giá trị trễ của Δy (công thức 3.9, Bảng 3.1); RF và XGBoost dùng đủ đặc trưng với p và w.
- Mỗi ứng viên (cấu hình cuối của GA/SA, hoặc Baseline) được **đánh giá lặp lại 30 lần** trên tập kiểm tra rồi mới chọn.
- **Chạy tiếp:** mọi phần việc (mỗi seed, mỗi lần chạy GA/SA) được lưu vào `artifacts/nckh_<id>/checkpoint` ngay khi xong.
  Máy tắt hoặc web khởi động lại thì mở phiên và bấm **Chạy tiếp**: phần đã xong được dùng lại, kết quả giống hệt khi chạy
  một mạch. Phiên xong thì thư mục này tự xóa.
- Khung **"Thiết lập bài không quy định, lựa chọn của web"** (trên form chạy và trang kết quả) liệt kê mọi thông số bài không
  cho giá trị cùng giá trị ở hai chế độ.
- Phiên chạy trước khi sửa mà ARIMA được chọn có ghi chú "quy tắc cũ"; dữ liệu cũ giữ nguyên.

- **Bảng 4.1** có thêm số ngày tỷ giá không đổi so với hôm trước và tỷ lệ %. Dữ liệu Yahoo Finance (VND=X) là tỷ giá
  thị trường, không phải tỷ giá niêm yết Vietcombank, và có các chuỗi ngày đi ngang làm RMSE nhỏ hơn thực tế.
- **Bảng 4.6**: P05–P95 là *dao động giữa các lần chạy thuật toán*. Khoảng **dự báo ± 1,96 × RMSE** (bổ sung ngoài bài)
  của mô hình được chọn mới phản ánh mức lệch thường gặp. Thêm mức thay đổi tuyệt đối và chiều biến động dự kiến.
- **H2 ở Chạy thử** hiện "Chưa đủ căn cứ (Chạy thử)" vì Bảng 4.5 chỉ có 1 lần chạy GA/SA × 3 seed mỗi ô.
- **Kiểm tra ngưỡng cảnh báo trên tập test** (bổ sung ngoài bài): phân phối |% thay đổi thực tế T+1| và tỷ lệ ngày
  Tăng / Giảm / Ổn định. Chỉ để báo cáo, web không tự đổi ngưỡng.
- **Tạo lịch sử dự báo giả lập (backtest)**: dự báo T+1 walk-forward cho 30 ngày cuối bằng mô hình được chọn (huấn luyện
  lại mỗi ngày với siêu tham số hiện hành), lưu vào `NCKH_Backtest` với `IsBacktest = 1`, hiện trong bảng "Dự báo trước
  đây và thực tế" với nhãn **Backtest**. Vòng phản hồi chỉ tính backtest khi bật tùy chọn ngay dưới bảng.
- Phiên dùng `tygia_mau.csv` có nhãn **Dữ liệu mô phỏng**; bảng lịch sử mặc định ẩn các phiên này (bỏ chọn
  "Ẩn phiên dữ liệu mẫu" để xem).

## Hai chế độ (`forecast_engine/run_config.py`)

| Tham số | Chạy thử | Chạy đầy đủ (đúng bài) |
|---|---|---|
| Seed baseline (Bảng 4.4) | 3 | 30 |
| Số lần chạy GA/SA mỗi mô hình | 1 | 30 |
| Ngân sách đánh giá mỗi lần GA/SA | 30 | 300 |
| GA quần thể / thế hệ tối đa | 6 / 5 | 20 / 15 |
| SA nghiệm hiệu chỉnh T0 / nghiệm mỗi mức nhiệt | 5 / 5 | 20 / 10 |
| Fold CV | 3 | 5 |
| Bảng 4.5: số giá trị mỗi ô | 3 (1 lần chạy × 3 seed) | 30 (30 lần chạy × 1 seed) |
| Seed refit T+1 (Bảng 4.6) | 3 | 30 |
| Trần epochs ANN / cây RF / cây XGB | 150 / 300 / 500 | 500 / 800 / 1500 |

Trên máy này (16 luồng), dữ liệu mẫu 783 dòng: **Chạy thử mất khoảng 1,5 phút**, **Chạy đầy đủ ước tính khoảng 9 giờ**.

## Cấu trúc

| Thành phần | Vai trò |
|---|---|
| `forecast_engine/run_config.py` | Mọi tham số của hai chế độ và các giá trị `[CHỐT]` |
| `data_io.py` | Đọc CSV/XLSX, làm sạch 6 bước |
| `stats_tests.py` | Bảng 4.1, ADF + Phillips–Perron (Bảng 4.2) |
| `features.py` | Đặc trưng: trễ của sai phân, lợi suất, thống kê trượt (p, w) |
| `splits.py` | 3 tầng: train/validation/test, CV cửa sổ mở rộng |
| `models.py` | ARIMA (25 cấu trúc, `append(refit=False)`), ANN PyTorch, RF, XGBoost – một hàm `fit_predict` |
| `search_space.py`, `ga.py`, `sa.py`, `budget.py` | Không gian tìm kiếm, GA, SA, ngân sách + cache |
| `evaluate.py` | Chỉ tiêu, Bảng 4.5, quy tắc chọn, cảnh báo, kết luận H1–H3 |
| `pipeline.py` | `run_pipeline(df, run_config, on_progress)` – 12 công đoạn; `estimate()` – ước tính thời gian |
| `progress.py` | Trạng thái 12 công đoạn, % tổng, thời gian còn lại, Hủy |
| `feedback.py` | Vòng phản hồi (sai số cuốn chiếu 20 phiên, fit lại với siêu tham số hiện hành) |
| `app.py`, `hoc_may.py`, `db.py` | Web Flask, chạy nền, SQL Server |
| `static/bieu_do.js` | Component biểu đồ so sánh (giữ nguyên kiểu vẽ của web), dùng cho Hình 4.1, 4.2 và các tab |
| `bai_goc.py` | Số liệu bài gốc – chỉ hiển thị ở cột "Bài gốc (tham chiếu)" |

## Database

Bảng mới (không sửa hay xóa bảng cũ): `PhienNCKH` (mỗi lần chạy: chế độ, phạm vi, tiến trình, Bảng 4.6, JSON đầy đủ),
`NCKH_UngVien` (chỉ tiêu và dự báo T+1 của từng ứng viên), `NCKH_DuBaoTest` (dự báo từng ngày trên tập test),
`NCKH_Backtest` (dự báo giả lập, `IsBacktest = 1`). Cột mới của `PhienNCKH`: `DiaChiIP`, `BacktestTrangThai`.
Sau khi cập nhật code, chạy lại `cai_dat.bat` (hoặc `python khoi_tao_db.py`) để thêm các cột/bảng này.
Các phiên cũ (`PhienHocMay`) vẫn xem được, có nhãn "Bản cũ".

## Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| "Không kết nối được SQL Server" | Bật dịch vụ **SQL Server (SQLEXPRESS)** (Windows → Services), chạy lại `cai_dat.bat`. |
| Lỗi driver ODBC | Trong `config.py`, đổi `ODBC_DRIVER` thành `"ODBC Driver 17 for SQL Server"`. |
| Biểu đồ không hiện | Chart.js và font tải từ internet, nên máy cần có mạng. |
| Phiên báo "Web đã khởi động lại" | Cửa sổ web bị tắt khi phiên đang chạy. Chạy lại phiên. |
