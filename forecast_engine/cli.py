"""Chạy pipeline không cần web.

    python -m forecast_engine.cli --data data/tygia_mau.csv --mode chay_thu
    python -m forecast_engine.cli --data data/tygia_mau.csv --mode chay_thu --models XGB --variants SA
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .data_io import parse_table, read_table
from .pipeline import estimate, run_pipeline
from .run_config import MODELS, VARIANTS, build_run_config


def main(argv=None):
    ap = argparse.ArgumentParser(description="Dự báo tỷ giá T+1 theo quy trình bài NCKH")
    ap.add_argument("--data", required=True)
    ap.add_argument("--mode", default="chay_thu", choices=["chay_thu", "chay_day_du"])
    ap.add_argument("--models", nargs="+", default=MODELS, choices=MODELS)
    ap.add_argument("--variants", nargs="+", default=VARIANTS, choices=VARIANTS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)

    cfg = build_run_config(args.mode, args.models, args.variants)
    raw, info = parse_table(read_table(args.data))
    est = estimate(raw, cfg)
    print(f"Ước tính thời gian: ~{est['total_seconds'] / 60:.1f} phút ({est['cores']} lõi)")
    out = Path(args.out or Path("artifacts") / f"cli_{datetime.now():%Y%m%d_%H%M%S}")
    last = {"pct": -1}

    def on_progress(snap):
        pct = int(snap["percent"])
        if pct != last["pct"]:
            last["pct"] = pct
            cur = next((s for s in snap["steps"] if s["status"] == "dang_chay"), None)
            print(f"[{pct:3d}%] {cur['name'] + ': ' + cur['detail'] if cur else ''}"[:160], flush=True)

    res = run_pipeline(raw, cfg, on_progress, output_dir=out, meta={"filename": Path(args.data).name, **info}, estimate=est)
    print(json.dumps(res["table_4_6"], ensure_ascii=False, indent=2))
    print(f"Xong sau {res['elapsed_seconds']} s. Kết quả: {out.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
