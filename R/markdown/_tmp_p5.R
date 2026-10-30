# ============================================================
# IPCEI DiD --- round-3 diagnostics
# ============================================================
# Separate from the primary scripts: writes ONLY to
# results/psm/diagnostics/ and never touches intensity/ or
# composition_techtagged/. Nothing here changes the primary estimates.
#
# Part 1  reference-period (anticipation) decomposition, hydrogen
# Part 2  cohort-level ATTs and Germany-exclusion sensitivity
# Part 3  approval-month vs later event-time split
# Part 5  funded-vs-unrelated difference outcome, raw counts
#
# Run:  Rscript 10_ck_diagnostics_reference_country.R
# Section flags below keep the slow bootstrap runs separable from the
# fast point-estimate decomposition.

suppressMessages({
  library(did); library(dplyr); library(tidyr)
})
# Must be run from R/markdown/ so that "../data" and "../results" resolve,
# exactly as the .Rmd scripts do.
if (!file.exists("_cs_helpers.R"))
  stop("run this from R/markdown/: Rscript 10_ck_diagnostics_reference_country.R")
source("_cs_helpers.R")

RUN_P1     <- FALSE    # fast: bstrap = FALSE
RUN_P2_P5  <- TRUE    # slow: full bootstrap
BITERS_DX  <- BITERS_DEFAULT   # 9999, same as the primary runs

OUT <- "../results/psm/diagnostics"
dir.create(OUT, showWarnings = FALSE, recursive = TRUE)

PANELS <- list(
  Battery  = "../data/battery_psm_spec1_cs_ready.csv",
  Hydrogen = "../data/hydrogen_psm_spec1_cs_ready.csv"
)
FIRMS <- list(
  Battery  = "../data/battery_psm_spec1_matched_firms.csv",
  Hydrogen = "../data/hydrogen_psm_spec1_matched_firms.csv"
)

# Outcomes carried through every part (keys into outcome_map).
KEYS <- c(tech_focused = "Technology-related",
          cross_border = "Cross-border EU",
          non_funded   = "Technology-unrelated")

# ------------------------------------------------------------
# Load panels; attach primary_country from the matched-firm files
# (the cs panels do not carry country, matching never used it).
# ------------------------------------------------------------
load_with_country <- function(tech) {
  df <- load_cs(PANELS[[tech]])
  fr <- read.csv(FIRMS[[tech]], stringsAsFactors = FALSE)
  cc <- fr %>%
    distinct(Linkedin_name, primary_country) %>%
    filter(!is.na(Linkedin_name)) %>%
    group_by(Linkedin_name) %>% slice(1) %>% ungroup()
  df <- df %>% left_join(cc, by = "Linkedin_name")
  df$is_de <- as.integer(!is.na(df$primary_country) & df$primary_country == "DE")
  df
}

panels <- lapply(names(PANELS), load_with_country)
names(panels) <- names(PANELS)

# Period index -> month label, for readable cohort names.
period_months <- function(df)
  df %>% distinct(period, month) %>% arrange(period)

cat("\n######## panel summary ########\n")
for (tech in names(panels)) {
  df <- panels[[tech]]
  gs <- sort(unique(df$g_period[df$g_period > 0]))
  pm <- period_months(df)
  lab <- format(pm$month[match(gs, pm$period)], "%Y-%m")
  cat(sprintf("%-9s periods %d..%d  cohorts: %s\n", tech,
              min(df$period), max(df$period),
              paste(sprintf("%s(p%d,n=%d)", lab, gs,
                            sapply(gs, function(g)
                              n_distinct(df$Linkedin_name[df$g_period == g]))),
                    collapse = ", ")))
}

# ============================================================
# PART 1 --- reference-period decomposition (hydrogen)
# ============================================================
# did sets the post-treatment base period to g-1-anticipation
# (compute.att_gt). The treated set, the cohorts and the aggregated
# cells (t >= g) are identical across k, so for every cell
#   ATT_k(g,t) - ATT_0(g,t) = DiD of the outcome between g-1-k and g-1,
# i.e. the relative evolution of treated vs never-treated over the k
# months before approval. This section verifies that cell by cell and
# then reconciles the two aggregates with did's own pg weights.

# did's simple aggregation: weights each post cell (t >= g) by pg, the
# share of the sample in cohort g. Reconstructed here so the aggregate
# can be rebuilt from the cells exactly.
pg_weights <- function(df) {
  n_tot <- n_distinct(df$Linkedin_name)
  df %>% distinct(Linkedin_name, g_period) %>%
    count(g_period, name = "n_g") %>%
    mutate(pg = n_g / n_tot)
}

# Mean log outcome by treated/never-treated at two periods -> 2x2 DiD.
# Used as the independent reconstruction of the cell-level gap.
raw_did <- function(df, yname, gval, t_pre, t_post) {
  # .env$ is required: the panel carries a column named `g` (the treatment
  # date), so an unqualified parameter would be masked by it.
  s <- df %>%
    filter(period %in% c(.env$t_pre, .env$t_post),
           g_period == .env$gval | g_period == 0) %>%
    mutate(grp = ifelse(g_period == .env$gval, "treated", "control"),
           tt  = ifelse(period == t_post, "post", "pre")) %>%
    group_by(grp, tt) %>% summarise(m = mean(.data[[yname]], na.rm = TRUE),
                                    .groups = "drop") %>%
    pivot_wider(names_from = tt, values_from = m)
  if (nrow(s) < 2) return(NA_real_)
  (s$post[s$grp == "treated"] - s$pre[s$grp == "treated"]) -
    (s$post[s$grp == "control"] - s$pre[s$grp == "control"])
}

if (RUN_P1) {
  cat("\n\n######## PART 1: reference-period decomposition (hydrogen) ########\n")
  df <- panels$Hydrogen
  pm <- period_months(df)
  w  <- pg_weights(df)
  cells <- list(); recon <- list()

  for (key in names(KEYS)) {
    y <- outcome_map[[key]][["hydrogen"]]
    if (!(y %in% names(df))) { cat("missing:", y, "\n"); next }

    cs0 <- run_cs(df, y, label = paste("Hydrogen", key, "k=0"), bstrap = FALSE)
    cs3 <- run_cs(df, y, label = paste("Hydrogen", key, "k=3"), bstrap = FALSE,
                  anticipation = 3)
    if (is.null(cs0) || is.null(cs3)) next

    a0 <- data.frame(g = cs0$group, t = cs0$t, att0 = cs0$att)
    a3 <- data.frame(g = cs3$group, t = cs3$t, att3 = cs3$att)
    cc <- a0 %>% inner_join(a3, by = c("g", "t")) %>%
      filter(t >= g) %>%                     # the cells aggte(simple) averages
      mutate(gap = att3 - att0)

    # Independent reconstruction of the gap from the raw pre-approval DiD.
    cc$gap_raw <- mapply(function(g, .) raw_did(df, y, g, g - 4, g - 1),
                         cc$g, cc$t)
    cc <- cc %>% left_join(w %>% select(g = g_period, pg, n_g), by = "g") %>%
      mutate(outcome = KEYS[[key]])
    cells[[key]] <- cc

    # Rebuild both aggregates from the cells with did's pg weights.
    rw <- cc$pg / sum(cc$pg)
    s0 <- sum(cc$att0 * rw); s3 <- sum(cc$att3 * rw)
    g0 <- agg_simple(cs0, bstrap = FALSE); g3 <- agg_simple(cs3, bstrap = FALSE)

    # Cohort shares of the aggregate: pg x (number of post cells for g).
    # pg is constant within a cohort, so the within-cohort average over its
    # post cells is an unweighted mean. Names kept distinct from the input
    # columns, since summarise() resolves later expressions against earlier
    # results and silently turned these into sums.
    coh <- cc %>% group_by(g) %>%
      summarise(n_cells = n(), n_g = first(n_g), pg_g = first(pg),
                att0 = mean(att0), att3 = mean(att3), gap = mean(gap),
                gap_raw = mean(gap_raw, na.rm = TRUE), .groups = "drop") %>%
      mutate(weight = n_cells * pg_g / sum(n_cells * pg_g),
             cohort = format(pm$month[match(g, pm$period)], "%Y-%m"),
             outcome = KEYS[[key]], contrib0 = weight * att0,
             contrib3 = weight * att3)
    recon[[key]] <- coh

    cat(sprintf("\n-- %s --\n", KEYS[[key]]))
    cat(sprintf("  aggte simple : k=0 %.4f | k=3 %.4f | gap %.4f\n",
                g0$overall.att, g3$overall.att,
                g3$overall.att - g0$overall.att))
    cat(sprintf("  rebuilt (pg) : k=0 %.4f | k=3 %.4f | gap %.4f\n",
                s0, s3, s3 - s0))
    cat(sprintf("  cell-gap mean vs raw-DiD mean: %.4f vs %.4f\n",
                weighted.mean(cc$gap, rw),
                weighted.mean(cc$gap_raw, rw)))
    print(as.data.frame(coh %>% select(cohort, n_g, n_cells, weight,
                                       att0, att3, gap, gap_raw)),
          row.names = FALSE, digits = 4)
  }
  if (length(cells)) {
    write.csv(bind_rows(cells), file.path(OUT, "p1_cells_k0_k3_hydrogen.csv"),
              row.names = FALSE)
    write.csv(bind_rows(recon), file.path(OUT, "p1_cohort_reconciliation.csv"),
              row.names = FALSE)
  }

  # Cohort-specific pre-approval relative trajectories, on the exact
  # log outcome, treated(g) minus never-treated, normalised at g-1.
  traj <- list()
  for (key in names(KEYS)) {
    y <- outcome_map[[key]][["hydrogen"]]
    if (!(y %in% names(df))) next
    for (g in sort(unique(df$g_period[df$g_period > 0]))) {
      for (e in -12:3) {
        tt <- g + e
        if (tt < min(df$period) || tt > max(df$period)) next
        mt <- mean(df[[y]][df$g_period == g & df$period == tt], na.rm = TRUE)
        mc <- mean(df[[y]][df$g_period == 0 & df$period == tt], na.rm = TRUE)
        traj[[length(traj) + 1]] <- data.frame(
          outcome = KEYS[[key]], g = g,
          cohort = format(pm$month[match(g, pm$period)], "%Y-%m"),
          e = e, rel = mt - mc)
      }
    }
  }
  tr <- bind_rows(traj) %>% group_by(outcome, cohort) %>%
    mutate(rel_norm = rel - rel[e == -1]) %>% ungroup()
  write.csv(tr, file.path(OUT, "p1_cohort_pretrajectories_hydrogen.csv"),
            row.names = FALSE)
  cat("\n-- relative trajectory, normalised at e=-1, technology-related --\n")
  print(as.data.frame(tr %>% filter(outcome == "Technology-related",
                                    e >= -6, e <= 1) %>%
                        select(cohort, e, rel_norm) %>%
                        pivot_wider(names_from = e, values_from = rel_norm)),
        row.names = FALSE, digits = 3)
}

# ============================================================
# PART 2 + 5 --- bootstrap runs
# ============================================================
if (RUN_P2_P5) {

  cat("\n\n######## PART 5: difference contrasts, extensive margin, raw counts ########\n")
  # The contrast columns now come from load_cs (both implementations), so these
  # are ordinary outcomes rather than an ad hoc routine. Reported as secondary
  # analyses with nominal p-values; they do NOT enter the primary table's
  # Benjamini-Hochberg family, which stays at its original nine outcomes.
  p5 <- list()
  CONTRASTS <- list(
    rel_tech = "Relative technology (log diff)",
    rel_geo  = "Relative geography, EU minus non-EU (log diff)")

  for (tech in c("Battery", "Hydrogen")) {
    sdf <- panels[[tech]]
    tl  <- tolower(tech)

    for (ck in names(CONTRASTS)) {
      y <- outcome_map[[ck]][[tl]]
      if (!(y %in% names(sdf))) { cat("missing contrast column:", y, "\n"); next }
      ks <- if (tech == "Hydrogen") c(0, 3) else 0
      for (k in ks) {
        cs <- run_cs(sdf, y, label = sprintf("%s %s k=%d", tech, ck, k),
                     biters = BITERS_DX, anticipation = k)
        ag <- agg_simple(cs); if (is.null(ag)) next
        pt <- es_pretrend(cs)
        p5[[paste(tech, ck, k)]] <- data.frame(
          technology = tech, outcome = CONTRASTS[[ck]],
          anticipation = k, att = round(ag$overall.att, 4),
          se = round(ag$overall.se, 4),
          p = pval_from_att(ag$overall.att, ag$overall.se),
          lo = round(ag$overall.att - 1.96 * ag$overall.se, 4),
          hi = round(ag$overall.att + 1.96 * ag$overall.se, 4),
          pretrend_p = pt$p)
      }
    }

    # Extensive margin on the primary outcome, re-run here so all three
    # estimands in the supplementary table come from one script and one seed.
    yext <- paste0("any_collabs_", tl)
    if (yext %in% names(sdf)) {
      cs <- run_cs(sdf, yext, label = paste(tech, "extensive margin"),
                   biters = BITERS_DX)
      ag <- agg_simple(cs)
      if (!is.null(ag))
        p5[[paste(tech, "ext")]] <- data.frame(
          technology = tech, outcome = "Technology-related (any collaboration)",
          anticipation = 0, att = round(ag$overall.att, 4),
          se = round(ag$overall.se, 4),
          p = pval_from_att(ag$overall.att, ag$overall.se),
          lo = round(ag$overall.att - 1.96 * ag$overall.se, 4),
          hi = round(ag$overall.att + 1.96 * ag$overall.se, 4),
          pretrend_p = es_pretrend(cs)$p)
    }

    yf <- outcome_map$tech_focused[[tl]]

    # Raw-count ATT: extra recorded collaborations per firm-month.
    ycount <- sub("^log_collabs", "n_collabs", yf)
    if (ycount %in% names(sdf)) {
      cs <- run_cs(sdf, ycount, label = paste(tech, "raw count"),
                   biters = BITERS_DX)
      ag <- agg_simple(cs)
      if (!is.null(ag)) {
        base <- mean(sdf[[ycount]][sdf$is_treated == 1 & sdf$post_event == 0],
                     na.rm = TRUE)
        p5[[paste(tech, "count")]] <- data.frame(
          technology = tech, outcome = "Technology-related (raw count)",
          anticipation = 0, att = round(ag$overall.att, 4),
          se = round(ag$overall.se, 4),
          p = pval_from_att(ag$overall.att, ag$overall.se),
          lo = round(ag$overall.att - 1.96 * ag$overall.se, 4),
          hi = round(ag$overall.att + 1.96 * ag$overall.se, 4),
          pretrend_p = es_pretrend(cs)$p)
        cat(sprintf("  %s pre-treatment treated mean count: %.3f\n", tech, base))
      }
    }
  }
  if (length(p5)) {
    pp <- bind_rows(p5)
    write.csv(pp, file.path(OUT, "p5_relative_and_counts.csv"), row.names = FALSE)
    cat("\n-- relative-technology and raw-count ATTs --\n")
    print(as.data.frame(pp), row.names = FALSE)
  }
}

cat("\n\nDone. Outputs in", normalizePath(OUT), "\n")
