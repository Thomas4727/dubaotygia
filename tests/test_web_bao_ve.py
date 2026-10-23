"""Nhóm A – bảo vệ khi chia sẻ link công khai: 1 phiên cùng lúc, giới hạn Chạy thử theo IP, kiểm tra cột,
không giới hạn dung lượng, chế độ chỉ xem PUBLIC_READONLY, quyền hủy/xóa. Không ghi vào SQL Server (db được thay bằng bản giả)."""
import io

import pandas as pd
import pytest

import app as web
import bao_mat
import config
import db
from forecast_engine import data_io

CSV_MAU = "Ngay,TyGia\n" + "\n".join(f"{d:%d/%m/%Y},{25000 + i}" for i, d in
                                       enumerate(pd.bdate_range("2023-01-02", periods=400)))


@pytest.fixture
def goi(monkeypatch):
    """Client Flask + db giả. Trả về (client, nhật ký các lần tạo phiên)."""
    monkeypatch.delenv("PUBLIC_READONLY", raising=False)
    tao = []
    trang_thai = {"dang_ban": 0, "theo_ip": 0}
    monkeypatch.setattr(db, "dem_phien_dang_hoat_dong", lambda *a, **k: trang_thai["dang_ban"])
    monkeypatch.setattr(db, "dem_phien_chay_thu_theo_ip", lambda ip, *a: trang_thai["theo_ip"])
    monkeypatch.setattr(db, "luu_lan_tai_len", lambda ten, df: 99)
    monkeypatch.setattr(db, "lay_lan_tai_len", lambda lan_id: {"Id": lan_id, "TenFile": "x.csv"})
    monkeypatch.setattr(db, "tao_phien_nckh", lambda lan_id, cfg, ip=None: tao.append((lan_id, cfg["mode"], ip)) or 500)
    monkeypatch.setattr(db, "lay_trang_thai_nckh", lambda pid: {"Id": pid, "CheDo": "chay_thu", "TrangThai": "dang_chay"})
    monkeypatch.setattr(db, "cap_nhat_nckh", lambda *a, **k: tao.append(("cap_nhat", a, k)))
    monkeypatch.setattr(db, "xoa_phien_nckh", lambda pid: tao.append(("xoa", pid)))
    monkeypatch.setattr(web.hoc_may, "bat_dau", lambda pid: None)
    web.app.config["TESTING"] = True
    c = web.app.test_client()
    with c.session_transaction() as s:
        s["csrf"] = "tok"
    c.trang_thai = trang_thai
    return c, tao


def _tai_len(c, noi_dung=CSV_MAU, ten="tygia.csv", che_do="chay_thu", **headers):
    return c.post("/tai-len", data={"csrf_token": "tok", "che_do": che_do, "thuat_toan": "XGB", "bien_the": "SA",
                                    "tep": (io.BytesIO(noi_dung.encode()), ten)},
                  content_type="multipart/form-data", headers=headers)


def _thong_bao(c):
    with c.session_transaction() as s:
        return " | ".join(m for _, m in s.get("_flashes", []))


def test_tai_len_binh_thuong_tao_phien_kem_ip(goi):
    c, tao = goi
    r = _tai_len(c)
    assert r.status_code == 302 and "/nckh/500" in r.headers["Location"]
    assert tao == [(99, "chay_thu", "127.0.0.1")]


def test_chi_mot_phien_cung_luc(goi):
    c, tao = goi
    c.trang_thai["dang_ban"] = 1
    _tai_len(c)
    assert "Hệ thống đang bận, thử lại sau." in _thong_bao(c) and not tao


def test_gioi_han_chay_thu_moi_ip_moi_gio(goi):
    c, tao = goi
    c.trang_thai["theo_ip"] = config.CHAY_THU_MOI_IP_MOI_GIO
    _tai_len(c)
    assert "Mỗi địa chỉ IP chỉ được Chạy thử tối đa" in _thong_bao(c) and not tao


def test_quan_tri_khong_bi_gioi_han_ip_nhung_van_ton_trong_1_phien(goi):
    c, tao = goi
    with c.session_transaction() as s:
        s["vai_tro"] = "quan_tri"
    c.trang_thai["theo_ip"] = 100
    _tai_len(c)
    assert len(tao) == 1
    c.trang_thai["dang_ban"] = 1
    _tai_len(c)
    assert "Hệ thống đang bận" in _thong_bao(c) and len(tao) == 1


@pytest.mark.parametrize("noi_dung,loi", [
    ("A,B\n01/01/2024,25000\n02/01/2024,25010\n", "Không tìm thấy cột Ngày và cột Tỷ giá"),
    ("Ngay,Ghi chu\n01/01/2024,abc\n02/01/2024,xyz\n", "Không tìm thấy cột Tỷ giá"),
    ("01/01/2024,25000\n02/01/2024,25010\n03/01/2024,25020\n", "Không tìm thấy cột Ngày"),
    ("Ngay,TyGia\nabc,25000\nxyz,25010\nqwe,25020\n", "không đúng định dạng ngày"),
    ("Ngay,TyGia\n01/01/2024,abc\n02/01/2024,xyz\n03/01/2024,25020\n", "không phải số tỷ giá"),
])
def test_kiem_tra_dinh_dang_va_cot(goi, noi_dung, loi):
    c, tao = goi
    _tai_len(c, noi_dung)
    assert loi in _thong_bao(c) and not tao


def test_chap_nhan_dinh_dang_yahoo_va_investing():
    for tieu_de, mau in (("Date,Open,High,Low,Close,Adj Close,Volume", "2024-01-0{i},1,2,3,{v},4,5"),
                         ("Date,Price,Open,High,Low", "2024-01-0{i},{v},1,2,3")):
        dong = [tieu_de] + [mau.format(i=i, v=25000 + i) for i in range(1, 8)]
        df, info = data_io.parse_table(data_io.read_table("\n".join(dong).encode(), "f.csv"))
        assert info["date_column"] == "Date" and info["rate_column"] in ("Close", "Price")
        assert df["rate"].iloc[0] == 25001


def test_khong_gioi_han_dung_luong_file(goi):
    c, tao = goi
    assert web.app.config.get("MAX_CONTENT_LENGTH") is None
    dong = CSV_MAU.splitlines()                                      # thêm cột ghi chú dài: file > 6 MB, vẫn hợp lệ
    lon = "\n".join([dong[0] + ",GhiChu"] + [d + "," + "x" * 16_000 for d in dong[1:]])
    assert len(lon.encode()) > 6 * 1024 * 1024
    r = _tai_len(c, lon)
    assert r.status_code == 302 and "/nckh/500" in r.headers["Location"], _thong_bao(c)
    assert tao == [(99, "chay_thu", "127.0.0.1")]


def test_che_do_chi_xem(goi, monkeypatch):
    c, tao = goi
    monkeypatch.setenv("PUBLIC_READONLY", "1")
    _tai_len(c)
    assert "chế độ chỉ xem" in _thong_bao(c) and not tao
    c.post("/du-lieu/5/chay", data={"csrf_token": "tok", "che_do": "chay_thu", "thuat_toan": "XGB", "bien_the": "SA"})
    assert not tao
    with c.session_transaction() as s:
        s["phien_cua_toi"] = [7]
    c.post("/nckh/7/huy", data={"csrf_token": "tok"})                # kể cả phiên của chính mình
    assert not tao
    # Quản trị vẫn làm được
    with c.session_transaction() as s:
        s["vai_tro"] = "quan_tri"
    _tai_len(c)
    assert len(tao) == 1


def test_khach_khong_huy_khong_xoa_phien_cua_nguoi_khac(goi):
    c, tao = goi
    r = c.post("/nckh/7/huy", data={"csrf_token": "tok"})
    assert r.status_code == 302 and "cần chế độ Quản trị" in _thong_bao(c)
    c.post("/nckh/7/xoa", data={"csrf_token": "tok"})
    c.post("/phien/7/xoa", data={"csrf_token": "tok"})
    assert not tao
    with c.session_transaction() as s:
        s["phien_cua_toi"] = [7]
    c.post("/nckh/7/huy", data={"csrf_token": "tok"})                # phiên Chạy thử của chính mình: được
    assert tao and tao[0][0] == "cap_nhat"


def test_post_thieu_csrf_bi_chan(goi):
    c, tao = goi
    c.post("/tai-len", data={"che_do": "chay_thu"})
    assert "hết hạn" in _thong_bao(c) and not tao


def test_dia_chi_ip_chi_tin_header_cloudflare_tu_may_nay():
    class Req:
        def __init__(self, remote, h):
            self.remote_addr, self.headers = remote, h
    assert bao_mat.dia_chi(Req("127.0.0.1", {"Cf-Connecting-Ip": "1.2.3.4"})) == "1.2.3.4"
    assert bao_mat.dia_chi(Req("192.168.1.20", {"Cf-Connecting-Ip": "1.2.3.4"})) == "192.168.1.20"


def test_mo_khoa_khong_chuyen_huong_ra_web_khac(goi, monkeypatch):
    c, _ = goi
    monkeypatch.setattr(bao_mat, "da_dat_mat_khau", lambda: True)
    monkeypatch.setattr(bao_mat, "la_mat_khau_quan_tri", lambda mk: True)
    for tiep in ("//evil.com", "/\\evil.com", "https://evil.com"):
        with c.session_transaction() as s:
            s.clear()
            s["csrf"] = "tok"
        r = c.post(f"/quan-tri?tiep={tiep}", data={"csrf_token": "tok", "mat_khau": "x"})
        assert r.headers["Location"] == "/", tiep


def test_chay_day_du_khong_khoa(goi, monkeypatch):
    """Người dùng (không mật khẩu) chọn được Chạy đầy đủ, tự xác nhận và hủy phiên của mình; không đụng được phiên người khác."""
    c, tao = goi
    _tai_len(c, che_do="chay_day_du")
    assert tao == [(99, "chay_day_du", "127.0.0.1")] and "Quản trị" not in _thong_bao(c)
    xep = []
    monkeypatch.setattr(web.hoc_may, "xep_hang", lambda pid: xep.append(pid))
    monkeypatch.setattr(db, "lay_trang_thai_nckh",
                        lambda pid: {"Id": pid, "CheDo": "chay_day_du", "TrangThai": "cho_xac_nhan"})
    monkeypatch.setattr(db, "ket_thuc_nckh", lambda *a, **k: tao.append(("ket_thuc", a)))
    c.post("/nckh/500/xac-nhan", data={"csrf_token": "tok"})             # phiên 500 do chính trình duyệt này tạo
    assert xep == [500]
    c.post("/nckh/7/xac-nhan", data={"csrf_token": "tok"})               # phiên của người khác
    assert xep == [500] and "cần chế độ Quản trị" in _thong_bao(c)
    c.post("/nckh/500/huy", data={"csrf_token": "tok"})
    assert ("ket_thuc", (500, "huy")) in tao
    monkeypatch.setattr(db, "lay_lich_su_tat_ca", lambda: [])
    html = c.get("/").get_data(as_text=True)
    assert 'value="chay_day_du">' in html and 'value="chay_day_du" disabled' not in html
