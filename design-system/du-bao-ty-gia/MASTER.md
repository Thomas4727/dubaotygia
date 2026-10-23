# Design System: Dự báo tỷ giá USD/VND (MASTER)

Nguồn: skill **UI UX Pro Max** (nextlevelbuilder/ui-ux-pro-max-skill). Dữ liệu tra từ các file
`ui-reasoning.csv`, `colors.csv`, `typography.csv`, `styles.csv`, `charts.csv`, `ux-guidelines.csv`
và `references/pro-rules.md`. File này là chuẩn chung cho mọi trang; trang nào cần khác thì ghi đè trong `pages/<trang>.md`.

## 1. Phân tích sản phẩm
| Mục | Giá trị |
|---|---|
| Loại sản phẩm | Financial Dashboard + Analytics Dashboard (công cụ dự báo tỷ giá, học máy) |
| Người dùng | Sinh viên / giảng viên / người làm quản trị rủi ro tỷ giá, đọc số liệu kỹ |
| Stack | Flask + Jinja2 + CSS thuần + Chart.js (không có framework front-end) |
| Mẫu bố cục | **Data-Dense Dashboard** (ui-reasoning #6, #7) |
| Style | **Dark Mode (OLED)** + Data-Dense Dashboard, thêm tinh thần Minimalism/Swiss |
| Anti-pattern cần tránh | Light mode mặc định · render chậm · trang trí rườm rà · gradient tím/hồng kiểu "AI" · emoji làm icon |

## 2. Màu (token ngữ nghĩa, không dùng hex rời trong code)
Tối (mặc định), theo colors.csv #6 "Financial Dashboard" + trust blue:

| Token | Tối | Sáng (colors.csv #7) | Dùng cho |
|---|---|---|---|
| `--bg` | #020617 | #F8FAFC | Nền trang |
| `--surface` | #0E1223 | #FFFFFF | Thẻ |
| `--surface-2` | #1A1E2F | #EEF2F7 | Nền phụ, hàng hover, ô nhập |
| `--border` | #334155 | #D6DEE9 | Viền, đường kẻ |
| `--text` | #F8FAFC | #0F172A | Chữ chính (≥ 15:1) |
| `--text-muted` | #94A3B8 | #475569 | Chữ phụ (≥ 4.5:1 trên `--surface`) |
| `--primary` | #3B82F6 | #1E40AF | Trust blue: nút chính, link, mô hình được chọn |
| `--positive` | #22C55E | #15803D | Tốt hơn / ổn định |
| `--negative` | #F87171 | #DC2626 | Kém hơn / biến động mạnh / lỗi |
| `--warning` | #FBBF24 | #B45309 | Theo dõi / cảnh báo |

Màu chuỗi biểu đồ: thực tế = `--text` (nét liền) · được chọn = `--primary` (nét liền đậm) · RandomWalk = xám ·
ARIMA = hổ phách · ANN = cyan · RF = xanh ngọc · XGBoost = hồng. Mọi chuỗi phụ dùng nét đứt: **không phân biệt chỉ bằng màu**.

## 3. Chữ
- **Be Vietnam Pro** 400/500/600/700 cho toàn bộ giao diện (typography.csv #21 "Vietnamese Friendly").
- **Fira Code** cho con số lớn (KPI), nhật ký, tham số (typography.csv #42 "Dashboard Data"); tắt ligature.
- Cỡ chữ: thân 15px, bảng 14px, nhãn phụ 13px, **không dưới 12px**; line-height 1.5; số trong bảng `tabular-nums`, căn phải.

## 4. Khoảng cách & bố cục
- Thang 4/8: 4 · 8 · 12 · 16 · 24 · 32 · 48 px.
- Khung tối đa 1280px, lề 16px trên điện thoại; lưới 12 cột, gap 16px.
- Bo góc: thẻ 12px, nút/ô nhập 8px, nhãn 999px.
- Không cuộn ngang toàn trang; bảng rộng cuộn trong khung riêng, tiêu đề bảng dính (sticky).

## 5. Tương tác & chuyển động
- Vùng bấm ≥ 44×44px; khoảng cách giữa các nút ≥ 8px.
- Phản hồi khi bấm 80–150ms; hover 150–200ms; một bộ token thời gian dùng chung.
- Focus bàn phím: viền 2px `--primary` + khoảng hở 2px, không bao giờ tắt.
- `prefers-reduced-motion`: tắt mọi chuyển động/trượt thanh tiến độ.
- Nút gửi bị khóa + hiện "đang xử lý" khi đang tải lên (chống bấm 2 lần).
- Xóa phải xác nhận.

## 6. Icon
- SVG nét (bộ Lucide, stroke 2px, 24×24 viewBox) đặt trong sprite `templates/_icons.html`. Không emoji.
- Icon trang trí `aria-hidden="true"`; nút chỉ có icon phải có `aria-label`.

## 7. Biểu đồ (charts.csv)
| Dữ liệu | Loại | Quy tắc |
|---|---|---|
| Thực tế & dự báo T+1 | Line + dải tin cậy | Thực tế nét liền, dự báo nét đứt, dải 95% tô mờ ~15% cùng màu, có nhãn tên dải |
| So sánh 11 ứng viên | Thanh ngang, sắp xếp | Sắp theo RMSE, có giá trị trong tooltip + bảng, mô hình được chọn tô `--primary` |
| Hội tụ GA/SA | Line bậc thang | GA nét liền, SA nét đứt |
Luôn có chú thích (legend), tooltip, và màu lấy từ token theo giao diện sáng/tối.

## 8. Checklist trước khi giao (pro-rules.md)
- [ ] Không emoji; icon cùng một bộ, cùng độ dày nét
- [ ] Tương phản chữ ≥ 4.5:1 ở cả hai giao diện; viền phân biệt được ở cả hai
- [ ] Vùng bấm ≥ 44px; trạng thái disabled rõ ràng
- [ ] Focus thấy được; thứ tự tab theo thứ tự hiển thị
- [ ] Màu không phải tín hiệu duy nhất (luôn kèm icon/chữ/dấu +/−)
- [ ] Thử ở độ rộng 375px, không cuộn ngang trang
- [ ] Reduced-motion hoạt động
- [ ] Form có nhãn hiển thị; lỗi hiện rõ, gần chỗ sai
