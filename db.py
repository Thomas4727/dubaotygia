"""Mọi thao tác đọc/ghi SQL Server nằm trong file này."""
import pyodbc

import config


def ket_noi(database=None, autocommit=False):
    chuoi = (
        f"DRIVER={{{config.ODBC_DRIVER}}};"
        f"SERVER={config.SQL_SERVER};"
        f"DATABASE={database or config.DATABASE};"
        "Trusted_Connection=yes;"          # đăng nhập bằng tài khoản Windows
        "TrustServerCertificate=yes;"      # máy local không có chứng chỉ SSL chuẩn
    )
    return pyodbc.connect(chuoi, autocommit=autocommit)


def _thanh_dict(cur):
    cot = [c[0] for c in cur.description]
    return [dict(zip(cot, dong)) for dong in cur.fetchall()]


# ---------------------------------------------------------------- Ghi dữ liệu

def luu_lan_tai_len(ten_file, df):
    """Lưu dữ liệu tỷ giá của file tải lên (df: cột date, rate). Trả về Id lần tải lên."""
    with ket_noi() as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.execute(
            """INSERT INTO dbo.LanTaiLen (TenFile, SoDong, NgayBatDau, NgayKetThuc)
               OUTPUT INSERTED.Id VALUES (?, ?, ?, ?)""",
            ten_file, len(df), df["date"].iloc[0].date(), df["date"].iloc[-1].date(),
        )
        lan_id = cur.fetchone()[0]
        cur.executemany(
            "INSERT INTO dbo.TyGia (LanTaiLenId, Ngay, GiaTri) VALUES (?, ?, ?)",
            [(lan_id, n.date(), float(g)) for n, g in zip(df["date"], df["rate"])],
        )
        conn.commit()
    return lan_id


def xoa_phien(phien_id):
    """Xóa một phiên; nếu dữ liệu tải lên không còn phiên nào thì xóa luôn dữ liệu đó."""
    with ket_noi() as conn:
        dong = conn.execute("SELECT LanTaiLenId FROM dbo.PhienHocMay WHERE Id = ?", phien_id).fetchone()
        if dong is None:
            return
        conn.execute("DELETE FROM dbo.PhienHocMay WHERE Id = ?", phien_id)     # BangXepHang tự xóa theo (CASCADE)
        _xoa_lan_tai_len_mo_coi(conn, dong[0])
        conn.commit()


def _xoa_lan_tai_len_mo_coi(conn, lan_id):
    """Chỉ xóa dữ liệu tải lên khi không còn phiên nào (cũ hay mới) dùng nó."""
    conn.execute("""DELETE FROM dbo.LanTaiLen WHERE Id = ?
                    AND NOT EXISTS (SELECT 1 FROM dbo.PhienHocMay WHERE LanTaiLenId = ?)
                    AND NOT EXISTS (SELECT 1 FROM dbo.PhienNCKH WHERE LanTaiLenId = ?)""", lan_id, lan_id, lan_id)


# ---------------------------------------------------------------- Đọc dữ liệu

def lay_lich_su():
    """Mọi phiên dự báo, mới nhất trước, kèm thông tin file."""
    with ket_noi() as conn:
        return _thanh_dict(conn.execute(
            """SELECT p.Id, p.LanTaiLenId, p.CheDo, p.CheDoMucTieu, p.TrangThai, p.PhanTram, p.ThoiGianTao,
                      p.MoHinhChon, p.BienTheChon, p.NgayDuBao, p.DuBaoT1, p.CanhBao,
                      p.KhoangDuoi95, p.KhoangTren95, p.XuHuong,
                      l.TenFile, l.SoDong, l.NgayBatDau, l.NgayKetThuc
               FROM dbo.PhienHocMay p JOIN dbo.LanTaiLen l ON l.Id = p.LanTaiLenId
               ORDER BY p.Id DESC"""))


def lay_lan_tai_len(lan_id):
    with ket_noi() as conn:
        cur = conn.execute("SELECT * FROM dbo.LanTaiLen WHERE Id = ?", lan_id)
        ds = _thanh_dict(cur)
        return ds[0] if ds else None


def lay_ty_gia(lan_id):
    with ket_noi() as conn:
        cur = conn.execute("SELECT Ngay, GiaTri FROM dbo.TyGia WHERE LanTaiLenId = ? ORDER BY Ngay", lan_id)
        return _thanh_dict(cur)


def lay_ty_gia_dataframe(lan_id):
    import pandas as pd
    ds = lay_ty_gia(lan_id)
    return pd.DataFrame({"date": pd.to_datetime([d["Ngay"] for d in ds]),
                         "rate": [float(d["GiaTri"]) for d in ds]})


# ---------------------------------------------------------------- Phiên học máy (GA/SA)

def tao_phien(lan_id, che_do, muc_tieu):
    with ket_noi() as conn:
        cur = conn.execute(
            "INSERT INTO dbo.PhienHocMay (LanTaiLenId, CheDo, CheDoMucTieu) OUTPUT INSERTED.Id VALUES (?, ?, ?)",
            lan_id, che_do, muc_tieu)
        phien_id = cur.fetchone()[0]
        conn.commit()
    return phien_id


def cap_nhat_phien(phien_id, **cot):
    """Cập nhật các cột bất kỳ, ví dụ cap_nhat_phien(5, TrangThai='dang_chay', PhanTram=10)."""
    if not cot:
        return
    gan = ", ".join(f"{ten} = ?" for ten in cot)
    with ket_noi() as conn:
        conn.execute(f"UPDATE dbo.PhienHocMay SET {gan} WHERE Id = ?", *cot.values(), phien_id)
        conn.commit()


def bat_dau_phien(phien_id):
    with ket_noi() as conn:
        conn.execute("""UPDATE dbo.PhienHocMay SET TrangThai = N'dang_chay', ThoiGianBatDau = SYSDATETIME(),
                            TienDo = N'Đang chuẩn bị dữ liệu...' WHERE Id = ?""", phien_id)
        conn.commit()


def luu_ket_qua_phien(phien_id, kq, nhat_ky):
    import json
    with ket_noi() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE dbo.PhienHocMay SET TrangThai = N'xong', PhanTram = 100, ThoiGianKetThuc = SYSDATETIME(),
                   MoHinhChon = ?, BienTheChon = ?, NgayDuBao = ?, DuBaoT1 = ?, KhoangDuoi95 = ?, KhoangTren95 = ?,
                   XuHuong = ?, CanhBao = ?, KetQuaJson = ?, NhatKy = ?, TienDo = N'Hoàn tất'
               WHERE Id = ?""",
            kq["Chosen_Model"], kq["Chosen_Variant"], kq["Next_Forecast_Date"], kq["Next_Forecast_Rate_Mean"],
            kq["Prediction_Interval_95"][0], kq["Prediction_Interval_95"][1], kq["Direction"],
            kq["Management_Alert"], json.dumps(kq, ensure_ascii=False), nhat_ky, phien_id,
        )
        cur.execute("DELETE FROM dbo.BangXepHang WHERE PhienId = ?", phien_id)
        for r in kq["Leaderboard"]:
            cur.execute(
                """INSERT INTO dbo.BangXepHang (PhienId, Hang, MoHinh, BienThe, MeanRMSE, SdRMSE, MAE, MAPE, Bias,
                       DirAcc, CaiThienSoBaseline, CaiThienSoRW, DmPvalueRW, DmPvalueARIMA, J_CV, SoSeed, SieuThamSo,
                       DuocChon)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                phien_id, r["rank"], r["model"], r["variant"], r["mean_rmse"], r["sd_rmse"], r["mae"], r["mape"],
                r["bias"], r["dir_acc"], r["improvement_vs_baseline_pct"], r["improvement_vs_rw_pct"],
                r["dm_pvalue_vs_rw"], r["dm_pvalue_vs_arima"], r["j_cv"], r["n_seeds"],
                json.dumps(r["hyperparameters"], ensure_ascii=False),
                r["model"] == kq["Chosen_Model"] and r["variant"] == kq["Chosen_Variant"],
            )
        conn.commit()


def lay_phien(phien_id):
    with ket_noi() as conn:
        ds = _thanh_dict(conn.execute("SELECT * FROM dbo.PhienHocMay WHERE Id = ?", phien_id))
        return ds[0] if ds else None


def lay_danh_sach_phien(lan_id):
    with ket_noi() as conn:
        return _thanh_dict(conn.execute(
            """SELECT Id, CheDo, CheDoMucTieu, TrangThai, PhanTram, ThoiGianTao, ThoiGianKetThuc,
                      MoHinhChon, BienTheChon, NgayDuBao, DuBaoT1, CanhBao
               FROM dbo.PhienHocMay WHERE LanTaiLenId = ? ORDER BY Id DESC""", lan_id))


def danh_dau_phien_bi_gian_doan():
    """Khi web khởi động lại, các phiên đang chạy dở đã bị dừng theo."""
    with ket_noi() as conn:
        conn.execute("""UPDATE dbo.PhienHocMay SET TrangThai = N'loi',
                            Loi = N'Web đã khởi động lại khi phiên đang chạy. Hãy chạy lại.'
                        WHERE TrangThai IN (N'dang_cho', N'dang_chay')""")
        conn.commit()


# ================================================================ Quy trình bài NCKH (đặc tả v3)

def tao_phien_nckh(lan_id, cfg, dia_chi_ip=None):
    with ket_noi() as conn:
        cur = conn.execute(
            """INSERT INTO dbo.PhienNCKH (LanTaiLenId, CheDo, ThuatToan, BienThe, NguongTheoDoi, NguongManh, DiaChiIP)
               OUTPUT INSERTED.Id VALUES (?, ?, ?, ?, ?, ?, ?)""",
            lan_id, cfg["mode"], ",".join(cfg["models"]), ",".join(cfg["variants"]),
            cfg["alert_watch_pct"], cfg["alert_strong_pct"], dia_chi_ip)
        pid = cur.fetchone()[0]
        conn.commit()
    return pid


def cap_nhat_nckh(pid, **cot):
    if not cot:
        return
    gan = ", ".join(f"{k} = ?" for k in cot)
    with ket_noi() as conn:
        conn.execute(f"UPDATE dbo.PhienNCKH SET {gan} WHERE Id = ?", *cot.values(), pid)
        conn.commit()


def bat_dau_nckh(pid):
    with ket_noi() as conn:
        conn.execute("UPDATE dbo.PhienNCKH SET TrangThai = N'dang_chay', ThoiGianBatDau = SYSDATETIME() WHERE Id = ?", pid)
        conn.commit()


def ket_thuc_nckh(pid, trang_thai, **cot):
    cot = {"TrangThai": trang_thai, **cot}
    gan = ", ".join(f"{k} = ?" for k in cot)
    with ket_noi() as conn:
        conn.execute(f"UPDATE dbo.PhienNCKH SET {gan}, ThoiGianKetThuc = SYSDATETIME() WHERE Id = ?", *cot.values(), pid)
        conn.commit()


def dem_phien_dang_hoat_dong(cho_xac_nhan_toi_da_phut=None, tru_id=None):
    """Số phiên đang ước tính / chờ / chạy. Phiên chờ xác nhận chỉ tính khi tạo chưa quá N phút (nếu đặt N)."""
    dieu_kien_cho = ("" if cho_xac_nhan_toi_da_phut is None
                     else " AND ThoiGianTao >= DATEADD(MINUTE, -?, SYSDATETIME())")
    tham_so = [] if cho_xac_nhan_toi_da_phut is None else [int(cho_xac_nhan_toi_da_phut)]
    with ket_noi() as conn:
        return conn.execute(f"""SELECT COUNT(*) FROM dbo.PhienNCKH
                                WHERE Id <> ? AND (TrangThai IN (N'uoc_tinh', N'cho', N'dang_chay')
                                   OR (TrangThai = N'cho_xac_nhan'{dieu_kien_cho}))""",
                            tru_id or 0, *tham_so).fetchone()[0]


def dem_phien_chay_thu_theo_ip(dia_chi_ip, so_phut=60):
    """Số phiên Chạy thử tạo từ một địa chỉ IP trong N phút gần nhất."""
    with ket_noi() as conn:
        return conn.execute("""SELECT COUNT(*) FROM dbo.PhienNCKH
                               WHERE DiaChiIP = ? AND CheDo = N'chay_thu'
                                 AND ThoiGianTao >= DATEADD(MINUTE, -?, SYSDATETIME())""",
                            dia_chi_ip, int(so_phut)).fetchone()[0]


def co_yeu_cau_huy(pid):
    with ket_noi() as conn:
        r = conn.execute("SELECT YeuCauHuy FROM dbo.PhienNCKH WHERE Id = ?", pid).fetchone()
        return bool(r and r[0])


def luu_ket_qua_nckh(pid, kq, tien_do_json, ket_qua_json):
    """Lưu Bảng 4.6 vào PhienNCKH, mỗi ứng viên vào NCKH_UngVien, dự báo từng ngày vào NCKH_DuBaoTest."""
    import json
    t6 = kq["table_4_6"] or {}                        # None khi chỉ chạy ARIMA (không có mô hình chính)
    ch = kq["candidates"][kq["chosen_key"]] if kq["chosen_key"] else None
    with ket_noi() as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.execute(
            """UPDATE dbo.PhienNCKH SET TrangThai = N'xong', PhanTram = 100, ThoiGianKetThuc = SYSDATETIME(), Loi = NULL,
                   MoHinhChon = ?, BienTheChon = ?, NgayQuanSatCuoi = ?, TyGiaCuoi = ?, NgayDuBao = ?, DuBaoT1 = ?,
                   DuBaoSD = ?, DuBaoP05 = ?, DuBaoP95 = ?, ThayDoiPct = ?, CanhBao = ?, TienDoJson = ?, KetQuaJson = ?
               WHERE Id = ?""",
            ch["model"] if ch else None, (ch["variant"] or "—") if ch else None, t6.get("Latest_Observed_Date"),
            t6.get("Latest_Observed_Rate"), t6.get("Next_Forecast_Date"), t6.get("Next_Forecast_Rate_Mean"),
            t6.get("Next_Forecast_Rate_SD"), t6.get("Next_Forecast_P05"), t6.get("Next_Forecast_P95"),
            t6.get("Next_Forecast_Change_Percent_Mean"), t6.get("Management_Alert"), tien_do_json, ket_qua_json, pid)
        rw = kq["random_walk"]
        dong = [(pid, "RW", "RW", None, 1, rw["MAE"], rw["RMSE"], rw["MAPE"], rw["MeanErr"], rw["SdErr"], None,
                 None, None, None, None, None, None, False, None)]
        for k, c in kq["candidates"].items():
            s, t = c["summary"], c.get("t1", {})
            dong.append((pid, k, c["model"], c["variant"], s["n_runs"], s["MAE"], s["RMSE"], s["MAPE"], s["MeanErr"],
                         s["SdErr"], s["SD_RMSE"], t.get("mean"), t.get("sd"), t.get("p05"), t.get("p95"),
                         t.get("change_pct_mean"), t.get("alert"), bool(c.get("chosen")),
                         json.dumps(c["params"], ensure_ascii=False, default=str)))
        cur.executemany(
            """INSERT INTO dbo.NCKH_UngVien (PhienId, Khoa, MoHinh, BienThe, SoLanChay, MAE, RMSE, MAPE, SaiSoTB,
                   SaiSoChuan, SdRMSE, DuBaoT1, DuBaoT1SD, DuBaoP05, DuBaoP95, ThayDoiPct, CanhBao, DuocChon, SieuThamSo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", dong)
        t = kq["test"]
        fig = kq.get("figure_4_1") or {}
        test = []
        for k, preds in [("RW", t["random_walk"])] + [(k, c["pred"]) for k, c in kq["candidates"].items()]:
            for i, (ngay, thuc, du) in enumerate(zip(t["dates"], t["actual"], preds)):
                lo = fig["lo"][i] if k == "ARIMA" and fig else None
                hi = fig["hi"][i] if k == "ARIMA" and fig else None
                test.append((pid, k, ngay, thuc, round(float(du), 4), lo, hi))
        cur.executemany("""INSERT INTO dbo.NCKH_DuBaoTest (PhienId, Khoa, Ngay, ThucTe, DuBao, Duoi95, Tren95)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""", test)
        conn.commit()


def lay_phien_nckh(pid):
    with ket_noi() as conn:
        ds = _thanh_dict(conn.execute("SELECT * FROM dbo.PhienNCKH WHERE Id = ?", pid))
        return ds[0] if ds else None


def lay_trang_thai_nckh(pid):
    with ket_noi() as conn:
        ds = _thanh_dict(conn.execute(
            """SELECT Id, TrangThai, PhanTram, TienDoJson, UocTinhGiay, UocTinhJson, Loi, CheDo
               FROM dbo.PhienNCKH WHERE Id = ?""", pid))
        return ds[0] if ds else None


def lay_du_bao_test(pid, khoa):
    with ket_noi() as conn:
        return _thanh_dict(conn.execute(
            """SELECT Ngay, ThucTe, DuBao, Duoi95, Tren95 FROM dbo.NCKH_DuBaoTest
               WHERE PhienId = ? AND Khoa = ? ORDER BY Ngay""", pid, khoa))


def xoa_phien_nckh(pid):
    with ket_noi() as conn:
        dong = conn.execute("SELECT LanTaiLenId FROM dbo.PhienNCKH WHERE Id = ?", pid).fetchone()
        if dong is None:
            return
        conn.execute("DELETE FROM dbo.PhienNCKH WHERE Id = ?", pid)      # NCKH_UngVien, NCKH_DuBaoTest tự xóa theo
        _xoa_lan_tai_len_mo_coi(conn, dong[0])
        conn.commit()


def danh_dau_nckh_bi_gian_doan():
    with ket_noi() as conn:
        conn.execute("""UPDATE dbo.PhienNCKH SET TrangThai = N'loi',
                            Loi = N'Web đã khởi động lại (hoặc máy tắt) khi phiên đang chạy hoặc đang chờ. Bấm "Chạy tiếp" để tiếp tục từ phần đã xong.'
                        WHERE TrangThai IN (N'uoc_tinh', N'cho', N'dang_chay')""")
        conn.execute("""UPDATE dbo.PhienNCKH SET BacktestTrangThai = N'loi: Web đã khởi động lại khi đang tạo backtest. Hãy tạo lại.'
                        WHERE BacktestTrangThai IN (N'cho', N'dang_chay')""")
        conn.commit()


# ---------------------------------------------------------------- Lịch sử dự báo giả lập (backtest, IsBacktest = 1)

def luu_backtest(pid, rows, mo_hinh, bien_the):
    with ket_noi() as conn:
        cur = conn.cursor()
        cur.fast_executemany = True
        cur.executemany(
            """INSERT INTO dbo.NCKH_Backtest (PhienId, NgayDuBao, NgayQuanSat, TyGiaQuanSat, DuBaoT1, ThucTe, MoHinh,
                   BienThe, SoSeed, ThayDoiPct, CanhBao, IsBacktest)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            [(pid, r["date"], r["obs_date"], r["obs_rate"], round(r["forecast"], 4), r["actual"], mo_hinh, bien_the,
              r["n_seeds"], r["change_pct"], r["alert"]) for r in rows])
        cur.execute("UPDATE dbo.PhienNCKH SET BacktestTrangThai = N'xong' WHERE Id = ?", pid)
        conn.commit()


def lay_backtest(pid):
    with ket_noi() as conn:
        return _thanh_dict(conn.execute(
            """SELECT NgayDuBao, NgayQuanSat, TyGiaQuanSat, DuBaoT1, ThucTe, MoHinh, BienThe, SoSeed, ThayDoiPct, CanhBao,
                      IsBacktest, ThoiGianTao
               FROM dbo.NCKH_Backtest WHERE PhienId = ? AND IsBacktest = 1 ORDER BY NgayDuBao""", pid))


def lay_lich_su_tat_ca():
    """Lịch sử dự báo: phiên theo quy trình NCKH (mới) và phiên phiên bản cũ, mới nhất trước."""
    with ket_noi() as conn:
        moi = _thanh_dict(conn.execute(
            """SELECT 'nckh' AS Loai, p.Id, p.LanTaiLenId, p.CheDo, p.ThuatToan, p.BienThe, p.TrangThai, p.PhanTram,
                      p.ThoiGianTao, p.MoHinhChon, p.BienTheChon, p.NgayDuBao, p.DuBaoT1, p.DuBaoP05, p.DuBaoP95,
                      p.ThayDoiPct, p.CanhBao, l.TenFile, l.SoDong, l.NgayBatDau, l.NgayKetThuc,
                      (SELECT TOP 1 u.RMSE FROM dbo.NCKH_UngVien u WHERE u.PhienId = p.Id AND u.DuocChon = 1) AS RmseChon
               FROM dbo.PhienNCKH p JOIN dbo.LanTaiLen l ON l.Id = p.LanTaiLenId"""))
        cu = _thanh_dict(conn.execute(
            """SELECT 'cu' AS Loai, p.Id, p.LanTaiLenId, p.CheDo, NULL AS ThuatToan, NULL AS BienThe, p.TrangThai,
                      p.PhanTram, p.ThoiGianTao, p.MoHinhChon, p.BienTheChon, p.NgayDuBao, p.DuBaoT1,
                      NULL AS DuBaoP05, NULL AS DuBaoP95, NULL AS ThayDoiPct, p.CanhBao,
                      l.TenFile, l.SoDong, l.NgayBatDau, l.NgayKetThuc, NULL AS RmseChon
               FROM dbo.PhienHocMay p JOIN dbo.LanTaiLen l ON l.Id = p.LanTaiLenId"""))
    return sorted(moi + cu, key=lambda p: p["ThoiGianTao"], reverse=True)


def lay_phien_nckh_cung_du_lieu(lan_id, tru_id):
    with ket_noi() as conn:
        return _thanh_dict(conn.execute(
            """SELECT Id, CheDo, ThuatToan, BienThe, TrangThai, PhanTram, ThoiGianTao, MoHinhChon, BienTheChon,
                      NgayDuBao, DuBaoT1, CanhBao
               FROM dbo.PhienNCKH WHERE LanTaiLenId = ? AND Id <> ? ORDER BY Id DESC""", lan_id, tru_id))


def du_bao_truoc_day(lan_id, tru_id):
    """Mục 13.4: dự báo T+1 của các lần chạy trước (mọi lần tải) có ngày dự báo nằm trong dữ liệu
    của lần tải này -> so với tỷ giá thực tế."""
    with ket_noi() as conn:
        moi = _thanh_dict(conn.execute(
            """SELECT p.Id, 'nckh' AS Loai, p.CheDo, p.MoHinhChon, p.BienTheChon, p.NgayDuBao, p.DuBaoT1, p.CanhBao,
                      t.GiaTri AS ThucTe
               FROM dbo.PhienNCKH p JOIN dbo.TyGia t ON t.LanTaiLenId = ? AND t.Ngay = p.NgayDuBao
               WHERE p.TrangThai = N'xong' AND p.Id <> ?""", lan_id, tru_id))
        cu = _thanh_dict(conn.execute(
            """SELECT p.Id, 'cu' AS Loai, p.CheDo, p.MoHinhChon, p.BienTheChon, p.NgayDuBao, p.DuBaoT1, p.CanhBao,
                      t.GiaTri AS ThucTe
               FROM dbo.PhienHocMay p JOIN dbo.TyGia t ON t.LanTaiLenId = ? AND t.Ngay = p.NgayDuBao
               WHERE p.TrangThai = N'xong'""", lan_id))
    return sorted(moi + cu, key=lambda r: (r["NgayDuBao"], r["Id"]))
