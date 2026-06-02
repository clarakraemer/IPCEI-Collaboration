# CLAUDE.md

Project context for Claude Code. Read this before editing anything.

## What this project is

Academic paper estimating the **causal effect of IPCEI subsidies** (Important
Projects of Common European Interest) on **firm-level collaboration behaviour**
in the EU **battery** and **hydrogen** value chains. IPCEI lets member states
subsidise innovative projects conditional on firms cooperating and
disseminating knowledge within the EU.

Data: a LinkedIn-based dataset (~800k firm collaboration announcements,
2020–2025; Toetzke et al. 2025). One observation = one announced partnership
between two firms, tagged with technology (battery/hydrogen), activity type,
and firm metadata.

Identification: **propensity-score matching + Callaway & Sant'Anna (2021)
staggered DiD** (`did` package v2.3.0, doubly robust, 999 bootstrap iters,
anticipation = 0, not-yet-treated controls). 154 treated firm-technology obs
(42 battery, 112 hydrogen) across multiple cohorts.

## Stack and where work happens

- **Python** (pandas, numpy, networkx, matplotlib, seaborn) — data cleaning,
  preparation, matching, descriptive and results **visualisation**. Lives in
  `notebooks/` and the `src/ipcei_spillovers/` package.
- **R** (`did` v2.3.0, dplyr, ggplot2, rbounds) — **all DiD estimation**, in
  the `*.Rmd` files. R never does data construction; it consumes the
  CS-ready panels Python writes.

Editing rule: Claude Code edits files on disk. It does **not** run notebook
cells — after edits, the user re-runs notebooks in PyCharm and knits the
`.Rmd` in RStudio. Do not assume a cell executed; if you need a result,
say which cell to run.

## Repo layout

```
ipcei-spillovers/
  notebooks/
    00-ck-data-cleaning.ipynb
    01-ck-data-merge.ipynb
    02-ck-visualisation-descriptives-raw.ipynb
    03-ck-data-preparation.ipynb          # imputation, covariates, OUTCOME construction
    04-ck-visualisation-descriptives-prematch.ipynb
    05_ck_analysis_matching.ipynb          # PSM, builds CS-ready panels
    08_ck_visualisation-results.ipynb      # reads R's exported dynamic ATTs
  src/ipcei_spillovers/
    io.py            # data_path, results_path, load_df, save_df, save_fig
    matching.py      # propensity_score_match()
    plotting.py      # style_ax(), COLORS
    processing_ipcei.py, processing_linkedin.py
    config_paths.py, config_logging.py
  src/data/{raw,interim,processed}/        # raw is READ-ONLY; never modify
  results/
```

### Two-tree layout and the data handoff

`PythonProject/` and `R/` are **siblings** under `Analyse/`:

```
Analyse/
  PythonProject/ipcei-spillovers/   # Python: prep, matching, viz
  R/
    data/        # everything R CONSUMES: *_cs_ready.csv, *_matched_firms.csv
    markdown/    # the .Rmd files; their `../data/` resolves to R/data/
    results/     # everything R PRODUCES: att_summary_all.csv, composition/, ...
```

R estimation files live in `R/markdown/`:
`06_ck_didestimation_intensity.Rmd`, `06_ck_didestimation_composition.Rmd`,
`07_ck_didestimation_composition_techtagged.Rmd`. They read panels via
`../data/...` (= `R/data/`) and write to `../results/...` (= `R/results/`).

**Handoff contract (single source of truth, no manual copying):**
Python writes the R-consumed files directly into `R/data/` and reads R outputs
directly from `R/results/`. Use the `R_DATA_DIR` / `R_RESULTS_DIR` constants in
`config_paths.py` (anchored on `Analyse/`). Do **not** reintroduce a
copy-back-and-forth step or a second copy of the `cs_ready` panels in the
Python tree — a stale panel in `R/data/` makes R silently run on old data
(`run_cs` only warns "column not found -- skipping"). Plot panels stay in the
Python tree; only the four `cs_ready` and four `matched_firms` files cross to
`R/data/`. Safety/versioning is git's job, not folder copies.

## Key datasets and variable names

- `firm_master_ipcei` — firm-level dataset (one row per firm). Saved as
  `firm_master_ipcei_corrected_extended_jan26.csv`.
- `partnership_master` — collaboration-level (one row per partnership; columns
  `source`, `target`, `collaboration_id`, `post_date`, tech flags `Battery`/
  `Hydrogen`, geo flags `is_eu_*`, `is_non_eu`, `is_domestic`).
- `firm_month_outcomes` — firm × month panel of outcome counts. Saved as
  `firm_month_outcomes_extended_jan26.csv`.
- `{battery,hydrogen}_spec{1,2}_cs_ready.csv` — matched CS-ready panels.
  Spec 1 = balance, Spec 2 = power/**primary**.

Outcome columns are all `n_collabs*` (monthly integer counts). R log-transforms
each into `log_collabs*` via `log1p` and a binary `any_collabs*` for
extensive-margin checks. DiD panel columns: `is_treated`, `is_control`,
`matched_to`, `g`, `g_period`, `firm_id`, `period`.

## Outcome construction — the pattern

Outcomes are built in `03-ck-data-preparation.ipynb` (last code cell,
"Extend firm_month_outcomes") with the `_stack_and_count(df_sub, name)`
helper: it stacks `source`+`target` endpoints and counts unique
`collaboration_id` per firm-month over a **masked** partnership frame `p`.

**Technology-tagging is just mask intersection.** A tech-tagged composition
outcome = `_stack_and_count(p[(p[tech]==1) & p[flag]], ...)`. Naming
convention: `n_collabs_{flag}_{tech}` (e.g. `n_collabs_eu_crossborder_hydrogen`).
The plain tech totals `n_collabs_battery` / `n_collabs_hydrogen` are the
**intensity** outcome — they are already tech-tagged; no new column needed.

## How a new outcome flows through the pipeline (3 touch-points)

1. **Prep** (`03`, last cell): add the masked `_stack_and_count` block; it
   merges into `firm_month_outcomes`.
2. **Matching** (`05`, "Save Selected Control Group Specifications" cell): the
   two outcome-column lists are now **programmatic** —
   `[c for c in df.columns if c.startswith("n_collabs")]`. Keep them that way;
   never reintroduce a hardcoded list, or new outcomes get silently dropped
   from the CS-ready panels.
3. **R** (`load_cs()`): log-transforms every `n_collabs*` column generically,
   and `outcome_map` selects the `_battery`/`_hydrogen` column per technology.
   Adding an outcome here = one `outcome_map` entry.

## Methodology conventions — do not change without asking

- **C&S, not Wooldridge ETWFE.** Hydrogen pre-trends show a structured uptick
  4–5 months *before* EC approval (pre-approval partner formation). Wooldridge
  would read this as a parallel-trends violation; C&S only needs parallel
  trends from one period pre-treatment.
- **Treatment date = EC formal approval date** (not national selection);
  financial transfer occurs only post-approval. `anticipation = 0` is defended
  on the same grounds.
- **Matching is per-technology, with replacement**, exact on `nace1_psm` and
  `has_eu_operation`; covariates `log_staffCount`, `age`,
  `log_collab_count_2020`, `degree_centrality_2020`. Control pool excludes all
  IPCEI beneficiaries. Two specs per technology (balance / power).
- **Monthly is the primary time unit**; quarterly is a robustness check (one
  toggle in the R script). Keep monthly primary — the monthly event study is
  the identification argument for choosing C&S.
- **Channel vs placebo:** cross-sector and cross-border EU are policy-goal
  *channel* outcomes; non-EU and within-sector are *placebos*. Tech-tag both
  channels and placebos on the same support.

## Known gotchas

- **Period index must be contiguous (1, 2, 3, …), not `YYYY*100+MM`.**
  `aggte(type="dynamic")` computes event time as `t − g` from raw values, so
  `YYYYMM` coding breaks at year boundaries (Dec→Jan jumps by 89) and silently
  drops post-periods outside `min_e/max_e`. The `type="simple"` headline ATTs
  are unaffected. The current R script codes `period` as a dense rank — keep it.
- **`_x`/`_y` merge duplicates:** prep notebook deliberately keeps `_y` and
  drops `_x` after re-running merge chunks. Don't "fix" this blindly.
- Counts must be **summed then logged** (never average monthly logs) when
  aggregating to quarter.
- High **zero shares** in tech-tagged composition outcomes are expected;
  report extensive-margin (binary) C&S alongside `log1p` for sparse outcomes.

## Plotting

Use `COLORS = {"two": [hydrogen_blue, battery_green]}` for consistent
hydrogen/battery colours, `style_ax(ax)` for axes, `save_fig(fig, folder,
filename)` to save. Hydrogen before battery in two-series plots.

## Writing / LaTeX conventions (for any prose or tables generated)

- No em dashes (use `---` sparingly or rewrite).
- p-values in math mode: `$p = 0.025$`.
- "**Technology-tagged**" (the term used throughout the current draft; not
  technology-focused / tech-domain / tech-specific).
- "**Collaborations**" (not partnerships — distinct objects in the data).
- `\citet{}` in-text, `\citep{}` parenthetical.
- Tables use `booktabs` + `threeparttable`; significance via `\sym{}`.
