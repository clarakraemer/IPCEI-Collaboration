from __future__ import annotations

from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt

from ipcei_spillovers.config_paths import PATHS
from ipcei_spillovers.io import results_path
from ipcei_spillovers.config_logging import setup_logging

log = setup_logging(filename="plotting.log")
