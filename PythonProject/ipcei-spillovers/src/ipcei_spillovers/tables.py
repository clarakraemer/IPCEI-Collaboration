# ============================================================
# Paper tables: generate house-format LaTeX (.tex) directly from the
# result CSVs, so there is no CSV -> AI -> reformat step.
#
# Every table is emitted with the project convention (booktabs +
# threeparttable + \sym{} stars + math-mode p) into
#   results/tables/paper/tab_<role>_<slug>.tex
# which mirrors the Overleaf Tables/ folder 1:1 (just upload/sync it and
# \input{Tables/tab_...}).
#
# Preamble the paper needs (once):
#   \usepackage{booktabs}
#   \usepackage{threeparttable}
#   \newcommand{\sym}[1]{\ensuremath{^{#1}}}
#
# Run:  python -m ipcei_spillovers.tables      (regenerates all)
# ============================================================
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from .config_paths import R_RESULTS_DIR, R_DATA_DIR, PATHS
from .io import load_df
from .plotting import PLOT_START, PLOT_END

MAIN_DIR  = PATHS.results_tables / "main"                  # main-text tables
SI_DIR    = PATHS.results_tables / "si"                    # supplementary tables
EXTRA_DIR = PATHS.results_tables / "extra"                 # produced but not in the draft
POSTAUDIT = PATHS.results_tables / "post-audit" / "psm"    # working CSVs feeding the tables

# The SI is a standalone document, so SI tables cannot \ref main-text labels.
MAIN_RESULTS_REF = "Table~1 in the main text"

# Outcome labels as they appear in Table 1 (CSV outcome name -> row label).
# Geography and sector are now classified at the COLLABORATION level, from the
# attributes of all participants, giving mutually exclusive categories. The
# earlier dyad-level outcomes (cross-border EU / non-EU / domestic, and
# cross-sector / within-sector at NACE-2) let one collaboration enter several
# outcomes at once and are no longer reported.
OUTCOME_LABELS = {
    "Technology-tagged collaborations": "Technology-related",
    "EU-internal collaborations":       "EU-internal",
    "Cross-sector collaborations":      "Cross-sector",
    "Total collabs":                    "Total collaborations",
    "Non-funded collaborations":        "Technology-unrelated",
    "Cross-border collaborations":      "Cross-border",
    "International collaborations":     "International",
    "National collaborations":          "National",
    "Same-sector collaborations":       "Same-sector",
}

PSM_TT   = R_RESULTS_DIR / "psm" / "composition_techtagged" / "month"
PSM_INT  = R_RESULTS_DIR / "psm" / "intensity"
UNM_TT   = R_RESULTS_DIR / "unmatched" / "composition_techtagged" / "month"
DIAG_R   = R_RESULTS_DIR / "psm" / "diagnostics"        # round-3 diagnostics (R)
DIAG_PY  = PATHS.results_tables / "diagnostics"         # round-3 diagnostics (Python)
UNM_INT  = R_RESULTS_DIR / "unmatched" / "intensity"


# ---------- formatting helpers ------------------------------------------------
def _exact_p(att, se):
    att, se = float(att), float(se)
    if se == 0:
        return 0.0
    z = abs(att / se)
    return 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))


def star(p):
    p = float(p)
    return "***" if p < 0.01 else "**" if p < 0.05 else "*" if p < 0.10 else ""


def sym(p):
    s = star(p)
    return f"\\sym{{{s}}}" if s else ""


def pstr(p):
    """p-value for a table cell (plain, matches the existing tables)."""
    p = float(p)
    return "$<$0.001" if p < 0.0005 else f"{p:.3f}"


def pct(att):
    return f"{round((math.exp(float(att)) - 1) * 100)}\\%"


def _att_cell(att, se, italic=False):
    """ATT with stars (exact-p based); optionally italicised (failed pre-trend)."""
    a = float(att)
    cell = f"{a:.3f}{sym(_exact_p(a, se))}"
    return f"\\textit{{{cell}}}" if italic else cell


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    print("wrote", path)


# ---------- Table 1: main results (tab_results_main) ---------------------------
def build_results_main():
    tt  = pd.read_csv(PSM_TT / "att_techtagged_table.csv")
    it  = pd.read_csv(PSM_INT / "att_summary_intensity.csv")
    # consortium_size_att.csv used to be concatenated in here for a Panel C on
    # consortium size. That panel was dropped (RUN_CONSORTIUM <- FALSE: neither
    # the zero-filled nor the active-months-only version is identified), so none
    # of the row() calls below ever looked it up. The read was left behind and
    # made Table 1 depend on a file it does not use, which would have crashed
    # the build if that CSV were ever cleaned away. Removed Nov 2026.
    d = {(r.Technology, r.Outcome): r for r in pd.concat([tt, it]).itertuples()}

    # Layout: tabular* at \linewidth with \extracolsep{\fill}; an empty spacer
    # column (GAP) sits between the battery and hydrogen blocks so the two
    # groups read as separate. Rows therefore join the blocks with " & & ".
    def row(label, outcome, mech=False):
        blocks = []
        for tech in ("Battery", "Hydrogen"):
            r = d[(tech, outcome)]
            ital = float(r.pretrend_p_value) < 0.05 if pd.notna(r.pretrend_p_value) else False
            delta = "---" if mech else pct(r.ATT)   # mech kept for level outcomes
            blocks.append(" & ".join([_att_cell(r.ATT, r.SE, ital), delta, f"{float(r.SE):.3f}", pstr(r.p_value)]))
        return f"\\quad {label}\n  & " + " & & ".join(blocks) + " \\\\"

    body = "\n".join([
        r"\multicolumn{10}{l}{\textbf{A. Main collaboration outcomes}} \\[2pt]",
        row("Technology-related",   "Technology-tagged collaborations"),
        row("EU-internal",          "EU-internal collaborations"),
        row("Cross-sector",         "Cross-sector collaborations"),
        r"\multicolumn{10}{l}{\textbf{B. Benchmarks}} \\[2pt]",
        row("Total collaborations",  "Total collabs"),
        row("Technology-unrelated",  "Non-funded collaborations"),
        row("Cross-border",          "Cross-border collaborations"),
        row("International",         "International collaborations"),
        row("National",              "National collaborations"),
        row("Same-sector",           "Same-sector collaborations"),
    ])

    # Panel C (the funded-minus-unrelated contrast) is not reported in the first
    # submission. The estimates remain in results/psm/diagnostics/.

    nbt = int(d[("Battery", "Total collabs")].N_units); tbt = int(d[("Battery", "Total collabs")].N_treated)
    nht = int(d[("Hydrogen", "Total collabs")].N_units); tht = int(d[("Hydrogen", "Total collabs")].N_treated)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table*}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Effect of IPCEI approval on firm collaboration}}
\label{{tab:main_results}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rrrr c rrrr @{{}}}}
\toprule\toprule
& \multicolumn{{4}}{{c}}{{\textbf{{Battery IPCEI}}}}
& & \multicolumn{{4}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-5}}\cmidrule(lr){{7-10}}
& ATT & $\Delta$ & SE & $p$ & & ATT & $\Delta$ & SE & $p$ \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\setlength{{\itemsep}}{{2pt}}
\small
\item \textit{{Notes:}} Callaway--Sant'Anna estimator \citep{{callaway2021difference}} (\texttt{{did}} v2.3.0) on the matched sample with never-treated controls. Battery $N={nbt}$ ({tbt} treated); hydrogen $N={nht}$ ({tht} treated). Standard errors clustered at the firm level, $9{{,}}999$ bootstrap replications. Outcomes are monthly collaboration counts in $\log(1+y)$; $\%\Delta = 100[\exp(\widehat{{ATT}})-1]$. Geographic and sectoral outcomes are classified from all participants of a collaboration, so national and cross-border, and same-sector and cross-sector, are mutually exclusive pairs; cross-border splits into EU-internal and international. \textit{{Italicised}} estimates fail the joint pre-trend test.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table*}}
"""
    _write(MAIN_DIR / "tab_results_main.tex", tex)


# ---------- Table 4: robustness (tab_results_appendix) ------------------------
def build_results_appendix():
    rb = pd.read_csv(PSM_TT / "robustness_techtagged_table.csv")
    # Total collaborations is estimated in the intensity script, not the
    # composition one, so it was missing from panels A and B while panel C
    # carried it. Fold it in, so every panel reports the same rows as Table 1.
    # NB: in att_summary_table.csv "Specification" holds the technology and
    # "Type" holds the robustness arm.
    ti = (pd.read_csv(PSM_INT / "att_summary_table.csv")
            .rename(columns={"Specification": "Technology"}))
    ti["Outcome"] = "Total collabs"
    rb = pd.concat(
        [rb, ti.loc[ti["Type"] != "Primary",
                    ["Technology", "Outcome", "Type", "ATT", "SE",
                     "p_value", "N_units"]]],
        ignore_index=True)

    def _nu(typ, tech):
        s = rb[(rb["Type"] == typ) & (rb["Technology"] == tech)]
        return str(int(s["N_units"].iloc[0])) if len(s) else "---"
    NA = f'{_nu("Larger control group","Battery")}/{_nu("Larger control group","Hydrogen")}'
    NB = _nu("Not-yet-treated controls", "Hydrogen")
    # Same layout as Table 1: tabular* at \linewidth with a spacer column
    # between the battery and hydrogen blocks (blocks joined with " & & ").
    # Within-sector is deliberately not listed here (Table 1 placebo only).
    label_map = {k: v for k, v in OUTCOME_LABELS.items() if k != "Within-sector collaborations"}
    order = list(label_map.keys())

    def panel(type_value, techs=("Battery", "Hydrogen"), nstr=""):
        sub = rb[rb["Type"] == type_value]
        d = {(r.Technology, r.Outcome): r for r in sub.itertuples()}
        lines = []
        for oc in [o for o in order if o in set(sub["Outcome"])]:
            blocks = []
            for tech in techs:
                if (tech, oc) in d:
                    r = d[(tech, oc)]
                    blocks.append(" & ".join([f"{float(r.ATT):.3f}{sym(_exact_p(r.ATT, r.SE))}", f"{float(r.SE):.3f}", pstr(r.p_value)]))
                else:
                    blocks.append("--- & --- & ---")
            lines.append(f"\\quad {label_map[oc]} & {nstr} & " + " & & ".join(blocks) + r" \\")
        return "\n".join(lines)

    a = panel("Larger control group", nstr=NA)
    # Panel B only hydrogen: pad battery columns with ---
    b_lines = []
    subB = rb[rb["Type"] == "Not-yet-treated controls"]
    dB = {(r.Technology, r.Outcome): r for r in subB.itertuples()}
    for oc in [o for o in order if o in set(subB["Outcome"])]:
        r = dB[("Hydrogen", oc)]
        b_lines.append(rf"\quad {label_map[oc]} & {NB} & --- & --- & --- & & {float(r.ATT):.3f}{sym(_exact_p(r.ATT,r.SE))} & {float(r.SE):.3f} & {pstr(r.p_value)} \\")
    b = "\n".join(b_lines)

    # Rosenbaum bounds are no longer reported. `rbounds::psens` is the Wilcoxon
    # signed-rank sensitivity for INDEPENDENT 1:1 matched pairs, whereas the
    # design is 1:3 (battery) and 1:2 (hydrogen) collapsed to a control mean,
    # and 1 battery / 5 hydrogen controls sit in two matched sets at once, so
    # set independence fails. A valid matched-set procedure exists
    # (Rosenbaum's sensitivitymult::senm) but is not installed, and the
    # contrast's estimand (full pre-window baseline) differs from the C&S
    # estimand (baseline at g-1), which matters for hydrogen. The old panel is
    # kept in git history; rosenbaum_bounds_techtagged.csv is retained and
    # marked obsolete rather than deleted.

    # Panel C: no matching (unmatched eligible pool, doubly-robust). Same layout
    # as Panel A; hydrogen italicised where it fails the joint pre-trend test.
    ut = pd.read_csv(UNM_TT / "att_techtagged_table.csv")
    ui = pd.read_csv(UNM_INT / "att_summary_intensity.csv")
    ui = ui[ui["Type"] == "Primary"]                      # DR total (not the raw diagnostic)
    # The unmatched run still writes the legacy dyad-level NACE-2 estimate under
    # the SAME label as the reported collaboration-level NACE-1 one
    # ("Cross-sector collaborations"), so (Technology, Outcome) is not unique.
    # The reported block is written last by the R script, hence keep="last" --
    # but that is an ordering assumption, so say out loud what was dropped. If
    # this ever prints an unexpected label, Panel C has silently changed
    # definition and the R spec is what to check.
    _uall = pd.concat([ut, ui])
    _dups = _uall[_uall.duplicated(subset=["Technology", "Outcome"], keep="last")]
    if len(_dups):
        print("  appendix panel C: superseded duplicates dropped -> "
              + ", ".join(sorted({f"{r.Technology}/{r.Outcome}"
                                  for r in _dups.itertuples()})))
    _uall = _uall.drop_duplicates(subset=["Technology", "Outcome"], keep="last")
    du = {(r.Technology, r.Outcome): r for r in _uall.itertuples()}
    ND = f'{int(ut[ut["Technology"]=="Battery"]["N_units"].iloc[0])}/{int(ut[ut["Technology"]=="Hydrogen"]["N_units"].iloc[0])}'


    def urow(lab, oc):
        blocks = []
        for tech in ("Battery", "Hydrogen"):
            r = du.get((tech, oc))
            if r is None:
                blocks.append("--- & --- & ---")
                continue
            ital = float(r.pretrend_p_value) < 0.05 if pd.notna(r.pretrend_p_value) else False
            a = f"{float(r.ATT):.3f}{sym(_exact_p(r.ATT, r.SE))}"
            a = f"\\textit{{{a}}}" if ital else a
            blocks.append(" & ".join([a, f"{float(r.SE):.3f}", pstr(r.p_value)]))
        return f"\\quad {lab} & {ND} & " + " & & ".join(blocks) + r" \\"

    # Same row set and same order as panels A and B, which is the order of
    # Table 1. The hardcoded six-row list this replaces silently omitted
    # technology-unrelated, national and same-sector, although the unmatched
    # run estimates all three, so panel C could not be read down a column
    # against the panels above it.
    dpanel = "\n".join(
        urow(label_map[oc], oc) for oc in order
        if ("Battery", oc) in du or ("Hydrogen", oc) in du)

    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Robustness checks for the main results}}
\label{{tab:robustness}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l c rrl c rrl @{{}}}}
\toprule\toprule
& & \multicolumn{{3}}{{c}}{{\textbf{{Battery IPCEI}}}}
  & & \multicolumn{{3}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{3-5}}\cmidrule(lr){{7-9}}
& $N$ & ATT & SE & $p$ & & ATT & SE & $p$ \\
\midrule
\multicolumn{{9}}{{l}}{{\textbf{{A. Larger control group}}}} \\[2pt]
{a}
\multicolumn{{9}}{{l}}{{\textbf{{B. Not-yet-treated control group}}}} \\[2pt]
{b}
\multicolumn{{9}}{{l}}{{\textbf{{C. No matching (unmatched eligible pool, doubly-robust)}}}} \\[2pt]
{dpanel}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Robustness checks for the outcomes in {MAIN_RESULTS_REF}; ATT, SE and $p$ as defined there. $N$ is the number of firms (battery/hydrogen). Panel~A uses the larger-control-group matching specification. Panel~B substitutes not-yet-treated for never-treated controls, for hydrogen only, since the single battery cohort has no not-yet-treated units. Panel~C drops matching and estimates on all eligible controls with doubly robust adjustment. \textit{{Italicised}} estimates fail the joint pre-trend test.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_appendix.tex", tex)


# ---------- SI: pre-trend comparison (tab_results_pretrend-comparison) --------
def build_results_pretrend():
    cols = ["Technology", "Outcome", "pretrend_p_value"]
    psm = pd.read_csv(PSM_TT / "att_techtagged_table.csv")[cols].rename(columns={"pretrend_p_value": "psm"})
    unm = pd.read_csv(UNM_TT / "att_techtagged_table.csv")[cols].rename(columns={"pretrend_p_value": "unm"})
    m = psm.merge(unm, on=["Technology", "Outcome"])
    d = {(r.Technology, r.Outcome): r for r in m.itertuples()}
    # Same block layout as Table 1: outcomes x (Battery | Hydrogen), each block
    # matched vs unmatched, spacer column between the technologies. Total
    # collaborations is estimated in the intensity scripts and not part of
    # the pre-trend comparison.
    # Grouped order: technology pair, then geography, then sector.
    order = ["Technology-tagged collaborations", "Non-funded collaborations",
             "Cross-border collaborations", "EU-internal collaborations",
             "International collaborations", "National collaborations",
             "Cross-sector collaborations", "Same-sector collaborations"]

    def cell(p):
        p = float(p)
        s = "$<$0.001" if p < 0.0005 else f"{p:.3f}"
        return f"\\textbf{{{s}}}" if p < 0.05 else s

    lines = []
    for oc in order:
        # Skip outcomes with no unmatched counterpart (e.g. added to the PSM run
        # after the last unmatched run); an all-"---" row carries no information.
        if not any((t, oc) in d for t in ("Battery", "Hydrogen")):
            continue
        blocks = []
        for tech in ("Battery", "Hydrogen"):
            r = d.get((tech, oc))
            blocks.append(f"{cell(r.psm)} & {cell(r.unm)}" if r is not None else "--- & ---")
        lines.append(f"\\quad {OUTCOME_LABELS[oc]} & " + " & & ".join(blocks) + r" \\")
    body = "\n".join(lines)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{5pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Joint pre-trend tests with and without matching}}
\label{{tab:pretrend_comparison}}
\begin{{threeparttable}}
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rr c rr @{{}}}}
\toprule\toprule
& \multicolumn{{2}}{{c}}{{\textbf{{Battery IPCEI}}}}
& & \multicolumn{{2}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-3}}\cmidrule(lr){{5-6}}
& Matched & Unmatched & & Matched & Unmatched \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} $p$-values of the joint test that all pre-treatment event-study coefficients are zero, for the outcomes in {MAIN_RESULTS_REF}. \textit{{Matched}} is the primary specification; \textit{{unmatched}} estimates on all eligible controls with doubly robust adjustment (Table~\ref{{tab:robustness}}, Panel~C). Values below 0.05 (in \textbf{{bold}}) reject parallel pre-treatment trends.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_pretrend-comparison.tex", tex)


# ---------- Discussion: activity mix (tab_descriptive_activity-mix) -----------
def build_descriptive_activity_mix():
    t = pd.read_csv(POSTAUDIT / "activity_mix_prepost.csv")
    c = pd.read_csv(POSTAUDIT / "activity_mix_prepost_control_benchmark.csv")
    acts = ["R&D", "Demonstration / pilot", "Production / manufacturing",
            "Commercialisation", "Adoption / deployment"]
    # Treated change and matched-control change side by side, so the
    # difference-in-differences reading is explicit (this is the point of
    # the exhibit: battery shifts toward production, the controls do not).
    lines = []
    for a in acts:
        blocks = []
        for tech in ("Battery", "Hydrogen"):
            r = t[(t.Activity == a) & (t.Technology == tech)].iloc[0]
            cd = c[(c.Activity == a) & (c.Technology == tech)].iloc[0]["ctrl_delta"]
            blocks.append(" & ".join([f"{r.pre:.1f}", f"{r.post:.1f}",
                                      f"{float(r.delta):+.1f}", f"{cd:+.1f}"]))
        lines.append(f"{a.replace('&', chr(92) + '&')} & " + " & & ".join(blocks) + r" \\")
    body = "\n".join(lines)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Activity mix of IPCEI firms' technology-related collaborations around approval}}
\label{{tab:activity_mix}}
\begin{{threeparttable}}
\footnotesize
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rrrr c rrrr @{{}}}}
\toprule\toprule
& \multicolumn{{4}}{{c}}{{\textbf{{Battery IPCEI}}}}
& & \multicolumn{{4}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-5}}\cmidrule(lr){{7-10}}
Activity & Before & After & $\Delta$ & Control $\Delta$
& & Before & After & $\Delta$ & Control $\Delta$ \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Share (\%) of IPCEI firms' technology-related collaborations carrying each activity tag, months $-12$ to $-1$ and $0$ to $12$ relative to approval. $\Delta$ is the change in percentage points; \textit{{control}} $\Delta$ is the same change for matched controls around their treated firm's approval date. Tags are not mutually exclusive, so columns do not sum to 100\%.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_activity-mix.tex", tex)


# ---------- Descriptive: top-10 firms (tab_descriptive_active-firms) ----------
def build_descriptive_active_firms():
    base = POSTAUDIT
    b = pd.read_csv(base / "top10_battery_ipcei_firms.csv")
    h = pd.read_csv(base / "top10_hydrogen_ipcei_firms.csv")

    # map Linkedin_name slug -> display name (top10 CSVs carry only the slug)
    fm = pd.read_csv(PATHS.data_interim / "combined" /
                     "firm_master_ipcei_corrected_extended_jan26.csv",
                     usecols=["Linkedin_name", "name"], low_memory=False)
    slug2name = fm.drop_duplicates("Linkedin_name").set_index("Linkedin_name")["name"].to_dict()

    def name(row):
        disp = slug2name.get(row["Linkedin_name"], row["Linkedin_name"])
        return str(disp).replace("&", r"\&")
    lines = []
    for i in range(10):
        rb, rh = b.iloc[i], h.iloc[i]
        lines.append(
            f"{int(rb['rank'])} & {name(rb)} & {rb['primary_country']} & {int(rb['n_collabs']):,} & "
            f"{int(rh['rank'])} & {name(rh)} & {rh['primary_country']} & {int(rh['n_collabs']):,} \\\\")
    body = "\n".join(lines)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table*}}[!ht]
\centering
\setlength{{\tabcolsep}}{{5pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Top 10 IPCEI firms by cumulative number of unique collaborations, 2020--2025}}
\label{{tab:top_ipcei_firms}}
\begin{{threeparttable}}
\begin{{tabular}}{{r l c r r l c r}}
\toprule\toprule
\multicolumn{{4}}{{c}}{{\textbf{{Battery IPCEI firms}}}} & \multicolumn{{4}}{{c}}{{\textbf{{Hydrogen IPCEI firms}}}} \\
\cmidrule(lr){{1-4}} \cmidrule(lr){{5-8}}
Rank & Firm & Country & Collaborations & Rank & Firm & Country & Collaborations \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Ranked by the cumulative number of unique collaboration IDs per firm over 2020--2025. Country codes are the firm's primary country (ISO-2). Firms can appear in both columns if tagged in both technologies.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table*}}
"""
    _write(EXTRA_DIR / "tab_descriptive_active-firms.tex", tex)


# ---------- Descriptive: partner overlap (tab_descriptive_partner-overlap) ----
def build_descriptive_partner_overlap():
    base = POSTAUDIT
    b = pd.read_csv(base / "battery_spec2_partner_overlap_summary.csv").iloc[0]
    h = pd.read_csv(base / "hydrogen_spec2_partner_overlap_summary.csv").iloc[0]
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table*}}[!ht]
\centering
\setlength{{\tabcolsep}}{{8pt}}
\renewcommand{{\arraystretch}}{{1.2}}
\caption{{Overlap in collaboration partners between treated firms and matched controls}}
\label{{tab:partner_overlap}}
\begin{{threeparttable}}
\begin{{tabular}}{{l r r r r r r}}
\toprule\toprule
& \multicolumn{{3}}{{c}}{{\textbf{{Battery IPCEI}}}} & \multicolumn{{3}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-4}} \cmidrule(lr){{5-7}}
& Mean & Median & Share (\%) & Mean & Median & Share (\%) \\
\midrule
\quad Treated--control pairs
  & \multicolumn{{3}}{{c}}{{{int(b.n_pairs)}}} & \multicolumn{{3}}{{c}}{{{int(h.n_pairs)}}} \\[2pt]
\quad Pairs with any shared partner
  & \multicolumn{{2}}{{c}}{{--}} & {b.share_with_any_overlap_pct:.1f}
  & \multicolumn{{2}}{{c}}{{--}} & {h.share_with_any_overlap_pct:.1f} \\[2pt]
\quad Number of shared partners
  & {b.mean_shared_partners:.2f} & {b.median_shared_partners:.2f} & --
  & {h.mean_shared_partners:.2f} & {h.median_shared_partners:.2f} & -- \\[2pt]
\quad Jaccard overlap
  & {b.mean_jaccard_overlap:.4f} & {b.median_jaccard_overlap:.4f} & --
  & {h.mean_jaccard_overlap:.4f} & {h.median_jaccard_overlap:.4f} & -- \\
\bottomrule\bottomrule
\end{{tabular}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Overlap in collaboration partners between treated IPCEI firms and their matched controls (larger-control specification). Partner sets are all observed collaborations over 2020--2025. The Jaccard index is shared/total unique partners.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table*}}
"""
    _write(EXTRA_DIR / "tab_descriptive_partner-overlap.tex", tex)


# ---------- SI: collaboration categories (tab_descriptive_collab-types) -------
# Column name -> table label. Collaboration-level counts within the paper's
# analysis window (PLOT_START..PLOT_END); a collaboration carries a tag if any
# of its dyads does. Categories are not mutually exclusive.
TECH_LABELS = {
    "Solar": "Solar", "Electric_Vehicles": "Electric vehicles", "Hydrogen": "Hydrogen",
    "Battery": "Battery", "Wind": "Wind", "Offshore_Wind": "Offshore wind",
    "Other_Technology": "Other technology", "Biogas": "Biogas",
    "Carbon_Capture_And_Storage": "Carbon capture and storage (CCS)",
    "Electric_Shipping": "Electric shipping", "Heat_Pumps": "Heat pumps",
    "Biofuels": "Biofuels", "Sustainable_Aviation_Fuels": "Sustainable aviation fuels",
    "Nuclear_Energy": "Nuclear energy", "Geothermal": "Geothermal",
    "Marine_Energy": "Marine energy", "Hydro_Energy": "Hydro energy", "Biomass": "Biomass",
    "Railway": "Railway", "Fuel_Cell_Aviation": "Fuel cell aviation", "E_Fuels": "E-fuels",
    "Electric_Aviation": "Electric aviation", "Waste_to_Heat": "Waste-to-heat",
    "Carbon_Direct_Removal": "Carbon direct removal", "Biochar": "Biochar",
    "Direct_Air_Capture": "Direct air capture", "Nuclear_Fusion": "Nuclear fusion",
    "Concentrated_Solar": "Concentrated solar", "BECCS": "Bioenergy with CCS",
}
ACTIVITY_LABELS = {
    "adoption_and_deployments": "Adoption and deployment",
    "r_and_d_collaborations": r"R\&D",
    "demonstrations_and_pilots": "Demonstrations and pilots",
    "grants": "Grants", "equity_investments": "Equity investments",
    "production_and_manufacturing": "Production and manufacturing",
    "offtake_agreements_and_futures": "Offtake agreements and futures",
    "commercialisation_and_product_launches": "Commercialisation and launches",
    "training": "Training", "other_unspecified_finance": "Other unspecified finance",
    "joint_ventures": "Joint ventures", "loans": "Loans",
    "operations_and_maintenance": "Operations and maintenance",
    "certification_and_approvals": "Certification and approvals",
    "incubators_and_accelerator_programs": "Incubators and accelerators",
    "spin_offs": "Spin-offs",
}
DOMAIN_LABELS = {
    "core_technology": "Core technology", "infrastructure": "Infrastructure",
    "software_and_digital_platforms": "Software and digital platforms",
    "other_complementary_activities": "Other complementary", "recycling": "Recycling",
    "raw_materials": "Raw materials",
}


def build_descriptive_collab_types():
    flags = list(TECH_LABELS) + list(ACTIVITY_LABELS) + list(DOMAIN_LABELS)
    pm = load_df("interim", "combined", "partnership_master_ipcei_jan26.csv",
                 usecols=["collaboration_id", "post_date"] + flags, low_memory=False)
    pm["post_date"] = pd.to_datetime(pm["post_date"], errors="coerce")
    agg = {"post_date": ("post_date", "min"), **{f: (f, "max") for f in flags}}
    c = pm.groupby("collaboration_id").agg(**agg)
    c = c[(c["post_date"] >= PLOT_START) & (c["post_date"] < PLOT_END)]
    n_total = len(c)

    def rows(labels):
        counts = c[list(labels)].sum().sort_values(ascending=False)
        return [f"{labels[k]} & {int(v):,} & {100 * v / n_total:.1f}" for k, v in counts.items()]

    left = rows(TECH_LABELS)
    right = (rows(ACTIVITY_LABELS)
             + [r"& & ", r"\multicolumn{3}{l}{\textbf{C. Activity domain}}", r"Category & $N$ & \%"]
             + rows(DOMAIN_LABELS))
    n = max(len(left), len(right))
    left  += [r"& & "] * (n - len(left))
    right += [r"& & "] * (n - len(right))
    body = "\n".join(f"{l} & & {r} \\\\" for l, r in zip(left, right))

    start, end = PLOT_START.year, (PLOT_END - pd.Timedelta(days=1)).year
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.12}}
\caption{{Collaboration categories in the dataset, {start}--{end}}}
\label{{tab:collab_types}}
\begin{{threeparttable}}
\footnotesize
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l r r c l r r @{{}}}}
\toprule\toprule
\multicolumn{{3}}{{l}}{{\textbf{{A. Technology}}}} & & \multicolumn{{3}}{{l}}{{\textbf{{B. Activity type}}}} \\
Category & $N$ & \% & & Category & $N$ & \% \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Counts at the collaboration level, {start}--{end} ($N = {str(f'{n_total:,}').replace(',', '{{,}}')}$). A collaboration is assigned to a category if any constituent organisation pair carries the tag. Categories are not mutually exclusive, so shares within a panel do not sum to 100\%. Tags follow \citet{{ToetzkeEtAl2025}}; activity type is the purpose of the collaboration, activity domain the part of the value chain.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_collab-types.tex", tex)



# ---------- SI: matching attrition (tab_descriptive_attrition) ----------------
def build_descriptive_attrition():
    """Treated firms lost to matching, and how they differ from those retained."""
    import numpy as np
    fm = load_df("interim", "combined",
                 "firm_master_ipcei_corrected_extended_jan26.csv", low_memory=False)
    rows = []
    n_pre = {}
    for tech in ("battery", "hydrogen"):
        # Only firms whose approval falls inside the panel window can be matched
        # at all. The 17 battery firms approved in December 2019 are excluded
        # before matching because the collaboration data start in 2020; counting
        # them as "lost" reported battery attrition as 29 of 47 instead of 29 of 30.
        appr = pd.to_datetime(fm[f"first_{tech}_date"], errors="coerce")
        in_window = appr.notna() & (appr >= PLOT_START) & (appr < PLOT_END)
        n_pre[tech] = int((appr.notna() & ~in_window).sum())
        tr = set(fm.loc[in_window, "Linkedin_name"])
        mf = pd.read_csv(R_DATA_DIR / f"{tech}_psm_spec1_matched_firms.csv", low_memory=False)
        matched = set(mf.loc[mf.is_treated == 1, "Linkedin_name"])
        sub = fm[fm.Linkedin_name.isin(tr)].copy()
        sub["matched"] = sub.Linkedin_name.isin(matched)
        r = {"Technology": tech.capitalize(),
             "n_matched": int(sub.matched.sum()), "n_unmatched": int((~sub.matched).sum())}
        for v, lab in [("collab_count_2020", "collab"), ("staffCount", "staff"), ("age", "age")]:
            g = sub.groupby("matched")[v].median()
            r[f"{lab}_matched"] = g.get(True, np.nan)
            r[f"{lab}_unmatched"] = g.get(False, np.nan)
        rows.append(r)
    d = pd.DataFrame(rows)
    body = "\n".join(
        f"{r.Technology} & {r.n_matched} & {r.n_unmatched} & & "
        f"{r.collab_matched:.0f} & {r.collab_unmatched:.0f} & & "
        f"{r.staff_matched:,.0f} & {r.staff_unmatched:,.0f} & & "
        f"{r.age_matched:.0f} & {r.age_unmatched:.0f} \\\\" for r in d.itertuples())
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{5pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Treated firms retained and lost in matching}}
\label{{tab:attrition}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rr c rr c rr c rr @{{}}}}
\toprule\toprule
& \multicolumn{{2}}{{c}}{{Firms}} & & \multicolumn{{2}}{{c}}{{Collaborations 2020}}
& & \multicolumn{{2}}{{c}}{{Employees}} & & \multicolumn{{2}}{{c}}{{Age}} \\
\cmidrule(lr){{2-3}}\cmidrule(lr){{5-6}}\cmidrule(lr){{8-9}}\cmidrule(lr){{11-12}}
& Matched & Lost & & Matched & Lost & & Matched & Lost & & Matched & Lost \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Treated firms with no comparable control are dropped by the matching procedure. The sample is firms approved within the observation window; the {n_pre['battery']} battery firms approved in December 2019 are excluded beforehand, since the collaboration data begin in 2020. Entries are medians, except battery \textit{{Lost}}, which is a single firm.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_attrition.tex", tex)



# ---------- SI: complementary estimands (tab_results_estimands) ---------------
def build_results_estimands():
    """log1p, extensive-margin and raw-count effects on the same matched sample.

    Three different estimands on the same treated firms, controls and cohorts.
    They are deliberately not expressed in a common unit: the raw-count ATT is
    a level effect in collaborations per firm-month and must not be divided by
    a pre-treatment mean to manufacture a percentage.
    """
    f = DIAG_R / "p5_relative_and_counts.csv"
    if not f.exists():
        print("skip tab_results_estimands: run 10_ck_diagnostics_reference_country.R")
        return
    d = pd.read_csv(f)
    prim = pd.read_csv(PSM_TT / "att_techtagged_table.csv")

    def cell(att, se, p):
        return f"{float(att):.3f}{sym(float(p))} & {float(se):.3f} & {pstr(p)}"

    rows = []
    # log1p row comes from the primary table, so the three estimands are
    # anchored on the published estimate rather than re-estimated.
    pr = {r.Technology: r for r in prim[prim.Outcome == "Technology-tagged collaborations"].itertuples()}
    rows.append(r"\quad Log $(1+y)$, the reported specification" + "\n  & "
                + " & & ".join(cell(pr[t].ATT, pr[t].SE, pr[t].p_value)
                               for t in ("Battery", "Hydrogen")) + r" \\")
    for lab, oc in [("Any collaboration, extensive margin",
                     "Technology-related (any collaboration)"),
                    ("Raw count per firm-month",
                     "Technology-related (raw count)")]:
        sub = d[(d.outcome == oc) & (d.anticipation == 0)]
        if len(sub) != 2:
            continue
        g = {r.technology: r for r in sub.itertuples()}
        rows.append(rf"\quad {lab}" + "\n  & "
                    + " & & ".join(cell(g[t].att, g[t].se, g[t].p)
                                   for t in ("Battery", "Hydrogen")) + r" \\")
    body = "\n".join(rows)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Technology-related collaboration under three outcome definitions}}
\label{{tab:estimands}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rrr c rrr @{{}}}}
\toprule\toprule
& \multicolumn{{3}}{{c}}{{\textbf{{Battery IPCEI}}}}
& & \multicolumn{{3}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-4}}\cmidrule(lr){{6-8}}
& ATT & SE & $p$ & & ATT & SE & $p$ \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Rows are different estimands on the same matched samples, cohorts and controls, and are not comparable in size. Row~1 is the estimate in {MAIN_RESULTS_REF}; row~2 replaces the outcome by an indicator for any technology-related collaboration in the month; row~3 uses the untransformed count, a level effect that is not converted into a percentage. Secondary analyses with nominal $p$-values.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_estimands.tex", tex)


# ---------- SI: cohort effects and country sensitivity -----------------------
def build_results_cohort_country():
    fa, fb = DIAG_R / "p2a_cohort_atts_hydrogen.csv", DIAG_R / "p2b_germany_exclusion_hydrogen.csv"
    if not (fa.exists() and fb.exists()):
        print("skip tab_results_cohort-country: run the diagnostics script")
        return
    a = pd.read_csv(fa); b = pd.read_csv(fb)
    a = a[a.horizon == "e 0-12"]
    outs = ["Technology-related", "Cross-border EU", "Technology-unrelated"]

    coh = sorted(a.cohort.unique())
    nde = pd.read_csv(DIAG_R / "p2c_within_cohort_support.csv")
    nmap = {r.cohort: (int(r.DE), int(r.non_DE)) for r in nde.itertuples()}

    # Six columns, not nine. The earlier version carried a separate p column per
    # outcome and overflowed the text block by ~106pt; significance now rides on
    # the stars and the exact p-values stay in the result CSVs.
    rows = [r"\multicolumn{6}{l}{\textbf{A. Cohort-specific effects, months 0--12}} \\[2pt]"]
    for c in coh:
        de, non = nmap.get(c, (0, 0))
        cells = [(f"{float(r.att.iloc[0]):.3f}{sym(float(r.p.iloc[0]))}" if len(r) else "---")
                 for oc in outs
                 for r in [a[(a.cohort == c) & (a.outcome == oc)]]]
        rows.append(rf"\quad {c} & {de + non} & {de} & " + " & ".join(cells) + r" \\")
    rows.append(r"\multicolumn{6}{l}{\textbf{B. Excluding German firms}} \\[2pt]")
    lab = {"full": "Full matched sample",
           "drop DE treated": "Excluding German treated firms",
           "drop all DE firms": "Excluding all German firms"}
    for k, l in lab.items():
        sub = b[b["sample"] == k]
        if sub.empty:
            continue
        nt = int(sub.n_treated.iloc[0])
        cells = [(f"{float(r.att.iloc[0]):.3f}{sym(float(r.p.iloc[0]))}" if len(r) else "---")
                 for oc in outs
                 for r in [sub[sub.outcome == oc]]]
        rows.append(rf"\quad {l} & {nt} & --- & " + " & ".join(cells) + r" \\")
    body = "\n".join(rows)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Hydrogen effects by approval cohort and in samples excluding German firms}}
\label{{tab:cohort_country}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rr rrr @{{}}}}
\toprule\toprule
& \multicolumn{{2}}{{c}}{{Treated firms}} & \multicolumn{{3}}{{c}}{{ATT}} \\
\cmidrule(lr){{2-3}}\cmidrule(lr){{4-6}}
& Total & German & \textit{{Technology-}} & \textit{{Cross-border}} & \textit{{Technology-}} \\[-2pt]
& & & \textit{{related}} & \textit{{EU}} & \textit{{unrelated}} \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Hydrogen only. Panel~A reports cohort-specific effects from \texttt{{aggte(type = "group")}} over the common 0--12 month horizon, with the number of treated firms and the number headquartered in Germany. Panel~B re-estimates the overall effect on samples excluding German firms; no control firm is matched exclusively to a German treated firm. Stars mark significance; exact $p$-values are in the replication files.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_cohort-country.tex", tex)


# ---------- SI: reference period and event-time split ------------------------
def build_results_reference_period():
    f1, f3 = DIAG_R / "p1_cohort_reconciliation.csv", DIAG_R / "p3_eventtime_split_hydrogen.csv"
    if not (f1.exists() and f3.exists()):
        print("skip tab_results_reference-period: run the diagnostics script")
        return
    r1 = pd.read_csv(f1); r3 = pd.read_csv(f3)
    outs = ["Technology-related", "Cross-border EU", "Technology-unrelated"]

    rows = [r"\multicolumn{6}{l}{\textbf{A. Reference-period sensitivity by cohort}} \\[2pt]",
            r"\quad \textit{Cohort} & \textit{Treated} & \textit{Weight} & "
            r"\textit{Baseline} & \textit{Anticipation 3} & \textit{Difference} \\[1pt]"]
    sub = r1[r1.outcome == "Technology-related"].sort_values("cohort")
    for r in sub.itertuples():
        rows.append(rf"\quad {r.cohort} & {int(r.n_g)} & {r.weight:.3f} & "
                    rf"{r.att0:.3f} & {r.att3:.3f} & {r.gap:+.3f} \\")
    # Overall ATTs and the share of the change carried by the largest cohort,
    # both computed here so the note cannot drift from the panel.
    tot0 = float((sub.weight * sub.att0).sum())
    tot3 = float((sub.weight * sub.att3).sum())
    chg = tot3 - tot0
    top = sub.loc[(sub.weight * sub.gap).abs().idxmax()]
    top_share = round(100 * float(top.weight * top.gap) / chg) if chg else 0
    top_month = pd.Period(top.cohort, freq="M").strftime("%B %Y")
    rows.append(r"\addlinespace[2pt]")
    rows.append(rf"\quad \textit{{Overall}} & {int(sub.n_g.sum())} & 1.000 & \textit{{{tot0:.3f}}} & "
                rf"\textit{{{tot3:.3f}}} & \textit{{{chg:+.3f}}} \\")
    # Panel B has no use for the Treated and Weight columns, so its row labels
    # span the first three columns instead of leaving two cells empty.
    rows.append(r"\multicolumn{6}{l}{\textbf{B. Effects by event-time window}} \\[2pt]")
    rows.append(r"\multicolumn{3}{l}{\quad \textit{Window}} & \textit{Technology-} & "
                r"\textit{Cross-border} & \textit{Technology-} \\[-2pt]"
                "\n" r"\multicolumn{3}{l}{} & \textit{related} & \textit{EU} & "
                r"\textit{unrelated} \\[1pt]")
    wl = {"e 0-0": "Approval month", "e 1-3": "Months 1--3",
          "e 4-12": "Months 4--12", "e 1-12": "Months 1--12"}
    for w, l in wl.items():
        cells = []
        for oc in outs:
            s = r3[(r3.window == w) & (r3.outcome == oc)]
            cells.append(f"{float(s.att.iloc[0]):.3f}{sym(float(s.p.iloc[0]))}" if len(s) else "---")
        rows.append(rf"\multicolumn{{3}}{{l}}{{\quad {l}}} & " + " & ".join(cells) + r" \\")
    body = "\n".join(rows)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{5pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Timing of the hydrogen effects on collaboration}}
\label{{tab:reference_period}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rr rrr @{{}}}}
\toprule\toprule
& & & \multicolumn{{3}}{{c}}{{ATT}} \\
\cmidrule(lr){{4-6}}
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Hydrogen only. Panel~A gives cohort-level ATTs for technology-related collaboration under two reference periods, the month before approval (\textit{{Baseline}}) and four months before it (\textit{{Anticipation 3}}), holding cohorts, controls and post-approval months fixed. \textit{{Difference}} is the change in a cohort's outcome relative to controls between the two reference months, \textit{{Weight}} its share in the overall aggregation; the {top_month} cohort accounts for {abs(top_share)}\% of the change. Panel~B gives the baseline specification aggregated over event-time windows for three outcomes.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_reference-period.tex", tex)

# ---------- SI: country balance (tab_descriptive_country-balance) -------------
def build_descriptive_country_balance():
    d = pd.read_csv(POSTAUDIT / "country_balance.csv")
    lines = []
    for tech in ("Battery", "Hydrogen"):
        sub = d[d.technology == tech].sort_values("Treated", ascending=False).head(6)
        lines.append(rf"\multicolumn{{4}}{{l}}{{\textbf{{{tech} IPCEI}}}} \\[2pt]")
        for r in sub.itertuples():
            lines.append(f"\\quad {r.country} & {r.Treated:.1f} & {r.Control:.1f} & {r.diff_pp:+.1f} \\\\")
    body = "\n".join(lines)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{6pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Country composition of treated and control firms}}
\label{{tab:country_balance}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rrr @{{}}}}
\toprule\toprule
Country & Treated (\%) & Control (\%) & Difference (pp) \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Share of firms by headquarters country in the primary matched sample, six largest treated shares per technology. Matching does not condition on country.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_country-balance.tex", tex)


# ---------- SI: control exposure to IPCEI firms -------------------------------
def build_descriptive_exposure():
    """Control exposure, technology-matched and timed on approval status.

    Supersedes POSTAUDIT/control_ipcei_exposure.csv, which counted any
    collaboration in any technology with any IPCEI firm from either scheme and
    had no generator in the repository. That file is retained and marked
    obsolete for traceability. The measure here is the channel that can
    actually contaminate the estimated outcome: a control firm's collaboration
    IN the funded technology WITH a same-technology IPCEI firm that had
    already been approved in that month.
    """
    d = pd.read_csv(DIAG_PY / "p4_control_exposure_corrected.csv")
    g = {r.technology: r for r in d.itertuples()}

    def _n(x):
        """Thousands separator that survives the f-string and LaTeX maths."""
        return f"{int(x):,}".replace(",", "{,}")

    def row(label, fmt):
        return rf"\quad {label} & " + " & ".join(fmt(g[t]) for t in ("Battery", "Hydrogen")) + r" \\"

    # Transposed layout: one column per technology. The earlier wide version put
    # the five quantities in columns and overflowed the text block by ~118pt.
    body = "\n".join([
        r"\multicolumn{3}{l}{\textbf{A. Matched control sample}} \\[2pt]",
        row("Control firms", lambda r: _n(r.n_controls)),
        row("Control firm-months", lambda r: _n(r.ctrl_firm_months)),
        row("Technology-related collaborations", lambda r: _n(r.ctrl_events_tech)),
        r"\multicolumn{3}{l}{\textbf{B. Exposure to an already-approved IPCEI firm}} \\[2pt]",
        row("Control firms with any such collaboration",
            lambda r: rf"{_n(r.ctrl_ever_approved_partner)} ({r.share_ever_approved_pct:.1f}\%)"),
        row("Collaborations with such a partner",
            lambda r: rf"{_n(r.events_with_approved_partner)} ({r.share_events_approved_pct:.1f}\%)"),
        row("Control firm-months with such a collaboration",
            lambda r: rf"{_n(r.ctrl_firm_months_exposed)} ({r.share_firm_months_exposed_pct:.2f}\%)"),
        r"\multicolumn{3}{l}{\textbf{C. For comparison, not interference}} \\[2pt]",
        row("Collaborations with a later-approved IPCEI firm",
            lambda r: rf"{_n(r.events_with_future_treated_partner)} ({r.share_events_future_pct:.1f}\%)"),
    ])
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{6pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Exposure of control firms to already-approved IPCEI firms}}
\label{{tab:exposure}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rr @{{}}}}
\toprule\toprule
& Battery & Hydrogen \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Control firms in the primary matched sample. Panel~B counts collaboration with an IPCEI firm in the same technology already approved in that month, as unique (collaboration, control firm) pairs in the funded technology; percentages are shares of the corresponding Panel~A total. Such exposure would bias the estimates towards zero. Panel~C counts collaborations whose IPCEI partner was approved only later.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_exposure.tex", tex)



# ---------- SI: anticipation sensitivity (tab_results_anticipation) ----------
SENS_DIR = R_RESULTS_DIR / "psm" / "sensitivity"


def build_results_anticipation():
    """k = 0 / 3 / 6 months of anticipation on the three conditioned outcomes."""
    f = SENS_DIR / "att_anticipation.csv"
    if not f.exists():
        print("skip anticipation table:", f, "not found"); return
    d = pd.read_csv(f)
    order = ["Technology-related", "Cross-border EU", "Cross-sector"]
    ks = sorted(d.anticipation.unique())
    lines = []
    for tech in ("Battery", "Hydrogen"):
        lines.append(rf"\multicolumn{{{1 + 2 * len(ks)}}}{{l}}{{\textbf{{{tech} IPCEI}}}} \\[2pt]")
        for oc in order:
            cells = []
            for k in ks:
                r = d[(d.Technology == tech) & (d.Outcome == oc) & (d.anticipation == k)]
                if r.empty:
                    cells += ["---", "---"]
                else:
                    r = r.iloc[0]
                    cells += [f"{float(r.ATT):.3f}{sym(_exact_p(r.ATT, r.SE))}", pstr(r.p_value)]
            lines.append(f"\\quad {oc} & " + " & ".join(cells) + r" \\")
    body = "\n".join(lines)
    head = " & ".join(rf"\multicolumn{{2}}{{c}}{{$k={k}$}}" for k in ks)
    sub = " & ".join(["ATT & $p$"] * len(ks))
    cmid = " ".join(rf"\cmidrule(lr){{{2 + 2 * i}-{3 + 2 * i}}}" for i in range(len(ks)))
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{5pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Sensitivity to anticipation windows}}
\label{{tab:anticipation}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l {'rr ' * len(ks)}@{{}}}}
\toprule\toprule
& {head} \\
{cmid}
& {sub} \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} $k$ is the number of months before approval treated as already exposed; $k=0$ is the specification of {MAIN_RESULTS_REF}, from which it differs only through bootstrap simulation error. A six-month window is not estimable for battery, whose single cohort is approved twelve months after the panel begins. Outcomes in $\log(1+y)$.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_anticipation.tex", tex)


# ---------- SI: direct contrasts between the exclusive pairs ------------------
CONTRAST_ROWS = [
    ("Relative technology (log diff)",
     "Technology-related $-$ technology-unrelated"),
    ("Relative geography, EU-internal minus international (log diff)",
     "EU-internal $-$ international"),
    ("Relative sector, cross-sector minus same-sector (log diff)",
     "Cross-sector $-$ same-sector"),
]
BRIDGE_ROW = ("EU cross-border, broader definition (log diff)",
              "EU cross-border, broader definition")


def build_results_contrasts():
    """Differences between the mutually exclusive outcome pairs, estimated directly.

    C&S is linear in the outcome, so the ATT on the difference of two log1p
    outcomes equals the difference of their separately estimated ATTs but
    carries the correct standard error from the shared influence function.
    Comparing two ATTs by their significance stars is not a test of their
    difference; these rows are.
    """
    f = DIAG_R / "p5_relative_and_counts.csv"
    if not f.exists():
        print("skip tab_results_contrasts: run 10_ck_diagnostics_reference_country.R")
        return
    d = pd.read_csv(f)
    d = d[d.anticipation == 0]

    def row(src, label):
        sub = {r.technology: r for r in d[d.outcome == src].itertuples()}
        if len(sub) != 2:
            print(f"  tab_results_contrasts: no rows for {src!r}, skipping")
            return None
        cells = [f"{float(sub[t].att):.3f}{sym(float(sub[t].p))} & "
                 f"{float(sub[t].se):.3f} & {pstr(sub[t].p)}"
                 for t in ("Battery", "Hydrogen")]
        return rf"\quad {label}" + "\n  & " + " & & ".join(cells) + r" \\"

    body = [r"\multicolumn{8}{l}{\textbf{A. Differences between the exclusive pairs}} \\[2pt]"]
    body += [r for src, lab in CONTRAST_ROWS if (r := row(src, lab))]
    br = row(*BRIDGE_ROW)
    if br:
        body += [r"\multicolumn{8}{l}{\textbf{B. Alternative geographic definition}} \\[2pt]", br]
    body = "\n".join(body)

    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{4pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Direct contrasts between the reported outcomes}}
\label{{tab:contrasts}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rrr c rrr @{{}}}}
\toprule\toprule
& \multicolumn{{3}}{{c}}{{\textbf{{Battery IPCEI}}}}
& & \multicolumn{{3}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-4}}\cmidrule(lr){{6-8}}
& ATT & SE & $p$ & & ATT & SE & $p$ \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Panel~A estimates the difference between the two members of each exclusive pair as a single outcome, so the standard error accounts for their covariance; comparing the separate ATTs in {MAIN_RESULTS_REF} by their significance stars does not test their difference. Panel~B reports a broader geographic definition. The EU-internal outcome in {MAIN_RESULTS_REF} counts a collaboration only if every participant is headquartered in the EU, so a collaboration between a German, a French and an American firm is classified as international; roughly a third of collaborations spanning two or more member states fall into that case. The broader outcome instead counts a collaboration whenever the firm has a partner in another member state, whether or not a non-EU participant is also present. It is not exclusive of the international outcome and is reported as a supplementary estimate. All rows are secondary analyses with nominal $p$-values.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_contrasts.tex", tex)


# ---------- SI: multiple testing over the full outcome set --------------------
def build_results_bh_all():
    """Benjamini-Hochberg over every composition outcome, not only the three targeted.

    The reported family is the three outcomes the scheme's conditions name.
    Correcting across all eight composition outcomes instead is the obvious
    referee question, and it changes the hydrogen conclusion, so it is reported
    rather than left to be discovered.
    """
    f = PSM_TT / "bh_correction_techtagged_alloutcomes.csv"
    if not f.exists():
        print("skip tab_results_bh-all:", f, "not found")
        return
    d = pd.read_csv(f)
    order = [o for o in OUTCOME_LABELS if o in set(d.outcome)]
    lines = []
    for oc in order:
        cells = []
        for tech in ("Battery", "Hydrogen"):
            r = d[(d.technology == tech) & (d.outcome == oc)]
            if r.empty:
                cells.append("--- & ---")
                continue
            r = r.iloc[0]
            cells.append(f"{pstr(r.p_raw)} & {pstr(r.p_bh)}{sym(float(r.p_bh))}")
        lines.append(rf"\quad {OUTCOME_LABELS[oc]} & " + " & & ".join(cells) + r" \\")
    body = "\n".join(lines)
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{5pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Multiple testing over all composition outcomes}}
\label{{tab:bh_all}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rr c rr @{{}}}}
\toprule\toprule
& \multicolumn{{2}}{{c}}{{\textbf{{Battery IPCEI}}}}
& & \multicolumn{{2}}{{c}}{{\textbf{{Hydrogen IPCEI}}}} \\
\cmidrule(lr){{2-3}}\cmidrule(lr){{5-6}}
& Raw $p$ & Adjusted $p$ & & Raw $p$ & Adjusted $p$ \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Benjamini--Hochberg correction applied within each technology across all {len(order)} outcomes estimated in the composition specification, rather than across the three outcomes the scheme's conditions name. The three-outcome family is the one reported in the main text, because the conditions define it; this table shows what the broader family gives. Under it the hydrogen technology-related effect no longer reaches conventional significance, while the battery effects and the hydrogen cross-border effect do.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_bh-all.tex", tex)


# ---------- NUMBERS_CRIB.md ---------------------------------------------------
def build_numbers_crib():
    """Regenerate results/NUMBERS_CRIB.md from the result CSVs.

    The crib used to be maintained by hand and went stale across the
    collaboration-level rewrite: it still listed dyad-level outcomes that are
    no longer reported ("Domestic", "Within-sector", "Cross-border non-EU"),
    a nine-outcome Benjamini-Hochberg family, and battery cross-sector at
    0.270 against the 0.187 in Table 1 -- while telling the reader that every
    in-text number must match it. A drafting source that disagrees with the
    tables is worse than no drafting source, so it is generated now.
    """
    tt = pd.read_csv(PSM_TT / "att_techtagged_table.csv")
    it = pd.read_csv(PSM_INT / "att_summary_intensity.csv")
    main = pd.concat([tt, it], ignore_index=True)

    def md(s):
        """LaTeX markup out, plain markdown in: this file is read, not compiled."""
        return (str(s).replace(r"\sym{", "").replace("}", "")
                      .replace(r"\%", "%").replace("$", ""))

    def fmt(r):
        att = md(f"{float(r.ATT):.3f}{sym(_exact_p(r.ATT, r.SE))}")
        pt = float(r.pretrend_p_value) if pd.notna(r.pretrend_p_value) else float("nan")
        flag = " **pre-trend FAILS**" if pt < 0.05 else ""
        return (f"{att} / {md(pct(r.ATT))} / SE {float(r.SE):.3f} / "
                f"p {float(r.p_value):.3f} / pre {pt:.3f}{flag}")

    lines = [
        "# Numbers crib",
        "",
        "**Generated by `python -m ipcei_spillovers.tables` -- do not hand-edit.**",
        "Regenerate after any R re-run; a hand-edited crib is how this file went",
        "stale last time. Every in-text number must match the tables in",
        "`results/tables/`, which come from the same CSVs as this file.",
        "",
        f"PSM balance spec (spec 1) = primary. Battery N = "
        f"{int(tt[tt.Technology=='Battery'].N_units.iloc[0])} "
        f"({int(tt[tt.Technology=='Battery'].N_treated.iloc[0])} treated); hydrogen N = "
        f"{int(tt[tt.Technology=='Hydrogen'].N_units.iloc[0])} "
        f"({int(tt[tt.Technology=='Hydrogen'].N_treated.iloc[0])} treated). "
        "Deterministic per-outcome seed, 9,999 bootstrap draws, firm-level clusters.",
        "",
        "## Table 1 -- main results (ATT / %D / SE / p / joint pre-trend p)",
        "",
        "| Outcome | Battery | Hydrogen |",
        "|---|---|---|",
    ]
    for oc, lab in OUTCOME_LABELS.items():
        rows = {r.Technology: r for r in main[main.Outcome == oc].itertuples()}
        if len(rows) != 2:
            continue
        lines.append(f"| {lab} | {fmt(rows['Battery'])} | {fmt(rows['Hydrogen'])} |")

    # Benjamini-Hochberg, both families.
    for fname, title in [("bh_correction_techtagged.csv",
                          "Benjamini-Hochberg, family of three primary outcomes"),
                         ("bh_correction_techtagged_alloutcomes.csv",
                          "Benjamini-Hochberg, family of all eight outcomes")]:
        f = PSM_TT / fname
        if not f.exists():
            continue
        d = pd.read_csv(f)
        lines += ["", f"## {title}", "", "| Technology | Outcome | p raw | p BH |",
                  "|---|---|---|---|"]
        lines += [f"| {r.technology} | {OUTCOME_LABELS.get(r.outcome, r.outcome)} "
                  f"| {float(r.p_raw):.3f} | {float(r.p_bh):.3f} |"
                  for r in d.itertuples()]

    # Direct contrasts.
    f = DIAG_R / "p5_relative_and_counts.csv"
    if f.exists():
        d = pd.read_csv(f)
        d = d[d.anticipation == 0]
        lines += ["", "## Direct contrasts (ATT on the difference of two log1p outcomes)",
                  "", "| Contrast | Battery | Hydrogen |", "|---|---|---|"]
        for src in d.outcome.unique():
            sub = {r.technology: r for r in d[d.outcome == src].itertuples()}
            if len(sub) != 2:
                continue
            cell = {t: f"{float(sub[t].att):.3f} / SE {float(sub[t].se):.3f} "
                       f"/ p {float(sub[t].p):.3f}" for t in sub}
            lines.append(f"| {src} | {cell['Battery']} | {cell['Hydrogen']} |")

    # Minimum detectable effects, once the power run has been done.
    f = POSTAUDIT / "power_mde.csv"
    if f.exists():
        d = pd.read_csv(f)
        d = d[~d["significant"].astype(bool)]
        lines += ["", "## Minimum detectable effect at 80% power (insignificant outcomes)",
                  "", "| Technology | Outcome | ATT | p | MDE |", "|---|---|---|---|---|"]
        for r in d.itertuples():
            mde = ("n/a on the grid tested" if pd.isna(r.mde_pct)
                   else (f"{r.mde_log:.3f} log pts" if r.is_contrast
                         else f"{r.mde_pct:.0f}%"))
            lines.append(f"| {r.Technology} | {r.Outcome} | {float(r.ATT):.3f} "
                         f"| {float(r.p_value):.3f} | {mde} |")
    else:
        lines += ["", "## Minimum detectable effect at 80% power",
                  "", "Not yet produced. Run the power chunks "
                  "(`RUN_POWER <- TRUE` in 06/07, `RUN_P6_POWER <- TRUE` in 10), "
                  "then notebook 08, then regenerate this file."]

    lines += ["", "## Robustness arms",
              "", "The three panels of `si/tab_results_appendix.tex` carry the same "
              "nine rows as Table 1: larger control group (spec 2), not-yet-treated "
              "controls (hydrogen only, battery is a single cohort), and no matching "
              "(unmatched eligible pool, doubly robust; all hydrogen rows fail the "
              "joint pre-trend test, which is why matching is primary). Read them "
              "there rather than duplicating them here.", ""]

    _write(PATHS.results / "NUMBERS_CRIB.md", "\n".join(lines))


def build_all():
    MAIN_DIR.mkdir(parents=True, exist_ok=True)
    SI_DIR.mkdir(parents=True, exist_ok=True)
    build_results_main()
    build_results_appendix()
    build_results_pretrend()
    build_descriptive_activity_mix()
    build_descriptive_active_firms()
    build_descriptive_partner_overlap()
    build_descriptive_collab_types()
    build_results_estimands()
    build_results_cohort_country()
    build_results_reference_period()
    build_descriptive_attrition()
    build_descriptive_country_balance()
    build_descriptive_exposure()
    build_results_anticipation()
    build_results_contrasts()
    build_results_bh_all()
    build_numbers_crib()
    print("\nNote: tab_descriptive_discontinued-projects.tex is kept hand-made (external sources).")


if __name__ == "__main__":
    build_all()
