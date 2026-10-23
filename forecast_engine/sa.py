"""Simulated Annealing (bài: mục 3.3.4.2, Bảng 3.6–3.7, Hình 3.2; đặc tả v3 mục 7.3)."""
import math

import numpy as np

from .budget import BudgetExhausted


def _neighbor(x, categorical, rng, sigma):
    """Bước 5: đổi ngẫu nhiên 1–2 gene. Số: + N(0, σ) trong [0,1] (số nguyên được làm tròn khi giải mã);
    phân loại / boolean: lấy mẫu lại."""
    y = x.copy()
    for g in rng.choice(len(x), size=min(len(x), int(rng.integers(1, 3))), replace=False):
        y[g] = rng.random() if categorical[g] else np.clip(y[g] + rng.normal(0, sigma), 0, 1)
    return y


def run_sa(evaluator, dim, categorical, rng, init_vector, t0_samples, accept0, cooling, moves_per_temp,
           sigma, t_min_ratio, patience, on_step=None):
    """Trả về dict: best_vector, best_j, n_evals, T0, T_final, stop_reason."""
    categorical = np.asarray(categorical, dtype=bool)
    current = np.clip(np.asarray(init_vector, dtype=float), 0, 1)       # bước 3: S_current = baseline
    T0 = T = None
    stop_reason = "hết ngân sách đánh giá"
    try:
        j_current = evaluator(current)                                   # J_current = J_best

        # Bước 4: hiệu chỉnh T0 từ các nghiệm lân cận thử (tính vào ngân sách)
        deltas = []
        for _ in range(t0_samples):
            j = evaluator(_neighbor(current, categorical, rng, sigma))
            if j > j_current:
                deltas.append(j - j_current)
        mean_up = float(np.mean(deltas)) if deltas else max(abs(j_current) * 1e-3, 1e-9)   # [TỰ QUYẾT] khi không có ΔJ>0
        T0 = T = -mean_up / math.log(accept0)
        if on_step:
            on_step(evaluator.n_evals, T, evaluator.best_j)

        since_improve = 0
        while True:
            for _ in range(moves_per_temp):                              # cân bằng: L nghiệm ở mỗi mức nhiệt
                if T < t_min_ratio * T0:
                    raise StopIteration("nhiệt độ dưới ngưỡng T_min")
                if since_improve >= patience:
                    raise StopIteration(f"{patience} lần đánh giá liên tiếp không cải thiện")
                candidate = _neighbor(current, categorical, rng, sigma)  # bước 5–6 (repair khi giải mã)
                best_before = evaluator.best_j
                j = evaluator(candidate)                                 # bước 7
                delta = j - j_current                                    # bước 8
                if delta <= 0 or rng.random() < math.exp(-delta / T):   # bước 9: Metropolis
                    current, j_current = candidate, j
                since_improve = 0 if evaluator.best_j < best_before else since_improve + 1   # bước 10
                if on_step:
                    on_step(evaluator.n_evals, T, evaluator.best_j)
            T *= cooling                                                 # làm nguội hình học
    except StopIteration as e:
        stop_reason = str(e)
    except BudgetExhausted:
        pass
    return {"best_vector": evaluator.best_vector, "best_j": evaluator.best_j, "n_evals": evaluator.n_evals,
            "T0": T0, "T_final": T, "stop_reason": stop_reason}
