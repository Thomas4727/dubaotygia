"""Bộ đếm ngân sách + cache dùng chung cho GA và SA (mục 6)."""
import numpy as np


class BudgetExhausted(Exception):
    pass


class Evaluator:
    """Bọc hàm mục tiêu J(vector).

    - Mỗi lần gọi tính 1 vào ngân sách, kể cả khi lấy từ cache.
    - Cache theo khóa của cấu hình ĐÃ GIẢI MÃ (key_fn), nên hai vector khác nhau nhưng
      giải mã ra cùng cấu hình sẽ không huấn luyện lại.
    """

    def __init__(self, objective, budget, key_fn=None):
        self.objective, self.budget = objective, budget
        self.key_fn = key_fn or (lambda v: tuple(np.round(v, 12)))
        self.cache = {}
        self.n_evals = 0
        self.n_trained = 0
        self.best_j = np.inf
        self.best_vector = None
        self.history = []            # J tốt nhất sau mỗi lần đánh giá

    @property
    def remaining(self):
        return self.budget - self.n_evals

    def __call__(self, vector):
        if self.n_evals >= self.budget:
            raise BudgetExhausted
        self.n_evals += 1
        key = self.key_fn(vector)
        if key not in self.cache:
            self.cache[key] = float(self.objective(vector))
            self.n_trained += 1
        j = self.cache[key]
        if j < self.best_j:
            self.best_j, self.best_vector = j, np.array(vector, dtype=float)
        self.history.append(self.best_j)
        return j
