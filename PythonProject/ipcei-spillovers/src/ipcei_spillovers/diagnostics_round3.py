# ============================================================
# Round-3 diagnostics on the dyadic collaboration records
# ============================================================
# Part 3  composition of approval-month collaboration events
# Part 4  technology- and timing-specific control exposure to IPCEI firms
#
# Read-only with respect to the primary pipeline: writes only to
# results/tables/diagnostics/. Run with
#   python -m ipcei_spillovers.diagnostics_round3
#
# Replaces the orphaned `control_ipcei_exposure.csv`, which had no
# generator in the repository and counted ANY collaboration with ANY
# IPCEI firm in ANY technology. Exposure here is defined on the channel
# that can actually contaminate the estimated outcome: a control firm's
# collaboration IN the funded technology WITH a same-technology IPCEI firm.

from __future__ import annotations

import numpy as np
import pandas as pd

from .config_paths import R_DATA_DIR
from .io import load_df, results_path
from .plotting import PLOT_END, PLOT_START

OUT = results_path("tables", "diagnostics")
TECHS = (("battery", "Battery"), ("hydrogen", "Hydrogen"))


def _write(df: pd.DataFrame, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT / name, index=False)
    print(f"wrote {OUT / name}")


def _load():
    p = load_df("interim", "combined", "partnership_master_ipcei_jan26.csv",
                low_memory=False)
    p["post_date"] = pd.to_datetime(p["post_date"], errors="coerce")
    p = p[(p["post_date"] >= PLOT_START) & (p["post_date"] < PLOT_END)].copy()
    p["month"] = p["post_date"].dt.to_period("M").dt.to_timestamp()
    fm = load_df("interim", "combined",
                 "firm_master_ipcei_corrected_extended_jan26.csv",
                 low_memory=False)
    for t, _ in TECHS:
        fm[f"first_{t}_date"] = pd.to_datetime(fm[f"first_{t}_date"],
                                               errors="coerce")
    return p, fm


def _sets(fm, tech):
    """IPCEI firms of this technology, with their approval month."""
    col = f"first_{tech}_date"
    sub = fm.loc[fm[col].notna(), ["Linkedin_name", col]].copy()
    sub["g"] = sub[col].dt.to_period("M").dt.to_timestamp()
    return dict(zip(sub["Linkedin_name"], sub["g"]))


def _matched(tech):
    mf = pd.read_csv(R_DATA_DIR / f"{tech}_psm_spec1_matched_firms.csv",
                     low_memory=False)
    ctrl = sorted(set(mf.loc[mf.is_control == 1, "Linkedin_name"].dropna()))
    trt = sorted(set(mf.loc[mf.is_treated == 1, "Linkedin_name"].dropna()))
    return ctrl, trt


# ------------------------------------------------------------
# Part 4: control exposure
# ------------------------------------------------------------
def exposure():
    p, fm = _load()
    summary, trend = [], []

    for tech, Tech in TECHS:
        gmap = _sets(fm, tech)
        ctrl, _ = _matched(tech)
        ctrl_set = set(ctrl)
        sub = p[p[Tech] == 1].copy()

        # partnership_master is a DYAD list, so one multi-firm collaboration
        # spans several rows sharing a collaboration_id. The outcome counts
        # unique collaboration_ids per firm-month, so the unit of exposure is
        # the (collaboration, control firm) pair, and the pair is exposed when
        # ANY other participant is an IPCEI firm. Collapsing to a single
        # arbitrary partner would miss the IPCEI member of a large consortium.
        a = sub[["collaboration_id", "month", "source", "target"]].rename(
            columns={"source": "firm", "target": "partner"})
        b = sub[["collaboration_id", "month", "target", "source"]].rename(
            columns={"target": "firm", "source": "partner"})
        dy = (pd.concat([a, b], ignore_index=True)
                .dropna(subset=["firm", "partner", "month"]))
        dy["partner_g"] = dy["partner"].map(gmap)
        dy["p_appr"] = dy["partner_g"].notna() & (dy["month"] >= dy["partner_g"])
        dy["p_fut"] = dy["partner_g"].notna() & (dy["month"] < dy["partner_g"])

        ev = (dy[dy["firm"].isin(ctrl_set)]
              .groupby(["collaboration_id", "firm", "month"], as_index=False)
              .agg(partner_is_ipcei=("partner_g", lambda s: s.notna().any()),
                   partner_approved_now=("p_appr", "any"),
                   partner_future=("p_fut", "any")))

        n_ctrl = len(ctrl)
        tot_events = len(ev)
        ever = ev.loc[ev["partner_is_ipcei"], "firm"].nunique()
        ever_appr = ev.loc[ev["partner_approved_now"], "firm"].nunique()

        # Control firm-months: denominator is every control x month in the
        # panel window, so the share is not conditional on activity.
        months = pd.date_range(PLOT_START, PLOT_END, freq="MS")[:-1]
        fm_total = n_ctrl * len(months)
        fm_exposed = (ev.loc[ev["partner_approved_now"], ["firm", "month"]]
                        .drop_duplicates().shape[0])

        summary.append(dict(
            technology=Tech, n_controls=n_ctrl,
            ctrl_events_tech=tot_events,
            ctrl_ever_any_ipcei_partner=ever,
            share_ever_any_pct=round(100 * ever / n_ctrl, 1),
            ctrl_ever_approved_partner=ever_appr,
            share_ever_approved_pct=round(100 * ever_appr / n_ctrl, 1),
            events_with_approved_partner=int(ev["partner_approved_now"].sum()),
            share_events_approved_pct=round(
                100 * ev["partner_approved_now"].mean(), 1),
            events_with_future_treated_partner=int(ev["partner_future"].sum()),
            share_events_future_pct=round(100 * ev["partner_future"].mean(), 1),
            ctrl_firm_months=fm_total,
            ctrl_firm_months_exposed=fm_exposed,
            share_firm_months_exposed_pct=round(100 * fm_exposed / fm_total, 2),
        ))

        # Exposure trend relative to the first approval in the technology.
        first_g = min(gmap.values())
        ev["rel_month"] = ((ev["month"].dt.year - first_g.year) * 12
                           + (ev["month"].dt.month - first_g.month))
        tr = (ev.groupby("rel_month")
                .agg(events=("collaboration_id", "size"),
                     with_approved=("partner_approved_now", "sum"))
                .reset_index())
        tr["share_pct"] = (100 * tr["with_approved"] / tr["events"]).round(1)
        tr["technology"] = Tech
        trend.append(tr)

    s = pd.DataFrame(summary)
    _write(s, "p4_control_exposure_corrected.csv")
    _write(pd.concat(trend, ignore_index=True), "p4_exposure_trend.csv")
    print("\n== Part 4: corrected control exposure ==")
    print(s.T.to_string())
    return s


# ------------------------------------------------------------
# Part 3: what the approval-month collaborations look like
# ------------------------------------------------------------
def approval_month_composition():
    p, fm = _load()
    rows, detail = [], []

    for tech, Tech in TECHS:
        gmap = _sets(fm, tech)
        _, trt = _matched(tech)
        trt_set = set(trt)
        ip_all = set(gmap)
        sub = p[p[Tech] == 1].copy()

        a = sub[["collaboration_id", "month", "source", "target"]].rename(
            columns={"source": "firm", "target": "partner"})
        b = sub[["collaboration_id", "month", "target", "source"]].rename(
            columns={"target": "firm", "source": "partner"})
        ev = (pd.concat([a, b], ignore_index=True)
                .dropna(subset=["firm", "partner", "month"])
                .drop_duplicates(subset=["collaboration_id", "firm"]))
        ev = ev[ev["firm"].isin(trt_set)].copy()
        ev["g"] = ev["firm"].map(gmap)
        ev["e"] = ((ev["month"].dt.year - ev["g"].dt.year) * 12
                   + (ev["month"].dt.month - ev["g"].dt.month))

        # Consortium size, counted at the collaboration level.
        size = (pd.concat([sub[["collaboration_id", "source"]]
                           .rename(columns={"source": "f"}),
                           sub[["collaboration_id", "target"]]
                           .rename(columns={"target": "f"})], ignore_index=True)
                  .dropna().drop_duplicates()
                  .groupby("collaboration_id")["f"].nunique()
                  .rename("consortium_size"))
        ev = ev.merge(size, on="collaboration_id", how="left")

        # Is the partner an IPCEI firm, and is this the pair's first ever
        # recorded collaboration? First-time status is computed over the whole
        # window, so it does not depend on the event's own timing.
        ev["partner_ipcei"] = ev["partner"].isin(ip_all)
        pair = (ev.assign(k=ev[["firm", "partner"]].min(axis=1) + "||"
                          + ev[["firm", "partner"]].max(axis=1))
                  .sort_values("month")
                  .groupby("k")["month"].min().rename("first_month"))
        ev["k"] = (ev[["firm", "partner"]].min(axis=1) + "||"
                   + ev[["firm", "partner"]].max(axis=1))
        ev = ev.merge(pair, on="k", how="left")
        ev["is_new_pair"] = ev["month"] == ev["first_month"]

        for lab, mask in (("e = 0", ev["e"] == 0),
                          ("e = 1 to 3", ev["e"].between(1, 3)),
                          ("e = 4 to 12", ev["e"].between(4, 12)),
                          ("e = -3 to -1", ev["e"].between(-3, -1)),
                          ("all pre (e < 0)", ev["e"] < 0)):
            d = ev[mask]
            if d.empty:
                continue
            rows.append(dict(
                technology=Tech, window=lab,
                firm_events=len(d),
                unique_collabs=d["collaboration_id"].nunique(),
                events_per_treated_firm_month=round(
                    len(d) / max(d["firm"].nunique(), 1)
                    / max(d["e"].nunique(), 1), 3),
                pct_partner_ipcei=round(100 * d["partner_ipcei"].mean(), 1),
                pct_new_pair=round(100 * d["is_new_pair"].mean(), 1),
                mean_consortium_size=round(d["consortium_size"].mean(), 2),
                pct_consortium_gt2=round(
                    100 * (d["consortium_size"] > 2).mean(), 1),
                median_collab_per_firm=float(
                    d.groupby("firm")["collaboration_id"].nunique().median()),
            ))

        # Which cohort do the e = 0 events come from?
        d0 = ev[ev["e"] == 0].copy()
        if not d0.empty:
            c = (d0.groupby(d0["g"].dt.strftime("%Y-%m"))
                   .agg(firm_events=("collaboration_id", "size"),
                        unique_collabs=("collaboration_id", "nunique"),
                        firms=("firm", "nunique"),
                        pct_partner_ipcei=("partner_ipcei", "mean"),
                        pct_new_pair=("is_new_pair", "mean"),
                        mean_size=("consortium_size", "mean"))
                   .reset_index().rename(columns={"g": "cohort"}))
            c["pct_partner_ipcei"] = (100 * c["pct_partner_ipcei"]).round(1)
            c["pct_new_pair"] = (100 * c["pct_new_pair"]).round(1)
            c["events_per_firm"] = (c["firm_events"] / c["firms"]).round(2)
            c["technology"] = Tech
            detail.append(c)

    r = pd.DataFrame(rows)
    _write(r, "p3_approval_month_composition.csv")
    print("\n== Part 3: approval-month collaboration composition ==")
    print(r.to_string(index=False))
    if detail:
        dd = pd.concat(detail, ignore_index=True)
        _write(dd, "p3_approval_month_by_cohort_descriptive.csv")
        print("\n== Part 3: e = 0 events by cohort ==")
        print(dd.to_string(index=False))
    return r


def date_fields():
    """Is a separate public-announcement date available at all?"""
    p = load_df("interim", "combined", "partnership_master_ipcei_jan26.csv",
                low_memory=False)
    cand = [c for c in p.columns
            if any(k in c.lower() for k in
                   ("date", "time", "post", "announce", "publish", "created"))]
    print("\n== Part 3.5: date-like fields in partnership_master ==")
    for c in cand:
        nn = p[c].notna().mean()
        print(f"  {c:28s} non-null {100 * nn:5.1f}%  e.g. {p[c].dropna().head(1).tolist()}")
    return cand


if __name__ == "__main__":
    exposure()
    approval_month_composition()
    date_fields()


# ------------------------------------------------------------
# Figures (diagnostics only, not paper exhibits)
# ------------------------------------------------------------
def figures():
    import matplotlib.pyplot as plt
    from .io import save_fig
    from .plotting import COLORS, style_ax

    R_DIAG = (R_DATA_DIR.parent / "results" / "psm" / "diagnostics")
    hyd, bat = COLORS["two"]
    FIG = "diagnostics"

    # 1. Cohort ATTs, hydrogen, common 0-12 horizon vs all post periods
    g = pd.read_csv(R_DIAG / "p2a_cohort_atts_hydrogen.csv")
    outs = ["Technology-related", "Cross-border EU", "Technology-unrelated"]
    fig, axes = plt.subplots(1, 3, figsize=(11, 3.4), sharey=True)
    for ax, oc in zip(axes, outs):
        for j, (hz, mk, col) in enumerate([("all post", "o", hyd),
                                           ("e 0-12", "s", bat)]):
            d = g[(g.outcome == oc) & (g.horizon == hz)].sort_values("cohort")
            x = np.arange(len(d)) + (j - 0.5) * 0.18
            ax.errorbar(x, d.att, yerr=1.96 * d.se, fmt=mk, color=col,
                        capsize=3, ms=5, lw=1.2, label=hz)
            ax.set_xticks(np.arange(len(d)))
            ax.set_xticklabels(d.cohort, rotation=45, ha="right", fontsize=8)
        ax.axhline(0, color="grey", lw=0.8)
        ax.set_title(oc, fontsize=10)
        style_ax(ax)
    axes[0].set_ylabel("ATT (log points)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.tight_layout()
    save_fig(fig, FIG, "diag_cohort_atts_hydrogen")

    # 2. Germany-exclusion sensitivity
    b = pd.read_csv(R_DIAG / "p2b_germany_exclusion_hydrogen.csv")
    order = ["full", "drop DE treated", "drop all DE firms"]
    b = b[b["sample"].isin(order)]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    for j, oc in enumerate(outs):
        d = b[b.outcome == oc].set_index("sample").loc[order].reset_index()
        x = np.arange(len(order)) + (j - 1) * 0.2
        ax.errorbar(x, d.att, yerr=1.96 * d.se, fmt="o", capsize=3, ms=5,
                    lw=1.2, label=oc,
                    color=[hyd, bat, "darkorange"][j])
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xticks(np.arange(len(order)))
    ax.set_xticklabels(["Full matched\nsample", "Drop German\ntreated",
                        "Drop all\nGerman firms"], fontsize=9)
    ax.set_ylabel("ATT (log points)")
    ax.legend(frameon=False, fontsize=8)
    style_ax(ax)
    fig.tight_layout()
    save_fig(fig, FIG, "diag_germany_exclusion_hydrogen")

    # 3. Approval-month dynamics: event-time windows, e=0 separated
    s = pd.read_csv(R_DIAG / "p3_eventtime_split_hydrogen.csv")
    s = s[s.window.isin(["e 0-0", "e 1-3", "e 4-12"])]
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labs = ["Approval month", "Months 1-3", "Months 4-12"]
    for j, oc in enumerate(outs):
        d = s[s.outcome == oc].set_index("window").loc[
            ["e 0-0", "e 1-3", "e 4-12"]].reset_index()
        x = np.arange(3) + (j - 1) * 0.2
        ax.errorbar(x, d.att, yerr=1.96 * d.se, fmt="o", capsize=3, ms=5,
                    lw=1.2, label=oc, color=[hyd, bat, "darkorange"][j])
    ax.axhline(0, color="grey", lw=0.8)
    ax.set_xticks(np.arange(3)); ax.set_xticklabels(labs, fontsize=9)
    ax.set_ylabel("ATT (log points)")
    ax.legend(frameon=False, fontsize=8)
    style_ax(ax)
    fig.tight_layout()
    save_fig(fig, FIG, "diag_approval_month_split_hydrogen")

    # 4. Cohort pre-approval relative trajectories (Part 1 deliverable)
    t = pd.read_csv(R_DIAG / "p1_cohort_pretrajectories_hydrogen.csv")
    t = t[(t.outcome == "Technology-related") & t.e.between(-12, 2)]
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    cmap = plt.cm.viridis(np.linspace(0.1, 0.85, t.cohort.nunique()))
    for col, (ch, d) in zip(cmap, t.groupby("cohort")):
        ax.plot(d.e, d.rel_norm, marker="o", ms=3.5, lw=1.3, color=col, label=ch)
    ax.axvline(0, color="grey", lw=0.8)
    ax.axvline(-3.5, color="firebrick", lw=0.9, ls=":")
    ax.axhline(0, color="grey", lw=0.6)
    ax.set_xlabel("Months relative to approval")
    ax.set_ylabel("Treated minus control,\nnormalised at $e=-1$")
    ax.legend(frameon=False, fontsize=8, title="Cohort", title_fontsize=8)
    style_ax(ax)
    fig.tight_layout()
    save_fig(fig, FIG, "diag_cohort_pretrajectories_hydrogen")

    # 5. Control exposure
    e = pd.read_csv(OUT / "p4_control_exposure_corrected.csv")
    fig, axes = plt.subplots(1, 2, figsize=(8.6, 3.3))
    m = ["share_ever_approved_pct", "share_events_approved_pct",
         "share_firm_months_exposed_pct"]
    ml = ["Controls ever linked\nto an approved firm",
          "Technology-tagged events\nwith an approved partner",
          "Control firm-months\nexposed"]
    x = np.arange(len(m))
    for j, (tech, col) in enumerate([("Hydrogen", hyd), ("Battery", bat)]):
        r = e[e.technology == tech].iloc[0]
        axes[0].bar(x + (j - 0.5) * 0.36, [r[k] for k in m], 0.34,
                    color=col, label=tech)
    axes[0].set_xticks(x); axes[0].set_xticklabels(ml, fontsize=7.5)
    axes[0].set_ylabel("Per cent")
    axes[0].legend(frameon=False, fontsize=8)
    style_ax(axes[0])
    tr = pd.read_csv(OUT / "p4_exposure_trend.csv")
    for tech, col in [("Hydrogen", hyd), ("Battery", bat)]:
        d = tr[(tr.technology == tech) & tr.rel_month.between(-24, 36)]
        d = d.sort_values("rel_month")
        axes[1].plot(d.rel_month, d.share_pct, lw=1.3, color=col, label=tech)
    axes[1].axvline(0, color="grey", lw=0.8)
    axes[1].set_xlabel("Months relative to first approval in the technology")
    axes[1].set_ylabel("Share of control events with\nan approved IPCEI partner (%)")
    axes[1].legend(frameon=False, fontsize=8)
    style_ax(axes[1])
    fig.tight_layout()
    save_fig(fig, FIG, "diag_control_exposure")
    print("figures written to results/figures/diagnostics/")
