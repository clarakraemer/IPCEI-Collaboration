# ============================================================
# Propensity score matching & diagnostics for IPCEI analysis
# ============================================================

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression


# ============================================================
# Balance diagnostics
# ============================================================

def calculate_balance(data, treatment_var, continuous_vars):
    """
    Calculate standardized mean differences (SMD) for balance checks.
    """
    diagnostics = {}

    for var in continuous_vars:
        treated_mean = data[data[treatment_var] == 1][var].mean()
        control_mean = data[data[treatment_var] == 0][var].mean()
        pooled_sd = data[var].std()

        smd = (treated_mean - control_mean) / pooled_sd
        diagnostics[var] = smd

    return diagnostics

def choose_best_spec(results_dict, prefer="balanced_010"):
    """
    Choose best spec data-driven:
      1) prefer balanced_010 if available, else balanced_015 if available, else all specs
      2) within tier: minimize max_smd, then maximize total N
    Returns: (best_key, best_result) or (None, None)
    """
    if not results_dict:
        return None, None

    # Tier 1: balanced_010
    tier = {k: v for k, v in results_dict.items() if v.get("balanced_010")}
    if not tier:
        # Tier 2: balanced_015
        tier = {k: v for k, v in results_dict.items() if v.get("balanced_015")}
    if not tier:
        # Tier 3: fallback to everything
        tier = results_dict

    def score(item):
        k, v = item
        n_total = v.get("n_treated", 0) + v.get("n_control", 0)
        return (v.get("max_smd", float("inf")), -n_total)

    best_key, best_result = min(tier.items(), key=score)
    return best_key, best_result


# ============================================================
# Propensity score matching
# ============================================================

def propensity_score_match(
    data,
    treatment_var,
    continuous_vars,
    exact_match_vars,
    ratio=5,
    caliper=0.2,
    exclude_other_treated=True,
    treated_any_col="treated_any",
    random_state=42,
):
    """
    Perform PSM with exact matching on categorical variables.
    """

    df = data.copy()

    treated = df[df[treatment_var] == 1].copy()

    if exclude_other_treated:
        potential_controls = df[df[treated_any_col] == 0].copy()
    else:
        potential_controls = df[df[treatment_var] == 0].copy()

    # Drop missing
    all_vars = continuous_vars + exact_match_vars
    treated = treated.dropna(subset=all_vars)
    potential_controls = potential_controls.dropna(subset=all_vars)

    matched_controls = []
    unmatched_treated = []

    def create_exact_group(row):
        return tuple(row[var] for var in exact_match_vars)

    treated["exact_group"] = treated.apply(create_exact_group, axis=1)
    potential_controls["exact_group"] = potential_controls.apply(create_exact_group, axis=1)

    for exact_group in treated["exact_group"].unique():

        treated_group = treated[treated["exact_group"] == exact_group].copy()
        controls_group = potential_controls[
            potential_controls["exact_group"] == exact_group
        ].copy()

        if len(controls_group) == 0:
            unmatched_treated.append(treated_group)
            continue

        group_data = pd.concat([treated_group, controls_group], axis=0)

        X = group_data[continuous_vars].values
        y = group_data[treatment_var].values

        if y.sum() == 0 or y.sum() == len(y):
            # fallback: nearest neighbour on covariates
            for idx, treated_row in treated_group.iterrows():
                X_treated = treated_row[continuous_vars].values
                X_controls = controls_group[continuous_vars].values

                distances = np.sqrt(((X_controls - X_treated) ** 2).sum(axis=1))
                controls_group["distance"] = distances

                matched = controls_group.nsmallest(
                    min(ratio, len(controls_group)), "distance"
                )
                matched["matched_to"] = idx
                matched["treatment_group"] = treatment_var
                matched_controls.append(matched)

            continue

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        lr = LogisticRegression(max_iter=1000, random_state=random_state)
        lr.fit(X_scaled, y)

        ps = lr.predict_proba(X_scaled)[:, 1]
        group_data["propensity_score"] = ps

        ps_std = ps.std()
        caliper_width = caliper * ps_std

        treated_ps = group_data[group_data[treatment_var] == 1].copy()
        controls_ps = group_data[group_data[treatment_var] == 0].copy()

        for idx, trow in treated_ps.iterrows():

            treated_score = trow["propensity_score"]

            controls_ps["ps_distance"] = np.abs(
                controls_ps["propensity_score"] - treated_score
            )

            within = controls_ps[
                controls_ps["ps_distance"] <= caliper_width
            ].copy()

            if len(within) == 0:
                unmatched_treated.append(treated.loc[[idx]])
                continue

            matched = within.nsmallest(
                min(ratio, len(within)), "ps_distance"
            )
            matched["matched_to"] = idx
            matched["treatment_group"] = treatment_var
            matched_controls.append(matched)

    if len(matched_controls) == 0:
        return None, None

    matched_controls_df = pd.concat(matched_controls, axis=0)

    matched_ids = matched_controls_df["matched_to"].unique()
    treated_matched = treated[treated.index.isin(matched_ids)].copy()

    treated_matched["matched_to"] = treated_matched.index
    treated_matched["treatment_group"] = treatment_var

    matched_sample = pd.concat([treated_matched, matched_controls_df], axis=0)
    matched_sample = matched_sample.drop(columns=["exact_group"], errors="ignore")

    diagnostics = calculate_balance(
        matched_sample, treatment_var, continuous_vars
    )

    return matched_sample, diagnostics


# ============================================================
# Eligible pool (NO matching) — structural comparators only
# ============================================================

def eligible_pool(
    data,
    treatment_var,
    exact_match_vars,
    treated_any_col="treated_any",
    exclude_other_treated=True,
    require_vars=None,
    n_controls=None,
    random_state=42,
):
    """
    Return treated firms + all *structurally eligible* controls, with NO
    matching applied.

    Eligibility uses only the exact-match strata the PSM design conditions on
    (e.g. nace1_psm x has_eu_operation), so the pool is the same universe PSM
    draws from, minus the caliper / nearest-neighbour step. Baseline
    collaboration and centrality are deliberately NOT used to gate the pool --
    those belong in the estimator's covariate adjustment (xformla), so the
    unmatched design is a genuine no-matching-on-selection test.

    Adds is_treated / is_control (0/1) and returns one concatenated frame.
    """
    df = data.copy()

    treated = df[df[treatment_var] == 1].copy()

    if exclude_other_treated:
        controls = df[df[treated_any_col] == 0].copy()
    else:
        controls = df[df[treatment_var] == 0].copy()

    # Drop rows missing the strata (and any explicitly required covariates)
    need = list(exact_match_vars) + (list(require_vars) if require_vars else [])
    treated = treated.dropna(subset=need)
    controls = controls.dropna(subset=need)

    # Restrict controls to strata that actually occur among treated firms
    treated_strata = set(
        treated[exact_match_vars].itertuples(index=False, name=None)
    )
    ctrl_keys = controls[exact_match_vars].itertuples(index=False, name=None)
    mask = [k in treated_strata for k in ctrl_keys]
    controls = controls[mask].copy()

    # Optional seeded random subsample of the control pool. This is a purely
    # computational device for a very large never-treated pool -- random, so it
    # does NOT reintroduce selection or undermine the no-matching test. All
    # treated units are always kept.
    if n_controls is not None and len(controls) > n_controls:
        controls = controls.sample(n=n_controls, random_state=random_state)

    treated["is_treated"] = 1
    treated["is_control"] = 0
    controls["is_treated"] = 0
    controls["is_control"] = 1

    pool = pd.concat([treated, controls], axis=0, ignore_index=True)
    return pool


# ============================================================
# Entropy balancing (Hainmueller 2012) — matching alternative
# ============================================================

def entropy_balance(
    data,
    treatment_var,
    continuous_vars,
    exact_match_vars,
    treated_any_col="treated_any",
    exclude_other_treated=True,
    balance_variance=False,
    max_iter=1000,
    n_controls=None,
    random_state=42,
):
    """
    Entropy balancing as an alternative to PSM.

    Builds the same eligible pool as `eligible_pool`, then solves for weights on
    the control firms so that the *weighted* control covariate means match the
    treated means (first moments; optionally variances too, if
    `balance_variance`). Treated firms receive weight 1. The exact-match
    categoricals enter as dummy moment constraints, so the reweighted controls
    also reproduce the treated distribution across sectors / EU-operation.

    Unlike PSM this keeps every treated unit (crucial with few treated) and is
    not exposed to the King & Nielsen (2019) propensity-score matching critique.

    Returns (pool, info):
      pool : eligible-pool frame with a firm-level column ``w`` (treated = 1,
             controls = balancing weight, mean-1 normalised within controls).
      info : dict with convergence flag, achieved moment gap, effective control
             sample size (Kish), max weight, and Ns. A False ``converged`` with
             a concentrated weight (large max_weight / small eff_n_control) is
             the overlap-failure signal: the treated moments lie outside the
             control support and no reweighting can balance them.
    """
    pool = eligible_pool(
        data,
        treatment_var,
        exact_match_vars,
        treated_any_col=treated_any_col,
        exclude_other_treated=exclude_other_treated,
        require_vars=continuous_vars,
        n_controls=n_controls,
        random_state=random_state,
    )

    # Moment matrix: continuous covariates + strata dummies (+ squares).
    dummies = pd.get_dummies(
        pool[exact_match_vars].astype(str), drop_first=True, dtype=float
    )
    parts = [pool[continuous_vars].astype(float).reset_index(drop=True),
             dummies.reset_index(drop=True)]
    if balance_variance:
        sq = pool[continuous_vars].astype(float) ** 2
        sq.columns = [f"{c}__sq" for c in continuous_vars]
        parts.append(sq.reset_index(drop=True))
    M = pd.concat(parts, axis=1)

    is_t = (pool["is_treated"].values == 1)
    Mt = M.values[is_t]
    Mc = M.values[~is_t]
    target = Mt.mean(axis=0)                 # treated moment means
    Z0 = Mc - target                         # centered control moments
    scale = Z0.std(axis=0)
    scale[scale == 0] = 1.0
    Z = Z0 / scale                           # standardise for conditioning

    # Hainmueller (2012) dual: minimise L(lam)=log mean exp(-Z@lam); the balance
    # condition sum_i w_i Z_i = 0 holds at the minimum. Newton + Armijo.
    n_c = Z.shape[0]

    def _weights(lam):
        a = -Z @ lam
        a -= a.max()
        w = np.exp(a)
        return w / w.sum()

    def _loss(lam):
        a = -Z @ lam
        c = a.max()
        return c + np.log(np.exp(a - c).sum())

    lam = np.zeros(Z.shape[1])
    it = 0
    for it in range(max_iter):
        w = _weights(lam)
        imb = (w[:, None] * Z).sum(axis=0)        # gradient of -L
        if np.max(np.abs(imb)) < 1e-9:
            break
        H = (Z * w[:, None]).T @ Z - np.outer(imb, imb)   # weighted covariance
        step = np.linalg.solve(H + 1e-12 * np.eye(Z.shape[1]), imb)
        f0 = _loss(lam)
        a = 1.0
        for _ in range(60):
            if _loss(lam + a * step) <= f0 - 1e-4 * a * (imb @ step):
                break
            a *= 0.5
        lam = lam + a * step

    w = _weights(lam)
    balance_gap = float(np.max(np.abs((w[:, None] * Z).sum(axis=0))))
    w = w * n_c                                  # mean-1 normalise within controls

    pool["w"] = 1.0
    pool.loc[~is_t, "w"] = w

    achieved = (w[:, None] * Mc).sum(axis=0) / w.sum()
    eff_n = float((w.sum() ** 2) / (w ** 2).sum())   # Kish effective sample size
    info = {
        "converged": balance_gap < 1e-6,
        "iterations": int(it),
        "balance_gap_std": balance_gap,
        "max_abs_moment_gap": float(np.max(np.abs(achieved - target))),
        "max_weight": float(w.max()),
        "eff_n_control": eff_n,
        "n_treated": int(is_t.sum()),
        "n_control": int(n_c),
        "moments": list(M.columns),
    }
    return pool, info
