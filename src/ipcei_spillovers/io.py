from __future__ import annotations
from pathlib import Path
from typing import Literal
import pandas as pd
from ipcei_spillovers.config_paths import PATHS

# ---------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------
Stage = Literal["raw", "intermediate", "processed"]
ResultsKind = Literal["figures", "tables"]

__all__ = ["data_path", "results_path", "load_df", "save_df"]

# ---------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------
def data_path(stage: Stage, *parts: str) -> Path:
    """
    Build a path under src/data/<stage>/...

    Example:
        data_path("raw", "linkedin", "profiles.csv")
    """
    return PATHS.data_path(stage, *parts)


def results_path(kind: ResultsKind, *parts: str) -> Path:
    """
    Build a path under results/<kind>/...

    Example:
        results_path("figures", "plot1.png")
    """
    return PATHS.results_path(kind, *parts)


# ---------------------------------------------------------------------
# DataFrame I/O helpers
# ---------------------------------------------------------------------
def load_df(stage: Stage, *parts: str, **read_kwargs) -> pd.DataFrame:
    """
    Load a pandas DataFrame based on file extension.
    Supported: .csv, .parquet, .pkl/.pickle, .xlsx
    """
    path = data_path(stage, *parts)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path, **read_kwargs)
    elif suffix == ".parquet":
        return pd.read_parquet(path, **read_kwargs)
    elif suffix in {".pkl", ".pickle"}:
        return pd.read_pickle(path, **read_kwargs)
    elif suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path, **read_kwargs)
    else:
        raise ValueError(f"Unsupported file extension: {suffix}")


def save_df(
    df: pd.DataFrame,
    stage: Stage,
    *parts: str,
    index: bool = False,
    **write_kwargs,
) -> Path:
    """
    Save a pandas DataFrame based on file extension.
    Supported: .csv, .parquet, .pkl/.pickle, .xlsx
    """
    path = data_path(stage, *parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df.to_csv(path, index=index, **write_kwargs)
    elif suffix == ".parquet":
        df.to_parquet(path, index=index, **write_kwargs)
    elif suffix in {".pkl", ".pickle"}:
        df.to_pickle(path, **write_kwargs)
    elif suffix in {".xlsx", ".xls"}:
        df.to_excel(path, index=index, **write_kwargs)
    else:
        raise ValueError(f"Unsupported file extension: {suffix}")

    return path
