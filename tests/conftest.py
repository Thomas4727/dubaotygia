import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def sample_df():
    from forecast_engine.data_io import parse_table, read_table
    df, _ = parse_table(read_table(ROOT / "data" / "tygia_mau.csv"))
    return df


@pytest.fixture
def series():
    """Chuỗi giả lập nhỏ: 300 ngày làm việc, bước ngẫu nhiên quanh 25.000."""
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2024-01-01", periods=300)
    return pd.DataFrame({"date": dates, "rate": np.round(25_000 + np.cumsum(rng.normal(1, 10, len(dates))))})
