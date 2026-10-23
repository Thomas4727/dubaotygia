"""Nhóm D – nhãn "Dữ liệu mô phỏng" và bộ lọc "Ẩn phiên dữ liệu mẫu" trên trang chủ (db giả, không đụng SQL Server)."""
from datetime import date, datetime

import app as web
import db


def _phien(pid, ten_file):
    return {"Loai": "nckh", "Id": pid, "LanTaiLenId": pid, "CheDo": "chay_thu", "ThuatToan": "ARIMA,XGB",
            "BienThe": "SA", "TrangThai": "xong", "PhanTram": 100, "ThoiGianTao": datetime(2026, 10, pid),
            "MoHinhChon": "XGB", "BienTheChon": "SA", "NgayDuBao": date(2026, 9, 24), "DuBaoT1": 26000.5,
            "DuBaoP05": 25990, "DuBaoP95": 26010, "ThayDoiPct": 0.01, "CanhBao": "Ổn định", "TenFile": ten_file,
            "SoDong": 783, "NgayBatDau": date(2023, 1, 2), "NgayKetThuc": date(2026, 9, 23), "RmseChon": 10.0}


def test_nhan_du_lieu_mo_phong_va_bo_loc(monkeypatch):
    monkeypatch.setattr(db, "lay_lich_su_tat_ca", lambda: [_phien(2, "tygia_mau.csv"), _phien(1, "tygia_USDVND_5nam.csv")])
    html = web.app.test_client().get("/").get_data(as_text=True)
    assert html.count("<tr data-du-lieu-mau>") == 1                   # chỉ dòng dùng file mẫu
    assert html.count(">Dữ liệu mô phỏng</span>") == 2                # cột File + thẻ "Dự báo gần nhất" (phiên #2)
    assert 'id="an-du-lieu-mau" checked' in html                       # bộ lọc mặc định bật
    assert "tối đa 5 MB" not in html
    # Khoảng theo sai số lịch sử trên thẻ "Dự báo gần nhất": 26.000,5 ± 1,96 × 10
    assert "25.980,9 – 26.020,1" in html and "Dao động giữa các lần huấn luyện" in html


def test_la_du_lieu_mau():
    assert web.la_du_lieu_mau("tygia_mau.csv") and web.la_du_lieu_mau(" TYGIA_MAU.CSV ")
    assert not web.la_du_lieu_mau("tygia_USDVND_5nam.csv") and not web.la_du_lieu_mau(None)
