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
                         hydrogen = "log_collabs_crosssector_nace1_hydrogen")
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
  cross_sector_nace1 = "Robustness (NACE-1)"
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
  cross_sector_nace1 = "Cross-sector collaborations (NACE-1)"
)
