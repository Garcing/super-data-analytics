"""数据加载与缓存 helper。

- cached：装饰器，等价于 @st.cache_data，给报告一个统一入口。
- load_df：按扩展名读 CSV/Parquet/Excel，相对路径基于 reports/data/。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

# reports/data/ 的绝对根（lib/ 的上一级再下到 reports/data）
_DATA_ROOT = Path(__file__).resolve().parent.parent / "reports" / "data"


def cached(func):
    """装饰器：等价于 ``@st.cache_data``，供报告统一使用。

    用法::

        @cached
        def load_region_df():
            return pd.read_csv(...)
    """
    return st.cache_data(func)


def load_df(path: str) -> pd.DataFrame:
    """读取 CSV / Parquet / Excel。

    相对路径基于 ``reports/data/``，也接受绝对路径。
    """
    p = Path(path)
    if not p.is_absolute():
        p = _DATA_ROOT / path
    if not p.exists():
        raise FileNotFoundError(f"找不到数据文件: {p}")
    ext = p.suffix.lower()
    if ext == ".csv":
        return pd.read_csv(p)
    if ext in (".parquet", ".pq"):
        return pd.read_parquet(p)
    if ext in (".xlsx", ".xls"):
        return pd.read_excel(p)
    raise ValueError(f"不支持的文件类型: {ext}（仅支持 csv/parquet/xlsx）")
