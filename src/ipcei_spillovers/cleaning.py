from __future__ import annotations

from typing import Any
import pandas as pd

from ipcei_spillovers.config_paths import PATHS
from ipcei_spillovers.io import data_path, load_df, save_df
from ipcei_spillovers.config_logging import setup_logging

log = setup_logging(filename="cleaning.log")
