"""Chạy quy trình bài NCKH (forecast_engine) ở chế độ nền cho web.

Trình tự một phiên: ước tính thời gian -> (Chạy đầy đủ: chờ người dùng xác nhận) -> xếp hàng -> chạy.
Mỗi lần chỉ chạy 1 phiên; trạng thái và tiến trình 12 công đoạn lưu vào SQL Server (PhienNCKH).
"""
import json
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import db
from forecast_engine.pipeline import estimate, run_pipeline
from forecast_engine.progress import Cancelled
from forecast_engine.run_config import build_run_config

THU_MUC_KET_QUA = Path(__file__).parent / "artifacts"
_hang_doi = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nckh-chay")
_uoc_tinh = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nckh-uoc-tinh")


def thu_muc_phien(pid):
    return THU_MUC_KET_QUA / f"nckh_{pid}"


def _json(o):
    return json.dumps(o, ensure_ascii=False, default=str)


def cau_hinh_phien(pid):
    """Dựng lại (lan_id, run_config, meta) từ dòng PhienNCKH – không phụ thuộc bộ nhớ của web."""
    p = db.lay_phien_nckh(pid)
    lan = db.lay_lan_tai_len(p["LanTaiLenId"])
    cfg = build_run_config(p["CheDo"], p["ThuatToan"].split(","), p["BienThe"].split(",") if p["BienThe"] else [],
                           alert_watch_pct=p["NguongTheoDoi"], alert_strong_pct=p["NguongManh"])
    return p["LanTaiLenId"], cfg, {"filename": lan["TenFile"]}


def bat_dau(pid):
    """Tạo xong phiên -> ước tính thời gian ngay (mục 12.1)."""
    _uoc_tinh.submit(_chay_uoc_tinh, pid)


def _chay_uoc_tinh(pid):
    lan_id, cfg, meta = cau_hinh_phien(pid)
    try:
        est = estimate(db.lay_ty_gia_dataframe(lan_id), cfg)
        db.cap_nhat_nckh(pid, UocTinhGiay=est["total_seconds"], UocTinhJson=_json(est))
        if db.co_yeu_cau_huy(pid):
            db.ket_thuc_nckh(pid, "huy", Loi="Đã hủy trước khi chạy.")
        elif cfg["mode"] == "chay_day_du":
            db.cap_nhat_nckh(pid, TrangThai="cho_xac_nhan")      # Chạy đầy đủ: phải bấm xác nhận thêm một lần
        else:
            xep_hang(pid)
    except Exception as e:
        db.ket_thuc_nckh(pid, "loi", Loi=f"Lỗi khi ước tính thời gian: {type(e).__name__}: {e}")


def xep_hang(pid):
    db.cap_nhat_nckh(pid, TrangThai="cho")
    _hang_doi.submit(_chay, pid)


def co_tien_do_luu(pid):
    """Phiên có phần việc đã lưu (thư mục checkpoint) để Chạy tiếp hay không."""
    thu_muc = thu_muc_phien(pid) / "checkpoint"
    return thu_muc.exists() and any(thu_muc.glob("*.joblib"))


def chay_tiep(pid):
    """Chạy lại phiên bị dừng (máy tắt, web khởi động lại, lỗi, hủy): pipeline bỏ qua các đơn vị việc đã lưu
    trong <thư mục phiên>/checkpoint nên kết quả giống hệt khi chạy một mạch với cùng seed."""
    db.cap_nhat_nckh(pid, YeuCauHuy=False, Loi=None)
    xep_hang(pid)


SO_NGAY_BACKTEST = 30


def tao_backtest(pid):
    """Xếp hàng tạo lịch sử dự báo giả lập (walk-forward 30 ngày cuối) cho mô hình được chọn của phiên.
    Dùng chung hàng đợi 1 luồng với các phiên chạy, nên không bao giờ chạy song song với một phiên khác."""
    db.cap_nhat_nckh(pid, BacktestTrangThai="cho")
    _hang_doi.submit(_chay_backtest, pid)


def _chay_backtest(pid):
    from forecast_engine.data_io import clean
    from forecast_engine.feedback import backtest
    try:
        db.cap_nhat_nckh(pid, BacktestTrangThai="dang_chay")
        lan_id, cfg, _ = cau_hinh_phien(pid)
        kq = json.loads(db.lay_phien_nckh(pid)["KetQuaJson"])
        ch = kq["candidates"][kq["chosen_key"]]
        df, _, _ = clean(db.lay_ty_gia_dataframe(lan_id), cfg)
        rows = backtest(df["rate"].to_numpy(), df["date"].to_numpy(), ch["model"], ch["params"], cfg,
                        n_days=SO_NGAY_BACKTEST)
        db.luu_backtest(pid, rows, ch["model"], ch["variant"])
    except Exception as e:
        db.cap_nhat_nckh(pid, BacktestTrangThai=f"loi: {type(e).__name__}: {e}"[:400])


def _chay(pid):
    lan_id, cfg, meta = cau_hinh_phien(pid)
    if db.co_yeu_cau_huy(pid):
        db.ket_thuc_nckh(pid, "huy", Loi="Đã hủy trước khi chạy.")
        return
    phien = db.lay_trang_thai_nckh(pid)
    est = json.loads(phien["UocTinhJson"]) if phien and phien["UocTinhJson"] else None
    trang_thai = {"snap": None, "da_ghi": None, "huy": False}
    dung = threading.Event()

    def on_progress(snap):
        trang_thai["snap"] = snap                                  # luồng ghi bên dưới sẽ lưu vào DB
        return trang_thai["huy"]

    def ghi_dinh_ky():
        """Mỗi giây: lưu trạng thái mới nhất vào DB và đọc cờ Hủy (API /api/tien-do đọc từ DB)."""
        while not dung.wait(1.0):
            snap = trang_thai["snap"]
            if snap is not None and snap is not trang_thai["da_ghi"]:
                trang_thai["da_ghi"] = snap
                try:
                    db.cap_nhat_nckh(pid, PhanTram=snap["percent"], TienDoJson=_json(snap))
                except Exception:
                    pass
            try:
                trang_thai["huy"] = db.co_yeu_cau_huy(pid)
            except Exception:
                pass

    def dung_ghi():                      # dừng luồng ghi định kỳ TRƯỚC khi lưu trạng thái cuối, tránh bị ghi đè
        dung.set()
        luong_ghi.join(timeout=5)

    db.bat_dau_nckh(pid)
    luong_ghi = threading.Thread(target=ghi_dinh_ky, daemon=True)
    luong_ghi.start()
    try:
        kq = run_pipeline(db.lay_ty_gia_dataframe(lan_id), cfg, on_progress,
                          output_dir=thu_muc_phien(pid), meta=meta, estimate=est)
        dung_ghi()
        snap = kq.pop("progress", None)
        db.luu_ket_qua_nckh(pid, kq, _json(snap), _json(kq))
        shutil.rmtree(thu_muc_phien(pid) / "checkpoint", ignore_errors=True)   # xong rồi: không cần tiến độ để chạy tiếp
    except Cancelled:
        dung_ghi()
        snap = trang_thai["snap"]
        db.ket_thuc_nckh(pid, "huy", Loi="Đã hủy theo yêu cầu.", TienDoJson=_json(snap) if snap else None)
    except Exception as e:
        dung_ghi()
        snap = trang_thai["snap"] or {}
        err = (snap or {}).get("error") or {}
        buoc = f"Lỗi ở bước {err['step']} – {err['step_name']}: " if err else ""
        huong_dan = f" Cách khắc phục: {err['hint']}" if err.get("hint") else ""
        db.ket_thuc_nckh(pid, "loi", Loi=f"{buoc}{type(e).__name__}: {e}.{huong_dan}\n\n{traceback.format_exc()}",
                         TienDoJson=_json(snap) if snap else None)
    finally:
        dung_ghi()
