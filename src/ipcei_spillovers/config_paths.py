from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path


def find_project_root(start: Path | None = None, marker: str = "ipcei-spillovers") -> Path:
    """
    Find the project root.
      1) Walk upwards from this file until a folder name matches `marker`
      2) Fallback: current file's parent chain
    """
    if start is None:
        start = Path(__file__).resolve()

    for p in [start, *start.parents]:
        if p.is_dir() and p.name == marker:
            return p

    # Fallback: assume config.py lives under <root>/src/
    return Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Paths:
    root: Path
    src: Path
    data: Path
    data_raw: Path
    data_intermediate: Path
    data_processed: Path
    results: Path
    results_figures: Path
    results_tables: Path

    def ensure_dirs(self) -> None:
        """Create expected directories if they don't exist."""
        for d in [
            self.data_raw, self.data_intermediate, self.data_processed,
            self.results_figures, self.results_tables,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def data_path(self, stage: str, *parts: str) -> Path:
        """
        stage in {"raw","intermediate","processed"}; returns a full path under that stage.
        Example: PATHS.data_path("raw", "linkedin", "profiles.csv")
        """
        stage = stage.lower()
        base = {
            "raw": self.data_raw,
            "intermediate": self.data_intermediate,
            "processed": self.data_processed,
        }.get(stage)
        if base is None:
            raise ValueError(f"Unknown stage '{stage}'. Use raw/intermediate/processed.")
        return base.joinpath(*parts)

    def results_path(self, kind: str, *parts: str) -> Path:
        """
        kind in {"figures","tables"}.
        Example: PATHS.results_path("figures", "plot1.png")
        """
        kind = kind.lower()
        base = {"figures": self.results_figures, "tables": self.results_tables}.get(kind)
        if base is None:
            raise ValueError(f"Unknown results kind '{kind}'. Use figures/tables.")
        return base.joinpath(*parts)


# Instantiate project structure
PROJECT_ROOT = find_project_root(marker="ipcei-spillovers")

PATHS = Paths(
    root=PROJECT_ROOT,
    src=PROJECT_ROOT / "src",
    data=PROJECT_ROOT / "src" / "data",
    data_raw=PROJECT_ROOT / "src" / "data" / "raw",
    data_intermediate=PROJECT_ROOT / "src" / "data" / "intermediate",
    data_processed=PROJECT_ROOT / "src" / "data" / "processed",
    results=PROJECT_ROOT / "results",
    results_figures=PROJECT_ROOT / "results" / "figures",
    results_tables=PROJECT_ROOT / "results" / "tables",
)

# Create dirs at import time (optional; you can remove this if you dislike side-effects)
PATHS.ensure_dirs()
