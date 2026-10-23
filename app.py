"""Web Dự báo tỷ giá USD/VND T+1 – tái lập quy trình bài NCKH (đặc tả v3).

Chạy:  python app.py   rồi mở http://localhost:5000
"""
import csv
import io
import json
import os
import threading
from datetime import date
from pathlib import Path

import pyodbc
from flask import (Flask, Response, abort, flash, jsonify, redirect, render_template, request, send_from_directory,
                   session, url_for)

import bai_goc
import bao_mat
import config
import db
import hoc_may
from forecast_engine import data_io, report_extras
from forecast_engine.evaluate import FIELDS_46
from forecast_engine.feedback import monitor_records, rolling_status
from forecast_engine.progress import STEPS, scope_text, skip_reasons
from forecast_engine import search_space as ss
from forecast_engine.run_config import (COMMON, MODE_NAMES, MODEL_NAMES, MODELS, ML_MODELS, VARIANTS,
                                        build_run_config, paper_settings_table, settings_table)

THU_MUC = Path(__file__).parent
TEP_CU = {"result.json", "leaderboard.csv", "test_predictions.csv", "test_chart.png"}

app = Flask(__name__)
app.secret_key = bao_mat.khoa_bi_mat()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")    # không giới hạn dung lượng file
_khoa_tao_phien = threading.Lock()      # kiểm tra "đang bận" và tạo phiên là một bước, hai người bấm cùng lúc không lọt


# ---------------------------------------------------------------- Đăng nhập, phân quyền, CSRF

def vai_tro():
    """Mặc định mọi người là Người dùng (không cần mật khẩu); Quản trị khi đã mở ổ khóa."""
    return "quan_tri" if session.get("vai_tro") == "quan_tri" else "khach"


def la_quan_tri():
    return vai_tro() == "quan_tri"


def phien_cua_toi():
    """Các phiên do trình duyệt này tạo (lưu trong cookie phiên) – người dùng chỉ được hủy phiên của mình."""
    return session.get("phien_cua_toi", [])


@app.before_request
def bao_ve():
    """Mọi thao tác gửi form (POST) phải có mã CSRF. Xem và chạy mô hình không cần đăng nhập."""
    if request.endpoint == "static":
        return None
    if request.method == "POST" and not bao_mat.csrf_hop_le(session, request.form.get("csrf_token")):
        flash("Phiên làm việc đã hết hạn, vui lòng tải lại trang và thử lại.", "loi")
        return redirect(request.referrer or url_for("trang_chu"))
    return None


@app.route("/quan-tri", methods=["GET", "POST"])
def dang_nhap():
    """Mở khóa chế độ Quản trị (biểu tượng ổ khóa trên thanh trên cùng)."""
    if not bao_mat.da_dat_mat_khau():
        return render_template("dang_nhap.html", chua_dat=True)
    if la_quan_tri():
        return redirect(url_for("trang_chu"))
    if request.method == "POST":
        dc = bao_mat.dia_chi(request)
        if bao_mat.dang_bi_khoa(dc):
            flash(f"Sai mật khẩu quá nhiều lần. Thử lại sau {bao_mat.KHOA_GIAY // 60} phút.", "loi")
            return redirect(url_for("dang_nhap"))
        if not bao_mat.la_mat_khau_quan_tri(request.form.get("mat_khau", "")):
            bao_mat.ghi_sai(dc)
            flash("Mật khẩu không đúng.", "loi")
            return redirect(url_for("dang_nhap"))
        bao_mat.xoa_sai(dc)
        cua_toi = phien_cua_toi()
        session.clear()                                   # đổi phiên đăng nhập, tránh dùng lại cookie cũ
        session["vai_tro"] = "quan_tri"
        session["phien_cua_toi"] = cua_toi
        flash("Đã mở khóa chế độ Quản trị.", "ok")
        tiep = request.args.get("tiep", "/")
        an_toan = tiep.startswith("/") and not tiep.startswith("//") and "\\" not in tiep    # chặn chuyển hướng ra web khác
        return redirect(tiep if an_toan else "/")
    return render_template("dang_nhap.html", chua_dat=False)


@app.post("/quan-tri/thoat")
def dang_xuat():
    cua_toi = phien_cua_toi()
    session.clear()
    session["phien_cua_toi"] = cua_toi
    flash("Đã khóa lại chế độ Quản trị.", "ok")
    return redirect(url_for("trang_chu"))


def chi_quan_tri():
    if not la_quan_tri():
        abort(403)


def chi_xem():
    """PUBLIC_READONLY=1: người dùng chỉ xem lịch sử và kết quả (không tải lên, không chạy, không hủy).
    Chế độ Quản trị (mở ổ khóa) vẫn làm được mọi thao tác."""
    return os.environ.get("PUBLIC_READONLY") == "1" and not la_quan_tri()


THONG_BAO_CHI_XEM = "Web đang ở chế độ chỉ xem: không tải dữ liệu lên, chạy hay hủy phiên được."


@app.errorhandler(403)
def cam(_):
    flash("Thao tác này cần chế độ Quản trị (bấm biểu tượng ổ khóa ở góc trên).", "loi")
    return redirect(request.referrer or url_for("trang_chu"))

def danh_dau_phien_bi_gian_doan():
    """Chỉ gọi khi web khởi động (trong khối __main__). KHÔNG để ở cấp module: trên Windows, các tiến trình con
    chạy song song nạp lại file này và sẽ đánh dấu nhầm phiên đang chạy là lỗi."""
    try:
        db.danh_dau_phien_bi_gian_doan()
        db.danh_dau_nckh_bi_gian_doan()
    except pyodbc.Error:
        pass        # chưa có database: trang chủ sẽ báo lỗi kết nối


# ---------------------------------------------------------------- Định dạng hiển thị

@app.template_filter("so")
def dinh_dang_so(gia_tri, chu_so=0):
    """26345.5 -> '26.345,50' kiểu Việt Nam."""
    if gia_tri is None:
        return "—"
    chuoi = f"{float(gia_tri):,.{chu_so}f}"
    return chuoi.replace(",", "_").replace(".", ",").replace("_", ".")


@app.template_filter("pt")
def dinh_dang_phan_tram(gia_tri, chu_so=1):
    """3.2 -> '+3,2%'."""
    if gia_tri is None:
        return "—"
    return f"{float(gia_tri):+.{chu_so}f}%".replace(".", ",")


@app.template_filter("pval")
def dinh_dang_p(gia_tri):
    if gia_tri is None:
        return "—"
    return "<0,0001" if gia_tri < 1e-4 else f"{gia_tri:.4f}".replace(".", ",")


@app.template_filter("lop_canh_bao")
def lop_canh_bao(nhan):
    # Tăng / Giảm / Ổn định (Hình 3.3). "Theo dõi", "Biến động mạnh" chỉ còn ở các phiên chạy trước khi sửa.
    return {"Ổn định": "cb-on-dinh", "Tăng": "cb-theo-doi", "Giảm": "cb-theo-doi",
            "Theo dõi": "cb-theo-doi", "Biến động mạnh": "cb-bien-dong"}.get(nhan, "")


@app.template_filter("ngay")
def dinh_dang_ngay(gia_tri, co_gio=False):
    if gia_tri is None:
        return "—"
    if isinstance(gia_tri, str):                      # "2026-09-24" trong JSON
        gia_tri = date.fromisoformat(gia_tri[:10])
    return gia_tri.strftime("%d/%m/%Y %H:%M" if co_gio else "%d/%m/%Y")


@app.template_filter("thoi_luong")
def thoi_luong(giay):
    if giay is None:
        return "—"
    giay = int(giay)
    if giay < 90:
        return f"{giay} giây"
    if giay < 5400:
        return f"{giay / 60:.0f} phút".replace(".", ",")
    return f"{giay / 3600:.1f} giờ".replace(".", ",")


TEP_DU_LIEU_MAU = "tygia_mau.csv"           # dữ liệu mô phỏng của web (lệch khoảng 430 VND so với thực tế)


def la_du_lieu_mau(ten_file):
    return (ten_file or "").strip().lower() == TEP_DU_LIEU_MAU


@app.context_processor
def bien_chung():
    return {"MODEL_NAMES": MODEL_NAMES, "MODE_NAMES": MODE_NAMES, "MODELS": MODELS, "VARIANTS": VARIANTS,
            "ML_MODELS": ML_MODELS, "COMMON": COMMON, "vai_tro": vai_tro(), "la_quan_tri": la_quan_tri(),
            "TEN_VAI_TRO": bao_mat.VAI_TRO, "csrf_token": lambda: bao_mat.csrf_token(session),
            "phien_cua_toi": phien_cua_toi(), "chi_xem": chi_xem(), "THONG_BAO_CHI_XEM": THONG_BAO_CHI_XEM,
            "la_du_lieu_mau": la_du_lieu_mau, "THIET_LAP_WEB": settings_table(), "THIET_LAP_BAI": paper_settings_table(),
            "FIELDS_46": FIELDS_46,
            "CFG_CHE_DO": {m: build_run_config(m) for m in ("chay_thu", "chay_day_du")}}


# ---------------------------------------------------------------- Form chọn chế độ và phạm vi (mục 12, 13)

THONG_BAO_BAN = "Hệ thống đang bận, thử lại sau."


def he_thong_dang_ban(tru_id=None):
    return db.dem_phien_dang_hoat_dong(config.CHO_XAC_NHAN_TOI_DA_PHUT, tru_id) >= config.PHIEN_CHAY_DONG_THOI


def _doc_form():
    """Đọc chế độ, thuật toán, cách cấu hình, ngưỡng cảnh báo và kiểm tra giới hạn chạy.
    Trả về run_config hoặc ném ValueError. Gọi trong `_khoa_tao_phien`."""
    if chi_xem():
        raise ValueError(THONG_BAO_CHI_XEM)
    che_do = request.form.get("che_do", "chay_thu")         # Chạy thử và Chạy đầy đủ đều mở cho mọi người
    if he_thong_dang_ban():
        raise ValueError(THONG_BAO_BAN)
    if (not la_quan_tri() and che_do == "chay_thu"
            and db.dem_phien_chay_thu_theo_ip(bao_mat.dia_chi(request)) >= config.CHAY_THU_MOI_IP_MOI_GIO):
        raise ValueError(f"Mỗi địa chỉ IP chỉ được Chạy thử tối đa {config.CHAY_THU_MOI_IP_MOI_GIO} phiên trong 1 giờ. "
                         "Vui lòng thử lại sau.")
    models = [m for m in request.form.getlist("thuat_toan") if m in MODELS]
    variants = [v for v in request.form.getlist("bien_the") if v in VARIANTS]
    if not models:
        raise ValueError("Phải chọn ít nhất 1 thuật toán.")
    if any(m in ML_MODELS for m in models) and not variants:
        raise ValueError("Đã chọn ANN / Random Forest / XGBoost thì phải chọn ít nhất 1 cách cấu hình siêu tham số.")
    try:                                    # một ngưỡng duy nhất (Hình 3.3): |%Δ| < ngưỡng -> Ổn định, ngược lại Tăng/Giảm
        watch = float(str(request.form.get("nguong_theo_doi") or COMMON["alert_watch_pct"]).replace(",", "."))
    except ValueError:
        raise ValueError("Ngưỡng cảnh báo phải là số.")
    if watch < 0:
        raise ValueError("Ngưỡng cảnh báo phải lớn hơn hoặc bằng 0.")
    return build_run_config(che_do, models, variants or VARIANTS, alert_watch_pct=watch)


def _tao_phien(lan_id, cfg):
    pid = db.tao_phien_nckh(lan_id, cfg, bao_mat.dia_chi(request))
    session["phien_cua_toi"] = (phien_cua_toi() + [pid])[-50:]      # ghi nhớ phiên do trình duyệt này tạo
    hoc_may.bat_dau(pid)
    return redirect(url_for("xem_nckh", pid=pid))


@app.get("/")
def trang_chu():
    lich_su, loi_db = [], None
    try:
        lich_su = db.lay_lich_su_tat_ca()
    except pyodbc.Error as e:
        loi_db = str(e)
    # "Dự báo gần nhất": chỉ phiên có mô hình chính là ANN / RF / XGBoost (ARIMA chỉ là chuẩn đối chiếu – mục 3.3.5)
    moi_nhat = next((p for p in lich_su if p["Loai"] == "nckh" and p["TrangThai"] == "xong"
                     and p["MoHinhChon"] in ML_MODELS), None)
    dang_chay = [p for p in lich_su if p["TrangThai"] in ("uoc_tinh", "cho_xac_nhan", "cho", "dang_chay", "dang_cho")]
    return render_template("index.html", lich_su=lich_su, loi_db=loi_db, moi_nhat=moi_nhat, dang_chay=dang_chay)


@app.post("/tai-len")
def tai_len():
    """Đọc file -> lưu tỷ giá vào SQL Server -> ước tính thời gian -> chạy quy trình ở chế độ nền."""
    tep = request.files.get("tep")
    if chi_xem():
        flash(THONG_BAO_CHI_XEM, "loi")
        return redirect(url_for("trang_chu"))
    if not tep or not tep.filename:
        flash("Bạn chưa chọn file.", "loi")
        return redirect(url_for("trang_chu"))
    with _khoa_tao_phien:
        try:
            cfg = _doc_form()
            bang, _ = data_io.parse_table(data_io.read_table(tep.stream, tep.filename))
            df, _ = data_io.basic_clean(bang)
            data_io.clean(df, cfg)                                       # kiểm tra đủ dữ liệu trước khi lưu
        except (ValueError, data_io.DataError) as e:
            flash(str(e), "loi")
            return redirect(url_for("trang_chu"))
        try:
            lan_id = db.luu_lan_tai_len(tep.filename, df)
        except pyodbc.Error as e:
            flash(f"Không lưu được vào SQL Server: {e}", "loi")
            return redirect(url_for("trang_chu"))
        return _tao_phien(lan_id, cfg)


@app.post("/du-lieu/<int:lan_id>/chay")
def chay_lai(lan_id):
    """Chạy thêm một phiên trên dữ liệu đã tải (đổi chế độ hoặc phạm vi)."""
    if db.lay_lan_tai_len(lan_id) is None:
        abort(404)
    with _khoa_tao_phien:
        try:
            cfg = _doc_form()
        except ValueError as e:
            flash(str(e), "loi")
            return redirect(request.referrer or url_for("trang_chu"))
        return _tao_phien(lan_id, cfg)


# ---------------------------------------------------------------- Phiên quy trình NCKH

@app.get("/nckh/<int:pid>")
def xem_nckh(pid):
    p = db.lay_phien_nckh(pid)
    if p is None:
        abort(404)
    lan = db.lay_lan_tai_len(p["LanTaiLenId"])
    kq = json.loads(p["KetQuaJson"]) if p["KetQuaJson"] else None
    tien_do = json.loads(p["TienDoJson"]) if p["TienDoJson"] else None
    uoc_tinh = json.loads(p["UocTinhJson"]) if p["UocTinhJson"] else None
    _, cfg, _ = hoc_may.cau_hinh_phien(pid)
    buoc_mac_dinh = [{"id": i, "name": n, "caption": c, "status": "bo_qua" if i in skip_reasons(cfg) else "cho",
                      "detail": skip_reasons(cfg).get(i, "")} for i, n, c in STEPS]
    truoc_day, phan_hoi = [], None
    if kq:                                  # kết quả lưu trước khi có các mục bổ sung: tính thêm khi xem
        y = None
        if "flat_days" not in kq["table_4_1"]:
            y = data_io.clean(db.lay_ty_gia_dataframe(p["LanTaiLenId"]), cfg)[0]["rate"].to_numpy()
        report_extras.enrich(kq, y)
    tinh_backtest = request.args.get("tinh_backtest") == "1"
    if kq:
        truoc_day = db.du_bao_truoc_day(p["LanTaiLenId"], pid)
        for r in truoc_day:
            r["Backtest"] = False
        for r in db.lay_backtest(pid):              # dự báo giả lập (IsBacktest = 1) của chính phiên này
            truoc_day.append({"Id": pid, "Loai": "nckh", "CheDo": p["CheDo"], "MoHinhChon": r["MoHinh"],
                              "BienTheChon": r["BienThe"] or "—", "NgayDuBao": r["NgayDuBao"], "DuBaoT1": r["DuBaoT1"],
                              "ThucTe": r["ThucTe"], "CanhBao": r["CanhBao"], "Backtest": True})
        for r in truoc_day:
            r["SaiLech"] = float(r["ThucTe"]) - float(r["DuBaoT1"])
            r["SaiLechPct"] = r["SaiLech"] / float(r["ThucTe"]) * 100
        truoc_day.sort(key=lambda r: (r["NgayDuBao"], r["Backtest"], r["Id"]))
        if kq["chosen_key"]:                # vòng phản hồi theo dõi mô hình chính (không có khi chỉ chạy ARIMA)
            ch = kq["candidates"][kq["chosen_key"]]
            ban_ghi = lambda ds: [{"date": r["NgayDuBao"], "forecast": float(r["DuBaoT1"]), "actual": float(r["ThucTe"])}
                                  for r in ds]
            phan_hoi = rolling_status(monitor_records(ban_ghi(r for r in truoc_day if not r["Backtest"]),
                                                      ban_ghi(r for r in truoc_day if r["Backtest"]), tinh_backtest),
                                      ch["summary"]["RMSE"], COMMON["monitor_window"],
                                      COMMON["monitor_factor"], COMMON["monitor_consecutive"])
    kq_bieu_do = None
    if kq:                                  # chỉ gửi xuống trình duyệt phần dữ liệu biểu đồ/bảng cần dùng
        kq_bieu_do = {"test": kq["test"], "random_walk": kq["random_walk"], "figure_4_1": kq.get("figure_4_1"),
                      "figure_4_2": kq.get("figure_4_2"),
                      "chosen_key": kq["chosen_key"], "ranking": kq["ranking"],
                      "candidates": {k: {x: c.get(x) for x in ("label", "model", "variant", "pred", "summary", "t1", "pi95",
                                                               "vs_arima_pct", "vs_rw_pct")}
                                     for k, c in kq["candidates"].items()}}
    return render_template("nckh.html", p=p, lan=lan, kq=kq, kq_bieu_do=kq_bieu_do, tien_do=tien_do, uoc_tinh=uoc_tinh, cfg=cfg,
                           du_lieu_mo_phong=la_du_lieu_mau(lan["TenFile"]),
                           pham_vi=scope_text(cfg), buoc_mac_dinh=buoc_mac_dinh, bai_goc=bai_goc,
                           truoc_day=truoc_day, phan_hoi=phan_hoi, tinh_backtest=tinh_backtest,
                           co_backtest=any(r["Backtest"] for r in truoc_day),
                           duoc_backtest=duoc_tao_backtest(p), so_ngay_backtest=hoc_may.SO_NGAY_BACKTEST,
                           duoc_chay_tiep=duoc_chay_tiep(p), co_tien_do_luu=hoc_may.co_tien_do_luu(pid),
                           khong_gian=ss.space_table(build_run_config("chay_thu")["caps"], build_run_config("chay_day_du")["caps"]),
                           phien_khac=db.lay_phien_nckh_cung_du_lieu(p["LanTaiLenId"], pid))


@app.get("/api/tien-do/<int:pid>")
def api_tien_do(pid):
    p = db.lay_trang_thai_nckh(pid)
    if p is None:
        abort(404)
    return jsonify({"TrangThai": p["TrangThai"], "PhanTram": p["PhanTram"], "Loi": p["Loi"],
                    "UocTinhGiay": p["UocTinhGiay"],
                    "TienDo": json.loads(p["TienDoJson"]) if p["TienDoJson"] else None})


def la_chu_phien(pid):
    """Phiên do trình duyệt này tạo (không áp dụng khi web ở chế độ chỉ xem)."""
    return not chi_xem() and pid in phien_cua_toi()


@app.post("/nckh/<int:pid>/xac-nhan")
def xac_nhan(pid):
    """Xác nhận Chạy đầy đủ sau khi xem thời gian ước tính: người tạo phiên hoặc Quản trị."""
    p = db.lay_trang_thai_nckh(pid)
    if p is None:
        abort(404)
    if not (la_quan_tri() or la_chu_phien(pid)):
        chi_quan_tri()
    if p["TrangThai"] == "cho_xac_nhan":
        with _khoa_tao_phien:
            if he_thong_dang_ban(tru_id=pid):
                flash(THONG_BAO_BAN + " (đang có phiên khác chạy; hủy phiên đó hoặc chờ xong rồi xác nhận lại).", "loi")
            else:
                hoc_may.xep_hang(pid)
    return redirect(url_for("xem_nckh", pid=pid))


def duoc_chay_tiep(p):
    """Phiên dừng giữa chừng (lỗi, hủy, web khởi động lại). Quản trị hoặc người tạo phiên (cả hai chế độ)."""
    if p["TrangThai"] not in ("loi", "huy"):
        return False
    return la_quan_tri() or la_chu_phien(p["Id"])


@app.post("/nckh/<int:pid>/chay-tiep")
def chay_tiep(pid):
    p = db.lay_trang_thai_nckh(pid)
    if p is None:
        abort(404)
    if chi_xem():
        flash(THONG_BAO_CHI_XEM, "loi")
        return redirect(url_for("xem_nckh", pid=pid))
    if not duoc_chay_tiep(p):
        chi_quan_tri()
        return redirect(url_for("xem_nckh", pid=pid))
    with _khoa_tao_phien:
        if he_thong_dang_ban(tru_id=pid):
            flash(THONG_BAO_BAN, "loi")
        else:
            hoc_may.chay_tiep(pid)
            flash("Đã xếp hàng chạy tiếp: các phần đã xong được dùng lại, chỉ chạy phần còn thiếu.", "ok")
    return redirect(url_for("xem_nckh", pid=pid))


@app.post("/nckh/<int:pid>/huy")
def huy(pid):
    p = db.lay_trang_thai_nckh(pid)
    if p is None:
        abort(404)
    if chi_xem():
        flash(THONG_BAO_CHI_XEM, "loi")
        return redirect(url_for("xem_nckh", pid=pid))
    if pid not in phien_cua_toi():                           # người dùng: chỉ hủy phiên do mình tạo (cả hai chế độ)
        chi_quan_tri()
    db.cap_nhat_nckh(pid, YeuCauHuy=True)
    if p["TrangThai"] == "cho_xac_nhan":                     # chưa chạy: hủy ngay
        db.ket_thuc_nckh(pid, "huy", Loi="Đã hủy trước khi chạy.")
    flash("Đã gửi yêu cầu hủy. Phiên sẽ dừng ở điểm kiểm tra gần nhất.", "ok")
    return redirect(url_for("xem_nckh", pid=pid))


def duoc_tao_backtest(p):
    """Quản trị, hoặc người tạo phiên (khi không ở chế độ chỉ xem). Mỗi phiên tạo backtest một lần."""
    if (p["TrangThai"] != "xong" or p.get("BacktestTrangThai") in ("cho", "dang_chay", "xong")
            or p.get("MoHinhChon") not in ML_MODELS):          # chỉ backtest mô hình chính (ANN / RF / XGBoost)
        return False
    return la_quan_tri() or (not chi_xem() and p["Id"] in phien_cua_toi())


@app.post("/nckh/<int:pid>/backtest")
def tao_backtest(pid):
    """Tạo lịch sử dự báo giả lập (walk-forward) để kiểm chứng vòng phản hồi (mục 8.8)."""
    p = db.lay_phien_nckh(pid)
    if p is None:
        abort(404)
    if chi_xem():
        flash(THONG_BAO_CHI_XEM, "loi")
    elif not (la_quan_tri() or pid in phien_cua_toi()):
        chi_quan_tri()
    elif duoc_tao_backtest(p):
        hoc_may.tao_backtest(pid)
        flash("Đã xếp hàng tạo lịch sử dự báo giả lập (backtest). Trang sẽ tự cập nhật khi xong.", "ok")
    return redirect(url_for("xem_nckh", pid=pid))


@app.get("/nckh/<int:pid>/csv/<path:khoa>")
def tai_csv(pid, khoa):
    """Bảng từng ngày trên tập test của một ứng viên – file CSV tạo ở phía server (mục 13.3)."""
    dong = db.lay_du_bao_test(pid, khoa)
    if not dong:
        abort(404)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Ngay", "TyGiaThucTe", "DuBao", "SaiLech", "SaiLechPct"] + (["Duoi95", "Tren95"] if khoa == "ARIMA" else []))
    for r in dong:
        tt, db_ = float(r["ThucTe"]), float(r["DuBao"])
        row = [f"{r['Ngay']:%Y-%m-%d}", tt, db_, round(tt - db_, 4), round((tt - db_) / tt * 100, 6)]
        if khoa == "ARIMA":
            row += [r["Duoi95"], r["Tren95"]]
        w.writerow(row)
    ten = f"phien{pid}_{khoa.replace('|', '_')}.csv"
    return Response("﻿" + buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={ten}"})


@app.get("/nckh/<int:pid>/tep/result.json")
def tai_json(pid):
    return send_from_directory(hoc_may.thu_muc_phien(pid), "result.json", as_attachment=True)


@app.post("/nckh/<int:pid>/xoa")
def xoa_nckh(pid):
    chi_quan_tri()
    db.xoa_phien_nckh(pid)
    flash(f"Đã xóa phiên #{pid}.", "ok")
    return redirect(url_for("trang_chu"))


# ---------------------------------------------------------------- Phiên phiên bản cũ (chỉ xem)

@app.get("/phien/<int:phien_id>")
def xem_phien(phien_id):
    phien = db.lay_phien(phien_id)
    if phien is None:
        abort(404)
    lan = db.lay_lan_tai_len(phien["LanTaiLenId"])
    kq = json.loads(phien["KetQuaJson"]) if phien["KetQuaJson"] else None
    phien_khac = [p for p in db.lay_danh_sach_phien(lan["Id"]) if p["Id"] != phien_id]
    return render_template("phien.html", phien=phien, lan=lan, kq=kq, phien_khac=phien_khac)


@app.get("/api/phien/<int:phien_id>")
def trang_thai_phien(phien_id):
    phien = db.lay_phien(phien_id)
    if phien is None:
        abort(404)
    return jsonify({k: phien[k] for k in ("TrangThai", "PhanTram", "TienDo", "NhatKy", "Loi")})


@app.get("/phien/<int:phien_id>/tep/<ten>")
def tai_tep(phien_id, ten):
    if ten not in TEP_CU:
        abort(404)
    return send_from_directory(THU_MUC / "artifacts" / f"phien_{phien_id}", ten, as_attachment=ten != "test_chart.png")


@app.post("/phien/<int:phien_id>/xoa")
def xoa_phien(phien_id):
    chi_quan_tri()
    db.xoa_phien(phien_id)
    flash(f"Đã xóa phiên #{phien_id}.", "ok")
    return redirect(url_for("trang_chu"))


@app.get("/du-lieu-mau")
def du_lieu_mau():
    return send_from_directory(THU_MUC / "data", "tygia_mau.csv", as_attachment=True)


if __name__ == "__main__":
    # Chỉ dùng trên máy mình (127.0.0.1). Chia sẻ cho người khác: dùng chia_se_web.bat (máy chủ waitress).
    # Debug TẮT mặc định: bật debug khi web mở ra ngoài cho phép người khác chạy lệnh trên máy. Bật bằng FLASK_DEBUG=1.
    danh_dau_phien_bi_gian_doan()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", use_reloader=False, host="127.0.0.1", port=5000)
