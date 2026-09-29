# Annotation QC checks

[annotation_qc.py](../scripts/annotation_qc.py) owns the computation and its options
(`--help`). This page defines each check, its default and how to read it. Defaults are
starting points; record the values used (`run_info.json`) and justify changes with
the dataset's own evidence.

## Statuses

| Status | Meaning |
|---|---|
| `supported` | No check failed. |
| `review` | At least one moderate check failed, or the label has fewer than `--min-label-cells` cells. The label may be right; the reasons say what to look at. |
| `unsupported` | A strong check failed (`lineage_marker_unsupported`, `defined_by_foreign_markers`), or moderate checks failed in at least `--moderate-to-unsupported` (3) families while lineage-marker enrichment is below `--strong-lineage-support` (3) or untestable. |
| `not_a_type` | The label names no cell type (lineage `none`): unresolved, unknown, low-RNA, doublet, mixed, excluded and similar. It is counted and described, not tested. |

Moderate checks are grouped into families that share evidence (`failed_families`):
depth (`low_depth_enriched`, `share_tracks_group_depth`, `label_fragile_at_its_depth`,
`qc_flag_enriched`), contamination (`foreign_marker_high`,
`foreign_markers_among_distinct_genes`), distinctness (`not_distinct_within_lineage`,
`not_recoverable`, `single_gene_defined`), unit (`failed_group_enriched`), agreement,
spatial and species. A family counts once: a genuinely
low-RNA type fails several depth checks for one reason, and counting them separately
would mark such types `unsupported` on depth alone. A label whose cells clearly express
its lineage (enrichment at least `--strong-lineage-support`) stays at `review` unless a
strong check fails.

A status is a statement about the evidence for a label in this dataset, not a
relabelling. Cells keep their labels; `cell_reasons` carries the cell-level evidence.

## Lineages and markers

Each label belongs to a lineage, from `--label-map` or as the label's most common value
of `--lineage-column` (for example the main type of a detailed type). Labels or
lineages matching `--none-pattern` (unresolved, unknown, low-RNA, low-information,
doublet, mixed, excluded, artefact, unassigned, ambiguous, low-quality) become `none`; override the pattern when a dataset
uses those words for real populations.

Lineage markers are derived from reference-depth cells (at least `--ref-min-counts`
gene counts) of type labels: detection at least `--min-detection` in the lineage, at
least 0.2 above and twice the highest detection in any other lineage, top
`--markers-per-lineage` genes. They come from the labels under test, so they test
consistency, not truth; supply curated markers with `--markers` when available.
`lineage_markers.json` records the sets used.

## Checks

| Reason | Kind | Definition (default) | Read as |
|---|---|---|---|
| `lineage_marker_unsupported` | strong | Mean share of the label's counts on its lineage markers, divided by the same share in cells of other lineages, below `--lineage-enrichment` (1.5) | The cells do not express the lineage the label claims. |
| `defined_by_foreign_markers` | strong | At least 3 of the label's top 5 distinct genes (and at least 60%) are markers of another lineage, and its foreign-lineage marker share is at least `--foreign-ratio` (2) times the median of the other labels of its lineage | The label is separated from its lineage by another lineage's genes: spillover, doublets or mis-assigned lineage. |
| `foreign_markers_among_distinct_genes` | moderate | The first condition without the second | Shared biology is possible (lymphatic endothelium expresses Mrc1; transitional tumour states share epithelial genes); check the genes listed in `top_distinct_genes`. |
| `not_distinct_within_lineage` | moderate | No gene with mean count share at least `--distinct-fold` (2) times that of the closest label of the same lineage, detection at least `--min-detection` and share at least half the uniform share | Possible over-split of a lineage. |
| `low_depth_enriched` | moderate | Share of the label among cells below `--low-depth` (50) gene counts divided by its share among cells at twice that depth, at least `--depth-enrichment` (3) | The label is found mostly where the data are thin. Some real types are low-RNA (neutrophils, lymphocytes, smooth muscle): read with the lineage support. |
| `share_tracks_group_depth` | moderate | Spearman between the label's share within its lineage per group and the group's median depth, abs(rho) at least `--depth-rho` (0.6), p < 0.01, over at least `--min-groups` groups with `--min-group-cells` cells and `--min-lineage-cells` cells of the lineage | The label's share within its lineage follows technical depth across cores. Group depth partly reflects composition (RNA-rich tumours raise core depth); the within-lineage share limits but does not remove that confound. |
| `qc_flag_enriched` | moderate | Share of the label's cells with any cell-QC flag at least 0.2 and at least `--flag-enrichment` (2) times the share in all cells (needs `--cell-qc`) | The label collects cells that failed cell QC. |
| `edge_enriched` | moderate | Share within `--edge-um` (20 um) of the tissue edge at least `--edge-enrichment` (3) times the overall share (needs `dist_to_edge_um` in `--cell-qc`) | Edge signal loss or edge artefact. |
| `foreign_marker_high` | moderate | Mean foreign-lineage marker share at least `--foreign-ratio` (2) times the median of the other labels of its lineage (of all other type labels when it has none), and at least `--dose-ratio` (1.5) times higher in cells with at least half foreign neighbours than in cells with at most 10% | Contamination that grows with foreign neighbours. |
| `single_gene_defined` | moderate | The label's most specific gene has at least `--single-gene-fold` (3) times its mean count share in every other type label; without that gene the label's profile has cosine similarity at least `--single-gene-similarity` (0.95) to another label, from which it differs by at most one gene | A population defined by one extra gene on another label's programme. On a mouse NE-tumour slide, 13 clusters (171,331 cells) were an NE-tumour programme plus one gene detected in 60–100% of cells, with high nuclear fraction and no neighbour dose-response: detection-level artefact candidates, not cell types, until verified. |
| `failed_group_enriched` | moderate | At least `--failed-group-share` (0.1) of the label's cells sit in whole-group-failure groups (`flag_group_low_depth` in `--cell-qc`), and at least `--flag-enrichment` times the overall share | The label draws on groups that failed as a whole; confirm those groups are meant to be analysed. |
| `not_recoverable` | moderate | Accuracy of a kNN classifier (trained on reference-depth cells of type labels, PCA of log-normalised counts) on held-out unthinned cells below `--thin-accuracy` (0.5) | Expression alone does not reproduce the label, even at full depth: the label may rest on batch correction, clustering resolution or spatial context. |
| `label_fragile_at_its_depth` | moderate | Recoverable at full depth, but accuracy interpolated at the label's median depth (from cells thinned to `--thin-depths` and the unthinned point) below `--thin-accuracy` | At the depths where it is called, the label cannot be told apart reliably. Thinning models depth, not segmentation error. |
| `qc_lineage_disagrees` | moderate | Among cells with a confident QC-level label (`--qc-labels`: reference, rescued_type, rescued_lineage), share whose QC-level lineage equals the label's lineage below `--agreement` (0.5) | The annotation and the QC-level labels disagree on lineage. |
| `species_inconsistent` | moderate | Share of cells whose species differs from `--label-species`, at least `--species-minority` (0.1) | Species calls contradict the label (xenografts, mixed slides). |
| `single_group_dominated` | note | At least 90% of the label's cells in one group while it occurs in at least 3 groups | Expected for patient-specific tumour states; a batch or artefact otherwise. Does not change the status. |
| `few_cells` | note | Fewer than `--min-label-cells` (50) cells | Status at least `review`; other checks may be unstable. |
| `no_lineage_markers` | note | No gene passes the lineage-marker rule for the label's lineage | Lineage support cannot be tested; overlapping lineages in the map are the usual cause. |

## Groups and cells

`group_qc.csv` gives, per group (for example a TMA core), the share of cells whose label
is `review`, `unsupported` or `not_a_type`, with the group's median depth; a group whose
`review` plus `unsupported` share reaches `--review-group-share` (0.2) is `review`:
composition and neighbourhood results for it rest on uncertain labels.
`label_group.csv` gives cells and share per label and group.

`cell_annotation_qc.parquet` keeps every input cell with its label, lineage, label
status, gene counts, own- and foreign-lineage marker evidence, foreign neighbour share
and `cell_reasons` (`label_review`, `label_unsupported`, `low_depth`, `no_own_marker`,
`qc_flagged`, `counts_missing`). `thinning_accuracy.csv` gives label and lineage
accuracy per label and depth.

## Limits

Data-driven markers and the classifier learn from the labels being checked: they
detect internal inconsistency, not a wrong but consistent annotation. The checks do
not replace review by the annotation owner; they tell the owner where to look first.
