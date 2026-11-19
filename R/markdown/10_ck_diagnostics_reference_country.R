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
# Part 6  power simulation for the direct contrasts
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

  # ---- 2a cohort-level ATTs (hydrogen) ------------------------------------
  cat("\n\n######## PART 2a: cohort-level ATTs (hydrogen) ########\n")
  df <- panels$Hydrogen
  pm <- period_months(df)
  grp_rows <- list(); dyn_rows <- list(); esplit_rows <- list()

  for (key in names(KEYS)) {
    y <- outcome_map[[key]][["hydrogen"]]
    if (!(y %in% names(df))) next
    cs <- run_cs(df, y, label = paste("Hydrogen", key, "(cohort)"),
                 biters = BITERS_DX)
    if (is.null(cs)) next

    # Cohort ATTs over all available post periods.
    gg <- tryCatch(aggte(cs, type = "group", bstrap = TRUE, cband = TRUE),
                   error = function(e) NULL)
    if (!is.null(gg)) {
      n_by_g <- df %>% distinct(Linkedin_name, g_period, is_de) %>%
        filter(g_period > 0) %>% count(g_period, is_de) %>%
        pivot_wider(names_from = is_de, values_from = n, values_fill = 0,
                    names_prefix = "n_de")
      r <- data.frame(outcome = KEYS[[key]], g = gg$egt,
                      att = gg$att.egt, se = gg$se.egt,
                      crit = gg$crit.val.egt, horizon = "all post") %>%
        mutate(cohort = format(pm$month[match(g, pm$period)], "%Y-%m"),
               p = pval_from_att(att, se),
               lo = att - 1.96 * se, hi = att + 1.96 * se) %>%
        left_join(n_by_g, by = c("g" = "g_period"))
      grp_rows[[paste(key, "all")]] <- r
    }

    # Cohort ATTs on a common 0-12 horizon where support allows.
    gg12 <- tryCatch(aggte(cs, type = "group", max_e = 12,
                           bstrap = TRUE, cband = TRUE),
                     error = function(e) NULL)
    if (!is.null(gg12)) {
      grp_rows[[paste(key, "0_12")]] <- data.frame(
        outcome = KEYS[[key]], g = gg12$egt, att = gg12$att.egt,
        se = gg12$se.egt, crit = gg12$crit.val.egt, horizon = "e 0-12") %>%
        mutate(cohort = format(pm$month[match(g, pm$period)], "%Y-%m"),
               p = pval_from_att(att, se),
               lo = att - 1.96 * se, hi = att + 1.96 * se)
    }

    # ---- 3 event-time split: e=0, e=1-3, e=4-12 --------------------------
    for (rng in list(c(0, 0), c(1, 3), c(4, 12), c(1, 12))) {
      a <- tryCatch(aggte(cs, type = "dynamic", min_e = rng[1], max_e = rng[2],
                          bstrap = TRUE, cband = TRUE),
                    error = function(e) NULL)
      if (is.null(a)) next
      esplit_rows[[paste(key, rng[1], rng[2])]] <- data.frame(
        outcome = KEYS[[key]], window = sprintf("e %d-%d", rng[1], rng[2]),
        att = a$overall.att, se = a$overall.se,
        p = pval_from_att(a$overall.att, a$overall.se))
    }

    # Cohort x e=0, to see whether the spike is the 2024-02 cohort.
    c0 <- data.frame(g = cs$group, t = cs$t, att = cs$att, se = cs$se) %>%
      filter(t == g) %>%
      mutate(outcome = KEYS[[key]],
             cohort = format(pm$month[match(g, pm$period)], "%Y-%m"),
             p = pval_from_att(att, se))
    dyn_rows[[key]] <- c0
  }

  if (length(grp_rows)) {
    gr <- bind_rows(grp_rows)
    write.csv(gr, file.path(OUT, "p2a_cohort_atts_hydrogen.csv"), row.names = FALSE)
    cat("\n-- cohort ATTs --\n"); print(as.data.frame(gr), row.names = FALSE, digits = 3)
  }
  if (length(esplit_rows)) {
    es <- bind_rows(esplit_rows)
    write.csv(es, file.path(OUT, "p3_eventtime_split_hydrogen.csv"), row.names = FALSE)
    cat("\n-- event-time split --\n"); print(as.data.frame(es), row.names = FALSE, digits = 3)
  }
  if (length(dyn_rows)) {
    d0 <- bind_rows(dyn_rows)
    write.csv(d0, file.path(OUT, "p3_approval_month_by_cohort.csv"), row.names = FALSE)
    cat("\n-- approval-month ATT(g,g) by cohort --\n")
    print(as.data.frame(d0 %>% select(outcome, cohort, att, se, p)),
          row.names = FALSE, digits = 3)
  }

  # ---- 2b Germany exclusion ----------------------------------------------
  # Three samples, so the treated-side and control-side changes separate.
  cat("\n\n######## PART 2b: Germany-exclusion sensitivity (hydrogen) ########\n")
  de_treated <- unique(df$Linkedin_name[df$is_treated == 1 & df$is_de == 1])
  de_control <- unique(df$Linkedin_name[df$is_control == 1 & df$is_de == 1])
  # Controls matched ONLY to German treated firms: dropping these keeps the
  # comparison symmetric without touching controls shared with other cohorts.
  link <- df %>% distinct(Linkedin_name, is_control, matched_to)
  orphan <- link %>% filter(is_control == 1, !is.na(matched_to)) %>%
    group_by(Linkedin_name) %>%
    summarise(all_de = all(matched_to %in% de_treated), .groups = "drop") %>%
    filter(all_de) %>% pull(Linkedin_name)

  samples <- list(
    "full"                  = df,
    "drop DE treated"       = df %>% filter(!Linkedin_name %in% de_treated),
    "drop DE treated+orphan controls" =
      df %>% filter(!Linkedin_name %in% c(de_treated, orphan)),
    "drop all DE firms"     = df %>% filter(is_de == 0 | is.na(is_de))
  )
  cat(sprintf("German treated: %d | German controls: %d | controls matched only to DE treated: %d\n",
              length(de_treated), length(de_control), length(orphan)))

  de_rows <- list()
  for (sn in names(samples)) {
    sdf <- samples[[sn]]
    gs <- sort(unique(sdf$g_period[sdf$g_period > 0]))
    cat(sprintf("\n[%s] firms=%d treated=%d controls=%d cohorts=%s\n", sn,
                n_distinct(sdf$Linkedin_name),
                n_distinct(sdf$Linkedin_name[sdf$g_period > 0]),
                n_distinct(sdf$Linkedin_name[sdf$g_period == 0]),
                paste(sapply(gs, function(g)
                  sprintf("p%d:%d", g, n_distinct(sdf$Linkedin_name[sdf$g_period == g]))),
                  collapse = " ")))
    for (key in names(KEYS)) {
      y <- outcome_map[[key]][["hydrogen"]]
      if (!(y %in% names(sdf))) next
      cs <- run_cs(sdf, y, label = paste(sn, key), biters = BITERS_DX)
      ag <- agg_simple(cs)
      if (is.null(ag)) next
      pt <- es_pretrend(cs)
      de_rows[[paste(sn, key)]] <- data.frame(
        sample = sn, outcome = KEYS[[key]],
        n_firms = n_distinct(sdf$Linkedin_name),
        n_treated = n_distinct(sdf$Linkedin_name[sdf$g_period > 0]),
        att = round(ag$overall.att, 4), se = round(ag$overall.se, 4),
        p = pval_from_att(ag$overall.att, ag$overall.se),
        lo = round(ag$overall.att - 1.96 * ag$overall.se, 4),
        hi = round(ag$overall.att + 1.96 * ag$overall.se, 4),
        pretrend_p = pt$p)
    }
  }
  if (length(de_rows)) {
    dr <- bind_rows(de_rows)
    write.csv(dr, file.path(OUT, "p2b_germany_exclusion_hydrogen.csv"), row.names = FALSE)
    cat("\n-- Germany exclusion --\n"); print(as.data.frame(dr), row.names = FALSE)
  }

  # ---- 2c within-cohort Germany vs non-Germany ---------------------------
  cat("\n\n######## PART 2c: within-cohort DE vs non-DE support ########\n")
  sup <- df %>% distinct(Linkedin_name, g_period, is_de) %>%
    filter(g_period > 0) %>% count(g_period, is_de) %>%
    pivot_wider(names_from = is_de, values_from = n, values_fill = 0) %>%
    rename(non_DE = `0`, DE = `1`) %>%
    mutate(cohort = format(pm$month[match(g_period, pm$period)], "%Y-%m"))
  print(as.data.frame(sup), row.names = FALSE)
  write.csv(sup, file.path(OUT, "p2c_within_cohort_support.csv"), row.names = FALSE)

  # Estimated only where both arms clear a minimum; otherwise reported as
  # unidentified rather than forced.
  MIN_ARM <- 10
  wc_rows <- list()
  for (i in seq_len(nrow(sup))) {
    if (sup$DE[i] < MIN_ARM || sup$non_DE[i] < MIN_ARM) {
      cat(sprintf("cohort %s: DE=%d non-DE=%d -> not estimated (arm < %d)\n",
                  sup$cohort[i], sup$DE[i], sup$non_DE[i], MIN_ARM)); next
    }
    g <- sup$g_period[i]
    for (arm in c(0, 1)) {
      sdf <- df %>% filter(g_period == 0 | (g_period == g & is_de == arm))
      for (key in names(KEYS)) {
        y <- outcome_map[[key]][["hydrogen"]]
        cs <- run_cs(sdf, y, label = sprintf("cohort %s arm_de=%d %s",
                                             sup$cohort[i], arm, key),
                     biters = BITERS_DX)
        ag <- agg_simple(cs); if (is.null(ag)) next
        wc_rows[[paste(g, arm, key)]] <- data.frame(
          cohort = sup$cohort[i], german = arm, outcome = KEYS[[key]],
          n_treated = n_distinct(sdf$Linkedin_name[sdf$g_period > 0]),
          att = round(ag$overall.att, 4), se = round(ag$overall.se, 4),
          p = pval_from_att(ag$overall.att, ag$overall.se))
      }
    }
  }
  if (length(wc_rows)) {
    wc <- bind_rows(wc_rows)
    write.csv(wc, file.path(OUT, "p2c_within_cohort_atts.csv"), row.names = FALSE)
    print(as.data.frame(wc), row.names = FALSE)
  }

  # ---- 5 funded vs unrelated difference, and raw counts ------------------
  # C&S is linear in the outcome, so the ATT on the difference equals the
  # difference of the two separately estimated ATTs, with the correct SE
  # from the shared influence function. That covariance is the whole point.
  cat("\n\n######## PART 5: difference contrasts, extensive margin, raw counts ########\n")
  # The contrast columns now come from load_cs (both implementations), so these
  # are ordinary outcomes rather than an ad hoc routine. Reported as secondary
  # analyses with nominal p-values; they do NOT enter the primary table's
  # Benjamini-Hochberg family, which stays at its original nine outcomes.
  p5 <- list()
  CONTRASTS <- list(
    rel_tech = "Relative technology (log diff)",
    rel_geo  = "Relative geography, EU-internal minus international (log diff)")

  # Added Nov 2026 and deliberately estimated LAST, after every block that was
  # already published, so the bootstrap stream reaching those blocks is
  # unchanged and their p-values reproduce exactly.
  LATE <- list(
    rel_sector   = "Relative sector, cross-sector minus same-sector (log diff)",
    cross_border = "EU cross-border, broader definition (log diff)")

  # Broader geographic definition, reported as a bridge to the strict one.
  # cl_eu_internal counts a collaboration only if EVERY participant is in the
  # EU, so a German-French-American consortium is classified international even
  # though two member states cooperate in it. About a third of collaborations
  # spanning two or more EU countries fall into that case. The dyad-level
  # cross_border outcome instead counts a collaboration whenever the firm itself
  # has a partner in another EU member state, whether or not a non-EU
  # participant is also present, which is closer to the wording of the scheme's
  # condition. It is non-exclusive by construction, hence a supplementary
  # estimate rather than a replacement.

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
  # ---- 5b sectoral contrast and the broader EU definition ----------------
  # Appended after everything above so the published estimates keep their
  # bootstrap draws. The sectoral contrast completes the set of three
  # mutually exclusive pairs; the broader EU outcome bridges the strict
  # EU-internal definition to the wording of the scheme's condition.
  cat("\n\n######## PART 5b: sectoral contrast and broader EU definition ########\n")
  for (tech in c("Battery", "Hydrogen")) {
    sdf <- panels[[tech]]
    tl  <- tolower(tech)
    for (lk in names(LATE)) {
      y <- outcome_map[[lk]][[tl]]
      if (!(y %in% names(sdf))) { cat("missing column:", y, "\n"); next }
      cs <- run_cs(sdf, y, label = sprintf("%s %s", tech, lk), biters = BITERS_DX)
      ag <- agg_simple(cs); if (is.null(ag)) next
      p5[[paste(tech, lk)]] <- data.frame(
        technology = tech, outcome = LATE[[lk]],
        anticipation = 0, att = round(ag$overall.att, 4),
        se = round(ag$overall.se, 4),
        p = pval_from_att(ag$overall.att, ag$overall.se),
        lo = round(ag$overall.att - 1.96 * ag$overall.se, 4),
        hi = round(ag$overall.att + 1.96 * ag$overall.se, 4),
        pretrend_p = es_pretrend(cs)$p)
    }
  }

  if (length(p5)) {
    pp <- bind_rows(p5)
    write.csv(pp, file.path(OUT, "p5_relative_and_counts.csv"), row.names = FALSE)
    cat("\n-- relative-technology and raw-count ATTs --\n")
    print(as.data.frame(pp), row.names = FALSE)
  }
}


# ============================================================
# PART 6: power simulation for the direct contrasts
# ============================================================
# The contrasts carry the paper's strongest negative claims, above all
# "the sectoral mix is unchanged", so they are the outcomes where the
# difference between "no effect" and "cannot tell" matters most.
#
# A caveat worth keeping in view: where the confidence interval is already
# tight, the interval is BETTER evidence than a simulated power curve. The
# battery sectoral contrast is 0.000 with SE 0.050, so it rules out anything
# beyond roughly +/- 0.10 log points directly, with no assumption about an
# imposed constant effect. Power simulation earns its place for the wide
# nulls. Both are produced here; use the one that fits the claim.
#
# Note on units: a contrast outcome is a difference of two log1p counts, so
# `att_true` is a shift in that DIFFERENCE. The att_pct column is carried for
# a common axis with the other power files, but for contrasts read att_log.

RUN_P6_POWER <- FALSE    # slow: set TRUE for the overnight run

CONTRASTS <- list(
  rel_tech   = "Relative technology (log diff)",
  rel_geo    = "Relative geography, EU-internal minus international (log diff)",
  rel_sector = "Relative sector, cross-sector minus same-sector (log diff)"
)

N_SIMS_POWER <- 500   # matched to section 9 of script 07; see the note there

# Zero is prepended to the grid as a size check and 199 bootstrap draws run
# inside each simulated draw. Both mirror section 9 of script 07; the reasoning
# is in the run_power_sim header in _cs_helpers.R.
POWER_GRID_RUN <- c(0, POWER_LOG_GRID)
BITERS_SIM     <- 199

# The effect sizes of a cell run in parallel, so one core per size keeps a
# cell to a single draw-batch of wall clock. Leave one core for the machine.
POWER_CORES <- max(1L, min(length(POWER_GRID_RUN),
                           parallel::detectCores() - 1L))

if (RUN_P6_POWER) {
  library(parallel)
  # Fork when available, fall back to serial if the workers fail, so an
  # overnight run never silently returns no results.
  mclapply <- function(X, FUN, ..., mc.cores = POWER_CORES) {
    res <- tryCatch(parallel::mclapply(X, FUN, ..., mc.cores = mc.cores),
                    error = function(e) base::lapply(X, FUN))
    if (any(vapply(res, function(z) inherits(z, "try-error"), logical(1))))
      res <- base::lapply(X, FUN)
    res
  }

  cat("\n\n######## PART 6: power simulation, direct contrasts ########\n")

  # Reported ATTs for these outcomes, if Part 5 has already been run, so the
  # output carries the same ATT / p_value columns as the other power files.
  p5_path <- file.path(OUT, "p5_relative_and_counts.csv")
  p5_ref  <- if (file.exists(p5_path)) read.csv(p5_path, stringsAsFactors = FALSE)
             else NULL

  # One timed draw per technology, so the run can be budgeted before it starts.
  for (tech in c("Battery", "Hydrogen")) {
    y <- outcome_map[["rel_sector"]][[tolower(tech)]]
    if (!(y %in% names(panels[[tech]]))) next
    el <- system.time(
      run_power_sim(panels[[tech]], y, POWER_LOG_GRID[1], cg_for(tolower(tech)),
                    n_sims = 2, label = paste("timing", tech),
                    biters_sim = BITERS_SIM)
    )[["elapsed"]] / 2
    cat(sprintf("%-9s %.2f s/draw x %d sims x %d sizes x %d contrasts = %.2f h serial\n",
                tech, el, N_SIMS_POWER, length(POWER_GRID_RUN),
                length(CONTRASTS),
                el * N_SIMS_POWER * length(POWER_GRID_RUN) *
                  length(CONTRASTS) / 3600))
  }

  p6 <- list()
  for (tech in c("Battery", "Hydrogen")) {
    sdf <- panels[[tech]]
    tl  <- tolower(tech)
    for (ck in names(CONTRASTS)) {
      y <- outcome_map[[ck]][[tl]]
      if (!(y %in% names(sdf))) { cat("missing column:", y, "\n"); next }
      lbl <- paste(tech, "--", CONTRASTS[[ck]])

      ref <- if (!is.null(p5_ref))
        p5_ref[p5_ref$technology == tech &
                 p5_ref$outcome == CONTRASTS[[ck]] &
                 p5_ref$anticipation == 0, , drop = FALSE] else NULL
      p_ref <- if (!is.null(ref) && nrow(ref)) ref$p[1] else NA_real_

      # Only the null contrasts are simulated, on the same rule as section 9 of
      # script 07: a contrast that is significant needs no power defence.
      if (!is.na(p_ref) && p_ref < 0.10) {
        cat("skipping (significant, p =", sprintf("%.3f", p_ref), "):", lbl, "\n")
        next
      }
      cat("Power simulation:", lbl, "(", y, ")\n")

      # att_hat imposes the null, so the true effect in a draw is `a` rather
      # than `a` on top of the contrast the data already carry.
      att_ref <- if (!is.null(ref) && nrow(ref)) ref$att[1] else 0
      rows <- mclapply(POWER_GRID_RUN, function(a)
        run_power_sim(sdf, y, a, cg_for(tl), n_sims = N_SIMS_POWER, label = lbl,
                      att_hat = att_ref, biters_sim = BITERS_SIM),
        mc.cores = POWER_CORES)
      rows <- rows[!vapply(rows, is.null, logical(1))]
      if (!length(rows)) next

      out <- do.call(rbind, rows)
      out$Technology  <- tech
      out$Outcome     <- CONTRASTS[[ck]]
      out$Type        <- "Contrast"
      out$key         <- ck
      out$yname       <- y
      out$ATT         <- if (!is.null(ref) && nrow(ref)) ref$att[1] else NA_real_
      out$p_value     <- p_ref
      out$significant <- !is.na(p_ref) & p_ref < 0.10
      p6[[length(p6) + 1]] <- out
    }
  }

  if (length(p6)) {
    power_contrasts <- bind_rows(p6)
    power_contrasts <- power_contrasts[, c("Technology", "Outcome", "Type",
                                           "key", "yname", "att_log", "att_pct",
                                           "power", "n_draws", "n_sims",
                                           "ATT", "p_value", "significant")]
    write.csv(power_contrasts, file.path(OUT, "p6_power_contrasts.csv"),
              row.names = FALSE)
    cat("\n-- power curves, direct contrasts --\n")
    print(as.data.frame(power_contrasts), row.names = FALSE)

    mde <- do.call(rbind, lapply(
      split(power_contrasts, list(power_contrasts$Technology,
                                  power_contrasts$Outcome), drop = TRUE),
      function(d) data.frame(
        technology = d$Technology[1],
        outcome    = d$Outcome[1],
        att        = d$ATT[1],
        p          = d$p_value[1],
        mde_log    = round(mde_at(d$att_log, d$power, 0.80), 4),
        mde_pct    = round(mde_at(d$att_pct, d$power, 0.80), 1),
        # Rejection rate at a true effect of zero; must sit near 0.05 or the
        # MDE on that row is void. Read this before quoting anything.
        size       = d$power[which(abs(d$att_log) < 1e-12)[1]],
        stringsAsFactors = FALSE)))
    write.csv(mde, file.path(OUT, "p6_power_contrasts_mde.csv"),
              row.names = FALSE)
    cat("\n-- minimum detectable effect at 80% power (NA = never reached) --\n")
    print(as.data.frame(mde), row.names = FALSE)
  }
}

cat("\n\nDone. Outputs in", normalizePath(OUT), "\n")
