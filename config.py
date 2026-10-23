"""Cấu hình web. Cấu hình thuật toán nằm ở forecast_engine/run_config.py."""

# Kết nối SQL Server (đăng nhập bằng tài khoản Windows - "Integrated")
SQL_SERVER = r"localhost\SQLEXPRESS"
DATABASE = "DuBaoTyGia"
ODBC_DRIVER = "ODBC Driver 18 for SQL Server"   # hoặc "ODBC Driver 17 for SQL Server"

# Bảo vệ khi chia sẻ link công khai (không giới hạn dung lượng file tải lên)
PHIEN_CHAY_DONG_THOI = 1            # số phiên được ước tính/chờ/chạy cùng lúc; phiên tiếp theo báo "Hệ thống đang bận"
CHAY_THU_MOI_IP_MOI_GIO = 5         # số phiên Chạy thử tối đa mỗi địa chỉ IP trong 1 giờ (Quản trị không bị giới hạn)
CHO_XAC_NHAN_TOI_DA_PHUT = 30       # phiên Chạy đầy đủ chờ xác nhận quá lâu thì không còn tính là "đang bận"
