---
name: xenium-composition
description: Summarize cell-type composition from a prepared Xenium H5AD, or compare two groups with sccomp using confirmed subjects or an explicitly chosen exploratory source-block policy.
---

# Xenium cell-type composition

Read the personal profile
([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile)) and reuse the saved
project and environment choices. Select the prepared H5AD and its build/input-check
evidence. Input enrichment belongs to the project; this module consumes that version.
Before BioHPC imports or data reads, enter and verify allocated compute using the
[setup guidance](../xenium-biohpc-setup/references/biohpc-usage.md#select-compute-resources).
Read the [input/output contract](references/contract.md) when choosing fields,
denominators or the inferential branch.

## Choose the scope

Map the observation/core field and one cell-type annotation field explicitly.
Choose the cell cohort and exclusions before calculating counts.
Use the sibling [scientific figure skill](../xenium-figures/SKILL.md) for figure
design, shared colors, exports and rendered review. Keep missing
annotations as a visible class and retain Unknown by default. Record every exclusion
and its effect on the denominator. Overall composition does not require spatial
coordinates; this analysis measures fractions among retained cells, not tissue density.

- **Descriptive:** counts and proportions per observation, with figures and denominator
  records. Available block/model labels can organize results, but they do not establish
  independent biological replicates.
- **Confirmed-subject comparison:** study-appropriate experimental-unit IDs, one
  group per subject and an explicit reference/comparison. Repeated observations
  share their subject's random intercept. This default policy requires the caller's
  confirmation; source labels alone cannot supply it.
- **Exploratory source-block comparison:** when the project explicitly chooses source
  records as working units despite unresolved biological identities, aggregate counts
  to one observation per unit and select `--analysis-unit-policy source_block_record`.
  Do not supply `--subjects-confirmed`. Independence remains a working assumption;
  report named-group associations and retain the original member mapping.

More complex designs require an explicit method decision before extending the
supported entrypoint. Missing identity confirmation does not automatically select
the exploratory policy.

## Run and inspect

1. Run [summarize_composition.py](scripts/summarize_composition.py) with `--input`,
   `--output`, `--sample-key`, `--cell-type-key`, and any `--metadata-key` or
   `--exclude-label` selections. Its `--help` owns the available options. Use a new
   output directory; input H5AD is read-only.
2. Reconcile included and excluded cells to the input, zero-filled type combinations,
   per-observation denominators and any zero-denominator observations. Then run
   [plot_composition.py](scripts/plot_composition.py) on these tables, specifying
   `--unit-key` and `--group-key` from their metadata. This renderer reads the shared
   style asset and produces a broad overview (one to five main types), optional
   detailed heatmap and paginated observation inventory. Use `--help` for the table
   and hierarchy arguments; a richer primary label set needs a heatmap/facet design
   rather than silently dropping categories. For a report-sized broad figure, use
   `--layout report --main-only`. Artwork explanations are preserved in caption
   metadata for the report; assemble editable reports through the [xenium-reporting](../xenium-reporting/SKILL.md)
   module. Inspect exports when the shared style calls for targeted verification.
3. Run [fit_composition.R](scripts/fit_composition.R) with the generated count table,
   unit/group mapping and chosen policy from the contract. Inspect its recorded policy,
   actual design, estimates, uncertainty and diagnostics before interpreting group
   differences. Preserve failed diagnostics as failed evidence.
4. Write the project report from observed results. Identify the H5AD version, label
   field, cohort, denominator, analysis-unit policy, identity/independence assumptions,
   method/runtime and actual outputs. Distinguish observed proportions from model
   estimates and exploratory associations from confirmed-subject comparisons.

The scripts never install dependencies. A missing runtime routes to the saved setup
strategy within the user's request. Package installation alone does not establish
that the sccomp model compiles or fits.

## Completion and verification

A descriptive run is complete when its counts reconcile, metadata mapping is
consistent, tables and figures are readable, and the report states its limits.
A model run additionally needs its specified contrast, recorded unit policy and
actual design, uncertainty/FDR output and acceptable diagnostics. Report untested branches.

The repository's `tests/test_composition_cli.py` exercises this actual count CLI
against hand-calculated values, ordering changes and failure cases. A project
verification skill should call these production entrypoints and exercise the chosen
independent or repeated-observation branch in its pinned R runtime. Synthetic agreement establishes
computational behavior, not biological validity or power for another experiment.
