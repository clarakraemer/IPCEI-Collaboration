# ============================================================
# Shared Callaway & Sant'Anna helpers
# ============================================================
# Sourced by the method-specific estimation scripts
# (06/07_ck_didestimation_*_{ebal,unmatched}.Rmd) so the estimation logic has a
# single definition. The PSM scripts (…_psm.Rmd) keep their own inline copies;
# these functions reproduce that logic verbatim.
#
# Requires: did, dplyr (loaded by the calling script).

# --- Panel loader ------------------------------------------------------------
# Floors months, builds a CONTIGUOUS integer period index (dense rank -- NOT
# YYYY*100+MM, which distorts dynamic event time at year boundaries), a numeric
# g_period (0 = never-treated; numeric so did's Inf recoding does not NA it),
# an integer firm_id, and log1p / any() transforms of every n_collabs* column.
# A weight column `w` (entropy balancing) and the level outcome mean_collab_size
# pass through untouched.
load_cs <- function(path) {
  # fread: the ebal/unmatched panels are ~600-700 MB, far too slow for read.csv
  df <- as.data.frame(data.table::fread(path, showProgress = FALSE))
  df$month <- as.Date(df$month)

  mfloor     <- as.Date(format(df$month, "%Y-%m-01"))
  u_periods  <- sort(unique(mfloor))
  period_idx <- setNames(seq_along(u_periods), as.character(u_periods))
  df$period  <- as.integer(period_idx[as.character(mfloor)])

  df$g <- as.character(df$g)
  df$g[df$g == "" | df$g == "NA"] <- NA
  g_floor     <- as.Date(format(as.Date(df$g), "%Y-%m-01"))
  df$g_period <- period_idx[as.character(g_floor)]
  df$g_period[is.na(df$g_period)] <- 0L
  df$g_period <- as.numeric(df$g_period)

  df$firm_id <- as.integer(factor(df$Linkedin_name))

  count_cols <- grep("^n_collabs", names(df), value = TRUE)
  for (cc in count_cols) {
    df[[sub("^n_collabs", "log_collabs", cc)]] <- log1p(df[[cc]])
    df[[sub("^n_collabs", "any_collabs", cc)]] <- as.integer(df[[cc]] > 0)
  }

  # Difference-of-logs contrasts. C&S is linear in the outcome, so the ATT on a
  # difference equals the difference of the two separately estimated ATTs, but
  # with the correct standard error from the shared influence function. That
  # covariance is the point: comparing two separately estimated ATTs by their
  # significance stars is not a test of their difference.
  # These are NOT n_collabs* columns, so they never enter the generic log1p
  # loop above and never enter the primary outcome table or its BH family.
  for (tech in c("battery", "hydrogen")) {
    f <- paste0("log_collabs_", tech)
    u <- paste0("log_collabs_nonfunded_", tech)
    if (all(c(f, u) %in% names(df)))
      df[[paste0("log_rel_tech_", tech)]] <- df[[f]] - df[[u]]
    # Geographic contrast on the COLLABORATION-LEVEL, mutually exclusive
    # categories. The earlier version differenced the dyad-level cross-border EU
    # and non-EU outcomes, which overlap (one collaboration could enter both),
    # so that contrast was attenuated by construction and is not used.
    e <- paste0("log_collabs_eu_internal_", tech)
    n <- paste0("log_collabs_international_", tech)
    if (all(c(e, n) %in% names(df)))
      df[[paste0("log_rel_geo_", tech)]] <- df[[e]] - df[[n]]
    # Sectoral contrast, same logic on the mutually exclusive NACE-1 pair.
    x <- paste0("log_collabs_crosssector_n1_", tech)
    s <- paste0("log_collabs_samesector_n1_", tech)
    if (all(c(x, s) %in% names(df)))
      df[[paste0("log_rel_sector_", tech)]] <- df[[x]] - df[[s]]
  }
  df
}

# --- Primary control group (mirrors PSM): never-treated for both technologies -
cg_for <- function(technology) "nevertreated"

# Bootstrap draws. At 999 the Monte Carlo error moved borderline p-values
# across 0.05 between otherwise identical runs; 9999 is stable to ~0.7%.
BITERS_DEFAULT <- 9999

# --- att_gt wrapper ----------------------------------------------------------
# weightsname carries entropy-balancing weights ("w"); xformla carries
# doubly-robust covariates (unmatched). biters can be lowered for the large
# unmatched pool. Returns NULL on failure so a single bad outcome never aborts
# the whole run.
run_cs <- function(df, yname, label = "", xformla = NULL,
                   control_group = "nevertreated", clustervars = "firm_id",
                   weightsname = NULL, biters = BITERS_DEFAULT, bstrap = TRUE,
                   anticipation = 0, allow_unbalanced_panel = FALSE) {
  cat("\n=== C&S:", label, "(", yname, ") ===\n")
  # Deterministic per-outcome seed: makes every estimate reproducible and
  # independent of how many other outcomes ran earlier in the same session.
  # With a single set.seed() up front, adding one outcome shifts the bootstrap
  # stream for every later run and moves all downstream p-values.
  set.seed(42L + sum(utf8ToInt(paste0(yname, control_group))))
  cs_out <- tryCatch(
    att_gt(
      yname         = yname,
      tname         = "period",
      idname        = "firm_id",
      gname         = "g_period",
      control_group = control_group,
      clustervars   = clustervars,
      weightsname   = weightsname,
      anticipation  = anticipation,
      bstrap        = bstrap,
      cband         = bstrap,   # cband requires the bootstrap; off when bstrap=FALSE
      biters        = biters,
      panel         = TRUE,
      allow_unbalanced_panel = allow_unbalanced_panel,
      xformla       = xformla,
      pl            = TRUE,
      data          = df
    ),
    error = function(e) { cat("   att_gt failed:", conditionMessage(e), "\n"); NULL }
  )
  cs_out
}

# --- Aggregation + inference -------------------------------------------------
agg_simple  <- function(cs, bstrap = TRUE) if (is.null(cs)) NULL else
  aggte(cs, type = "simple", bstrap = bstrap, cband = bstrap)
agg_dynamic <- function(cs, bstrap = TRUE) if (is.null(cs)) NULL else
  aggte(cs, type = "dynamic", min_e = -12, max_e = 24, bstrap = bstrap, cband = bstrap)

pval_from_att <- function(att, se) round(2 * pnorm(-abs(att / se)), 3)

# Pre-trend test: did's Wald when available, else a joint chi-square of the
# pre-period (e < 0) dynamic event-study t-statistics.
es_pretrend <- function(cs_out) {
  if (is.null(cs_out)) return(list(stat = NA_real_, p = NA_real_, method = NA_character_))
  if (!is.null(cs_out$Wpval))
    return(list(stat = round(cs_out$W, 3), p = round(cs_out$Wpval, 3), method = "Wald"))
  dyn <- tryCatch(
    aggte(cs_out, type = "dynamic", min_e = -12, max_e = 24, bstrap = FALSE, cband = FALSE),
    error = function(e) NULL)
  if (is.null(dyn)) return(list(stat = NA_real_, p = NA_real_, method = NA_character_))
  pre <- dyn$egt < 0
  t2  <- (dyn$att.egt[pre] / dyn$se.egt[pre])^2
  ok  <- is.finite(t2); k <- sum(ok)
  if (k == 0) return(list(stat = NA_real_, p = NA_real_, method = NA_character_))
  stat <- sum(t2[ok])
  list(stat = round(stat, 3), p = round(1 - pchisq(stat, df = k), 3), method = "ES-joint")
}

sample_stats <- function(df, yname) {
  df_use <- df %>%
    filter(!is.na(.data[[yname]]), !is.na(firm_id), !is.na(period), !is.na(g_period))
  data.frame(
    N_obs     = nrow(df_use),
    N_units   = n_distinct(df_use$firm_id),
    N_treated = n_distinct(df_use$firm_id[df_use$g_period > 0]),
    stringsAsFactors = FALSE
  )
}

# --- Design-based power simulation -------------------------------------------
# What it answers: if the true ATT on this outcome were `att_true`, how often
# would THIS design -- these treated firms, these cohort sizes and approval
# dates, these matched controls, this estimator -- reject the null at `alpha`?
#
# Design (rewritten Nov 2026; see the note below for what it replaces):
#  1. Impose the null on the real sample. The estimated effect `att_hat` is
#     subtracted from the treated firms' post-approval observations, so the
#     data carry no average effect while keeping every firm's actual level and
#     volatility.
#  2. Add the hypothesised effect `att_true` over the same post-period. The net
#     shift is (att_true - att_hat).
#  3. Draw sampling variation by resampling FIRMS with replacement: treated
#     firms within their own cohort, so cohort sizes and approval dates are held
#     at their real values, and controls from the matched control pool. Each
#     drawn copy becomes its own unit, so a firm sampled twice contributes two
#     independent units exactly as in a cluster bootstrap.
#  4. Re-estimate the C&S overall ATT per draw with the SAME inference the paper
#     reports -- the multiplier bootstrap, not the analytic influence function.
#     `biters_sim` trades precision for runtime; the reported tables use 9,999.
#
# WHAT THIS REPLACES, AND WHY (do not revert without reading this).
# The previous version built synthetic treated firms by DRAFTING THEM FROM THE
# MATCHED CONTROLS. That overstated power in every cell, by 1.07x on hydrogen
# non-funded up to 4.5x on battery EU-internal, because a control firm is not
# exchangeable with a treated firm on a technology-tagged outcome: controls are
# 96-99% zeros there (battery EU-internal sd(log1p) 0.097 against 0.430 for the
# treated), so a constant added to a near-degenerate series is detected almost
# surely. The measured variance ratio tracked the measured bias in the minimum
# detectable effect almost exactly (4.42 against 4.50 on battery EU-internal,
# 2.11 against 2.12 on hydrogen national). It also used `bstrap = FALSE`, which
# on its own cost a further ~1.7x at battery's 29 clusters. The result was
# self-contradicting: the simulation claimed to detect a 5% effect on battery
# EU-internal while the observed 11% effect on that outcome has p = 0.144.
# Resampling the REAL treated firms fixes the first cause by construction, since
# the placebo population is then the treated population; `bstrap = TRUE` fixes
# the second. Validate with the size check below, never by eye.
#
# SIZE CHECK. At att_true = att_hat the net shift is zero and the rejection rate
# must come out near `alpha`. The run chunks therefore prepend 0 to the effect
# grid. A size far from 0.05 means the design is broken again, and it is the one
# diagnostic that would have caught the version this replaces. `mde_at` ignores
# the zero row.
#
# Other properties kept from the previous version:
#  * `control_group` has NO default. The simulation must mirror the estimator it
#    defends. An earlier inline copy in 07 hard-coded "notyettreated" while every
#    reported estimate uses never-treated controls (cg_for()); for staggered
#    hydrogen that is a different design.
#  * the seed is derived from (outcome, label, effect size), so each cell is
#    reproducible and independent of how many simulations ran before it.
#  * returns a one-row data.frame carrying the number of draws that converged,
#    so a cell that silently failed is visible instead of averaging over NAs.
#
# Works for the log1p count outcomes and for the difference-of-logs contrasts
# alike; for a contrast, `att_true` is a shift in the log DIFFERENCE, so read
# the grid in log points rather than as a percentage change.
run_power_sim <- function(cs_data, outcome_var, att_true, control_group,
                          n_sims = 200, label = "", alpha = 0.05,
                          att_hat = 0, biters_sim = 199) {
  if (!outcome_var %in% names(cs_data)) {
    cat("  !! power sim:", outcome_var, "not found -- skipping\n")
    return(NULL)
  }
  # Leave the global RNG stream exactly as we found it. run_cs() reseeds before
  # every att_gt, but aggte()'s multiplier bootstrap does NOT, so its standard
  # errors depend on the stream position. Without this guard a power run placed
  # before any reported aggregation would move that outcome's p-value.
  .old_seed <- if (exists(".Random.seed", envir = .GlobalEnv))
    get(".Random.seed", envir = .GlobalEnv) else NULL
  on.exit({
    if (!is.null(.old_seed))
      assign(".Random.seed", .old_seed, envir = .GlobalEnv)
  }, add = TRUE)

  set.seed(1000L + sum(utf8ToInt(paste0(outcome_var, label))) +
             as.integer(round(att_true * 1e4)))
  crit <- qnorm(1 - alpha / 2)

  # Keep only what att_gt needs. Copying a 4-column frame per draw rather than
  # the full panel is most of the runtime difference at 500 draws.
  keep <- c("Linkedin_name", "period", outcome_var)
  base_trt <- cs_data[cs_data$is_treated == 1, keep, drop = FALSE]
  base_ctl <- cs_data[cs_data$is_control == 1, keep, drop = FALSE]
  if (!nrow(base_trt) || !nrow(base_ctl)) {
    cat("  !! power sim:", outcome_var, "has no treated or no control rows\n")
    return(NULL)
  }

  # Real cohort structure: which treated firms were approved in which period.
  trt_firms <- unique(cs_data[cs_data$is_treated == 1,
                              c("Linkedin_name", "g_period")])
  cohorts   <- split(trt_firms$Linkedin_name, trt_firms$g_period)
  ctl_firms <- unique(base_ctl$Linkedin_name)

  # Row indices per firm, computed once. Drawing a firm is then an index lookup.
  rows_trt <- split(seq_len(nrow(base_trt)), base_trt$Linkedin_name)
  rows_ctl <- split(seq_len(nrow(base_ctl)), base_ctl$Linkedin_name)

  net_shift <- att_true - att_hat
  results   <- rep(NA_integer_, n_sims)

  for (i in seq_len(n_sims)) {
    # Treated: resample within cohort, so cohort sizes and approval dates hold.
    trt_draw <- unlist(lapply(cohorts, function(f)
      sample(f, length(f), replace = TRUE)), use.names = FALSE)
    g_draw   <- rep(as.numeric(names(cohorts)), lengths(cohorts))
    ctl_draw <- sample(ctl_firms, length(ctl_firms), replace = TRUE)

    it <- rows_trt[trt_draw]
    ic <- rows_ctl[ctl_draw]
    n_t <- lengths(it)
    n_c <- lengths(ic)

    sim_data <- rbind(base_trt[unlist(it, use.names = FALSE), , drop = FALSE],
                      base_ctl[unlist(ic, use.names = FALSE), , drop = FALSE])
    # Every drawn copy is its own unit, so a firm sampled twice enters twice.
    sim_data$firm_id_sim  <- rep(seq_len(length(it) + length(ic)), c(n_t, n_c))
    sim_data$g_period_sim <- rep(c(g_draw, rep(0, length(ic))), c(n_t, n_c))

    post <- sim_data$g_period_sim > 0 &
      sim_data$period >= sim_data$g_period_sim
    sim_data$outcome_sim <- sim_data[[outcome_var]] + net_shift * as.integer(post)

    results[i] <- tryCatch({
      cs_sim <- att_gt(
        yname = "outcome_sim", tname = "period", idname = "firm_id_sim",
        gname = "g_period_sim", control_group = control_group,
        anticipation = 0, bstrap = TRUE, biters = biters_sim, cband = FALSE,
        panel = TRUE, print_details = FALSE, data = sim_data)
      agg <- aggte(cs_sim, type = "simple", bstrap = TRUE,
                   biters = biters_sim, cband = FALSE)
      if (!is.finite(agg$overall.se) || agg$overall.se <= 0) NA_integer_
      else as.integer(abs(agg$overall.att / agg$overall.se) > crit)
    }, error = function(e) NA_integer_)
  }

  data.frame(
    att_log  = att_true,
    att_pct  = round((exp(att_true) - 1) * 100, 1),
    power    = mean(results, na.rm = TRUE),
    n_draws  = sum(!is.na(results)),
    n_sims   = n_sims,
    att_hat  = att_hat,
    stringsAsFactors = FALSE
  )
}

# Minimum detectable effect: the effect size at which a simulated power curve
# first reaches `target`, linearly interpolated between the two bracketing grid
# points. With a finite number of draws the curve is not guaranteed monotone, so
# the convention is the FIRST crossing. NA when the curve never reaches target
# on the grid, which is itself the finding ("not powered over the range tested").
mde_at <- function(effect, power, target = 0.80) {
  ok <- is.finite(effect) & is.finite(power)
  effect <- effect[ok]; power <- power[ok]
  if (!length(effect)) return(NA_real_)
  o <- order(effect); effect <- effect[o]; power <- power[o]
  if (max(power) < target) return(NA_real_)
  if (power[1] >= target)  return(effect[1])
  i <- which(power >= target)[1]
  effect[i - 1] + (target - power[i - 1]) *
    (effect[i] - effect[i - 1]) / (power[i] - power[i - 1])
}

# Standard effect grid for every power run in the project, so the three CSVs
# (intensity, composition, contrasts) stack into one figure.
POWER_PCT_GRID <- c(5, 10, 15, 20, 30, 40)
POWER_LOG_GRID <- log(1 + POWER_PCT_GRID / 100)

make_att_row_std <- function(agg_obj, technology, outcome, type,
                             cs_out = NULL, df = NULL, yname = NULL) {
  if (is.null(agg_obj))
    return(NULL)
  stats <- if (!is.null(df) && !is.null(yname)) sample_stats(df, yname) else
    data.frame(N_obs = NA_integer_, N_units = NA_integer_, N_treated = NA_integer_)
  pt <- es_pretrend(cs_out)
  data.frame(
    Technology       = technology,
    Outcome          = outcome,
    Type             = type,
    TimeUnit         = "month",
    ATT              = round(agg_obj$overall.att, 4),
    SE               = round(agg_obj$overall.se,  4),
    p_value          = pval_from_att(agg_obj$overall.att, agg_obj$overall.se),
    pretrend_stat    = pt$stat,
    pretrend_p_value = pt$p,
    pretrend_test    = pt$method,
    N_obs            = stats$N_obs,
    N_units          = stats$N_units,
    N_treated        = stats$N_treated,
    stringsAsFactors = FALSE
  )
}

# Dynamic event-study long frame for one cs_out (for plotting / export).
# Columns and label format match the PSM outputs exactly, since nb08 filters by
# `label == "<Technology> -- <Outcome>"` and reads `e` / `ci_lower` / `ci_upper`.
es_frame <- function(cs_out, technology, outcome_label, bstrap = TRUE) {
  if (is.null(cs_out)) return(NULL)
  dyn <- tryCatch(aggte(cs_out, type = "dynamic", min_e = -12, max_e = 24,
                        bstrap = bstrap, cband = bstrap),
                  error = function(e) NULL)
  if (is.null(dyn)) return(NULL)
  # Simultaneous critical value when the bootstrap supplies one (cband = TRUE),
  # pointwise normal otherwise.
  crit <- if (!is.null(dyn$crit.val.egt) && is.finite(dyn$crit.val.egt))
    dyn$crit.val.egt else qnorm(0.975)
  data.frame(
    label      = paste0(technology, " -- ", outcome_label),
    Technology = technology,
    Outcome    = outcome_label,
    e          = dyn$egt,
    att        = dyn$att.egt,
    se         = dyn$se.egt,
    crit_val   = crit,
    ci_lower   = dyn$att.egt - crit * dyn$se.egt,
    ci_upper   = dyn$att.egt + crit * dyn$se.egt,
    TimeUnit   = "month",
    stringsAsFactors = FALSE
  )
}

# --- Composition outcome map (tech-tagged) -----------------------------------
# Human-readable outcome name -> the log-transformed count column per technology.
outcome_map <- list(
  tech_focused       = c(battery = "log_collabs_battery",
                         hydrogen = "log_collabs_hydrogen"),
  cross_border       = c(battery = "log_collabs_eu_crossborder_battery",
                         hydrogen = "log_collabs_eu_crossborder_hydrogen"),
  cross_sector       = c(battery = "log_collabs_crosssector_battery",
                         hydrogen = "log_collabs_crosssector_hydrogen"),
  cross_sector_eu    = c(battery = "log_collabs_crosssector_eu_battery",
                         hydrogen = "log_collabs_crosssector_eu_hydrogen"),
  non_eu             = c(battery = "log_collabs_non_eu_battery",
                         hydrogen = "log_collabs_non_eu_hydrogen"),
  domestic           = c(battery = "log_collabs_domestic_battery",
                         hydrogen = "log_collabs_domestic_hydrogen"),
  within_sector      = c(battery = "log_collabs_withinsector_battery",
                         hydrogen = "log_collabs_withinsector_hydrogen"),
  non_funded         = c(battery = "log_collabs_nonfunded_battery",
                         hydrogen = "log_collabs_nonfunded_hydrogen"),
  cross_sector_nace1 = c(battery = "log_collabs_crosssector_nace1_battery",
                         hydrogen = "log_collabs_crosssector_nace1_hydrogen"),
  # Collaboration-level geography (built in nb03). Unlike the dyad-level
  # outcomes above, these classify the collaboration as a whole from its
  # participants' headquarters countries, so national/cross-border and
  # EU-internal/international are mutually exclusive pairs.
  cl_national        = c(battery = "log_collabs_national_battery",
                         hydrogen = "log_collabs_national_hydrogen"),
  cl_crossborder     = c(battery = "log_collabs_crossborder_battery",
                         hydrogen = "log_collabs_crossborder_hydrogen"),
  cl_eu_internal     = c(battery = "log_collabs_eu_internal_battery",
                         hydrogen = "log_collabs_eu_internal_hydrogen"),
  cl_international   = c(battery = "log_collabs_international_battery",
                         hydrogen = "log_collabs_international_hydrogen"),
  cl_crosssector_n1  = c(battery = "log_collabs_crosssector_n1_battery",
                         hydrogen = "log_collabs_crosssector_n1_hydrogen"),
  cl_samesector_n1   = c(battery = "log_collabs_samesector_n1_battery",
                         hydrogen = "log_collabs_samesector_n1_hydrogen"),
  # Secondary contrasts, introduced during the robustness analysis. They are
  # deliberately absent from the outcome_map in 07_..._psm.Rmd so that the
  # primary table and its Benjamini-Hochberg family stay at the original nine
  # outcomes; these are reported with nominal p-values as exploratory results.
  rel_tech           = c(battery = "log_rel_tech_battery",
                         hydrogen = "log_rel_tech_hydrogen"),
  rel_geo            = c(battery = "log_rel_geo_battery",
                         hydrogen = "log_rel_geo_hydrogen"),
  rel_sector         = c(battery = "log_rel_sector_battery",
                         hydrogen = "log_rel_sector_hydrogen")
)

# Analytic classification for the att table Type column (matches the PSM tables,
# so method files stay structurally identical -- the method itself is encoded by
# the results/<method>/ folder, not the Type column).
outcome_type <- c(
  tech_focused       = "Primary",
  cross_border       = "Primary",
  cross_sector       = "Primary",
  cross_sector_eu    = "Primary",
  non_eu             = "Placebo",
  domestic           = "Placebo",
  within_sector      = "Placebo",
  non_funded         = "Benchmark",
  cross_sector_nace1 = "Robustness (NACE-1)",
  cl_national        = "Benchmark",
  cl_crossborder     = "Primary",
  cl_eu_internal     = "Primary",
  cl_international   = "Benchmark",
  cl_crosssector_n1  = "Primary",
  cl_samesector_n1   = "Benchmark",
  rel_tech           = "Contrast",
  rel_geo            = "Contrast",
  rel_sector         = "Contrast"
)

# Pretty labels for the att table Outcome column (match the PSM tables).
outcome_labels <- c(
  tech_focused       = "Technology-tagged collaborations",
  cross_border       = "Cross-border EU collaborations",
  cross_sector       = "Cross-sector collaborations",
  cross_sector_eu    = "Cross-sector EU-only collaborations",
  non_eu             = "Non-EU collaborations",
  domestic           = "Domestic collaborations",
  within_sector      = "Within-sector collaborations",
  cross_sector_nace1 = "Cross-sector collaborations (NACE-1)",
  non_funded         = "Non-funded collaborations",
  cl_national        = "National collaborations",
  cl_crossborder     = "Cross-border collaborations",
  cl_eu_internal     = "EU-internal collaborations",
  cl_international   = "International collaborations",
  cl_crosssector_n1  = "Cross-sector collaborations",
  cl_samesector_n1   = "Same-sector collaborations",
  # Secondary contrasts. Labelled so any script that loops over outcome_map
  # finds a label; outcome_type below gives them their own class.
  rel_tech           = "Relative technology (log diff)",
  rel_geo            = "Relative geography (log diff)",
  rel_sector         = "Relative sector (log diff)"
)
