"""Ghép offline/src/* thành MỘT file HTML tự chạy: du_bao_ty_gia.html (ở thư mục gốc của repo).

Chạy:  python offline/build.py
Sửa code trong offline/src/ rồi chạy lại lệnh này; không sửa trực tiếp file du_bao_ty_gia.html.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "offline" / "src"
OUT = ROOT / "du_bao_ty_gia.html"
ENGINE_PARTS = ["engine_core.js", "engine_arima.js", "engine_models.js", "engine_search.js", "engine_pipeline.js"]


def read(p):
    return Path(p).read_text(encoding="utf-8")


def build(out=OUT):
    engine = "\n".join(read(SRC / f) for f in ENGINE_PARTS)
    if "</script" in engine.lower():
        raise SystemExit("Mã engine không được chứa chuỗi </script")
    icons = re.sub(r"\{#.*?#\}\s*", "", read(ROOT / "templates" / "_icons.html"), flags=re.S)
    style = read(ROOT / "static" / "style.css") + "\n" + read(SRC / "extra.css")
    page = read(SRC / "page.html")
    for key, val in (("/*STYLE*/", style), ("<!--ICONS-->", icons), ("/*ENGINE*/", engine),
                     ("/*WORKER*/", read(SRC / "worker.js")), ("/*APP*/", read(SRC / "app.js"))):
        if key not in page:
            raise SystemExit(f"Thiếu chỗ đặt {key} trong page.html")
        page = page.replace(key, val)
    out = Path(out)
    out.write_text(page, encoding="utf-8")
    print(f"Đã tạo {out.name} ({out.stat().st_size / 1024:.0f} KB)")


def build_link(out):
    """Bản đăng lên link (trang Claude): bỏ khung <html>/<head>/<body> vì trang được bọc sẵn, bật cờ __ARTIFACT__
    để ẩn các nút tải file / in mà khung nhúng chặn."""
    tmp = Path(out).with_suffix(".full.html")
    build(tmp)
    page = tmp.read_text(encoding="utf-8")
    tmp.unlink()
    head = page[page.index("<head>") + 6:page.index("</head>")]
    body = page[page.index("<body>") + 6:page.index("</body>")]
    head = re.sub(r'<meta charset[^>]*>\s*<meta name="viewport"[^>]*>', "", head)
    page = head + "\n<script>window.__ARTIFACT__ = true;</script>\n" + body
    Path(out).write_text(page, encoding="utf-8")
    print(f"Đã tạo bản link {Path(out).name}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--link":
        build_link(sys.argv[2])
    else:
        build()
