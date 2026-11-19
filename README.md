# Do subsidy conditions change who firms collaborate with? Evidence from IPCEI

Krämer, Toetzke & Egli.

This study estimates the causal effect of IPCEI subsidies (Important Projects of
Common European Interest) on firm-level collaboration behaviour in the EU
battery and hydrogen value chains. IPCEI lets member states subsidise innovative
projects on condition that recipients cooperate and disseminate knowledge within
the EU, which makes it a rare case where a subsidy scheme targets the
*composition* of collaboration rather than its volume.

Identification is propensity-score matching followed by the
Callaway & Sant'Anna (2021) staggered difference-in-differences estimator, on a
firm-by-month panel built from a LinkedIn-based dataset of collaboration
announcements (Toetzke et al. 2025). Treatment is dated at formal EC approval.

## Repository structure

Two sibling trees. Python does all data construction and visualisation; R does
all estimation and never constructs data.

| Path | Purpose |
|---|---|
| `PythonProject/ipcei-spillovers/notebooks/00`–`05c` | Cleaning, merging, outcome construction, matching |
| `PythonProject/ipcei-spillovers/notebooks/08` | Every figure and working CSV for the paper |
| `PythonProject/ipcei-spillovers/src/ipcei_spillovers/` | Reusable package: matching, panels, plotting, LaTeX tables, publication bundle |
| `R/markdown/06_*`, `07_*` | DiD estimation: collaboration intensity, and composition by technology |
| `R/markdown/10_*` | Diagnostics, cohort and reference-period checks, direct contrasts |
| `R/markdown/_cs_helpers.R` | Shared estimation helpers used by all methods |
| `R/data/`, `R/results/` | What R consumes and produces. Git-ignored |
| `publish/` | The public replication bundle (see `publish/README.md`) |

Methodological decisions, including the alternatives that were tried and
rejected, are documented in the comments of the scripts that implement them.

## Pipeline

Run in order. Python notebooks are run in an IDE; R files are knitted in RStudio.

```
00 → 01 → 02 → 03        clean, merge, describe, construct outcomes
     05a                 propensity-score matching (primary)
     05b, 05c            entropy balancing / unmatched pool (robustness)
          ↓  writes *_cs_ready.csv into R/data/
     R: 06, 07           estimation, per method
     R: 10               diagnostics and direct contrasts
          ↓  writes into R/results/
     08                  figures and working CSVs
     python -m ipcei_spillovers.tables     all LaTeX exhibits
     python -m ipcei_spillovers.publish    the public bundle
```

The handoff is one-directional and has no copy step: Python writes the
R-consumed panels straight into `R/data/` and reads R's output straight from
`R/results/`, via the `R_DATA_DIR` and `R_RESULTS_DIR` constants in
`config_paths.py`. There is deliberately no second copy of a panel anywhere.

## Environment

**Python** (3.9 or later):

```bash
cd PythonProject/ipcei-spillovers
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

**R**: the exact versions used for the reported estimates are recorded in
[`R/SESSION_INFO.txt`](R/SESSION_INFO.txt). One of them matters more than the
rest: results come from **`did` 2.3.0**, and other minor versions of that package
can give different numbers.

```r
install.packages(c("did", "dplyr", "ggplot2", "tidyr", "purrr",
                   "knitr", "kableExtra", "scales", "rbounds"))
```

## Reproducibility notes

- **Seeding.** `run_cs()` reseeds deterministically per outcome, so `att_gt`
  output does not depend on where a call sits in the session. `aggte()` does
  not reseed, and its multiplier bootstrap draws from the global stream, so the
  overall SE moves with call order. New analyses are therefore **appended** to
  the end of a script rather than inserted. `run_power_sim()` seeds per cell and
  restores the global RNG state on exit, so a power run cannot move a reported
  p-value.
- **Inference** is a multiplier bootstrap with 9,999 replications, clustered on
  the firm, conditional on the matched sample.
- **The period index must stay a dense rank.** `aggte(type = "dynamic")`
  computes event time as `t - g` from raw values, so a `YYYYMM` coding breaks at
  year boundaries and silently drops post-periods.
- **Power simulations** impose the null on the real treated firms and report a
  size check at a true effect of zero in the first row of every curve. Read that
  row before quoting a minimum detectable effect: it should sit near 0.05.

## Data

The underlying collaboration data is third-party and is not redistributed here.
What is published is the matched panel data and the outputs behind every figure
and table, with firm identifiers replaced by pseudonyms. The bundle, and the
reasoning about what it includes and excludes, is documented in
[`publish/README.md`](publish/README.md).

## Licence

MIT, see [LICENSE](LICENSE).
