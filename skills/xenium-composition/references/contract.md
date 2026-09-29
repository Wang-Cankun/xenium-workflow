# Composition input and output contract

## Prepared input and denominator

Supply a readable H5AD with a unique, nonmissing cell index. Select one nonmissing
observation identifier (`--sample-key`) and one annotation column (`--cell-type-key`).
An observation can be a core; use globally unique IDs when names repeat across slides.
Additional `--metadata-key` values must be constant within each observation.

The count entrypoint uses annotations, not expression values. Preserve the input
cohort: it does not silently repeat upstream expression QC. Missing annotation is
reported as `__missing__` (configurable); Unknown remains an ordinary category.
`--exclude-label` is an explicit denominator change. Every retained annotation class
is represented for every observation, including zero counts. The denominator is the
sum of retained cells in that observation. A fully excluded observation has a zero
denominator and undefined (blank) proportions, never fabricated zero proportions.

| Output | Meaning |
|---|---|
| `counts.tsv` | Observation × retained type, integer count, denominator, proportion |
| `sample_metadata.tsv` | One row per observation, input/included/excluded counts and selected source fields |
| `exclusions.tsv` | Every explicitly excluded label's count per observation |
| `run.json` | Successful completion, input identity/path, field choices, totals and runtime |
| `report.md` | Descriptive scope, denominator and output links |
| Plot directory | PDF/PNG bars, PDF heatmap, palette, denominator table and numerical checks |

An existing output directory is rejected. The success manifest is written after
the other summary artifacts; a partial directory is not a completed run. Reports
and provenance identify file paths/versions; checksums are not required by this module.

## Analysis-unit policy

A block, core, slide or model label is not automatically an independent experimental
unit. The sccomp entrypoint supports two groups and an explicit comparison minus
reference under one of two declared policies:

- `confirmed_biological_subject` is the default. Supply confirmed experimental-unit
  IDs with `--subjects-confirmed` and document repeated observations. One observation
  per subject uses `~ condition`; repeated subject IDs use
  `~ condition + (1 | subject)`.
- `source_block_record` is an explicit project choice for exploratory analysis.
  Supply one already-aggregated count vector per working unit; repeated unit IDs and
  `--subjects-confirmed` are rejected. The model is `~ condition`. Biological identity
  stays unresolved and independence is a working assumption. Preserve a project
  member mapping for source records, including any hypothetical merged-record
  sensitivity; the fit does not infer their biological relationship.

The technical `--subject-column` argument selects the unit key for either policy;
its internal `subject` field is not a biological identity assertion under the
exploratory policy. Each unit must have one group. At least two units per group is
only a structural minimum, not evidence of independence or adequate power. The
actual fixed design must contain an intercept and the requested comparison indicator
(reference=0, comparison=1); repeated designs must match the supplied subject mapping.

Report observed proportions separately from model estimates. sccomp composition
coefficients are effects on its model scale; do not call them changes in percentage
points. Export effect estimates, uncertainty, FDR and convergence diagnostics, with
exact package/Stan versions and parameters. Diagnostic failures retain their outputs
but do not qualify as a successful inference. Synthetic verification thresholds are
not universal scientific thresholds for future experiments.

## sccomp entrypoint

The implemented R branch targets sccomp **2.2.0**, cmdstanr >=0.9.0 and a working
CmdStan/C++ runtime. Project setup owns the exact R/Bioconductor/Stan lock and launch.
`--samples` is the total posterior draws across chains. Confirm the scientific
identity mapping before using the default policy's confirmation flag:

```sh
Rscript scripts/fit_composition.R --counts counts.tsv --metadata subject_mapping.tsv \
  --subject-column experimental_unit_id --group-column condition \
  --reference control --comparison treated --subjects-confirmed \
  --output NEW_MODEL_DIRECTORY --cores 2 --chains 2 --warmup 1000 --samples 4000
```

For an explicitly chosen exploratory source-record analysis, replace the confirmation
flag with the policy and supply its working-unit column:

```sh
Rscript scripts/fit_composition.R --counts counts.tsv --metadata working_units.tsv \
  --subject-column analysis_unit_id --group-column group_label \
  --reference control --comparison treated --analysis-unit-policy source_block_record \
  --output NEW_MODEL_DIRECTORY --cores 2 --chains 2 --warmup 1000 --samples 4000
```

The metadata table has one row per `sample_id`, exactly matching the count-table
observations. Additional groups, unmapped samples, inconsistent subject groups,
zero denominators or incomplete count grids fail. `--validate-only` checks this
contract without fitting and saves the selected policy. Repeated subject IDs are
allowed only under the confirmed policy. This release rejects datasets whose maximum count
is <=1 because of sccomp 2.2.0's upstream exposure handling.

The output contains unchanged metadata, count tables, `sample-design.tsv`, actual
fixed/random designs, `analysis-policy.json`, `fit.rds`, `effects.tsv`,
`fitted-proportions.tsv`, diagnostics, `run.json` and `status.json`. Policy records
also appear in `run.json` and `status.json`; exploratory runs retain
`biological_identity_status=unresolved`,
`between_unit_independence=working_assumption` and
`inference_scope=exploratory_named_group_association`. A model's final status must
say `passed`; a fitted RDS alone is not success.
Effects use `sccomp_test` with a practical-null threshold of 0.1 on its logit
coefficient scale. The recorded posterior FDR applies to that test, not an
unspecified exact-zero null. Conditional fitted proportions summarize the pinned
Stan model's softmax of saved posterior coefficients for observed analysis units. Their
95% intervals describe the latent composition mean, not new-subject predictions or
posterior predictive counts. Convergence checks include all coefficients used for
those fitted proportions, the sampled `alpha`, `prec_coeff`, `prec_sd` and `mix_p`
parameters saved in `dispersion-parameter-diagnostics.tsv`, and sampler divergences,
tree depth and E-BFMI. Both model branches require finite Rhat ≤1.05 and bulk/tail
ESS ≥100 for these dispersion/prior parameters; generated constants are excluded.

Methods: [sccomp source and documentation](https://github.com/MangiolaLaboratory/sccomp),
[sccomp publication](https://pubmed.ncbi.nlm.nih.gov/37549298/).

## Figure bundle

The production `plot_composition.py` reads the count and metadata tables. Explicit
unit/group columns define descriptive pooling and grouping without asserting
biological independence. Broad-type views support one to five named types; detailed
counts/metadata are optional together. A supplied detailed-to-main hierarchy must
reproduce every observation's broad counts. Theme and palette defaults come from
the bundled sibling `xenium-figures/assets/style.json`.

Outputs include vector PDF/SVG, PNG previews, source-unit and observation plotted
tables, equal-weight source-unit group summaries, and a manifest with actual style,
font, dimensions and layout checks. Detailed heatmap saturation is explicit and
above-limit values remain in source tables and visible annotations. The previous
R renderer remains a legacy basic per-observation plotter; new standard bundles
use the Python entrypoint. Matplotlib, NumPy and pandas must be available in the
selected existing runtime; rendering does not install them.
