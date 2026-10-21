
# ============================================================
# Plotting & descriptive helpers for IPCEI analysis
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import pycountry


# ============================================================
# Basic coercion utilities
# ============================================================

def norm_str(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip()

def to_dt(s):
    return pd.to_datetime(s, errors="coerce")

def to_month(s):
    return to_dt(s).dt.to_period("M").dt.to_timestamp()


# ============================================================
# Country helpers
# ============================================================

def parse_iso2_list(x) -> set:
    """'DE, FR' → {'DE','FR'}"""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return set()
    return {p.strip().upper() for p in str(x).split(",") if p.strip()}

def iso2_to_iso3(code2: str):
    if code2 is None or pd.isna(code2):
        return None
    code2 = str(code2).strip().upper()
    if len(code2) != 2:
        return None
    c = pycountry.countries.get(alpha_2=code2)
    return c.alpha_3 if c else None

def iso3_to_name(code3: str):
    if code3 is None or pd.isna(code3):
        return None
    code3 = str(code3).strip().upper()
    c = pycountry.countries.get(alpha_3=code3)
    return c.name if c else code3

def cross_border(a: set, b: set):
    """
    If either side has empty set -> NaN (unknown).
    Else cross-border=0 if overlap, 1 if disjoint.
    """
    if not a or not b:
        return np.nan
    return 0 if len(a.intersection(b)) > 0 else 1

def monthly_rate(df, mask, label):
    d = df.loc[mask].dropna(subset=["cross_border"]).copy()
    out = (
        d.groupby("month")["cross_border"]
         .mean()
         .reset_index(name="rate")
    )
    out["series"] = label
    return out


def monthly_rate_column(df, col_name, label):
    """
    Calculate monthly rate for a binary column (0/1 values).

    Args:
        df: DataFrame with 'month' column
        col_name: Name of binary column to average
        label: Label for the series
    """
    d = df[[col_name, "month"]].dropna().copy()
    out = (
        d.groupby("month")[col_name]
        .mean()
        .reset_index(name="rate")
    )
    out["series"] = label
    return out


# EU member states (ISO 2-letter codes)
EU_COUNTRIES = {
    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
    'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
    'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
}

def classify_collaboration(source_set, target_set):
    """
    Classify collaboration type for cross-border analysis.

    Returns:
        'eu_internal': Both firms exclusively in EU, cross-border (no shared countries)
        'non_eu': At least one firm has non-EU presence, cross-border
        None: Not cross-border or insufficient data
    """
    if not source_set or not target_set:
        return None

    # Check if cross-border at all (using existing cross_border logic)
    if len(source_set & target_set) > 0:
        return None  # Not cross-border (shared country)

    # Get EU and non-EU components
    source_eu = source_set & EU_COUNTRIES
    target_eu = target_set & EU_COUNTRIES
    source_non_eu = source_set - EU_COUNTRIES
    target_non_eu = target_set - EU_COUNTRIES

    # Both firms are ONLY in EU countries
    if source_eu and target_eu and not source_non_eu and not target_non_eu:
        return 'eu_internal'

    # At least one firm has non-EU presence
    if source_non_eu or target_non_eu:
        return 'non_eu'

    return None

# ============================================================
# Descriptive aggregation helpers
# ============================================================

def cap_at_quantile(series: pd.Series, q: float = 0.98):
    s = series.dropna()
    if s.empty:
        return None
    return float(s.quantile(q))


def decade_shares(
    df,
    year_col="foundingYear",
    id_col="Linkedin_name",
    start=1900,
    end=2031,
    step=10,
):
    """
    Returns % shares by decade + 'Missing'
    """
    d = df[[id_col, year_col]].drop_duplicates(id_col).copy()
    d[year_col] = pd.to_numeric(d[year_col], errors="coerce")

    bins = list(range(start, end, step))
    labels = [f"{b}s" for b in bins[:-1]]

    d["decade"] = pd.cut(
        d[year_col],
        bins=bins,
        labels=labels,
        right=False,
        include_lowest=True,
    )

    d["decade"] = d["decade"].cat.add_categories(["Missing"]).fillna("Missing")

    share = d["decade"].value_counts(normalize=True).mul(100)

    order = labels + ["Missing"]
    return share.reindex([x for x in order if x in share.index])


def pct_dist(df: pd.DataFrame, mask: pd.Series, cap_value: int):
    """
    Percent distribution for capped count variables (0..cap_value)
    """
    sub = df.loc[mask, "n_collabs_capped"]
    idx = list(range(0, cap_value + 1))
    if sub.empty:
        return pd.Series(0.0, index=idx)
    counts = sub.value_counts().reindex(idx, fill_value=0)
    return 100 * counts / counts.sum()

def normalize_within_event(
    df: pd.DataFrame,
    *,
    event_id_col: str = "event_id",
    time_col: str = "event_time",
    value_col: str = "n_collabs",
    pre_window: tuple[int, int] = (-24, -1),
    out_col: str = "n_collabs_norm",
    drop_no_baseline: bool = True,
) -> pd.DataFrame:
    """
    Normalize an event-time panel within each event_id:
      out_col = value_col / mean(value_col in pre_window)

    - If baseline is NaN or 0 -> out_col becomes NaN (and can be dropped).
    - Returns a COPY with the new column added.

    Expected structure:
      one row per (event_id, event_time, ...) with `value_col` already computed.
    """
    d = df.copy()

    # compute baseline per event
    pre_mask = d[time_col].between(pre_window[0], pre_window[1])
    baseline = (
        d.loc[pre_mask]
         .groupby(event_id_col)[value_col]
         .mean()
         .rename("baseline")
    )

    d = d.merge(baseline, left_on=event_id_col, right_index=True, how="left")

    # normalize
    d[out_col] = np.where(
        d["baseline"].isna() | (d["baseline"] == 0),
        np.nan,
        d[value_col] / d["baseline"],
    )

    if drop_no_baseline:
        d = d.dropna(subset=[out_col])

    return d.drop(columns=["baseline"])


# ============================================================
# Sector bucketing
# ============================================================

def sector_bucket(s: str) -> str:
    s = str(s).lower()
    if any(k in s for k in ["battery", "energy storage"]):
        return "Energy storage"
    if any(k in s for k in ["hydrogen", "e-fuels", "fuel", "gas"]):
        return "Fuels & hydrogen"
    if any(k in s for k in ["automotive", "transport", "aviation", "shipping"]):
        return "Transport & mobility"
    if any(k in s for k in ["chemical", "materials", "manufacturing", "industrial"]):
        return "Process & materials"
    if any(k in s for k in ["power", "grid", "renewable", "solar", "wind"]):
        return "Power & renewables"
    if any(k in s for k in ["software", "digital", "platform", "data"]):
        return "Software & digital"
    return "Other / mixed"


# ============================================================
# Plot styling & saving
# ============================================================

COLORS = {
    "one": "steelblue",
    "two": ["steelblue", "seagreen"],
    "three": ["steelblue", "seagreen", "darkorange"],
}

def style_ax(ax):
    ax.grid(axis="y", alpha=0.25)
    ax.set_title("")

# ============================================================
# Time & cohort helpers (collaboration plots)
# ============================================================

# Analysis window of the paper (2020-2025): partnership_master carries a small
# pre-2020 tail (~3% of collaborations) that the panels and figures exclude.
PLOT_START = pd.Timestamp("2020-01-01")
PLOT_END   = pd.Timestamp("2026-01-01")   # exclusive

def pretty_type(t):
    t = str(t).lower().strip()
    return "Battery" if t == "battery" else "Hydrogen" if t == "hydrogen" else t.title()

def round_colors(ipcei_type, rounds):
    cmap = plt.cm.Greens if ipcei_type == "battery" else plt.cm.Blues
    vals = np.linspace(0.45, 0.9, max(len(rounds), 1))
    return dict(zip(rounds, cmap(vals)))


