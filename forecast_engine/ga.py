"""Genetic Algorithm (bài: mục 3.3.4.1, Bảng 3.4–3.5, Hình 3.1; đặc tả v3 mục 7.2).

Bước 1→12 của Bảng 3.5: chia dữ liệu (pipeline) → mã hóa (search_space) → khởi tạo P₀ → giải mã/sửa lỗi →
fitness = RMSE CV (evaluator) → chọn lọc tournament → lai ghép → đột biến → elitism → kiểm tra dừng →
test (pipeline, tầng 3) → lặp nhiều seed (pipeline).
"""
import numpy as np

from .budget import BudgetExhausted


def run_ga(evaluator, dim, categorical, rng, init_vector, pop_size, max_generations, tournament_k,
           p_crossover, p_mutation, sigma, elitism, patience, on_generation=None):
    """Trả về dict: best_vector, best_j, n_evals, generations, stop_reason.

    Thế hệ 0 là P₀; tối đa `max_generations` thế hệ mới sau đó.
    Dừng: đủ số thế hệ, hết ngân sách, hoặc `patience` thế hệ liên tiếp không cải thiện J tốt nhất.
    """
    categorical = np.asarray(categorical, dtype=bool)
    # P₀: ngẫu nhiên đều trong [0,1]^d, cá thể đầu tiên = cấu hình baseline
    pop = [np.clip(np.asarray(init_vector, dtype=float), 0, 1)] + [rng.random(dim) for _ in range(pop_size - 1)]

    def tournament(fitness):
        idx = rng.choice(len(fitness), size=min(tournament_k, len(fitness)), replace=False)
        return idx[np.argmin(np.asarray(fitness)[idx])]

    def mutate(child):
        child = child.copy()
        for g in range(dim):
            if rng.random() < p_mutation:
                child[g] = rng.random() if categorical[g] else np.clip(child[g] + rng.normal(0, sigma), 0, 1)
        return child

    generation, stall, stop_reason, fitness = 0, 0, f"đủ {max_generations} thế hệ", []
    try:
        for ind in pop:
            fitness.append(evaluator(ind))
        best = min(fitness)
        if on_generation:
            on_generation(0, best, evaluator.n_evals)
        while generation < max_generations:
            generation += 1
            order = np.argsort(fitness)
            new_pop = [pop[i] for i in order[:elitism]]                 # elitism
            new_fit = [fitness[i] for i in order[:elitism]]
            while len(new_pop) < pop_size:
                a, b = pop[tournament(fitness)], pop[tournament(fitness)]
                child = np.where(rng.random(dim) < 0.5, a, b) if rng.random() < p_crossover else a.copy()
                child = mutate(child)
                new_fit.append(evaluator(child))                       # giải mã + sửa lỗi nằm trong evaluator
                new_pop.append(child)
            pop, fitness = new_pop, new_fit
            if min(fitness) < best:
                best, stall = min(fitness), 0
            else:
                stall += 1
            if on_generation:
                on_generation(generation, best, evaluator.n_evals)
            if stall >= patience:
                stop_reason = f"{patience} thế hệ liên tiếp không cải thiện"
                break
    except BudgetExhausted:
        stop_reason = "hết ngân sách đánh giá"
    return {"best_vector": evaluator.best_vector, "best_j": evaluator.best_j, "n_evals": evaluator.n_evals,
            "generations": generation, "stop_reason": stop_reason}
