import logging
import sys
from pathlib import Path

from ipcei_spillovers.config_paths import PATHS


def setup_logging(
    name: str = "ipcei",
    level: int = logging.INFO,
    log_to_file: bool = True,
    filename: str = "run.log",
) -> logging.Logger:
    """
    Set up a logger that logs to console and (optionally) to a file.
    Safe to call multiple times.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    # If already configured, return it
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    if log_to_file:
        log_dir: Path = PATHS.results / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_dir / filename)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
