from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from ipcei_spillovers.io import load_df, save_df
from ipcei_spillovers.config_logging import setup_logging

log = setup_logging(filename="processing.log")

JOIN_KEY = "Linkedin_name"


# -----------------------------
# Helpers
# -----------------------------
def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if out[c].dtype == "object":
            out[c] = out[c].astype("string").str.strip()
    return out


def _parse_ipcei_date(df: pd.DataFrame, col: str = "ipcei_post_date") -> pd.DataFrame:
    if col in df.columns:
        # your file uses e.g. "12/9/19 0:00"
        df[col] = pd.to_datetime(df[col], format="%m/%d/%y %H:%M", errors="coerce")
    return df


def _norm_country_list(s: pd.Series) -> pd.Series:
    # Keep as a standardized comma-separated list: "FR, IT, BE"
    x = s.astype("string").str.upper().str.strip()
    x = x.str.replace(r"\s+", " ", regex=True)
    x = x.str.replace(r"\s*,\s*", ", ", regex=True)
    return x


# -----------------------------
# Load inputs
# -----------------------------
def load_ipcei_raw(filename: str = "IPCEI_final_h2_battery.csv") -> pd.DataFrame:
    ip = load_df("raw", "ipcei", filename)
    ip = _strip_strings(ip)
    ip = _parse_ipcei_date(ip, "ipcei_post_date")

    if "country" in ip.columns:
        ip["country"] = _norm_country_list(ip["country"])

    # normalize type casing to be consistent
    if "ipcei_type" in ip.columns:
        ip["ipcei_type"] = (
            ip["ipcei_type"]
            .astype("string")
            .str.strip()
            .str.lower()
        )

    return ip


def load_linkedin_masters(version: str) -> Dict[str, pd.DataFrame]:
    firm_master = load_df("interim", "linkedin", f"firm_master_{version}.csv", low_memory=False)
    partnership_master = load_df("interim", "linkedin", f"partnership_master_{version}.csv", low_memory=False)

    firm_master = _strip_strings(firm_master)
    partnership_master = _strip_strings(partnership_master)

    return {"firm_master": firm_master, "partnership_master": partnership_master}


# -----------------------------
# Build IPCEI-only outputs
# -----------------------------
def build_ipcei_events(ipcei: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (Linkedin_name, ipcei_type, ipcei_round).
    Keeps subtype + round name + country list + event date.
    """
    keep = [c for c in [
        JOIN_KEY, "name", "country", "ipcei_type", "ipcei_subtype",
        "ipcei_post_date", "ipcei_round", "ipcei_round_name"
    ] if c in ipcei.columns]

    ev = ipcei[keep].copy()
    ev = ev.dropna(subset=[JOIN_KEY, "ipcei_type", "ipcei_round", "ipcei_post_date"], how="any")

    # de-dup defensively (in case the same event appears twice)
    ev = ev.sort_values(["Linkedin_name", "ipcei_type", "ipcei_round", "ipcei_post_date"])
    ev = ev.drop_duplicates(subset=["Linkedin_name", "ipcei_type", "ipcei_round"], keep="last")

    ev["ipcei_post_date"] = pd.to_datetime(ev["ipcei_post_date"], errors="coerce")

    ev["event_id"] = (
        ev["Linkedin_name"].astype("string") + "|" +
        ev["ipcei_type"].astype("string") + "|r" +
        ev["ipcei_round"].astype("string")
    )

    ev["event_month"] = ev["ipcei_post_date"].dt.to_period("M").dt.to_timestamp()

    return ev.reset_index(drop=True)


def build_ipcei_firm_summary(ipcei_events: pd.DataFrame) -> pd.DataFrame:
    """
    One row per firm. Purely descriptive.
    """
    g = ipcei_events.groupby(JOIN_KEY, as_index=False)

    summ = g.agg(
        treated_any=("ipcei_round", lambda s: 1),
        n_ipcei_events=("ipcei_round", "size"),
        n_ipcei_types=("ipcei_type", lambda s: s.nunique()),
        first_ipcei_date=("ipcei_post_date", "min"),
        last_ipcei_date=("ipcei_post_date", "max"),
        ipcei_types=("ipcei_type", lambda s: "|".join(
            sorted(set(s.dropna().astype(str))))),
        ipcei_rounds=("ipcei_round", lambda s: "|".join(
            map(str, sorted(set(s.dropna().astype(int)))))),
    )

    # ── Technology-specific first treatment dates ─────────────────────────────
    # Needed for staggered DiD when firms participate in multiple IPCEI types.
    # first_ipcei_date is the global minimum — these are type-specific minima.
    for tech in ["battery", "hydrogen"]:
        tech_dates = (
            ipcei_events[
                ipcei_events["ipcei_type"].str.lower().str.strip() == tech
            ]
            .groupby(JOIN_KEY)["ipcei_post_date"]
            .min()
            .reset_index()
            .rename(columns={"ipcei_post_date": f"first_{tech}_date"})
        )
        summ = summ.merge(tech_dates, on=JOIN_KEY, how="left")
    # ─────────────────────────────────────────────────────────────────────────

    return summ.reset_index(drop=True)


# -----------------------------
# Orchestrator
# -----------------------------
def run_ipcei_processing(version: str = "jan26") -> Dict[str, pd.DataFrame]:
    """
    Loads:
      - raw IPCEI
      - interim LinkedIn masters (for matching checks only, not merged)
    Saves:
      interim/ipcei/ipcei_events_{version}.csv
      interim/ipcei/ipcei_firm_summary_{version}.csv
      interim/ipcei/ipcei_firm_event_panel_{version}.csv
    """
    log.info("Loading raw IPCEI + interim LinkedIn masters (version=%s)", version)

    ipcei = load_ipcei_raw()
    masters = load_linkedin_masters(version=version)

    ipcei_events = build_ipcei_events(ipcei)
    ipcei_firm_summary = build_ipcei_firm_summary(ipcei_events)
    ipcei_firm_event_panel = build_ipcei_firm_event_panel(ipcei_events)

    # Optional matching diagnostics (kept in-memory)
    firm_names = set(masters["firm_master"][JOIN_KEY].dropna().astype("string"))
    partnership_names = set(pd.concat([
        masters["partnership_master"]["source"],
        masters["partnership_master"]["target"],
    ]).dropna().astype("string"))

    ipcei_events["in_firm_master"] = ipcei_events[JOIN_KEY].isin(firm_names).astype(int)
    ipcei_events["in_partnerships"] = ipcei_events[JOIN_KEY].isin(partnership_names).astype(int)
    ipcei_events["in_either_master"] = ((ipcei_events["in_firm_master"] == 1) | (ipcei_events["in_partnerships"] == 1)).astype(int)

    # Save
    save_df(ipcei_events, "interim", "ipcei", f"ipcei_events_{version}.csv")
    save_df(ipcei_firm_summary, "interim", "ipcei", f"ipcei_firm_summary_{version}.csv")
    save_df(ipcei_firm_event_panel, "interim", "ipcei", f"ipcei_firm_event_panel_{version}.csv")

    log.info("Saved IPCEI interim outputs for version=%s", version)

    return {
        "ipcei_raw": ipcei,
        "ipcei_events": ipcei_events,
        "ipcei_firm_summary": ipcei_firm_summary,
        "ipcei_firm_event_panel": ipcei_firm_event_panel,
        # masters returned only for inspection
        "firm_master": masters["firm_master"],
        "partnership_master": masters["partnership_master"],
    }
