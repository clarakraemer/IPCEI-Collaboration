"""Build the public replication bundle at Analyse/publish/.

    python -m ipcei_spillovers.publish

Why a generated bundle rather than git-tracking the working folders: `R/data/`
and `results/` are ignored wholesale, and carving exceptions out of that with
negation patterns is fragile. Here the published set is an explicit, reviewable
directory that is rebuilt from scratch on every run, so what gets pushed is
always exactly what this script decided to include.

WHAT IS PUBLISHED, AND WHY ONLY THIS
------------------------------------
The coauthor's rule is "the panel data and the data behind the graphics", and
the binding constraint is that the panels are NOT anonymous: `Linkedin_name` is
a LinkedIn slug (e.g. "absolicon-solar-collector-ab") and the matched-firm files
additionally carry name, website, linkedinUrl, hq_city and coordinates.
Publishing them as they stand would name every IPCEI recipient and every matched
control, with their collaboration histories, out of a third-party LinkedIn-based
dataset (Toetzke et al. 2025).

Pseudonymising costs nothing analytically: `load_cs()` in R turns the name into
a `firm_id` immediately, so no estimate depends on it. The ONE thing that joined
the panels to the firm files by name was the Rosenbaum chunk, which is retired.
So every reported number reproduces bit-for-bit from the bundle below.

Included:
  panels/        the four PSM CS-ready panels (spec 1 = primary, spec 2 =
                 robustness), pseudonymised, with `matched_to` re-keyed to the
                 same pseudonyms so the matching structure survives
  panels/        reduced matched-firm files: matching covariates, propensity
                 score and treatment flags only
  results/       every R output (ATTs, event studies, diagnostics, power curves)
  tables/        the LaTeX exhibits, plus the working CSVs that carry no firm
                 identifiers
  ipcei_approvals.csv   the EC approval list that defines treatment (public)

Excluded, deliberately:
  src/data/                 3.6 GB of raw and interim third-party data
  *_ebal_*, *_unmatched_*   280 MB across four files of 68-73 MB; robustness
                            arms whose control pools are random 5,000-firm
                            draws, so they would add bulk and disclose ~10,000
                            more firms for no replication gain
  full matched-firm files   name / website / linkedinUrl / city / coordinates
  partner_overlap_pairs, non_eu_ipcei_firms, top10_*   carry firm names

The name -> pseudonym crosswalk is written to R/data/, which is git-ignored, so
it stays on the author's machine. Do not move it into the bundle.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pandas as pd

from .config_paths import ANALYSE_DIR, PATHS, R_DATA_DIR, R_RESULTS_DIR

OUT = ANALYSE_DIR / "publish"

TECHS = ("battery", "hydrogen")
SPECS = (1, 2)

# Columns kept from the matched-firm files: enough to re-check balance and the
# match itself, nothing that identifies a firm.
FIRM_KEEP = [
    "log_staffCount", "age", "log_collab_count_2020", "degree_centrality_2020",
    "nace1_psm", "has_eu_operation", "firm_type",
    "propensity_score", "ps_distance", "treatment_group",
    "is_treated", "is_control", "matched_to",
    "spec_key", "spec_number", "first_battery_date", "first_hydrogen_date",
]

# Working CSVs that carry firm names or are superseded; never published.
TABLE_BLOCKLIST = {
    "battery_spec2_partner_overlap_pairs.csv",
    "hydrogen_spec2_partner_overlap_pairs.csv",
    "non_eu_ipcei_firms.csv",
    "top10_battery_ipcei_firms.csv",
    "top10_hydrogen_ipcei_firms.csv",
    "control_ipcei_exposure.OBSOLETE.csv",
}


# Result files that exist on disk but must NOT be shipped, because a reader
# would reasonably quote them and the numbers are not ones we stand behind.
# Blocked by filename, which is fine here: both names are unique in the tree.
RESULTS_BLOCKLIST = {
    # Rosenbaum is retired. Matching is with replacement, so matched sets
    # overlap and psens's set-independence assumption fails; the panel was
    # dropped from the appendix table. This file also predates the
    # collaboration-level rewrite, so its outcome labels no longer exist.
    "rosenbaum_bounds_techtagged.csv",
    # Stale: the extensive-margin chunk was repointed from the dyad-level
    # cross_border / cross_sector outcomes to the collaboration-level ones
    # Table 1 actually reports, and 07 has not been re-run since. Ship it again
    # once it has. It is not referenced by any table in the paper.
    "att_extensive_margin.csv",
}


def _panel_paths() -> list[Path]:
    return [R_DATA_DIR / f"{t}_psm_spec{s}_cs_ready.csv"
            for t in TECHS for s in SPECS]


def _firm_paths() -> list[Path]:
    return [R_DATA_DIR / f"{t}_psm_spec{s}_matched_firms.csv"
            for t in TECHS for s in SPECS]


def build_crosswalk() -> pd.DataFrame:
    """One pseudonym per firm, shared across all four panels.

    Sorted so the mapping is deterministic: re-running the script on unchanged
    inputs reproduces the same ids, which matters because the published files
    are meant to be citable.
    """
    names: set[str] = set()
    for p in _panel_paths() + _firm_paths():
        if p.exists():
            names |= set(pd.read_csv(p, usecols=["Linkedin_name"])["Linkedin_name"].dropna())
    ordered = sorted(names)
    width = max(4, len(str(len(ordered))))
    return pd.DataFrame({
        "Linkedin_name": ordered,
        "firm_id": [f"firm_{i:0{width}d}" for i in range(1, len(ordered) + 1)],
    })


def _apply(df: pd.DataFrame, cw: dict[str, str]) -> pd.DataFrame:
    """Replace the VALUES of Linkedin_name, keeping the column name.

    Deliberate: `load_cs()` in _cs_helpers.R does
        df$firm_id <- as.integer(factor(df$Linkedin_name))
    and `run_power_sim()` splits on the same column, so a published panel with
    the column renamed to `firm_id` would break every R script on first read.
    Keeping the name makes the bundle a drop-in replacement for R/data/ and
    costs only a slightly legacy-looking header, which the bundle README
    explains. Nothing identifying survives, since every value is a pseudonym.
    """
    df = df.copy()
    df["Linkedin_name"] = df["Linkedin_name"].map(cw)
    if df["Linkedin_name"].isna().any():
        raise RuntimeError("firm missing from the crosswalk; rebuild it")
    if "matched_to" in df.columns:
        # Controls carry the name of the treated firm they matched to. Re-key it
        # or the matching structure is lost; keep NaN as NaN.
        df["matched_to"] = df["matched_to"].map(lambda v: cw.get(v, pd.NA)
                                                if pd.notna(v) else pd.NA)
    return df


def main() -> None:
    if not R_DATA_DIR.exists():
        raise SystemExit(f"no R/data at {R_DATA_DIR}; run 05a first")

    if OUT.exists():
        shutil.rmtree(OUT)                       # rebuilt from scratch each run
    (OUT / "panels").mkdir(parents=True)
    (OUT / "tables").mkdir(parents=True)

    cw_df = build_crosswalk()
    cw = dict(zip(cw_df["Linkedin_name"], cw_df["firm_id"]))
    cw_path = R_DATA_DIR / "_pseudonym_crosswalk_PRIVATE.csv"
    cw_df.to_csv(cw_path, index=False)
    print(f"crosswalk: {len(cw)} firms -> {cw_path}  (git-ignored, keep private)")

    for p in _panel_paths():
        out = OUT / "panels" / p.name
        _apply(pd.read_csv(p, low_memory=False), cw).to_csv(out, index=False)
        print(f"  panel  {out.name:<44} {out.stat().st_size/1e6:6.1f} MB")

    for p in _firm_paths():
        df = _apply(pd.read_csv(p, low_memory=False), cw)
        keep = ["Linkedin_name"] + [c for c in FIRM_KEEP if c in df.columns]
        dropped = [c for c in df.columns if c not in keep]
        df[keep].to_csv(OUT / "panels" / p.name, index=False)
        print(f"  firms  {p.name:<44} kept {len(keep)}, dropped {len(dropped)}")

    shutil.copytree(R_RESULTS_DIR, OUT / "results",
                    ignore=shutil.ignore_patterns(".DS_Store", "*.log",
                                                  *RESULTS_BLOCKLIST))
    for name in sorted(RESULTS_BLOCKLIST):
        if not any((OUT / "results").rglob(name)):
            print(f"  SKIP   {name}  (void or stale, see RESULTS_BLOCKLIST)")
    n_res = sum(1 for _ in (OUT / "results").rglob("*") if _.is_file())
    print(f"  results  {n_res} files")

    n_tab = 0
    for role in ("main", "si"):
        src = PATHS.results_tables / role
        if src.exists():
            shutil.copytree(src, OUT / "tables" / role,
                            ignore=shutil.ignore_patterns(".DS_Store"))
            n_tab += sum(1 for _ in (OUT / "tables" / role).rglob("*.tex"))
    post = PATHS.results_tables / "post-audit" / "psm"
    if post.exists():
        dst = OUT / "tables" / "working-csvs"
        dst.mkdir(parents=True)
        for f in sorted(post.glob("*.csv")):
            if f.name in TABLE_BLOCKLIST:
                print(f"  SKIP   {f.name}  (firm identifiers / superseded)")
                continue
            shutil.copy2(f, dst / f.name)
            n_tab += 1
    print(f"  tables   {n_tab} files")

    ipcei = PATHS.data_raw / "ipcei" / "IPCEI_final_h2_battery.csv"
    if ipcei.exists():
        shutil.copy2(ipcei, OUT / "ipcei_approvals.csv")
        print("  ipcei_approvals.csv (public EC source)")

    # The bundle README lives in the package, not in publish/, because OUT is
    # deleted and recreated on every run. Keeping it here also means it is
    # version-controlled with the code that produces the files it describes.
    readme = Path(__file__).with_name("publish_README.md")
    if not readme.exists():
        raise SystemExit(f"bundle README missing at {readme}")
    shutil.copy2(readme, OUT / "README.md")
    print("  README.md")

    # Fail loudly rather than ship an identifier by accident. Compare WHOLE
    # column names, not substrings: "n_treated_firms" is a count and contains
    # "treated_firm", and a substring test blocks it for no reason.
    BANNED = {"new_linkedin_name", "linkedinurl", "website",
              "name", "treated_firm", "control_firm", "source", "target",
              "primary_city", "hq_city", "primary_latitude", "primary_longitude"}
    leaks = []
    for f in OUT.rglob("*.csv"):
        if f.name == "ipcei_approvals.csv":
            continue                              # public, firm names expected
        cols = {c.strip().strip('"').lower()
                for c in f.read_text(errors="replace").split("\n", 1)[0].split(",")}
        for col in sorted(cols & BANNED):
            leaks.append(f"{f.relative_to(OUT)}: {col}")
        # Linkedin_name is kept by name but must hold ONLY pseudonyms. Checking
        # the values, not the header, is what actually makes the bundle safe.
        if "linkedin_name" in cols:
            vals = pd.read_csv(f, usecols=["Linkedin_name"])["Linkedin_name"]
            bad = vals[~vals.astype(str).str.fullmatch(r"firm_\d+")].unique()
            if len(bad):
                leaks.append(f"{f.relative_to(OUT)}: real names in "
                             f"Linkedin_name, e.g. {list(bad[:3])}")
        if "matched_to" in cols:
            vals = pd.read_csv(f, usecols=["matched_to"])["matched_to"].dropna()
            bad = vals[~vals.astype(str).str.fullmatch(r"firm_\d+")].unique()
            if len(bad):
                leaks.append(f"{f.relative_to(OUT)}: real names in "
                             f"matched_to, e.g. {list(bad[:3])}")
    if leaks:
        raise SystemExit("IDENTIFIER LEAK, bundle not safe to publish:\n  "
                         + "\n  ".join(leaks))

    total = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file())
    print(f"\nbundle OK, no identifier columns. {OUT}  ({total/1e6:.1f} MB)")


if __name__ == "__main__":
    main()
