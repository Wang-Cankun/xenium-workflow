# Evidence and defaults

## Published practice

| Source | Relevant finding | Scope and limits |
|---|---|---|
| Marco Salas et al., *Nat Methods* 22:813 (2025), [doi](https://doi.org/10.1038/s41592-025-02617-2) | Removed only cells with < 10 transcripts (about 0.2%) across 25 Xenium datasets. Normalisation, target library size, scaling and PC number affect clustering most; best simulated workflow: target 100, log, scaling, all PCs, 16 NN | Mostly targeted panels, not 5K |
| SPLIT, *Nat Methods* (2026), [doi](https://doi.org/10.1038/s41592-026-03089-8) | On 5K panels about 60% of cells fail a count-based QC; the Xenium filter removes only < 10 counts or < 5 genes and resolves low-count and mixed cells with RCTD. Mixed signal comes mainly from neighbour spillover and scales with neighbour abundance | Needs a single-nucleus reference; breast and lung tumours |
| OSTA imaging QC chapter, [Bioconductor](https://bioconductor.org/books/release/OSTA/pages/img-quality-control.html) | Flag low counts per area on a log scale with MAD; inspect the spatial location of excluded cells before removing them | Read from page excerpts, not the full chapter; its example uses a targeted panel, and its control-count > 0 rule does not transfer to 5K |
| SpaceTrooper, bioRxiv (2025), [doi](https://doi.org/10.64898/2025.12.24.696336) | Ridge logistic quality score from cell area, log2 density and log2 control fraction, trained on outlier-defined labels | Preprint; thresholds remain data-specific |
| CyLinter, *Nat Methods* 21:2248 (2024), [PMC11621021](https://pmc.ncbi.nlm.nih.gov/articles/PMC11621021/) | Modular, iterative QC with visual review; metaQC re-clusters removed and kept cells to add back or remove by cluster | Multiplex protein imaging; principles transfer |
| SpotSweeper, *Nat Methods* 22:1520 (2025), [doi](https://doi.org/10.1038/s41592-025-02713-3) | Local outliers against spatial k-nearest neighbours (robust z) and regional artefacts from local variance | Developed on spot-based data |
| resolVI, *Nat Methods* (2026), [doi](https://doi.org/10.1038/s41592-026-03212-9) | Generative model downstream of segmentation; separates own expression, neighbour diffusion and background | GPU; corrected counts are model estimates |
| ovrlpy, *Nat Biotechnol* (2026), [doi](https://doi.org/10.1038/s41587-026-03004-8) | Vertical signal integrity (VSI) from top and bottom virtual subslices finds overlapping cells and folds | Segmentation-free; thresholds are context-specific |
| MisTIC, bioRxiv (2025), [doi](https://doi.org/10.64898/2025.12.11.693759) | Variational Bayesian correction of transcript misassignment without resegmentation | Preprint; needs transcripts and cell masks |

## Basis of the defaults

The defaults were evaluated on unpublished data: a whole-transcriptome (5K) panel cohort
of whole sections and a multi-run targeted-panel TMA series with human, mouse and
mixed-species cores, against published comparators and existing collaborator QC and
labels. The quantitative results and their reproduction stay in the consuming projects;
what follows is what each default rests on.

- **Floors.** Fixed transcript floors removed cells in proportion to region or core depth
  and removed low-RNA types (neutrophils, smooth muscle and pericytes, lymphocytes) before
  tumour cells; the shallowest runs lost about half their cells at 50/10. The 10/5 floor
  removed a few percent. Most cells that stricter collaborator floors removed could be
  rescued to a type or lineage.
- **Grouping unit.** MAD flags computed per run tracked core depth and flagged most cells
  of shallow cores; computed per core they did not. In large cores and whole sections a
  substantial share of depth flags lay in low-RNA squares, far fewer in 1 mm cores.
- **Whole-group failure.** Per-group MAD could not see cores that failed as a whole, some
  nearly nucleus-free; only the between-group check found them. Most failed cores were
  replicates of one failed block, and replicate cores share depth.
- **Density.** Density-flagged cells were spatially clustered, edge-enriched, low in
  nuclear transcript fraction and enriched in low-RNA types.
- **Controls.** Where few cells carry any control count, the unconditional MAD rule flagged
  almost only zero-control low-depth cells, while a binomial excess test flagged a small
  set. A rule of any control count flagged a large share of 5K cells, most of it from
  deprecated codewords. Rerunning the revised rule reproduced every other flag and kept
  its control flags within the earlier set; earlier flag tables keep the rule they were
  built with.
- **Nucleus expansion.** Expansion cells carried markedly fewer transcripts than
  interior-stain cells of the same region: a segmentation indicator, not a quality verdict.
- **Comparators.** Local robust z against spatial neighbours gave depth-independent core
  rates only on log depth and found no regional artefact; the logistic quality score
  tracked core depth; regional metrics (kNN-smoothed depth ratio, low-RNA grid) were
  depth-independent and spatially coherent. XOA version and panel changed no conclusion
  but were confounded with run.
- **Normalisation and stability.** 1e4 log-normalisation gave a larger depth share of
  cluster variance than Pearson residuals in every species group and produced
  depth-defined clusters; the low-depth clusters under residuals were low-RNA types.
  Scaling and PCA fitted on high-quality cells did not help. Same-seed GPU reruns were not
  identical, seed changes moved partitions further, and cluster-to-type maps were stable
  for type groups and lineages but not fine types.
- **Calibration.** Unthinned re-projected cells almost always kept their parent label.
  Below 50 transcripts no vote threshold reached 90% type accuracy in any calibration;
  vote 0.95 reached it at 50 in most. Finer type maps, tumour cores below 30 transcripts
  and mouse cores dominated by one tumour type were less accurate, the last misassigning
  low-depth non-tumour cells to tumour. Lineage was more robust than type, and rare types
  were least accurate. A depth-quantile cut and a fixed cut calibrated alike.
- **Species.** In mixed-species designs species was the largest low-depth error, Harmony
  across runs of different species composition placed cells of a mouse-only run in human
  types, and cores registered as mouse could hold many human cells.
- **Rescue.** Rescued cells matched their reference neighbours' lineage nearly as often as
  reference cells beyond a permutation baseline; unresolved cells did not. Low-RNA types
  had the lowest reference shares, so reference-only composition underestimated them.
  Collaborator "low-information" labels were mostly reference cells in a distinct state.
  Without a hold rule, transfer labelled cells of failed cores that had no reference cell.
- **Composition.** Floors of 5-20 transcripts and removal of flagged cells kept the sign of
  every tested contrast; a 50/10 floor and reference-only composition reversed contrasts
  between groups that differed in depth. Best guesses for unresolved cells inflated rare
  types. Replicate consistency changed within resampling error between definitions, so it
  does not rank QC choices.
- **Contamination.** Foreign-marker share rose with foreign-neighbour dose; mixed-signal
  rates (MECR) rose with depth and were equal across QC definitions within depth bins.
  Foreign markers were nuclear-depleted in some lineages. SPLIT and MisTIC lowered
  depth-matched MECR; resolVI did not consistently; ovrlpy low VSI marked a small share of
  cells with little effect; the methods' flagged sets overlapped little. Reporter
  transgenes behaved as contamination markers, and a same-lineage marker pair does not
  measure contamination.
- **Artefact clusters.** A cluster whose signature transcripts were nuclear in every
  lineage persisted under all preprocessing. Clusters equal to a tumour type plus one gene
  spread across many cores, with the added gene rarely near cells that express it.

Revisit the defaults for other tissues, other segmentation versions or when the thinning
calibration of a new cohort differs materially.
