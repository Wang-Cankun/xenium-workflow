---
name: xenium-preprocess
description: Build an analysis H5AD of raw counts from native Xenium output folders and embed and cluster it on GPU with Pearson residuals, optional Harmony, Leiden, markers and per-cluster depth QC, saving the projection model that cell-QC label rescue reuses. Cell flags and label rescue belong to xenium-cell-qc; annotation is out of scope.
---

# Xenium preprocessing

Turn native Xenium Onboard Analysis (XOA) outputs into one counts H5AD and a clustering
that later steps can reuse. Nothing is filtered at build time; cell selection for the
embedding is an explicit option recorded with the outputs. Cell-level QC decisions, label
rescue and composition belong to [cell QC](../xenium-cell-qc/SKILL.md); cell-type
annotation is a separate scope.

Read the personal profile
([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile)) and reuse its workspace
and GPU runtime. Run both steps on allocated compute following the
[compute guidance](../xenium-biohpc-setup/references/biohpc-usage.md#select-compute-resources);
clustering needs a supported GPU partition. Take matrix meanings and cell joins from
[analysis input check](../xenium-analysis-input-check/SKILL.md) when they are unresolved.

## Build

Run [build_analysis_h5ad.py](scripts/build_analysis_h5ad.py) (`--help` owns the options)
on a CSV manifest with one row per region (XOA output folder). It writes:

- `layers['counts']` with gene-expression features only; every other feature class
  (control probes and codewords, genomic controls, unassigned and deprecated codewords)
  summed per cell into `obs['matrix_<class>']`, plus `matrix_gene_counts` and
  `matrix_genes_detected`.
- `obs_names` as `<region_id>_<cell_id>`, cell metadata from `cells.parquet` (or
  `cells.csv.gz`) in matrix barcode order, other manifest columns (run, slide, core) as
  categoricals, and `obsm['spatial']` in micrometres in each region's own frame.
- A region status table, a summary JSON and, for regions without a matrix, their
  cells-table rows in a separate parquet. A region read error writes the status table
  and stops without an H5AD.

Join per-cell tables such as [cell-QC](../xenium-cell-qc/SKILL.md) flags or a cell-to-core
map with `--join`. Panels must match across regions unless `--gene-mismatch intersect`
is chosen deliberately. Use `--check-transcript-counts` to confirm that matrix gene sums
equal the native `transcript_counts`.

## Embed and cluster

Run [cluster_analysis_h5ad.py](scripts/cluster_analysis_h5ad.py) in the GPU runtime.
Defaults follow the cell-QC evidence:

- Select cells with a boolean column (for example `pass_floor` from cell QC) or
  `--min-counts`/`--min-genes`; state the selection with the result.
- Analytic Pearson residuals (theta 100, clip sqrt(n)); all genes when the panel has at
  most `--n-top-genes` (2,000) genes, otherwise the top residual-variance genes. On 5K
  and on a targeted panel, 1e4 log-normalisation produced clusters defined by depth
  rather than type.
- Exact PCA with 50 components (held on a targeted panel), Harmony on the run or slide batch
  when there is more than one, kNN (15), Leiden at several resolutions, UMAP.
- Markers per cluster (strict and relaxed detection filters) and per-cluster QC: depth
  quartiles, low-depth flag (cluster median below half the overall median), top-gene
  share, batch entropy.
- A projection model for cells that were not embedded: `genes.csv`,
  `embedding_model.npz`, uncorrected and corrected PCs. Label rescue needs these.

Check before using clusters:

- **Stability.** GPU kNN and Leiden are not reproducible with a fixed seed. Repeat the run
  (the same seed, another seed, and without Harmony) and compare at the level of the
  decision being made, such as the cluster-to-type map, not a single fine partition: maps
  agreed well at type-group and lineage level but not for fine types.
- **Low-depth clusters.** A cluster flagged low-depth is not an artefact by itself; read
  its markers. On a targeted panel they were neutrophils, lymphocytes, smooth muscle and
  myofibroblasts.
- **Species.** Embed each species separately; a joint mouse-human embedding placed some
  mouse cells in human clusters.
- **Cluster summaries.** Versions 1.1 and earlier of the clustering script undercounted
  detections in their GPU cluster sums, distorting marker ranks; on multi-million-cell
  inputs the largest clusters lost up to most of their detections. Version 1.2 computes
  exact sums, equal to a SciPy recount on real inputs, and stops when they do not
  reconcile (`cluster_sum_check` in `run_info.json`). Recompute marker and cluster QC
  tables made with earlier versions. Any GPU script that aggregates with a sparse
  indicator product (`indicator @ X`) is affected: on a multi-million-cell run the product
  dropped detections from clusters with more than about 30 million non-zeros and changed
  the top markers of about half the clusters; the same product summed over 250,000-cell
  row chunks was exact. In synthetic tests the error needed both an output row with tens
  of millions of products and entries fed by tens of thousands of them; float64 values
  and 64-bit indices failed the same way, while sparse x dense products were exact.
- **Batch correction across unlike batches.** When batches differ in composition, such as
  mouse-only versus human-in-mouse runs, check that Harmony does not move cells into
  types that are absent from their batch; compare with the uncorrected embedding.
- Gene ranking by residual variance is not batch-aware, and markers are rankings, not
  tests.

## Outputs and completion

Keep the counts H5AD, its status table and summary, and each clustering in its own
versioned folder with `run_info.json` (parameters, versions, runtime, memory), cluster QC
and marker tables. A run is complete when the build reconciles with the native cell
counts, regions without a matrix are listed, the cell selection and batch key are
recorded, and the stability check is stated. Types derived from these clusters for QC
are provisional; figures and reports go through [xenium-figures](../xenium-figures/SKILL.md)
and [xenium-reporting](../xenium-reporting/SKILL.md).

`tests/test_build_analysis_h5ad.py` exercises the build CLI on synthetic folders and
`tests/test_gpu_script_helpers.py` the exact cluster sums on CPU. The clustering script
needs the GPU runtime; its evidence is the reproduction of an existing project embedding
and the targeted-panel trial and cross-cohort evaluation recorded in
[skill trials](../../docs/skill-trials.md).
