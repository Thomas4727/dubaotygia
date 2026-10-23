"""Tái lập quy trình dự báo tỷ giá VND/USD T+1 của bài NCKH (đặc tả v3).

Điểm vào: forecast_engine.pipeline.run_pipeline(df, run_config, on_progress)
          run_config = {"mode": "chay_thu" | "chay_day_du", "models": [...], "variants": [...]}
"""
from .run_config import build_run_config

__all__ = ["build_run_config", "run_pipeline", "estimate"]


def run_pipeline(*args, **kwargs):
    from .pipeline import run_pipeline as _run
    return _run(*args, **kwargs)


def estimate(*args, **kwargs):
    from .pipeline import estimate as _est
    return _est(*args, **kwargs)
