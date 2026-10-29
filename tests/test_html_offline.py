"""Bản HTML chạy trên trình duyệt (du_bao_ty_gia.html) phải khớp với mã nguồn trong offline/src."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_html_khop_ma_nguon(tmp_path):
    spec = importlib.util.spec_from_file_location("build_offline", ROOT / "offline" / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "x.html"
    mod.build(out)
    assert out.read_text(encoding="utf-8") == (ROOT / "du_bao_ty_gia.html").read_text(encoding="utf-8"), \
        "Chạy lại: python offline/build.py"
