"""Không gian tìm kiếm, mã hóa / giải mã / sửa lỗi (đặc tả v3 mục 7.1) và cấu hình baseline (mục 6.6).

Mỗi siêu tham số là 1 gene u ∈ [0, 1]:
  - số nguyên / thực: ánh xạ tuyến tính, hoặc theo log với biến "log"
  - phân loại / boolean: u chọn chỉ số trong danh sách
  - miền dạng {giá trị đặc biệt} ∪ [a, b] (vd max_depth ∈ {None} ∪ [3, 30]): mỗi giá trị đặc biệt
    chiếm một đoạn rộng 0,1 ở đầu [0, 1], phần còn lại là khoảng số   [TỰ QUYẾT – cách mã hóa]
"""
import hashlib
import json
import math

import numpy as np

SPECIAL_WIDTH = 0.1


class Param:
    def __init__(self, name, kind, low=None, high=None, log=False, choices=None, specials=()):
        self.name, self.kind, self.low, self.high, self.log = name, kind, low, high, log
        self.choices = list(choices) if choices is not None else None
        self.specials = list(specials)

    @property
    def categorical(self):
        return self.kind == "cat"

    def _num_decode(self, u):
        if self.log:
            v = math.exp(math.log(self.low) + u * (math.log(self.high) - math.log(self.low)))
        else:
            v = self.low + u * (self.high - self.low)
        v = min(max(v, self.low), self.high)
        return int(round(v)) if self.kind == "int" else float(f"{v:.6g}")

    def _num_encode(self, v):
        v = min(max(v, self.low), self.high)          # giá trị ngoài miền (vd reg_alpha = 0) bị cắt về biên
        if self.log:
            return (math.log(v) - math.log(self.low)) / (math.log(self.high) - math.log(self.low))
        return (v - self.low) / (self.high - self.low)

    def decode(self, u):
        u = min(max(float(u), 0.0), 1.0)
        if self.categorical:
            return self.choices[min(int(u * len(self.choices)), len(self.choices) - 1)]
        region = len(self.specials) * SPECIAL_WIDTH
        if u < region:
            return self.specials[int(u / SPECIAL_WIDTH)]
        return self._num_decode((u - region) / (1 - region) if region else u)

    def encode(self, value):
        if self.categorical:
            return (self.choices.index(value) + 0.5) / len(self.choices)
        if any(value is s or (value == s and type(value) is type(s)) for s in self.specials):
            return (self.specials.index(value) + 0.5) * SPECIAL_WIDTH
        region = len(self.specials) * SPECIAL_WIDTH
        return region + (1 - region) * self._num_encode(value)


def space(model, caps):
    """Không gian của một mô hình. Tên siêu tham số theo Bảng 3.1 (ANN), 3.2 (RF), 3.3 (XGBoost) và mục 3.3.3;
    p và w là siêu tham số của toàn chu trình. Miền giá trị: [WEB] – bài không nêu miền.
    ANN: hàm kích hoạt CỐ ĐỊNH là ReLU ("Nghiên cứu này dùng hàm ReLU", mục 3.3.3.1), không đưa vào không gian tìm
    kiếm; KHÔNG có w vì Bảng 3.1 và công thức 3.9 chỉ có số độ trễ p.
    RF, XGBoost: p và độ dài cửa sổ trượt w là siêu tham số của toàn chu trình (mục 3.3.3.2, 3.3.3.3).
    GA và SA dùng CHÍNH hàm này -> cùng không gian tìm kiếm (mục 3.3.5)."""
    common = [Param("p", "int", 3, 30), Param("w", "int", 5, 30)]
    if model == "ANN":
        return common[:1] + [
            Param("n_layers", "int", 1, 3),
            Param("units", "int", 8, 128, log=True),
            Param("learning_rate", "float", 1e-4, 1e-2, log=True),
            Param("epochs", "int", 50, caps["ANN_epochs"]),
            Param("batch_size", "cat", choices=[16, 32, 64, 128]),
            Param("dropout", "float", 0.0, 0.5),
        ]
    if model == "RF":
        return common + [
            Param("n_estimators", "int", 100, caps["RF_n_estimators"]),
            Param("max_depth", "int", 3, 30, specials=[None]),
            Param("max_features", "float", 0.3, 1.0, specials=["sqrt", "log2"]),
            Param("min_samples_split", "int", 2, 20),
            Param("min_samples_leaf", "int", 1, 20),
            Param("max_leaf_nodes", "int", 16, 512, specials=[None]),
            Param("bootstrap", "cat", choices=[True, False]),
            Param("max_samples", "float", 0.5, 1.0),
        ]
    if model == "XGB":
        return common + [
            Param("n_estimators", "int", 100, caps["XGB_n_estimators"]),
            Param("learning_rate", "float", 0.005, 0.3, log=True),
            Param("max_depth", "int", 2, 10),
            Param("min_child_weight", "float", 1, 20),
            Param("gamma", "float", 0, 5),
            Param("subsample", "float", 0.5, 1.0),
            Param("colsample_bytree", "float", 0.5, 1.0),
            Param("max_leaves", "int", 8, 256, specials=[0]),
            Param("reg_alpha", "float", 1e-4, 10, log=True),
            Param("reg_lambda", "float", 1e-2, 10, log=True),
            Param("objective", "cat", choices=["reg:squarederror", "reg:pseudohubererror"]),
        ]
    raise ValueError(model)


# Cấu hình định sẵn [CHỐT] (mục 6.6). Tham số không nêu = mặc định của thư viện.
BASELINES = {
    "ANN": dict(p=10, n_layers=1, units=64, learning_rate=1e-3, epochs=200, batch_size=32, dropout=0.1),
    "RF": dict(p=10, w=10, n_estimators=500, max_depth=None, max_features=1.0, min_samples_split=2,
               min_samples_leaf=1, max_leaf_nodes=None, bootstrap=True, max_samples=None),
    "XGB": dict(p=10, w=10, n_estimators=500, learning_rate=0.05, max_depth=4, subsample=0.8,
                colsample_bytree=0.8, min_child_weight=1.0, gamma=0.0, max_leaves=0, reg_alpha=0.0,
                reg_lambda=1.0, objective="reg:squarederror"),
}


def repair(model, params):
    """Sửa lỗi ràng buộc sau giải mã (Bảng 3.5 bước 4, Bảng 3.7 bước 6): bootstrap=False thì bỏ max_samples.
    XGBoost: KHÔNG có grow_policy (Bảng 3.3 không có) – dùng mặc định cố định của thư viện."""
    params = dict(params)
    if model == "RF" and not params.get("bootstrap", True):
        params["max_samples"] = None
    return params


def baseline(model):
    return repair(model, BASELINES[model])


def decode(model, vector, caps):
    return repair(model, {p.name: p.decode(u) for p, u in zip(space(model, caps), vector)})


def encode(model, params, caps):
    """Mã hóa một cấu hình thành vector gene (dùng để đưa baseline vào GA/SA)."""
    vec = []
    for p in space(model, caps):
        v = params.get(p.name)
        if v is None and p.name == "max_samples":
            v = 1.0                                 # max_samples=None của sklearn ≡ 1.0
        vec.append(p.encode(v))
    return np.array(vec)


def dim(model, caps):
    return len(space(model, caps))


def categorical_mask(model, caps):
    return np.array([p.categorical for p in space(model, caps)])


def params_key(params):
    return hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()


def describe_param(p):
    """Miền giá trị dạng chữ để hiển thị (vd "{None} ∪ [3, 30]", "[1e-4, 1e-2] (log)")."""
    if p.categorical:
        return "{" + ", ".join(str(c) for c in p.choices) + "}"
    rng = f"[{p.low:g}, {p.high:g}]" + (" (log)" if p.log else "")
    return ("{" + ", ".join(str(s) for s in p.specials) + "} ∪ " if p.specials else "") + rng


def space_table(caps_thu, caps_du):
    """[(mô hình, siêu tham số, miền Chạy thử, miền Chạy đầy đủ, baseline)] – miền và baseline là lựa chọn của web."""
    rows = []
    for m in ("ANN", "RF", "XGB"):
        for a, b in zip(space(m, caps_thu), space(m, caps_du)):
            rows.append((m, a.name, describe_param(a), describe_param(b), BASELINES[m].get(a.name)))
    return rows
