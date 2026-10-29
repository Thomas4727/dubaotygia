"""Chia sẻ web cho người khác dùng.

    python chia_se.py                 # mạng nội bộ (cùng Wi-Fi) + link công khai qua Cloudflare Tunnel (nếu đã cài)
    python chia_se.py --chi-noi-bo    # chỉ mạng nội bộ
    python chia_se.py --chi-link      # chỉ link công khai (không mở cho mạng nội bộ)
    python chia_se.py --chi-may-nay   # không chia sẻ: chỉ máy này (dùng để kiểm thử)
    python chia_se.py --chi-xem       # thêm vào các lệnh trên: người dùng chỉ xem kết quả (PUBLIC_READONLY=1)

Máy chủ: waitress (máy chủ thật, không dùng máy chủ phát triển của Flask, debug tắt).
"""
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

CONG = 5000
THU_MUC = Path(__file__).parent
FILE_LINK = THU_MUC / "link_chia_se.txt"


def ip_noi_bo():
    """Địa chỉ IP của máy trong mạng nội bộ (không gửi dữ liệu nào ra ngoài)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def cong_dang_dung(cong):
    """Cổng đã có chương trình khác lắng nghe (vd chay_web.bat đang mở) thì không chia sẻ được."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", cong)) == 0


def tim_cloudflared():
    ung_vien = [shutil.which("cloudflared"),
                r"C:\Program Files (x86)\cloudflared\cloudflared.exe",
                r"C:\Program Files\cloudflared\cloudflared.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\cloudflared.exe")]
    return next((p for p in ung_vien if p and Path(p).exists()), None)


def chep_vao_clipboard(text):
    """Chép link vào bộ nhớ tạm của Windows để người dùng chỉ cần Ctrl+V – không phải bôi đen và nhấn Ctrl+C
    trong cửa sổ đen (Ctrl+C ở đó sẽ TẮT web)."""
    try:
        subprocess.run(["clip"], input=text.encode("ascii"), check=True, timeout=5)
        return True
    except Exception:
        return False


def mo_duong_ham(exe):
    """Cloudflare quick tunnel: tạo link https://....trycloudflare.com trỏ về web trên máy này."""
    proc = subprocess.Popen([exe, "tunnel", "--no-autoupdate", "--url", f"http://localhost:{CONG}"],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")

    def doc():
        da_in = False
        for dong in proc.stdout:
            m = re.search(r"https://[-a-z0-9]+\.trycloudflare\.com", dong)
            if m and not da_in:
                da_in = True
                FILE_LINK.write_text(m.group(0), encoding="utf-8")
                da_chep = chep_vao_clipboard(m.group(0))
                print("\n" + "=" * 70)
                print(f"  LINK CÔNG KHAI (gửi cho mọi người):  {m.group(0)}")
                if da_chep:
                    print("  -> Link đã được CHÉP SẴN: mở Zalo/Messenger/trình duyệt và nhấn Ctrl+V để dán.")
                print("  -> KHÔNG nhấn Ctrl+C trong cửa sổ này: Ctrl+C sẽ TẮT web và link chết ngay.")
                print("  -> Chờ khoảng 30 giây rồi mới mở link (Cloudflare cần thời gian kích hoạt).")
                print(f"  (Link cũng được lưu trong file {FILE_LINK.name}; link đổi mỗi lần chạy lại.)")
                print("=" * 70 + "\n", flush=True)
            elif "ERR" in dong and not da_in:
                print("  cloudflared:", dong.strip(), flush=True)

    threading.Thread(target=doc, daemon=True).start()
    return proc


def main():
    args = set(sys.argv[1:])
    import bao_mat
    if not bao_mat.da_dat_mat_khau():
        print("Lần đầu chia sẻ: đặt mật khẩu Quản trị (người dùng khác vào web KHÔNG cần mật khẩu).")
        import dat_mat_khau
        dat_mat_khau.main()

    if "--chi-xem" in args:
        os.environ["PUBLIC_READONLY"] = "1"
    if cong_dang_dung(CONG):
        print("\n" + "=" * 70)
        print(f"  KHÔNG CHIA SẺ ĐƯỢC: cổng {CONG} đang được một chương trình khác dùng.")
        print("  Thường là do cửa sổ chay_web.bat (hoặc một cửa sổ chia_se_web.bat khác) vẫn đang mở.")
        print("  Hãy đóng các cửa sổ đó rồi bấm đúp lại chia_se_web.bat.")
        print("=" * 70, flush=True)
        return

    import app as web
    from waitress import serve

    web.danh_dau_phien_bi_gian_doan()
    chi_may_nay = "--chi-may-nay" in args
    host = "127.0.0.1" if ("--chi-link" in args or chi_may_nay) else "0.0.0.0"
    print("\n" + "=" * 70)
    print(f"  Trên máy này:            http://localhost:{CONG}")
    if host == "0.0.0.0":
        print(f"  Cùng mạng Wi-Fi/LAN:     http://{ip_noi_bo()}:{CONG}")
        print("  (Lần đầu Windows hỏi quyền mạng: chọn cho phép mạng Riêng tư/Private.)")
    if os.environ.get("PUBLIC_READONLY") == "1":
        print("  Chế độ CHỈ XEM: người dùng chỉ xem lịch sử và kết quả (Quản trị vẫn làm được mọi thao tác).")
    print("=" * 70, flush=True)

    duong_ham = None
    if "--chi-noi-bo" not in args and not chi_may_nay:
        exe = tim_cloudflared()
        if exe:
            print("Đang mở link công khai qua Cloudflare Tunnel...", flush=True)
            duong_ham = mo_duong_ham(exe)
        else:
            print("Chưa cài cloudflared nên chưa có link công khai. Cài bằng lệnh (một lần):\n"
                  "    winget install --id Cloudflare.cloudflared\n"
                  "rồi tắt và bấm đúp lại chia_se_web.bat.", flush=True)
    print("Thu nhỏ cửa sổ này và để nguyên. Muốn ngừng chia sẻ thì đóng cửa sổ (nút X).\n", flush=True)
    try:
        serve(web.app, host=host, port=CONG, threads=8)
    except KeyboardInterrupt:
        print("\n" + "=" * 70)
        print("  ĐÃ TẮT CHIA SẺ (vừa nhấn Ctrl+C). Link vừa rồi không dùng được nữa.")
        print("  Bấm đúp lại chia_se_web.bat để có link mới.")
        print("=" * 70, flush=True)
    finally:
        if duong_ham:
            duong_ham.terminate()
        FILE_LINK.unlink(missing_ok=True)


if __name__ == "__main__":         # bắt buộc: tiến trình con chạy song song trên Windows nạp lại file này
    main()
