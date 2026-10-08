---
name: xenium-cell-qc
description: "Choose and apply cell-level QC for Xenium data before and after clustering: per-cell flags with reasons, calibrated label transfer for low-information cells, composition sensitivity and contamination diagnostics. Descriptive metrics belong to xenium-quality-check."
---

# Xenium cell-level QC

Decide which cells are uninformative or artefactual and how each is handled. This
module marks cells; it does not delete them from the source objects. The only removal
is a low floor. Every other decision is a flag with a reason, stored with the cells
and recorded in the project with its parameters.

Read the personal profile
([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile)) and reuse the saved
workspace and runtimes. Run data reads on allocated compute following the
[compute guidance](../xenium-biohpc-setup/references/biohpc-usage.md#select-compute-resources).
Take matrix meanings and cell joins from [analysis input check](../xenium-analysis-input-check/SKILL.md)
and reuse [quality check](../xenium-quality-check/SKILL.md) metrics where they cover the
same cells. Read [evidence and defaults](references/evidence.md) before changing a
threshold or adding a rule.

## Stages

1. **Per-cell flags (before clustering).** Run [cell_qc_flags.py](scripts/cell_qc_flags.py)
   on a manifest of native output directories (`--help` owns the options). It keeps
   cells with at least 10 gene transcripts and 5 genes, and flags within each grouping
   unit: low depth and low transcript density (3 MAD below the unit median), high control
   fraction, nucleus-expansion boundaries. Transcript-level nuclear fraction, tissue-edge
   distance, neighbour counts and membership of low-RNA squares (`in_low_rna_bin`) are
   recorded as evidence. The floor is the only removal: stricter fixed floors remove
   cells in proportion to depth and remove low-RNA types first (in a targeted-panel series
   a 50/10 floor removed most neutrophils).
   - **Grouping unit.** The unit is the region unless a cell-to-group table is supplied
     (`--groups`). On a TMA, use the core: per-run MAD rates tracked core depth and
     flagged most cells of shallow cores, while per-core rates did not. Cells outside
     every core are not reference candidates. In large cores (2-3 mm) and whole sections,
     part of a unit's depth flags are regional (a substantial share lies in low-RNA
     squares); review them as regional signal loss, not cell quality.
   - **Whole-group failure.** Per-group MAD cannot see a group that failed as a whole; the
     between-group check flags groups whose median depth is 3 MAD below the region's
     groups, and the group summary counts corroborating evidence (`failure_evidence`: that
     flag, nucleus-free share, share below the region cut, absolute median depth). Review
     groups with two or more lines of evidence; when replicate groups of one block fail
     together, the block failed (most observed core failures were of this kind). Cells of
     a failed group are neither reference nor rescued (stage 3).
   - **Density.** The density flag enriches low-RNA types (smooth muscle, neutrophils);
     read it with the cells' lineage before treating it as a quality signal.
   - **Controls.** Only cells with at least one control count can be flagged for control
     fraction. The rule is chosen per region: MAD when at least 5% of cells carry a
     control count, otherwise a binomial excess test against the region's control rate.
     Without the control-count condition the MAD rule becomes a second low-depth flag:
     almost all cells it flagged had no control count, on 5K and targeted panels alike.
     Presence of any control count is not a rule; on 5K panels it flags a large share of
     cells, most of it from deprecated codewords.
   - **Not defaults.** Local outlier tests against spatial neighbours (SpotSweeper style)
     were independent of core depth only on log depth, not on genes or density, and do not
     see regional artefacts; a logistic quality score (SpaceTrooper style) followed core
     depth; regional depth metrics are spatially coherent and belong to core review.
     Tissue-edge distance is recorded, not flagged.
   Before relying on a flag, check where flagged cells lie: flags concentrated at tissue
   edges or in one group describe signal loss, not a cell type.
2. **Preprocessing for clustering.** Build and embed with
   [xenium-preprocess](../xenium-preprocess/SKILL.md): analytic Pearson residuals with
   Harmony on the run or slide batch, one embedding per species. 1e4 log-normalisation
   raised the depth share of cluster variance in every tested cohort and created
   depth-defined clusters on whole-transcriptome and targeted panels. A
   low-depth cluster is not an artefact by itself: under residuals they were low-RNA types
   (neutrophils, lymphocytes, smooth muscle, myofibroblasts). Do not remove cells
   because their cluster is low in depth, and do not decide QC from one fine Leiden
   partition: GPU neighbours and Leiden are not reproducible at a fixed seed so a same-seed
   rerun is the stability baseline, and cluster-to-type maps were stable at type-group
   and lineage level but not for fine types.
3. **Label low-information cells (after clustering).** Define reference cells and transfer
   labels to all other cells that pass the floor, with a calibrated vote and an explicit
   `unresolved` status, using [rescue_labels.py](scripts/rescue_labels.py) in the GPU
   runtime. Follow [label rescue](references/label-rescue.md) for reference definition,
   projection, calibration by thinning, the spatial check and, for mixed-species designs
   such as xenografts, the species check ([species_check.py](scripts/species_check.py)).
   Types at this stage are QC-level labels, not the final annotation; choose them no finer
   than the calibration supports. In every calibration so far no vote threshold reached
   90% type accuracy below 50 transcripts; vote 0.95 generally reached it at 50. Accuracy
   fell with finer type maps, for tumour cores below 30 transcripts and for cores
   dominated by one tumour type, so each cohort needs its own calibration
   ([evidence](references/evidence.md#basis-of-the-defaults)). Cells of failed groups get
   `unresolved_failed_group` (`--hold-column`).
4. **Composition sensitivity.** Report composition from reference plus confidently
   rescued cells and compare it with a fixed-threshold and a reference-only definition,
   per grouping unit and against its depth
   ([composition_sensitivity.py](scripts/composition_sensitivity.py)). Keep unresolved
   cells unresolved: forcing best guesses inflates rare types. When compared groups
   differ in depth, a 50-transcript cut or reference-only composition reversed group
   contrasts that floors of 5-20 transcripts, and removing cells flagged by the stage-1
   defaults or by any comparator rule, left unchanged. Exclude failed groups from
   compositions.
5. **Contamination diagnostics.** Report the neighbour dose-response of foreign-lineage
   markers and the nuclear fraction of own versus foreign markers
   ([contamination_diagnostics.py](scripts/contamination_diagnostics.py);
   [diagnostics](references/label-rescue.md#contamination-diagnostics)). Compare
   contamination between definitions or methods only within depth bins: mixed-signal
   rates rise with depth, and cell-level QC did not change them at matched depth. Treat
   a cluster whose defining genes are mostly nuclear across all lineages, or that equals
   another cluster plus one gene, as a flagged signal, not a cell type. Correction and
   scoring methods (transcript reassignment, SPLIT, resolVI, ovrlpy) are sensitivity
   analyses with their own scope, not default filters
   ([method comparison](references/label-rescue.md#correction-and-scoring-methods)).

Choose the stages the request needs; stage 1 alone is a valid task. Record per stage
the input version, cell cohort, parameters and outputs, and keep earlier QC versions
unchanged. After annotation, check the labels themselves with
[annotation QC](../xenium-annotation-qc/SKILL.md).

## Outputs and completion

The project keeps one table with a row per segmented cell: floor result, flags,
status (`reference`, `rescued_type`, `rescued_lineage`, `unresolved`,
`unresolved_no_signal`, `unresolved_failed_group`, `below_floor`, `no_matrix`),
provisional label and confidence,
and a semicolon-separated reason string (including whole-group failure and cells outside
every group), plus a data dictionary and per-region and per-group summaries. A run is
complete when cell counts reconcile with the input, each unit's flag rates are reported
with its depth,
thresholds and their calibration are recorded, and limits are stated: thinning models
depth but not segmentation error, and rare types are least accurate at low depth.
Figures and reports go through [xenium-figures](../xenium-figures/SKILL.md) and
[xenium-reporting](../xenium-reporting/SKILL.md).

`tests/test_cell_qc_flags.py` exercises the flag CLI on synthetic output directories and
`tests/test_gpu_script_helpers.py` the rescue status rule. They establish computational
behaviour, not that the defaults suit another panel or tissue. The rescue, composition and
contamination scripts need the GPU single-cell runtime; their evidence is the
targeted-panel trial and cross-cohort evaluation in
[skill trials](../../docs/skill-trials.md), and each new cohort needs its own calibration.
