"""Bảo mật khi chia sẻ web: mật khẩu Quản trị, khóa bí mật, chống CSRF, chặn đoán mật khẩu.

Vai trò:
  - khach (Người dùng): KHÔNG cần mật khẩu – xem kết quả, tải file lên, Chạy thử hoặc Chạy đầy đủ, xác nhận / hủy / chạy tiếp phiên do chính mình tạo.
  - quan_tri (Quản trị): bấm biểu tượng ổ khóa, nhập mật khẩu – thêm quyền xóa phiên, hủy hay xác nhận phiên của người khác.
Mật khẩu Quản trị chỉ lưu dạng băm trong tai_khoan.json (đặt bằng: python dat_mat_khau.py).
"""
import hmac
import json
import secrets
import time
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

THU_MUC = Path(__file__).parent
FILE_TAI_KHOAN = THU_MUC / "tai_khoan.json"
FILE_KHOA = THU_MUC / ".khoa_bi_mat"
VAI_TRO = {"quan_tri": "Quản trị", "khach": "Người dùng"}
MK_TOI_THIEU = 8
SAI_TOI_DA, KHOA_GIAY = 5, 300          # sai 5 lần -> khóa đăng nhập 5 phút theo địa chỉ


def khoa_bi_mat():
    """Khóa ký cookie phiên: tạo ngẫu nhiên một lần, lưu vào file (không để chuỗi cố định trong code)."""
    if not FILE_KHOA.exists():
        FILE_KHOA.write_text(secrets.token_hex(32), encoding="utf-8")
    return FILE_KHOA.read_text(encoding="utf-8").strip()


def _doc():
    try:
        return json.loads(FILE_TAI_KHOAN.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def da_dat_mat_khau():
    return "quan_tri" in _doc()


def dat_mat_khau(mat_khau):
    """Đặt / đổi mật khẩu Quản trị (người dùng thường không cần mật khẩu)."""
    if len(mat_khau) < MK_TOI_THIEU:
        raise ValueError(f"Mật khẩu phải có ít nhất {MK_TOI_THIEU} ký tự.")
    FILE_TAI_KHOAN.write_text(json.dumps({"quan_tri": generate_password_hash(mat_khau)}, indent=1), encoding="utf-8")


def la_mat_khau_quan_tri(mat_khau):
    h = _doc().get("quan_tri")
    return bool(h) and check_password_hash(h, mat_khau)


# ---------------------------------------------------------------- Chặn đoán mật khẩu
_sai = {}          # địa chỉ -> (số lần sai, thời điểm mở khóa)


def dia_chi(request):
    """Địa chỉ IP của người dùng. Qua Cloudflare Tunnel mọi yêu cầu đến từ 127.0.0.1 và địa chỉ thật nằm trong header
    Cf-Connecting-Ip. Chỉ tin header này khi yêu cầu đến từ chính máy này (đường hầm); người trong mạng Wi-Fi gửi
    header giả sẽ không đổi được địa chỉ của mình."""
    goc = request.remote_addr or "?"
    if goc in ("127.0.0.1", "::1"):
        return request.headers.get("Cf-Connecting-Ip") or goc
    return goc


def dang_bi_khoa(dc):
    so_lan, mo_khoa = _sai.get(dc, (0, 0))
    return mo_khoa > time.time()


def ghi_sai(dc):
    so_lan, _ = _sai.get(dc, (0, 0))
    so_lan += 1
    _sai[dc] = (0, time.time() + KHOA_GIAY) if so_lan >= SAI_TOI_DA else (so_lan, 0)


def xoa_sai(dc):
    _sai.pop(dc, None)


# ---------------------------------------------------------------- CSRF
def csrf_token(session):
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def csrf_hop_le(session, gia_tri):
    return bool(gia_tri) and "csrf" in session and hmac.compare_digest(session["csrf"], gia_tri)
