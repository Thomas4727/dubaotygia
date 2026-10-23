"""Tạo database DuBaoTyGia và các bảng từ file sql/tao_database.sql.

Chạy:  python khoi_tao_db.py
"""
import re
from pathlib import Path

import db

FILE_SQL = Path(__file__).parent / "sql" / "tao_database.sql"


def main():
    noi_dung = FILE_SQL.read_text(encoding="utf-8")
    # Tách các khối lệnh theo dòng "GO" (giống cách VS Code / SSMS chạy)
    cac_khoi = [k.strip() for k in re.split(r"^\s*GO\s*$", noi_dung, flags=re.MULTILINE | re.IGNORECASE)]

    # Kết nối vào master vì database có thể chưa tồn tại; autocommit bắt buộc cho CREATE DATABASE
    with db.ket_noi(database="master", autocommit=True) as conn:
        cur = conn.cursor()
        for khoi in cac_khoi:
            if khoi and not all(d.strip().startswith("--") or not d.strip() for d in khoi.splitlines()):
                cur.execute(khoi)
    print(f"Đã sẵn sàng database '{db.config.DATABASE}' trên {db.config.SQL_SERVER}.")


if __name__ == "__main__":
    main()
