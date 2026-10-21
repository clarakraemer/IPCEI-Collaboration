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
POSTAUDIT = PATHS.results_tables / "post-audit" / "psm"    # working CSVs feeding the tables

# The SI is a standalone document, so SI tables cannot \ref main-text labels.
MAIN_RESULTS_REF = "Table~1 in the main text"

# Outcome labels as they appear in Table 1 (CSV outcome name -> row label).
OUTCOME_LABELS = {
    "Technology-tagged collaborations": "Technology-related",
    "Cross-border EU collaborations":   "Cross-border EU",
    "Cross-sector collaborations":      "Cross-sector",
    "Total collabs":                    "Total collaborations",
    "Non-EU collaborations":            "Cross-border non-EU",
    "Domestic collaborations":          "Domestic",
    "Within-sector collaborations":     "Within-sector",
    "Non-funded collaborations":        "Technology-unrelated",
}

PSM_TT   = R_RESULTS_DIR / "psm" / "composition_techtagged" / "month"
PSM_INT  = R_RESULTS_DIR / "psm" / "intensity"
UNM_TT   = R_RESULTS_DIR / "unmatched" / "composition_techtagged" / "month"
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
    co  = pd.read_csv(PSM_TT / "consortium_size_att.csv")
    d = {(r.Technology, r.Outcome): r for r in pd.concat([tt, it, co]).itertuples()}

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
        row("Cross-border EU",      "Cross-border EU collaborations"),
        row("Cross-sector",         "Cross-sector collaborations"),
        r"\multicolumn{10}{l}{\textbf{B. Benchmarks}} \\[2pt]",
        row("Total collaborations",  "Total collabs"),
        row("Technology-unrelated",  "Non-funded collaborations"),
        row("Cross-border non-EU",   "Non-EU collaborations"),
        row("Domestic",              "Domestic collaborations"),
        row("Within-sector",         "Within-sector collaborations"),
    ])
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
\item \textit{{Notes:}} Callaway--Sant'Anna staggered difference-in-differences estimator \citep{{callaway2021difference}} (\texttt{{did}} v2.3.0) on the matched sample, with never-treated controls in both technologies. Battery: $N={nbt}$ (${tbt}$ treated); hydrogen: $N={nht}$ (${tht}$ treated). Standard errors are clustered at the firm level with $9{{,}}999$ bootstrap replications. Panel~A and~B outcomes are monthly collaboration counts in $\log(1+y)$; $\%\Delta = 100[\exp(\widehat{{ATT}})-1]$ is the approx. percentage change in $1+y$. Outcomes are not mutually exclusive. \textit{{Italicised}} estimates fail the joint pre-trend test.
\item \sym{{*}}~$p<0.10$\quad \sym{{**}}~$p<0.05$\quad \sym{{***}}~$p<0.01$
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table*}}
"""
    _write(MAIN_DIR / "tab_results_main.tex", tex)


# ---------- Table 4: robustness (tab_results_appendix) ------------------------
def build_results_appendix():
    rb = pd.read_csv(PSM_TT / "robustness_techtagged_table.csv")
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

    # Panel C: Rosenbaum critical Gamma (largest Gamma at which the upper-bound
    # p stays < 0.05). "---" = not significant in the primary spec (not tested).
    rz_path = PSM_TT / "rosenbaum_bounds_techtagged.csv"
    rz = pd.read_csv(rz_path) if rz_path.exists() else pd.DataFrame(columns=["Specification", "Gamma", "Upper bound"])

    def crit_gamma(tech, oc):
        s = rz[rz["Specification"] == f"{tech} -- {oc}"]
        if s.empty:
            return "---"
        sig = s[s["Upper bound"] < 0.05]
        if sig.empty:
            return "---"
        gmax, gtested = sig["Gamma"].max(), s["Gamma"].max()
        return "$>3.0$" if gmax >= gtested else f"{gmax:g}"

    c = "\n".join(
        rf"\quad {lab} & & \multicolumn{{3}}{{c}}{{{crit_gamma('Battery', oc)}}} & & "
        rf"\multicolumn{{3}}{{c}}{{{crit_gamma('Hydrogen', oc)}}} \\"
        for lab, oc in [("Technology-related", "Technology-tagged collaborations"),
                        ("Cross-border EU", "Cross-border EU collaborations"),
                        ("Cross-sector", "Cross-sector collaborations"),
                        ("Cross-border non-EU", "Non-EU collaborations")])

    # Panel D: no matching (unmatched eligible pool, doubly-robust). Same layout
    # as Panel A; hydrogen italicised where it fails the joint pre-trend test.
    ut = pd.read_csv(UNM_TT / "att_techtagged_table.csv")
    ui = pd.read_csv(UNM_INT / "att_summary_intensity.csv")
    ui = ui[ui["Type"] == "Primary"]                      # DR total (not the raw diagnostic)
    du = {(r.Technology, r.Outcome): r for r in pd.concat([ut, ui]).itertuples()}
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

    dpanel = "\n".join(urow(lab, oc) for lab, oc in [
        ("Technology-related", "Technology-tagged collaborations"),
        ("Cross-border EU", "Cross-border EU collaborations"),
        ("Cross-sector", "Cross-sector collaborations"),
        ("Total collaborations", "Total collabs"),
        ("Cross-border non-EU", "Non-EU collaborations"),
        ("Domestic", "Domestic collaborations")])

    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
% (Panel C Rosenbaum bounds are appended from rosenbaum_bounds_techtagged.csv if present.)
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
\multicolumn{{9}}{{l}}{{\textbf{{D. Rosenbaum bounds (critical $\Gamma$)}}}} \\[2pt]
{c}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Robustness checks for the outcomes in {MAIN_RESULTS_REF}; ATT, SE and $p$ as defined there. $N$ is the number of firms (battery/hydrogen). Panel~A uses the larger-control-group matching specification. Panel~B substitutes not-yet-treated for never-treated controls, for hydrogen only, since the single battery cohort has no not-yet-treated units. Panel~C drops matching, estimating on all structurally eligible controls with doubly-robust covariate adjustment; \textit{{italicised}} estimates fail the joint pre-trend test. Panel~D reports the critical $\Gamma$, the largest odds ratio of differential selection on an unobserved confounder at which the estimate stays significant at the 5\% level, where ``$>3.0$'' means the estimate stays significant throughout the tested range and ``---'' marks an outcome that is not significant in the primary specification.
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
             "Cross-border EU collaborations", "Non-EU collaborations",
             "Domestic collaborations",
             "Cross-sector collaborations", "Within-sector collaborations"]

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
\item \textit{{Notes:}} $p$-values of the joint test that all pre-treatment event-study coefficients are zero, for the outcomes in {MAIN_RESULTS_REF}. \textit{{Matched}} is the primary specification (matched sample, never-treated controls); \textit{{unmatched}} estimates on all structurally eligible controls with doubly-robust covariate adjustment (Table~\ref{{tab:robustness}}, Panel~C). Values below 0.05 (in \textbf{{bold}}) reject parallel pre-treatment trends.
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
\item \textit{{Notes:}} Share (\%) of IPCEI firms' technology-related collaborations carrying each activity tag, in the 12 months before approval (months $-12$ to $-1$) and from approval onward (months $0$ to $12$). $\Delta$ is the change in percentage points; \textit{{control}} $\Delta$ is the same change for the matched control firms, measured around the approval date of the treated firm they are matched to, and serves as a benchmark for secular trends. Activity tags are not mutually exclusive, so each column reports prevalence and does not sum to 100\%.
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
    _write(MAIN_DIR / "tab_descriptive_active-firms.tex", tex)


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
    _write(MAIN_DIR / "tab_descriptive_partner-overlap.tex", tex)


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
\item \textit{{Notes:}} Counts at the collaboration level within the {start}--{end} analysis window ($N = {str(f'{n_total:,}').replace(',', '{{,}}')}$ unique collaborations). A collaboration is assigned to a category if any of its constituent organisation pairs carries the corresponding tag. Categories are not mutually exclusive, since a collaboration can span several technologies, activity types and domains, so shares within a panel do not sum to 100\%. Technology and activity tags are those of \citet{{ToetzkeEtAl2025}}; activity type describes the purpose of the collaboration and activity domain the part of the value chain it concerns.
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
    for tech in ("battery", "hydrogen"):
        tr = set(fm.loc[fm[f"first_{tech}_date"].notna(), "Linkedin_name"])
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
\item \textit{{Notes:}} Treated firms with no comparable control are dropped by the matching procedure. Columns report medians. Attrition is mild for battery, where lost and retained firms are of similar size, age and collaboration activity, and severe for hydrogen, where the lost firms are far larger, older and more collaborative. The estimates in {MAIN_RESULTS_REF} therefore apply to IPCEI firms with observable counterparts rather than to all recipients.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_attrition.tex", tex)


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
\item \textit{{Notes:}} Share of firms by headquarters country in the primary matched sample, six largest treated shares per technology. Matching conditions on sector and European presence but not on country.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_descriptive_country-balance.tex", tex)


# ---------- SI: control exposure to IPCEI firms -------------------------------
def build_descriptive_exposure():
    d = pd.read_csv(POSTAUDIT / "control_ipcei_exposure.csv")
    body = "\n".join(
        f"{r.technology} & {r.n_controls} & {r.ctrl_with_ipcei_link_ever} ({r.share_ever_pct:.1f}\\%) & "
        f"{r.ctrl_linked_before} & {r.ctrl_linked_only_after} \\\\" for r in d.itertuples())
    tex = rf"""% Auto-generated by ipcei_spillovers.tables — do not hand-edit.
\begin{{table}}[!ht]
\centering
\setlength{{\tabcolsep}}{{6pt}}
\renewcommand{{\arraystretch}}{{1.15}}
\caption{{Control firms collaborating with IPCEI firms}}
\label{{tab:exposure}}
\begin{{threeparttable}}
\small
\begin{{tabular*}}{{\linewidth}}{{@{{\extracolsep{{\fill}}}} l rrrr @{{}}}}
\toprule\toprule
& Control firms & Ever linked & Linked before approval & Linked only after \\
\midrule
{body}
\bottomrule\bottomrule
\end{{tabular*}}
\begin{{tablenotes}}[flushleft]
\small
\item \textit{{Notes:}} Control firms in the primary matched sample that record at least one collaboration with an IPCEI firm. Approval dates are the first in each technology. Such interference would bias the estimates toward zero.
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
\item \textit{{Notes:}} $k$ is the number of months before approval treated as already exposed, so $k=0$ is the baseline specification of {MAIN_RESULTS_REF}; point estimates are identical and $p$-values differ only in the third decimal through bootstrap simulation error. A six-month window is not estimable for battery, whose single cohort is approved twelve months after the panel begins. Outcomes are monthly collaboration counts in $\log(1+y)$.
\end{{tablenotes}}
\end{{threeparttable}}
\end{{table}}
"""
    _write(SI_DIR / "tab_results_anticipation.tex", tex)


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
    build_descriptive_attrition()
    build_descriptive_country_balance()
    build_descriptive_exposure()
    build_results_anticipation()
    print("\nNote: tab_descriptive_discontinued-projects.tex is kept hand-made (external sources).")


if __name__ == "__main__":
    build_all()
