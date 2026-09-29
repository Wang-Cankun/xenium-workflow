---
name: xenium-quiche
description: Analyze local cellular niches from a prepared Xenium H5AD with QUICHE, or resume sampled differential niche enrichment from saved niches using confirmed biological subjects or an explicitly adopted exploratory source-record policy.
---

# Xenium spatial niches with QUICHE

Use the newly prepared, validated H5AD selected for this analysis. Link its build
and input-check evidence in the project; previous handoff findings do not establish
the contents of this new object. This module owns local niche composition and
QUICHE differential enrichment. Overall cell-type abundance belongs to the
composition task; coordinate repair and metadata reconciliation belong to input
preparation.

Read the personal profile
([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile)) and reuse saved
settings. Before Python imports or data reads on BioHPC, follow the sibling
[compute guidance](../xenium-biohpc-setup/references/biohpc-usage.md#select-compute-resources).
Read [the backend contract](references/backend.md) before selecting its environment
or running QUICHE. It needs a separate compatible runtime; a working H5AD-checking
environment does not establish QUICHE compatibility.

## Choose the question and inputs

Identify the selected annotation column, spatial coordinate key, independent
core/FOV boundary, coordinate units/frame and requested neighborhood radius.
Coordinates must be finite aligned x/y values. Accept supplied source coordinates
when the project adopts them, retaining provenance; image registration is a separate
question and is not a universal prerequisite for neighborhood analysis. Specify the radius in those exact
units; confirm any pixel-to-micrometer conversion in preparation evidence. The
wrapper records explicit units and frame but cannot establish their truth.

Use a globally unique FOV identifier for each independent tissue region, including
slide identity when core names repeat. Local coordinate ranges may overlap across
cores. Spatial edges stay inside FOVs; QUICHE's later niche-similarity graph may
connect similar compositions from different subjects.

Preserve supplied labels, including an explicit Unknown class. Missing labels
require an explicit preparation decision and exclusion accounting; the wrapper
rejects them. Select one documented cell cohort before analysis. Neither expression
normalization nor label reannotation is part of niche computation.

- **Descriptive niches:** require coordinates, labels and FOV boundaries. Export
  each eligible focal cell's neighborhood composition and the excluded-center ledger.
  Subject identity is optional; these results carry no differential-enrichment claim.
- **Differential enrichment:** additionally require confirmed biological-subject
  IDs, one condition per subject and a specified comparison versus reference. This
  first wrapper supports two independent groups, with at least two subjects each
  as a structural minimum, not a power recommendation. Repeated cores from a subject
  share `patient_key=subject`; they are not separate biological replicates. Paired,
  longitudinal, covariate-adjusted or multifactor designs need a separate method
  decision before extending this wrapper.
- **Exploratory source-record association:** when the project explicitly adopts
  this policy, `da-precomputed` may use named source-block records as working units.
  Set `--analysis-unit-policy source_block_record`; do not set
  `--biological-identity-confirmed`. Biological identity remains unresolved and
  independence between records is a working assumption. Results describe the
  specified group association, not a verified tumor/animal comparison. This is an
  explicit design choice, never an automatic fallback for missing subjects.

Use the sibling [scientific figure skill](../xenium-figures/SKILL.md) for spatial
maps and summaries, preserving equal aspect, units, label colors and source data.

## Execute the selected branch

Use [quiche_workflow.py](scripts/quiche_workflow.py) and its `--help`; it never installs
software. All modes require a new output directory and preserve the H5AD.

1. `prepare` reads selected obs and coordinates, validates their contract, and saves
   `cells.tsv` plus `manifest.json` and `report.md`. This is preparation evidence;
   it does not build a graph or run QUICHE.
2. `niches` invokes the pinned QUICHE spatial graph and composition APIs, audits
   cross-FOV edges and radius, then saves the graph, `local-niches.h5ad`, a cell-type
   proportion table and exclusions. Cells with fewer than `--min-neighbors` remain
   potential neighbors but are excluded as focal centers; QUICHE reports those cells
   without fully filtering them itself. A radius-only neighborhood is the default;
   set `--n-neighbors` for radius-bounded kNN after choosing the scientific scale.
3. `da` computes audited niches from the supplied prepared H5AD, optionally sketches niches per subject, runs
   QUICHE differential enrichment and annotation, and saves `quiche.h5mu` and
   `differential-niches.tsv`. Explicit reference/comparison labels map to internal
   A/B; positive logFC is B versus A. Annotation extrapolation is off, so subsampled
   neighborhoods are not presented as observed labels for every cell.
4. `da-precomputed` reads the completed `niches` output without rebuilding spatial
   neighborhoods. Supply `local-niches.h5ad`, its sibling `--source-manifest`, and a
   `--core-metadata` TSV with explicit `--core-key` (default `sample_id`), `--unit-key`
   and `--condition-key`. Specify reference, comparison, policy and `--seed`.
   The default confirmed-subject policy still requires the confirmation flag;
   the source-record policy and that flag are mutually exclusive. Each core must
   map once, each unit must have one group, and both groups need at least two units.

   `--uniform-per-unit` selects at most 1000 eligible centers uniformly without
   replacement per unit. It retains every selected center's original full-neighbor
   composition vector and all metadata. `--sketch-size` and raw coordinate/neighbor
   overrides are rejected. Use `--validate-only` to inspect selection/provenance
   without QUICHE or R; actual DA requires an allocated compute step. If requested,
   run two prespecified seeds into separate output directories; do not tune seeds
   to significance. The seed controls center selection, not a claim of bitwise
   reproducibility for the whole backend.

   The resumed entry accepts the canonical dense niche matrix. It builds only the
   niche-similarity graph and counts **sampled centers**, with overlapping memberships;
   it does not project DA counts back to all original centers. It saves selected
   IDs/vectors, sampling coverage, count-unit design, each neighborhood's unit
   contributions and membership matrix. Counts must exactly match
   `membership.T @ unit_one_hot` before successful completion.

Record the exact command, coordinate source/frame, selection/exclusion counts,
subject design, runtime versions, outputs and limitations in persistent project
evidence. The wrapper's minimal report is execution evidence; interpret the actual
outputs before producing the project-facing biological report. Keep requested
parameter sensitivity and plots alongside that report.

## Verification and completion

Run the contract tests under `tests/test_quiche_workflow.py` after adapter changes.
They use synthetic HDF5 data and graph audits, without substituting a homemade
QUICHE algorithm. In the pinned runtime, run
`QUICHE_SMOKE=1 python tests/test_quiche_backend.py` for the real hand-computed niche
fixture; enable
`QUICHE_DA_SMOKE=1` as well only when R/edgeR is ready. The backend reference explains
the expected outputs and coverage limits. For a project using `da-precomputed`,
exercise its actual CLI with two seeds: preserve selected vectors/metadata, verify
sampling and policy failures without the backend, then reload the actual H5MU and
independently reconstruct counts and R design. A sentinel should reject any attempt
to recompute physical neighborhoods on this resume path. Keep this project fixture
and its saved evidence with the project's verification skill.

Report which branch actually completed. Link the saved report, distinguish
uncomputed or non-estimable results, and retain failures with their manifest/logs.
A successful local-niche smoke does not establish DA correctness, biological
replication, or statistical calibration. This module is newly implemented;
consult project run evidence for actual backend validation status.
