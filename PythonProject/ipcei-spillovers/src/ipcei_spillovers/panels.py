# ============================================================
# Build Callaway & Sant'Anna-ready firm-month panels
# ============================================================
# Shared builder used by the alternative-method notebooks (entropy balancing,
# unmatched eligible pool). The PSM notebook keeps its own inline builder; this
# module reproduces the same panel structure so every method emits identical
# `*_cs_ready.csv` columns.

from __future__ import annotations

import numpy as np
import pandas as pd

# Firm-level covariates carried into the panel (only those present are kept).
# Mirrors the PSM panel's meta_back exactly so every method emits identical
# `*_cs_ready.csv` columns.
DEFAULT_FIRM_COLS = (
    "nace1_psm", "nace1_proxy", "firm_type", "log_staffCount",
    "age", "log_collab_count_2020", "degree_centrality_2020",
)


def build_cs_panel(
    firms: pd.DataFrame,
    firm_month_outcomes: pd.DataFrame,
    g_lookup: pd.DataFrame,
    mean_collab_size: pd.DataFrame | None = None,
    start: str = "2020-01-01",
    end: str = "2025-12-01",
    firm_cols=DEFAULT_FIRM_COLS,
    weight_col: str | None = None,
):
    """
    Assemble a C&S-ready firm-month panel from a set of firms.

    Parameters
    ----------
    firms : one row per firm; must contain ``Linkedin_name``, ``is_treated``,
        ``is_control``, the covariates in ``firm_cols``, and optionally
        ``matched_to`` and a weight column named by ``weight_col``.
    firm_month_outcomes : long firm-month frame with a datetime ``month`` column
        and ``n_collabs*`` count columns.
    g_lookup : columns ``[Linkedin_name, g]`` giving the treatment month (as a
        month-start timestamp) for treated firms. Controls get ``g = NaT``.
    mean_collab_size : optional ``[Linkedin_name, month, mean_collab_size]``
        level outcome; zero-filled where a firm-month has no collaboration.
    weight_col : optional firm-level column carried through (e.g. entropy
        balancing weight ``w``).

    Returns
    -------
    cs_panel : firm-month DataFrame on a contiguous monthly grid, columns
        ordered meta / outcomes / level outcomes / covariates.
    """
    firm_cols = [c for c in firm_cols if c in firms.columns]
    names = list(pd.unique(firms["Linkedin_name"].dropna()))

    # Firm-level lookup (one row per firm)
    keep = ["Linkedin_name", "is_treated", "is_control"] + firm_cols
    if "matched_to" in firms.columns:
        keep.append("matched_to")
    if weight_col and weight_col in firms.columns:
        keep.append(weight_col)
    lookup = firms[keep].drop_duplicates(subset=["Linkedin_name"]).copy()

    # Complete firm x month grid, zero-filled outcomes
    months = pd.date_range(start, end, freq="MS")
    grid = pd.MultiIndex.from_product(
        [names, months], names=["Linkedin_name", "month"]
    ).to_frame(index=False)

    sparse = firm_month_outcomes[
        firm_month_outcomes["Linkedin_name"].isin(names)
    ].copy()
    panel = grid.merge(sparse, on=["Linkedin_name", "month"], how="left")
    outcome_cols = [c for c in panel.columns if c.startswith("n_collabs")]
    for col in outcome_cols:
        panel[col] = panel[col].fillna(0).astype(int)

    panel = panel.merge(lookup, on="Linkedin_name", how="left")

    # Consortium-size level outcome (kept out of the n_collabs* set so R never
    # log1p's it). The merge yields NaN exactly in firm-months with no
    # collaboration, so two versions are carried: `_active` keeps the NaN, so
    # C&S drops those months and the ATT is intensive-margin (conditional on
    # collaborating); the zero-filled column mixes the extensive and intensive
    # margins and is kept only for comparison. Mirrors 05a.
    level_cols = []
    if mean_collab_size is not None:
        panel = panel.merge(mean_collab_size, on=["Linkedin_name", "month"], how="left")
        panel["mean_collab_size_active"] = panel["mean_collab_size"]
        panel["mean_collab_size"] = panel["mean_collab_size"].fillna(0)
        level_cols = ["mean_collab_size", "mean_collab_size_active"]

    # Treatment timing: treated firms get g; controls NaT.
    g = g_lookup[["Linkedin_name", "g"]].copy()
    g["g"] = pd.to_datetime(g["g"], errors="coerce").dt.to_period("M").dt.to_timestamp()
    panel = panel.merge(g, on="Linkedin_name", how="left")
    panel.loc[panel["is_control"] == 1, "g"] = pd.NaT

    # Event time (months since treatment) and post indicator
    m_per = panel["month"].dt.to_period("M")
    g_per = panel["g"].dt.to_period("M")
    panel["event_time"] = (m_per - g_per).apply(lambda x: x.n if pd.notna(x) else np.nan)
    panel["post_event"] = (panel["event_time"] >= 0).astype(int)
    panel.loc[panel["event_time"].isna(), "post_event"] = 0

    meta_front = ["Linkedin_name", "month", "g", "event_time", "post_event",
                  "is_treated", "is_control"]
    if "matched_to" in panel.columns:
        meta_front.append("matched_to")
    if weight_col and weight_col in panel.columns:
        meta_front.append(weight_col)

    cs_panel = panel[meta_front + outcome_cols + level_cols + firm_cols].copy()
    cs_panel = (cs_panel
                .drop_duplicates(subset=["Linkedin_name", "month"])
                .sort_values(["Linkedin_name", "month"]))
    return cs_panel
