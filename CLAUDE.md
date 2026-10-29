# Ghi chú cho Claude

- Người dùng là sinh viên mới học: trả lời bằng tiếng Việt, giải thích đơn giản.
- Bản web chính là bản HTML chạy trên trình duyệt (`offline/src/` -> `python offline/build.py` -> `du_bao_ty_gia.html`).
- Link chính thức (artifact): https://claude.ai/artifact/9uTzg9zKAm8HkhriojK68E, tên `dubaotygia`. Sau mỗi lần sửa
  `offline/src/`: chạy `python offline/build.py` và `python offline/build.py --link`, rồi đăng `offline/ban_link.html`
  lên ĐÚNG link này (Artifact publish với `url` là link trên). Không tạo link mới.
- GitHub Pages: https://thomas4727.github.io/dubaotygia/ lấy từ `docs/index.html` (build.py tự chép). Đẩy code là Pages tự cập nhật.
- Không sửa trực tiếp `du_bao_ty_gia.html`; test `tests/test_html_offline.py` kiểm tra file khớp mã nguồn.
