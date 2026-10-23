"""Tạo file dữ liệu MẪU data/tygia_mau.csv để chạy thử web.

LƯU Ý: đây là dữ liệu GIẢ LẬP (xu hướng + nhiễu ngẫu nhiên), chỉ mô phỏng hình dạng
chuỗi tỷ giá USD/VND. KHÔNG dùng số liệu này trong báo cáo đề tài - hãy thay bằng dữ liệu thật.

Chạy:  python tao_du_lieu_mau.py
"""
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(2026)   # cố định hạt giống -> lần nào chạy cũng ra cùng một file

# Chỉ lấy ngày làm việc (thứ 2 - thứ 6), khoảng 3 năm
ngay = pd.bdate_range("2023-09-25", "2026-09-23")

# Các mốc xu hướng (giả lập) rồi nội suy tuyến tính giữa các mốc
moc = pd.Series({
    "2023-09-25": 24250, "2024-01-15": 24450, "2024-04-22": 25450, "2024-07-01": 25470,
    "2024-10-01": 24700, "2024-12-31": 25450, "2025-04-15": 25950, "2025-08-15": 26250,
    "2026-01-15": 26300, "2026-05-15": 26380, "2026-09-23": 26450,
})
moc.index = pd.to_datetime(moc.index)
xu_huong = moc.reindex(moc.index.union(ngay)).interpolate("time").reindex(ngay).to_numpy()

# Nhiễu AR(1): dao động hôm nay phụ thuộc một phần vào hôm qua (giống chuỗi tài chính thật)
nhieu = np.zeros(len(ngay))
for t in range(1, len(ngay)):
    nhieu[t] = 0.9 * nhieu[t - 1] + rng.normal(0, 14)

ty_gia = np.round(xu_huong + nhieu).astype(int)

df = pd.DataFrame({"Ngay": ngay.strftime("%d/%m/%Y"), "TyGia": ty_gia})
duong_dan = Path(__file__).parent / "data" / "tygia_mau.csv"
duong_dan.parent.mkdir(exist_ok=True)
df.to_csv(duong_dan, index=False, encoding="utf-8-sig")
print(f"Đã tạo {duong_dan} với {len(df)} dòng ({df['Ngay'].iloc[0]} -> {df['Ngay'].iloc[-1]}).")
