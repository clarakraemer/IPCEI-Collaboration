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
