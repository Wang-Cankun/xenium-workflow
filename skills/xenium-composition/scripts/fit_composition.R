#!/usr/bin/env Rscript
# Two groups: confirmed subjects (optional repeated observations), or an explicit
# exploratory source-block policy (one aggregated observation per working unit).
parse_cli <- function(args) {
  opt <- list(cores = "2", chains = "2", warmup = "500", samples = "2000", seed = "7301")
  opt[["analysis-unit-policy"]] <- "confirmed_biological_subject"
  flags <- c("subjects-confirmed", "validate-only")
  values <- c("counts", "metadata", "subject-column", "group-column", "reference",
              "comparison", "output", "cores", "chains", "warmup", "samples", "seed", "stan-cache", "analysis-unit-policy")
  seen <- character()
  while (length(args)) {
    key <- sub("^--", "", args[1])
    if (!startsWith(args[1], "--") || !key %in% c(flags, values) || key %in% seen) {
      stop("Unknown or repeated option: ", args[1])
    }
    seen <- c(seen, key)
    if (key %in% flags) { opt[[key]] <- TRUE; args <- args[-1] }
    else {
      if (length(args) < 2 || startsWith(args[2], "--")) stop("Missing value: ", key)
      opt[[key]] <- args[2]; args <- args[-c(1, 2)]
    }
  }
  required <- c("counts", "metadata", "subject-column", "group-column", "reference", "comparison", "output")
  if (!all(required %in% names(opt))) stop("Required: --counts --metadata --subject-column --group-column --reference --comparison --output; confirmed biological IDs also require --subjects-confirmed")
  if (!opt[["analysis-unit-policy"]] %in% c("confirmed_biological_subject", "source_block_record")) {
    stop("Unknown analysis-unit policy; use confirmed_biological_subject or source_block_record")
  }
  for (key in c("cores", "chains", "warmup", "samples", "seed")) {
    if (!grepl("^[0-9]+$", opt[[key]])) stop("Expected positive integer: ", key)
    opt[[key]] <- as.integer(opt[[key]])
    if (is.na(opt[[key]]) || opt[[key]] < 1) stop("Invalid integer: ", key)
  }
  if (opt$chains < 2 || opt$chains > opt$cores || opt$cores %% opt$chains != 0 ||
      opt$samples %% opt$chains != 0) stop("Use >=2 chains, cores divisible by chains, and total posterior samples divisible by chains")
  opt
}
write_tsv <- function(x, path) write.table(x, path, sep = "\t", quote = TRUE, qmethod = "double", row.names = FALSE, na = "NA")
read_tsv <- function(path) {
  x <- read.delim(path, colClasses = "character", check.names = FALSE, quote = "\"", comment.char = "", na.strings = "")
  if (anyDuplicated(names(x)) || !nrow(x)) stop("Empty table or duplicate column names: ", path)
  x
}
nonempty <- function(x) !is.na(x) & nzchar(trimws(x))
require_ok <- function(value, message) if (!isTRUE(value)) stop(message)

# Same conditional mean as the pinned sccomp Stan likelihood (RELEASE_3_22,
# inst/stan/glm_multi_beta_binomial.stan lines 72-79). Summarize saved posterior
# draws through public CmdStanR APIs; this does not predict an unseen subject.
fitted_proportions <- function(stan_fit, mi, metadata) {
  X <- as.matrix(mi$X)
  Z <- as.matrix(mi$X_random_effect)
  variables <- "beta"
  if (ncol(Z)) variables <- c(variables, "random_effect")
  draws <- as.matrix(stan_fit$draws(variables = variables, format = "matrix"))
  dimensions <- c(nrow(X), ncol(mi$y))
  result <- vector("list", dimensions[1])
  for (n in seq_len(dimensions[1])) {
    eta <- matrix(0, nrow(draws), dimensions[2])
    for (m in seq_len(dimensions[2])) {
      columns <- sprintf("beta[%d,%d]", seq_len(ncol(X)), m)
      require_ok(all(columns %in% colnames(draws)), "Missing beta posterior columns")
      eta[, m] <- as.vector(draws[, columns, drop = FALSE] %*% X[n, ])
      if (ncol(Z)) {
        columns <- sprintf("random_effect[%d,%d]", seq_len(ncol(Z)), m)
        require_ok(all(columns %in% colnames(draws)), "Missing random-effect posterior columns")
        eta[, m] <- eta[, m] + as.vector(draws[, columns, drop = FALSE] %*% Z[n, ])
      }
    }
    probability <- exp(eta - apply(eta, 1, max))
    probability <- probability / rowSums(probability)
    require_ok(all(is.finite(probability)) && max(abs(rowSums(probability) - 1)) < 1e-10,
               "Invalid fitted-proportion draws")
    interval <- apply(probability, 2, quantile, probs = c(0.025, 0.975), names = FALSE)
    result[[n]] <- data.frame(sample_id = rownames(X)[n], cell_type = colnames(mi$y),
      proportion_mean = colMeans(probability), proportion_lower = interval[1, ],
      proportion_upper = interval[2, ], stringsAsFactors = FALSE)
  }
  result <- do.call(rbind, result)
  result$subject <- metadata$subject[match(result$sample_id, metadata$sample_id)]
  result$condition <- as.character(metadata$condition[match(result$sample_id, metadata$sample_id)])
  result
}

# Sampled dispersion and mean-variability prior parameters in sccomp 2.2.0.
# Exclude derived precision/log_lik and zero-sized random-effect structures.
dispersion_parameter_diagnostics <- function(stan_fit, mi) {
  require_ok(mi$A == 1 && mi$intercept_in_design == 1,
    "Dispersion diagnostics require the supported variability ~1 and composition intercept")
  diagnostic <- as.data.frame(stan_fit$summary(variables = c("alpha", "prec_coeff", "prec_sd", "mix_p")))
  expected <- c(sprintf("alpha[1,%d]", seq_len(ncol(mi$y))),
                "prec_coeff[1]", "prec_coeff[2]", "prec_sd", "mix_p")
  require_ok(all(c("variable", "rhat", "ess_bulk", "ess_tail") %in% names(diagnostic)) &&
    nrow(diagnostic) == length(expected) && !anyDuplicated(diagnostic$variable) &&
    setequal(diagnostic$variable, expected), "Incomplete sampled dispersion/prior parameter diagnostics")
  checks <- c(
    dispersion_parameter_Rhat = all(is.finite(diagnostic$rhat) & diagnostic$rhat <= 1.05),
    dispersion_parameter_ESS_bulk = all(is.finite(diagnostic$ess_bulk) & diagnostic$ess_bulk >= 100),
    dispersion_parameter_ESS_tail = all(is.finite(diagnostic$ess_tail) & diagnostic$ess_tail >= 100))
  list(summary = diagnostic, checks = checks)
}

main <- function(opt, out) {
  exploratory <- identical(opt[["analysis-unit-policy"]], "source_block_record")
  if (exploratory) {
    require_ok(!isTRUE(opt[["subjects-confirmed"]]), "source_block_record cannot be combined with --subjects-confirmed")
    policy <- list(analysis_unit_policy = "source_block_record",
      biological_identity_status = "unresolved", between_unit_independence = "working_assumption",
      inference_scope = "exploratory_named_group_association")
  } else {
    require_ok(isTRUE(opt[["subjects-confirmed"]]), "Biological subject IDs must be confirmed; core/model labels are not inferred as subjects")
    policy <- list(analysis_unit_policy = "confirmed_biological_subject",
      biological_identity_status = "confirmed_by_caller", between_unit_independence = "model_assumption",
      inference_scope = "confirmed_subject_group_comparison")
  }
  jsonlite::write_json(policy, file.path(out, "analysis-policy.json"), auto_unbox = TRUE, pretty = TRUE)
  unit_label <- if (exploratory) "working analysis unit" else "confirmed biological subject"
  require_ok(opt$reference != opt$comparison, "Reference and comparison must differ")
  counts <- read_tsv(opt$counts)
  metadata <- read_tsv(opt$metadata)
  required <- c("sample_id", "cell_type", "count", "denominator", "proportion")
  require_ok(all(required %in% names(counts)), "Counts require sample_id, cell_type, count, denominator, proportion")
  require_ok(all(c("sample_id", opt[["subject-column"]], opt[["group-column"]]) %in% names(metadata)), "Missing requested metadata columns")
  require_ok(all(nonempty(counts$sample_id)) && all(nonempty(counts$cell_type)), "Missing sample/type identifiers")
  require_ok(!anyDuplicated(counts[c("sample_id", "cell_type")]), "Duplicate sample/type counts")
  require_ok(!anyDuplicated(metadata$sample_id), "Duplicate metadata sample IDs")
  require_ok(setequal(counts$sample_id, metadata$sample_id), "Metadata and count sample sets must match exactly; no sample is silently dropped")
  for (column in c("count", "denominator", "proportion")) {
    counts[[column]] <- suppressWarnings(as.numeric(counts[[column]]))
    require_ok(all(is.finite(counts[[column]])), paste("Non-finite", column))
  }
  require_ok(all(counts$count >= 0 & counts$count == floor(counts$count) & counts$count <= .Machine$integer.max), "Counts must be nonnegative R-range integers")
  require_ok(all(counts$denominator > 0 & counts$denominator == floor(counts$denominator)), "Denominators must be positive integers")
  samples <- unique(counts$sample_id); types <- unique(counts$cell_type)
  require_ok(length(types) >= 2 && nrow(counts) == length(samples) * length(types), "Require the complete sample-by-type grid, including explicit zero counts")
  totals <- tapply(counts$count, counts$sample_id, sum)
  require_ok(all(counts$denominator == totals[counts$sample_id]), "Denominator must equal all included cell counts for each sample")
  require_ok(all(abs(counts$proportion - counts$count / counts$denominator) < 1e-8), "Proportions do not match counts/denominators")
  require_ok(all(tapply(counts$count, counts$cell_type, sum) > 0), "A type has zero counts in every sample; resolve it explicitly before fitting")
  require_ok(max(counts$count) > 1, "sccomp 2.2.0 cannot safely fit a count grid whose maximum is <=1 (its exposure heuristic treats it as proportions)")
  counts$count <- as.integer(counts$count)
  design <- data.frame(sample_id = metadata$sample_id, subject = metadata[[opt[["subject-column"]]]],
                       condition = metadata[[opt[["group-column"]]]], stringsAsFactors = FALSE)
  require_ok(all(nonempty(design$subject)) && all(nonempty(design$condition)), paste("Missing", unit_label, "or group mapping"))
  if (exploratory) {
    require_ok(!anyDuplicated(design$subject),
      "source_block_record requires one aggregated observation per working analysis unit; repeated unit IDs are not allowed")
  }
  require_ok(setequal(design$condition, c(opt$reference, opt$comparison)), "This branch requires exactly the two requested groups")
  require_ok(all(tapply(design$condition, design$subject, function(x) length(unique(x))) == 1), paste("Group must be constant within each", unit_label))
  subject_groups <- unique(design[c("subject", "condition")])
  require_ok(all(table(subject_groups$condition) >= 2), paste("Require at least two", paste0(unit_label, "s"), "in each group"))
  design$condition <- factor(design$condition, levels = c(opt$reference, opt$comparison))
  repeated <- anyDuplicated(design$subject) > 0
  formula <- if (repeated) ~ condition + (1 | subject) else ~ condition
  data <- merge(counts[c("sample_id", "cell_type", "count")], design, by = "sample_id", sort = FALSE)
  write_tsv(counts, file.path(out, "counts.tsv"))
  write_tsv(metadata, file.path(out, "metadata.tsv"))
  write_tsv(design, file.path(out, "sample-design.tsv"))
  writeLines(deparse(formula), file.path(out, "formula.txt"))
  writeLines(c("No cells or types were excluded automatically.",
               paste("Analysis-unit policy:", policy$analysis_unit_policy),
               if (exploratory) "Source records are working units; biological identity is unresolved and independence is an assumption."
               else "Biological identity is confirmed by the caller; the program does not establish it.",
               "The internal subject field holds the requested unit key; group labels are supplied by the caller."),
             file.path(out, "input-policy.txt"))
  if (isTRUE(opt[["validate-only"]])) return(list(status = "validated", fitted = FALSE))
  require_ok(nzchar(Sys.getenv("SLURM_JOB_ID")), "Fit on an allocated compute node")
  available <- as.integer(Sys.getenv("SLURM_CPUS_PER_TASK", "1"))
  require_ok(!is.na(available) && opt$cores <= available, "Requested fit CPUs exceed the allocated step")
  require_ok(as.character(packageVersion("sccomp")) == "2.2.0", "This verified entry targets sccomp 2.2.0")
  require_ok(packageVersion("cmdstanr") >= "0.9.0", "cmdstanr >=0.9.0 is required")
  require_ok(nzchar(cmdstanr::cmdstan_path()), "CmdStan is not configured")
  stan_dir <- system.file("stan", package = "sccomp")
  require_ok(file.access(stan_dir, 2) == 0, "sccomp 2.2.0 compiles in its package directory; use a writable private library")
  if (is.null(opt[["stan-cache"]])) opt[["stan-cache"]] <- file.path(out, "stan-cache")
  capture.output(sessionInfo(), file = file.path(out, "session-info.txt"))
  jsonlite::write_json(list(options = opt, analysis_policy = policy, repeated_samples = repeated,
    formula = deparse(formula), analysis_units = nrow(subject_groups),
    subjects = if (exploratory) NULL else nrow(subject_groups), samples = length(samples),
    types = length(types), R = R.version.string, sccomp = as.character(packageVersion("sccomp")),
    cmdstanr = as.character(packageVersion("cmdstanr")), CmdStan = as.character(cmdstanr::cmdstan_version()),
    job_id = Sys.getenv("SLURM_JOB_ID"), node = Sys.info()[["nodename"]],
    effect_scale = "sccomp c_effect coefficient, comparison relative to reference",
    test_composition_above_logit_fold_change = 0.1,
    prediction = "Conditional fitted proportions from posterior softmax(X beta + Z random_effect); observed analysis units only"),
    file.path(out, "run.json"), auto_unbox = TRUE, pretty = TRUE)
  fit <- sccomp::sccomp_estimate(tibble::as_tibble(data), formula_composition = formula,
    formula_variability = ~1, sample = "sample_id", cell_group = "cell_type", abundance = "count",
    inference_method = "hmc", mcmc_seed = opt$seed, cores = opt$cores, chains = opt$chains,
    warmup_samples = opt$warmup, output_samples = opt$samples,
    max_sampling_iterations = opt$samples, pass_fit = TRUE,
    cache_stan_model = opt[["stan-cache"]], output_directory = file.path(out, "draws"),
    adapt_delta = 0.95, refresh = 100)
  saveRDS(fit, file.path(out, "fit.rds"))
  mi <- attr(fit, "model_input")
  saveRDS(mi, file.path(out, "model-input.rds"))
  expected_y <- xtabs(count ~ sample_id + cell_type, data = counts)
  require_ok(mi$is_proportion == 0 && setequal(rownames(mi$y), samples) &&
    setequal(colnames(mi$y), types) && identical(rownames(mi$y), rownames(mi$X)),
    "Fitted model did not preserve count input identifiers/type")
  require_ok(all(mi$y == expected_y[rownames(mi$y), colnames(mi$y)]) &&
    all(as.numeric(mi$exposure) == totals[rownames(mi$y)]),
    "Fitted count matrix or exposure differs from supplied counts/denominators")
  X <- as.matrix(mi$X)
  write_tsv(data.frame(sample_id = rownames(X), X, check.names = FALSE), file.path(out, "fixed-design.tsv"))
  expected_X <- model.matrix(~ condition, design,
    contrasts.arg = list(condition = contr.treatment(levels(design$condition), base = 1)))
  rownames(expected_X) <- design$sample_id
  require_ok(!anyDuplicated(rownames(X)) && setequal(rownames(X), design$sample_id) &&
    identical(colnames(X), colnames(expected_X)), "Fixed-design identifiers do not match requested samples/contrast")
  expected_X <- expected_X[rownames(X), , drop = FALSE]
  require_ok(identical(dim(X), dim(expected_X)) && all(X == expected_X),
    "Actual fixed design must equal intercept plus comparison indicator (reference=0, comparison=1)")
  if (!repeated) {
    require_ok(mi$n_random_eff == 0 && ncol(as.matrix(mi$X_random_effect)) == 0,
      "Independent observations unexpectedly produced a random-effect design")
  }
  if (repeated) {
    Z <- as.matrix(mi$X_random_effect)
    write_tsv(data.frame(sample_id = rownames(Z), Z, check.names = FALSE), file.path(out, "random-design.tsv"))
    require_ok(setequal(rownames(Z), design$sample_id) && !anyDuplicated(rownames(Z)), "Random-design rows do not match input samples")
    subjects <- sub("(Intercept)___", "", colnames(Z), fixed = TRUE)
    require_ok(setequal(subjects, design$subject) && !anyDuplicated(subjects), "Random-design columns do not match confirmed subjects")
    expected <- outer(design$subject[match(rownames(Z), design$sample_id)], subjects, "==") * 1L
    require_ok(identical(dim(Z), dim(expected)) && all(Z == expected), "Observed random design is not the requested subject intercept")
  }
  tested <- sccomp::sccomp_test(fit, test_composition_above_logit_fold_change = 0.1)
  saveRDS(tested, file.path(out, "fit.rds"))
  atomic <- vapply(tested, function(x) is.atomic(x) && is.null(dim(x)), logical(1))
  writeLines(names(tested)[!atomic], file.path(out, "non-tabular-effect-fields.txt"))
  write_tsv(as.data.frame(tested[, atomic]), file.path(out, "all-effects.tsv"))
  parameter <- colnames(expected_X)[2]
  effects <- as.data.frame(tested[tested$parameter == parameter, atomic])
  require_ok(nrow(effects) == length(types) && setequal(effects$cell_type, types), "Comparison effect rows do not cover all cell types")
  required <- c("c_effect", "c_lower", "c_upper", "c_FDR", "c_rhat", "c_ess_bulk")
  require_ok(all(required %in% names(effects)), "Expected sccomp HMC diagnostic columns are missing; inspect all-effects.tsv")
  write_tsv(effects, file.path(out, "effects.tsv"))
  stan_fit <- attr(fit, "fit")
  predictions <- fitted_proportions(stan_fit, mi, design)
  write_tsv(predictions, file.path(out, "fitted-proportions.tsv"))
  diagnostic <- as.data.frame(stan_fit$diagnostic_summary())
  require_ok(nrow(diagnostic) == opt$chains &&
    all(c("num_divergent", "num_max_treedepth", "ebfmi") %in% names(diagnostic)), "Incomplete sampler diagnostics")
  diagnostic <- data.frame(chain = seq_len(nrow(diagnostic)), diagnostic)
  write_tsv(diagnostic, file.path(out, "sampler-diagnostics.tsv"))
  prediction_variables <- if (repeated) c("beta", "random_effect") else "beta"
  parameter_diagnostic <- stan_fit$summary(variables = prediction_variables)
  require_ok(nrow(parameter_diagnostic) > 0 &&
    all(c("rhat", "ess_bulk", "ess_tail") %in% names(parameter_diagnostic)), "Incomplete prediction-parameter diagnostics")
  write_tsv(parameter_diagnostic, file.path(out, "prediction-parameter-diagnostics.tsv"))
  dispersion <- dispersion_parameter_diagnostics(stan_fit, mi)
  write_tsv(dispersion$summary, file.path(out, "dispersion-parameter-diagnostics.tsv"))
  values <- as.matrix(effects[required])
  checks <- c(finite_effects = all(is.finite(values)),
    ordered_intervals = all(effects$c_lower <= effects$c_upper),
    bounded_FDR = all(effects$c_FDR >= 0 & effects$c_FDR <= 1),
    effect_Rhat = all(is.finite(effects$c_rhat) & effects$c_rhat <= 1.05),
    effect_ESS_bulk = all(is.finite(effects$c_ess_bulk) & effects$c_ess_bulk >= 100),
    prediction_parameter_Rhat = all(is.finite(parameter_diagnostic$rhat) & parameter_diagnostic$rhat <= 1.05),
    prediction_parameter_ESS_bulk = all(is.finite(parameter_diagnostic$ess_bulk) & parameter_diagnostic$ess_bulk >= 100),
    prediction_parameter_ESS_tail = all(is.finite(parameter_diagnostic$ess_tail) & parameter_diagnostic$ess_tail >= 100),
    no_divergences = all(diagnostic$num_divergent == 0),
    no_max_treedepth = all(diagnostic$num_max_treedepth == 0),
    EBFMI = all(is.finite(diagnostic$ebfmi) & diagnostic$ebfmi >= 0.3))
  checks <- c(checks, dispersion$checks)
  write_tsv(data.frame(assertion = names(checks), passed = unname(checks)), file.path(out, "diagnostics.tsv"))
  require_ok(all(checks), "Fit finished but diagnostics failed; retain evidence and do not interpret as a passing inference run")
  list(status = "passed", fitted = TRUE, conditional_fitted_proportions = TRUE)
}

opt <- parse_cli(commandArgs(trailingOnly = TRUE))
if (file.exists(opt$output)) stop("Output already exists; choose a new directory")
dir.create(opt$output, recursive = TRUE)
out <- normalizePath(opt$output, mustWork = TRUE)
result <- tryCatch(main(opt, out), error = function(error) {
  list(status = "failed", reason = conditionMessage(error))
})
policy_path <- file.path(out, "analysis-policy.json")
if (file.exists(policy_path)) result$analysis_policy <- jsonlite::read_json(policy_path, simplifyVector = TRUE)
jsonlite::write_json(result, file.path(out, "status.json"), pretty = TRUE, auto_unbox = TRUE)
if (result$status == "failed") { message(result$reason); quit(status = 2L) }
message("Composition CLI: ", result$status)
