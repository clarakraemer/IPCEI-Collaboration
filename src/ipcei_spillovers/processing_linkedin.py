from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

import pandas as pd

from ipcei_spillovers.io import load_df, save_df, data_path
from ipcei_spillovers.config_logging import setup_logging


# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
log = setup_logging(filename="cleaning.log")


# -----------------------------------------------------------------------------
# Configuration (filenames + join key)
# -----------------------------------------------------------------------------
JOIN_KEY = "Linkedin_name"

# Key columns in the edge tables
POST_ID_COL = "post_id"
COLLAB_ID_COL = "collaboration_id"
PARTNERSHIP_ID_COL = "partnership_id"

PARTNER_SRC_COL = "source"
PARTNER_TGT_COL = "target"

# Collaboration indicator columns (will automatically use only those that exist)
COLLAB_INDICATORS = [
    "Biomass",
    "Biofuels",
    "Biogas",
    "Wind",
    "Offshore_Wind",
    "Solar",
    "Concentrated_Solar",
    "Waste_to_Heat",
    "Direct_Air_Capture",
    "Carbon_Capture_And_Storage",
    "Biochar",
    "Carbon_Direct_Removal",
    "BECCS",
    "Hydrogen",
    "Nuclear_Energy",
    "Nuclear_Fusion",
    "Hydro_Energy",
    "Geothermal",
    "Battery",
    "Electric_Vehicles",
    "Sustainable_Aviation_Fuels",
    "E_Fuels",
    "Marine_Energy",
    "Heat_Pumps",
    "Railway",
    "Electric_Shipping",
    "Electric_Aviation",
    "Fuel_Cell_Aviation",
    "Other_Technology",
    "r_and_d_collaborations",
    "demonstrations_and_pilots",
    "commercialisation_and_product_launches",
    "production_and_manufacturing",
    "offtake_agreements_and_futures",
    "adoption_and_deployments",
    "operations_and_maintenance",
    "grants",
    "equity_investments",
    "loans",
    "other_unspecified_finance",
    "spin_offs",
    "mergers_and_accquisitions",
    "joint_ventures",
    "incubators_and_accelerator_programs",
    "certification_and_approvals",
    "training",
    "core_technology",
    "infrastructure",
    "software_and_digital_platforms",
    "raw_materials",
    "recycling",
    "other_complementary_activities",
]


@dataclass(frozen=True)
class LinkedinFiles:
    """
    Keeps all raw filenames in one place to make later updates easier.
    Folder: src/data/raw/linkedin/
    """

    partnerships: str
    firms: str
    locations: str
    collaborations: str
    meta: str


def files_for_version(version: str = "jan26") -> LinkedinFiles:
    """
    Build filenames from a version string.
    """
    return LinkedinFiles(
        partnerships=f"Network_partnerships_{version}.csv",
        firms=f"Linkedin_firms_{version}.csv",
        locations=f"Linkedin_locations_{version}.csv",
        collaborations=f"Linkedin_collaborations_{version}.csv",
        meta=f"Linkedin_dynamic_meta_{version}.csv",
    )


# -----------------------------------------------------------------------------
# Loading
# -----------------------------------------------------------------------------
def load_linkedin_tables(version: str = "jan26") -> Dict[str, pd.DataFrame]:
    """
    Load raw LinkedIn CSV exports into a dict of DataFrames.

    Returns keys:
      - partnerships
      - firms
      - locations
      - collaborations
      - meta
    """
    f = files_for_version(version)

    log.info("Loading LinkedIn tables for version=%s", version)

    # Force string IDs to avoid precision loss (e.g. scientific notation)
    read_opts = {
        "dtype": {
            POST_ID_COL: "string",
            COLLAB_ID_COL: "string",
            PARTNERSHIP_ID_COL: "string",
        }
    }

    tables = {
        "partnerships": load_df("raw", "linkedin", f.partnerships, encoding="utf-8-sig", low_memory=False, **read_opts),
        "firms": load_df("raw", "linkedin", f.firms, encoding="utf-8-sig", low_memory=False),
        "locations": load_df("raw", "linkedin", f.locations, encoding="utf-8-sig", low_memory=False),
        "collaborations": load_df(
            "raw", "linkedin", f.collaborations, encoding="utf-8-sig", low_memory=False, **read_opts
        ),
        "meta": load_df("raw", "linkedin", f.meta, encoding="utf-8-sig", low_memory=False),
    }

    for name in ["partnerships", "collaborations"]:
        df = tables[name]
        for col in [POST_ID_COL, COLLAB_ID_COL, PARTNERSHIP_ID_COL]:
            if col in df.columns:
                df[col] = df[col].astype("string")
        tables[name] = df

    for name, df in tables.items():
        log.info("Loaded %-15s shape=%s", name, df.shape)

    return tables


# -----------------------------------------------------------------------------
# Basic standardization helpers
# -----------------------------------------------------------------------------
def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Strip whitespace in all object (string) columns.
    Helps avoid join issues (e.g., 'ABC ' vs 'ABC').
    """
    out = df.copy()
    obj_cols = out.select_dtypes(include=["object"]).columns
    for c in obj_cols:
        out[c] = out[c].astype("string").str.strip()
    return out


def _drop_bad_keys(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if key not in df.columns:
        return df
    s = df[key].astype("string").str.strip()
    mask = s.notna() & (s.str.len() > 2) & ~s.str.startswith("#")
    return df.loc[mask].copy()


def _ensure_join_key(df: pd.DataFrame, name: str, join_key: str = JOIN_KEY) -> None:
    """Raise a clear error if the expected join key is missing."""
    if join_key not in df.columns:
        raise KeyError(f"[{name}] missing required join key column: {join_key}")


def _ensure_columns(df: pd.DataFrame, name: str, cols: list[str]) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"[{name}] missing required columns: {missing}")


def _parse_datetime(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Parse a datetime column in-place if it exists."""
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def _fix_text_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Fix mojibake in selected text columns.
    Requires 'ftfy'.
    """
    out = df.copy()
    try:
        import ftfy
        for c in cols:
            if c in out.columns:
                out[c] = out[c].astype("string").apply(lambda x: ftfy.fix_text(x) if pd.notna(x) else x)
    except Exception:
        pass
    return out


def _clean_firm_type(df: pd.DataFrame, col: str = "firm_type") -> pd.DataFrame:
    """
    firm_type should be a short categorical label.
    Some rows contain LLM-style explanations when the input was missing ("nan").
    Those should become pd.NA.
    """
    if col not in df.columns:
        return df

    s = df[col].astype("string").str.strip()

    # Treat these as corrupted "missing" artifacts (not real categories)
    artifact = (
        s.str.len().fillna(0).gt(80)  # long paragraphs
        | s.str.contains(r"\bclassification\b", case=False, na=False)
        | s.str.contains(r"\bnot classifiable\b", case=False, na=False)
        | s.str.contains(r"\bnot a number\b", case=False, na=False)
        | s.str.contains(r"\bthe provided text\b", case=False, na=False)
        | s.str.contains(r"\bstands for\b", case=False, na=False)
    )

    out = df.copy()
    out.loc[artifact, col] = pd.NA
    return out


def _clean_sector(df: pd.DataFrame, col: str = "sector") -> pd.DataFrame:
    """
    Sector should be a short comma-separated label list.
    Some rows contain LLM-style explanations appended after newline(s),
    or full narrative text.
    """
    if col not in df.columns:
        return df

    out = df.copy()
    s = out[col].astype("string").str.strip()

    # 1) Keep only first line (everything before first newline)
    first_line = s.str.split(r"\r?\n", n=1, expand=False).str[0].str.strip()

    # 2) Remove surrounding quotes and trailing punctuation
    # e.g. '"Solar, Built Environment "' -> 'Solar, Built Environment'
    first_line = first_line.str.replace(r'^[\'"]+|[\'"]+$', "", regex=True).str.strip()
    first_line = first_line.str.replace(r"[.;:]+$", "", regex=True).str.strip()

    # 3) If first line looks like narrative rather than labels, set NA
    # Heuristic: label lines are usually short and do NOT start with "Based on"/"Please"/etc.
    narrative_start = first_line.str.contains(
        r"^(?:based on|please note|note:|in this text|the text|given that|for the)",
        case=False,
        na=False,
    )
    too_long = first_line.str.len().gt(120)
    looks_like_bullets = first_line.str.contains(r"^-", na=False)

    # If it’s narrative, don’t keep it as a category value
    first_line = first_line.where(~(narrative_start | too_long | looks_like_bullets), pd.NA)

    out[col] = first_line
    return out


def _clean_country(df: pd.DataFrame, col: str = "country") -> pd.DataFrame:
    """
    Country is mostly ISO-2 in your data; normalize the known non-ISO spellings /
    encoding artifacts you observed.
    """
    if col not in df.columns:
        return df

    out = df.copy()
    s = out[col].astype("string").str.strip()

    # defensive mapping for both correct spelling + mojibake variant(s)
    fixes = {
        "ÖSTERREICH": "AT",
        "Österreich": "AT",
        "√ñSTERREICH": "AT",
        "√ÑSTERREICH": "AT",
    }

    out[col] = s.replace(fixes)
    return out


def _to_int01(s: pd.Series) -> pd.Series:
    """Convert typical 0/1 fields to Int64 safely."""
    return pd.to_numeric(s, errors="coerce").fillna(0).astype("Int64")


def _valid_latlon(df: pd.DataFrame) -> pd.Series:
    """
    Returns 1 where (lat, lon) exist and are plausible ranges:
      lat in [-90, 90], lon in [-180, 180]
    """
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return pd.Series([0] * len(df), index=df.index, dtype="int")

    lat = pd.to_numeric(df["latitude"], errors="coerce")
    lon = pd.to_numeric(df["longitude"], errors="coerce")
    return (lat.between(-90, 90) & lon.between(-180, 180)).astype(int)


def build_location_features(locations: pd.DataFrame, join_key: str = JOIN_KEY) -> pd.DataFrame:
    """
    Build a 1-row-per-firm location feature table from raw locations.
    """
    loc = _strip_strings(locations)
    _ensure_join_key(loc, "locations", join_key)

    # Clean country and normalize flags
    loc = _clean_country(loc, col="country")

    if "headquarter" in loc.columns:
        loc["headquarter"] = _to_int01(loc["headquarter"])
    else:
        loc["headquarter"] = pd.Series([0] * len(loc), dtype="Int64")

    if "location_closed" in loc.columns:
        loc["location_closed"] = _to_int01(loc["location_closed"])
    else:
        loc["location_closed"] = pd.Series([0] * len(loc), dtype="Int64")

    # Parse closingDate
    if "closingDate" in loc.columns:
        loc["closingDate"] = pd.to_datetime(loc["closingDate"], errors="coerce")

    if "updateDate" in loc.columns:
        loc["updateDate"] = pd.to_datetime(loc["updateDate"], errors="coerce")
    else:
        loc["updateDate"] = pd.NaT

    # Ensure numeric lat/lon
    for c in ["latitude", "longitude"]:
        if c in loc.columns:
            loc[c] = pd.to_numeric(loc[c], errors="coerce")

    # Pick one primary location row per firm
    def _pick_primary_row(g: pd.DataFrame) -> pd.Series:
        gg = g.copy()

        # 1) Prefer HQ rows
        hq = g[g["headquarter"] == 1]
        if len(hq) > 0:
            hq2 = hq.copy()

            # guard latitude / longitude
            hq2["_has_ll"] = 0
            if "latitude" in hq2.columns and "longitude" in hq2.columns:
                hq2["_has_ll"] = _valid_latlon(hq2)

            # deterministic tie-break: prefer lat/lon, then latest updateDate, then lowest location_id
            sort_cols = ["_has_ll", "updateDate"]
            asc = [False, False]
            if "location_id" in hq2.columns:
                sort_cols.append("location_id")
                asc.append(True)

            hq2 = hq2.sort_values(by=sort_cols, ascending=asc, kind="mergesort")
            return hq2.iloc[0]

        # 2) Else choose mode country
        if "country" in gg.columns:
            mode_country = gg["country"].dropna().mode()
            if len(mode_country) > 0:
                cand = gg.loc[gg["country"] == mode_country.iloc[0]].copy()
            else:
                cand = gg.copy()
        else:
            cand = gg.copy()

            # tie-break (deterministic):
            # 1) prefer rows with BOTH lat+lon
            # 2) then latest updateDate (if exists)
            # 3) then smallest location_id (if exists)
        cand["_has_ll"] = _valid_latlon(cand)

        # ensure updateDate exists (or fill with NaT)
        if "updateDate" not in cand.columns:
            cand["updateDate"] = pd.NaT

        sort_cols = ["_has_ll", "updateDate"]
        ascending = [False, False]

        if "location_id" in cand.columns:
            sort_cols.append("location_id")
            ascending.append(True)

        cand2 = cand.sort_values(by=sort_cols, ascending=ascending, kind="mergesort")
        return cand2.iloc[0]

    primary = (
        loc.groupby(join_key, group_keys=False, sort=False)
        .apply(_pick_primary_row, include_groups=False)
        .reset_index(names=join_key)
    )

    # core aggregates
    agg_kwargs = dict(
        n_locations=(join_key, "size"),
        n_countries=("country", lambda s: s.dropna().nunique()),
        countries=("country", lambda s: ", ".join(sorted(set(s.dropna())))),
        has_headquarter=("headquarter", lambda s: int((s == 1).any())),
        n_locations_closed=("location_closed", lambda s: int((s == 1).sum())),
        any_location_closed=("location_closed", lambda s: int((s == 1).any())),
    )

    if "closingDate" in loc.columns:
        agg_kwargs["latest_closingDate"] = ("closingDate", "max")
    else:
        # produce a NaT column deterministically
        agg_kwargs["latest_closingDate"] = (join_key, lambda s: pd.NaT)

    agg = loc.groupby(join_key, as_index=False).agg(**agg_kwargs)

    # attach primary fields
    keep_primary_cols = [join_key]
    for c in ["country", "city", "latitude", "longitude"]:
        if c in primary.columns:
            keep_primary_cols.append(c)

    primary_small = primary[keep_primary_cols].rename(
        columns={
            "country": "primary_country",
            "city": "primary_city",
            "latitude": "primary_latitude",
            "longitude": "primary_longitude",
        }
    )

    # HQ fields (only if HQ exists)
    hq_rows = loc.loc[loc["headquarter"] == 1].copy()
    if len(hq_rows) > 0:
        hq_first = (
            hq_rows.sort_values([join_key])
            .drop_duplicates(subset=[join_key], keep="first")
            [[c for c in [join_key, "country", "city"] if c in hq_rows.columns]]
            .rename(columns={"country": "hq_country", "city": "hq_city"})
        )
    else:
        hq_first = pd.DataFrame({join_key: loc[join_key].dropna().unique()})
        hq_first["hq_country"] = pd.NA
        hq_first["hq_city"] = pd.NA

    # merge all
    features = (
        agg.merge(primary_small, on=join_key, how="left", validate="1:1")
           .merge(hq_first, on=join_key, how="left", validate="1:1")
    )

    return features


# -----------------------------------------------------------------------------
# Column selection
# -----------------------------------------------------------------------------
def slim_tables(
    tables: Dict[str, pd.DataFrame],
    keep_firms: Optional[list[str]] = None,
    keep_meta: Optional[list[str]] = None,
    keep_locations: Optional[list[str]] = None,
) -> Dict[str, pd.DataFrame]:
    """
    Keeps only needed columns for firms/meta/locations.
    Partnership + collaboration edge tables are kept complete.
    """
    out = dict(tables)

    if keep_firms is None:
        keep_firms = [
            JOIN_KEY,
            "foundingYear",
            "website",
            "name",
            "linkedinUrl",
            "NEW_Linkedin_name",
            "firm_type",
            "sector",
            "industry",
            "meta_update",
        ]
    if keep_meta is None:
        keep_meta = [JOIN_KEY, "staffCount"]
    if keep_locations is None:
        keep_locations = [
            JOIN_KEY,
            "location_id",
            "country",
            "city",
            "headquarter",
            "postalCode",
            "latitude",
            "longitude",
            "updateDate",
            "closingDate",
            "location_closed",
        ]

    # Firms
    firms = _strip_strings(out["firms"])
    firms = _fix_text_cols(firms, ["name"])
    firms = _clean_firm_type(firms, col="firm_type")
    firms = _clean_sector(firms, col="sector")
    _ensure_join_key(firms, "firms")
    firms = firms[[c for c in keep_firms if c in firms.columns]]
    out["firms"] = firms

    # Meta
    meta = _strip_strings(out["meta"])
    meta = _drop_bad_keys(meta, JOIN_KEY)
    _ensure_join_key(meta, "meta")
    meta = meta[[c for c in keep_meta if c in meta.columns]]
    out["meta"] = meta

    # Locations (can be many rows per firm)
    loc = _strip_strings(out["locations"])
    loc = _clean_country(loc, col="country")
    _ensure_join_key(loc, "locations")
    loc = loc[[c for c in keep_locations if c in loc.columns]]
    out["locations"] = loc

    log.info(
        "Slimmed firms=%s meta=%s locations=%s",
        out["firms"].shape,
        out["meta"].shape,
        out["locations"].shape,
    )

    return out


# -----------------------------------------------------------------------------
# Build “master” tables
# -----------------------------------------------------------------------------
def build_firm_master(
    firms: pd.DataFrame,
    meta: pd.DataFrame,
    join_key: str = JOIN_KEY,
) -> pd.DataFrame:
    """
    Creates one row per firm by merging firm attributes with metadata.

    Both firms and meta can contain multiple rows per Linkedin_name in the CSV exports.
    Keeps the last row per Linkedin_name before merging.
    """
    firms = _strip_strings(firms)
    meta = _strip_strings(meta)

    _ensure_join_key(firms, "firms", join_key)
    _ensure_join_key(meta, "meta", join_key)

    # Deduplicate firms
    if firms.duplicated(subset=[join_key]).any():
        n_dup = int(firms.duplicated(subset=[join_key]).sum())
        log.warning("Firms has %s duplicate %s rows -> deduplicating", n_dup, join_key)

        if "meta_update" in firms.columns:
            firms["meta_update"] = pd.to_datetime(firms["meta_update"], errors="coerce")
            firms = (
                firms.sort_values([join_key, "meta_update"])
                .drop_duplicates(subset=[join_key], keep="last")
            )
        else:
            # fallback: deterministic "last occurrence in file order"
            firms = firms.drop_duplicates(subset=[join_key], keep="last")

    # Deduplicate meta
    if meta.duplicated(subset=[join_key]).any():
        n_dup = int(meta.duplicated(subset=[join_key]).sum())
        log.warning("Meta has %s duplicate %s rows -> deduplicating", n_dup, join_key)

        if "updateDate" in meta.columns:
            meta["updateDate"] = pd.to_datetime(meta["updateDate"], errors="coerce")
            meta = (
                meta.sort_values([join_key, "updateDate"])
                .drop_duplicates(subset=[join_key], keep="last")
            )
        else:
            meta = meta.drop_duplicates(subset=[join_key], keep="last")

    firm_master = firms.merge(meta, on=join_key, how="left", validate="1:1")
    if "firm_type" in firm_master.columns:
        max_len = firm_master["firm_type"].astype("string").str.len().max()
        if pd.notna(max_len) and max_len > 200:
            log.warning("firm_type still contains very long strings (max_len=%s).", max_len)

    log.info("Built firm_master shape=%s", firm_master.shape)
    return firm_master


# -----------------------------------------------------------------------------
# Collaboration features + partnership master
# -----------------------------------------------------------------------------
def build_partnership_master_from_collaborations(
    partnerships: pd.DataFrame,
    collaborations: pd.DataFrame,
    collab_id_col: str = COLLAB_ID_COL,
    indicators: list[str] = COLLAB_INDICATORS,
) -> pd.DataFrame:
    """
    Build partnership_master by aggregating collaboration indicator columns
    from the collaborations table and merging into partnerships.

    Result: partnerships (m rows) left-joined with aggregated indicators (1 row per collaboration_id).
    """
    p = _strip_strings(partnerships)
    p = _parse_datetime(p, "post_date")
    _ensure_columns(p, "partnerships", [collab_id_col, PARTNER_SRC_COL, PARTNER_TGT_COL])

    c = _strip_strings(collaborations)
    _ensure_columns(c, "collaborations", [collab_id_col])

    use_cols = [col for col in indicators if col in c.columns]
    if not use_cols:
        raise ValueError("No collaboration indicator columns found in collaborations table.")

    # force 0/1 numeric
    for col in use_cols:
        c[col] = pd.to_numeric(c[col], errors="coerce").fillna(0)

    # aggregate to 1 row per collaboration_id
    c_agg = c.groupby(collab_id_col, as_index=False)[use_cols].max()

    out = p.merge(c_agg, on=collab_id_col, how="left", validate="m:1")

    # fill missing indicators with 0 for collaborations with no match
    for col in use_cols:
        out[col] = out[col].fillna(0).astype("Int64")

    log.info("Built partnership_master shape=%s indicators_used=%d", out.shape, len(use_cols))
    return out


# -----------------------------------------------------------------------------
# Saving interim dataframe
# -----------------------------------------------------------------------------
def save_interim_tables(
    *,
    version: str,
    firm_master: pd.DataFrame,
    partnership_master: pd.DataFrame,
) -> None:
    """
    Save cleaned/curated interim outputs to:
      src/data/interim/linkedin/
    """
    log.info("Saving interim outputs for version=%s", version)

    save_df(firm_master, "interim", "linkedin", f"firm_master_{version}.csv")
    save_df(partnership_master, "interim", "linkedin", f"partnership_master_{version}.csv")

    log.info("Saved interim tables to %s", data_path("interim", "linkedin"))

# -----------------------------------------------------------------------------
# One-call pipeline
# -----------------------------------------------------------------------------
def run_linkedin_interim_pipeline(version: str = "jan26") -> Dict[str, pd.DataFrame]:
    """
    End-to-end:
      - load raw tables
      - build firm master (firms + meta + locations)
      - build partnership_master (partnerships + collab indicator columns)
      - save interim outputs
      - return key tables for inspection
    """
    tables = load_linkedin_tables(version=version)
    tables = slim_tables(tables)

    firm_master = build_firm_master(tables["firms"], tables["meta"])

    # Build 1-row-per-firm location features and merge into firm_master
    loc_features = build_location_features(tables["locations"], join_key=JOIN_KEY)
    firm_master = firm_master.merge(loc_features, on=JOIN_KEY, how="left", validate="1:1")

    partnership_master = build_partnership_master_from_collaborations(
        partnerships=tables["partnerships"],
        collaborations=tables["collaborations"],
    )

    save_interim_tables(
        version=version,
        firm_master=firm_master,
        partnership_master=partnership_master,
    )

    return {
        "firm_master": firm_master,
        "partnership_master": partnership_master,
        "loc_features": loc_features,
    }
