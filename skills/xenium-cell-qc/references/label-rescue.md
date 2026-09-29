# Label rescue and contamination diagnostics

Use this reference for stages 3-5. It describes required behaviour; implement it in the
project's GPU single-cell runtime and keep the project script with its outputs.

## Embedding

Analytic Pearson residuals (theta 100, clip sqrt(n)) on all genes when the panel has at
most 2,000, otherwise on the 2,000 genes with the largest residual variance, PCA 50 (held
on a targeted panel; 30 PCs gave a less stable type map), Harmony on the run or slide,
kNN graph on the corrected PCs, Leiden around resolution 1. Save the gene list, gene
frequencies used for the residuals, PCA loadings and mean, and the corrected embedding;
projection needs them. [cluster_analysis_h5ad.py](../../xenium-preprocess/scripts/cluster_analysis_h5ad.py)
writes all of these.

## Reference cells

Reference cells pass the floor, have at least 50 gene transcripts, carry none of the
stage-1 flags (depth, density, control fraction, nucleus expansion, whole-group failure),
lie inside a grouping unit when one is used (for example a TMA core) and belong to a
cluster with a clear marker-defined type. Record the cluster-to-type map with each
cluster's top markers and check it against repeated clusterings, including a same-seed
rerun (GPU clustering is not reproducible at a fixed seed). Exclude ambiguous clusters,
clusters defined by a nuclear artefact signature and single-gene clusters (below) from
the reference; their cells are queried like any other. Cells of whole-group failures are
held: never reference, never rescued (`--hold-column`, default `flag_group_low_depth`,
read from the label table and the H5AD obs; status `unresolved_failed_group`). Label
tables often list only embedded cells while failed-group cells are projected, so keep the
flag in the H5AD obs or list every cell in the label table. Without the hold, transfer
from other cores labelled most cells of a failed core that had no reference cell.

A cluster whose profile equals another cluster's plus one gene detected in most of its
cells, with few neighbours of the type that normally expresses that gene, is a
detection-artefact candidate rather than a type; such clusters recurred in cores dominated
by one tumour type. Flag and exclude it; the annotation QC check `single_gene_defined`
finds the same pattern in delivered labels. The 50-transcript cut held on a targeted
panel: a cut matched to the same depth quantile calibrated alike. It removes a larger
share of low-RNA types (neutrophils, lymphocytes) from the reference; report that share.

## Transfer and projection

- Cells in the embedding: take the 30 nearest reference cells in the corrected space;
  exclude the cell itself when it is a reference cell (leave-one-out).
- Cells that pass the floor but were not embedded: compute residuals with the saved gene
  frequencies and clip, project with the saved loadings, and add the mean Harmony offset
  (corrected minus uncorrected PCs) of their 15 nearest embedded cells from the same run.
- Record the type vote fraction and a lineage vote fraction (summed over types of one
  lineage). Cells with fewer than 5 counts on the embedding genes are `unresolved_no_signal`.

## Calibration by thinning

Binomially thin a random sample of reference cells to fixed depths (10, 15, 20, 30, 50,
80, 120 transcripts, plus unthinned controls), re-project them as above and transfer
labels while excluding the parent from both neighbour searches. Report agreement with
the parent's type and lineage by depth, with and without each vote threshold, and the
share of cells kept. Choose the smallest threshold meeting the target accuracy (for
example 90% type, 95% lineage below 50 transcripts); if none meets it, use the strictest
tested value and state the achieved accuracy. Unthinned controls check the projection.

Also report the type and lineage confusion of thinned cells below 50 transcripts:
low-depth errors concentrate between similar lineages (for example, one tumour type in
two species). If the strictest tested threshold still misses the target,
extend the grid towards 1.0 before accepting it.

Calibrate at the level the labels will be used and per species or tissue composition when
these differ. Accuracy depends on type granularity: with several dozen fine types, type
accuracy below 50 transcripts fell far below that of type groups and lineages. With maps
finer than about 30 types, use type groups as the QC-level types (the type map's `type`
column), and keep fine types for cells above 50 transcripts. Tumour cores below 30
transcripts and cores dominated by one tumour type (errors towards tumour) may support
lineage labels only; state this per cohort.

Statuses: `rescued_type` when the type vote meets the threshold; `rescued_lineage` when
only the lineage vote does; otherwise `unresolved`. Keep the best-guess type in its own
column for diagnostics.

[rescue_labels.py](../scripts/rescue_labels.py) implements transfer, projection,
calibration, statuses and the independent checks below from the preprocessing outputs, a
per-cell label table (`obs_name`, `own_type`, `reference`) and a type-to-lineage map.

## Species check (mixed-species designs)

In xenografts or other mixed-species tissue, species is part of the lineage. When the
panel has species-specific probes:

- Score each cell and cluster with the species-probe share, and type species from it.
- Compare the corrected embedding with the uncorrected one: Harmony across runs with
  different species composition placed mouse cells from a mouse-only run in human types.
- Report labels of a species in runs or groups where that species is absent, and the
  species-probe share of rescued versus reference cells of each species-specific type.
  For low-depth cells, assign species from probes rather than from transfer.
- Compare each group's probe-called species with its registered species. Cores registered
  as one species can hold many cells of the other and form their own cluster; report such
  groups to whoever owns the core assignment instead of relabelling them.
- Embed each species separately: a joint embedding placed mouse cells in human clusters.

[species_check.py](../scripts/species_check.py) computes the per-cell probe share and call,
agreement with the label species by status, and labels of species not allowed in a group
(from an expected-species table). On real data it reproduced the trial's species
checks.

## Independent checks

- Spatial: for each cell, the share of its reference neighbours (up to 10 within 30 um,
  same region) with the same lineage, against the same statistic after permuting labels
  within region and status. This uses coordinates only.
- Profiles: pooled counts of rescued cells per type should correlate best with the
  reference profile of the same type. Marker shares are partly circular because the
  markers overlap the embedding genes; say so.

## Composition sensitivity

Compare provisional type proportions per region under: the floor with own-cluster types;
a fixed 50-transcript threshold; the floor minus stage-1 flags; reference cells only;
reference plus `rescued_type` (the recommended definition); all best guesses. Report
per-group total-variation distance from the recommended definition against group
depth, and per-type median log2 ratios. Score a definition only in groups where it keeps
at least 50 cells (otherwise the distance is large by construction), and report cells
rescued from excluded clusters separately, since they can dominate one group.
[composition_sensitivity.py](../scripts/composition_sensitivity.py) applies the cell-count
guard (`--min-scenario-cells`); list rescued cells of excluded clusters from the rescue
labels table. Exclude failed groups.

When the analysis compares groups (genotypes, treatments, patients), also report the sign
of each group contrast under every definition. Depth cuts and reference-only compositions
reversed contrasts between groups of unequal depth that floors up to 20 transcripts left
unchanged; an existing annotation reversed more. Replicate-core distances did
not separate QC definitions and are a weak criterion.

## Contamination diagnostics

Build lineage-exclusive marker sets from reference cells and remove genes of any
cross-lineage artefact signature. For reference cells:

- Neighbour dose-response: share of transcripts from each foreign lineage's markers,
  binned by the fraction of reference neighbours (up to 15 within 30 um) of that lineage.
- Nuclear localisation (needs transcripts.parquet, qv >= 20): nuclear fraction of own
  versus foreign marker transcripts per lineage, per region and pooled, and the foreign
  share with whole-cell versus nuclear-only counting.
- Mutually exclusive gene pairs (for example PTPRC with EPCAM): observed versus
  independence-expected co-detection.

[contamination_diagnostics.py](../scripts/contamination_diagnostics.py) computes these
from reference cells; `--foreign-set` adds custom sets. Species-specific probes give a
marker-free spillover test: the other species' probe share rises steeply with the
fraction of neighbours of that species. Marker scores between
lineages that share a programme (one tumour type in two species) do not measure
contamination. Useful exclusive pairs include PTPRC with EPCAM or KRT8, KDR with EPCAM,
CD3E with EPCAM and COL1A2 with PTPRC.

Foreign markers that rise with neighbour dose and are depleted in the nucleus indicate
spillover. A signature that is mostly nuclear in every lineage indicates a nuclear
artefact; flag its cluster rather than annotating it. Nuclear depletion is not universal:
in one cohort's mouse cores foreign and own markers had the same nuclear fraction while
the dose response was clear, so its absence does not rule out spillover.

Compare mixed-signal rates (MECR, foreign-marker share) only within depth bins: MECR rose
steeply with depth, and cell-level QC definitions differed only through depth. Use
exclusive pairs across lineages (the B and T cell pair Ms4a1-Cd3e is same-lineage), and in
genetically engineered models keep reporter transgenes (EGFP, tdTomato) as foreign sets.

## Correction and scoring methods

Methods that change counts or score mixture are sensitivity analyses with their own
scope, not default filters. Evaluate each against depth-matched downsampling of the
native counts, and report kept cells and transcripts with the depth-stratified MECR and
foreign-marker share. Effects observed on a targeted-panel cohort:

| Method | Effect at matched depth | Use |
|---|---|---|
| MisTIC transcript reassignment | Largest MECR reduction measured, totals unchanged | Needs transcripts and masks; one cohort |
| SPLIT count purification | Lower MECR, most transcripts kept | Needs a single-cell reference (RCTD) |
| Cell exclusion (RCTD singlets, QC status) | Observed/expected MECR barely moved | Does not remove contamination |
| resolVI (50 epochs, unsupervised) | No change in foreign share; MECR unchanged, worse than downsampling, or lower only through rounding | Mixture proportion as a per-cell score |
| ovrlpy VSI < 0.7 | Small share of cells, slightly higher foreign share; MECR barely changed | Region-level check; unreliable in low-signal cores |

Flagged sets overlapped little. RCTD rejects are not low-quality cells (many were
reference cells); read them as reference mismatch or mixed
signal.
