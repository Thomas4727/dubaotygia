"""Đặt hoặc đổi mật khẩu Quản trị của web.

    python dat_mat_khau.py

Người dùng bình thường KHÔNG cần mật khẩu: vào là xem, tải file và chạy mô hình được.
Mật khẩu Quản trị dùng khi bấm biểu tượng ổ khóa để xóa phiên, Chạy đầy đủ, hủy phiên.
"""
from getpass import getpass

import bao_mat


def main():
    print("Đặt mật khẩu Quản trị (dùng khi bấm biểu tượng ổ khóa trên web).")
    while True:
        mk = getpass(f"Mật khẩu Quản trị (ít nhất {bao_mat.MK_TOI_THIEU} ký tự, không hiện khi gõ): ")
        if mk != getpass("Nhập lại mật khẩu: "):
            print("  Hai lần nhập không khớp, nhập lại.")
            continue
        try:
            bao_mat.dat_mat_khau(mk)
            print("  Đã lưu mật khẩu Quản trị.")
            return
        except ValueError as e:
            print(f"  {e}")


if __name__ == "__main__":
    main()
