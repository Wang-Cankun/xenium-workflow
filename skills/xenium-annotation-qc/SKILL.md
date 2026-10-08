---
name: xenium-annotation-qc
description: "Check existing Xenium cell-type annotations against the data: per-label, per-group and per-cell evidence (lineage-marker support, distinctness, depth dependence, cell-QC flags, contamination, thinning stability, agreement with QC-level labels) with a status and reasons. It reports; it never relabels."
---

# Xenium annotation QC

Evaluate an annotation that already exists (a collaborator's final or draft labels, or
labels made in this project) and report which labels, groups and cells the data
support. This module never relabels, merges or removes cells; the annotation owner
decides what to change. QC-level types from [cell QC](../xenium-cell-qc/SKILL.md) are
evidence here, not replacements.

Read the personal profile ([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile))
and run on allocated compute following the
[compute guidance](../xenium-biohpc-setup/references/biohpc-usage.md#select-compute-resources).

## Inputs

- **Labels keyed to native cells.** One row per cell with `region_id`, `cell_id` and the
  label column; add the group (for example the TMA core) and, for detailed types, the
  column that gives each label's lineage. Join exported objects to native IDs as in
  [analysis input check](../xenium-analysis-input-check/SKILL.md) and confirm that every
  label row maps to one native cell. Record the annotation's source, version and owner;
  an unconfirmed version stays marked as unconfirmed in every output.
- **Counts.** Native `cell_feature_matrix.h5` through a manifest, or an H5AD with raw
  counts; never normalised values.
- **Evidence from cell QC** (optional). The stage-1 table (depth, density, control and
  whole-group flags; nucleus expansion describes segmentation, not quality) and the
  stage-3 QC-level labels with their status.
- **Lineage map.** A label-to-lineage table or `--lineage-column`. Check the non-type
  pattern against the dataset's vocabulary before running.

## Run

Run [annotation_qc.py](scripts/annotation_qc.py) on a CPU node (`--help` owns the
options); the checks, statuses and defaults are defined in [checks](references/checks.md).
When an annotation has main and detailed levels, run both: the main level asks whether
the lineage is right, the detailed level whether the split is supported.

## Read the result

- Start with `label_qc.csv`: status, `reasons` and `failed_families`. Report the reasons
  with their numbers, not the status alone.
- A depth-family failure on a label with strong lineage support usually describes a
  low-RNA population (neutrophils, lymphocytes, capillary endothelium), not a wrong
  label; say which. When sibling labels of one lineage track group depth in opposite
  directions, the split between them depends on depth.
- `not_recoverable` means expression alone does not reproduce the label: it may rest on
  batch correction, clustering resolution or spatial context. It is a question for the
  owner, not a verdict.
- Contamination reasons come with the genes involved (`top_distinct_genes`); shared
  biology is possible, so name the genes.
- `single_gene_defined` means the label is another label's programme plus one gene: name
  the gene and the closest label, and ask the owner to verify the gene (spatial pattern,
  nuclear fraction) before it is read as biology. `failed_group_enriched` means the label
  draws on groups that failed as a whole; give the share.
- When a label's lineage has no exclusive markers (`no_lineage_markers`), lineage support
  cannot be tested and cannot protect the label, so three failed families already give
  `unsupported`; say that the lineage was untestable.
- `group_qc.csv` marks groups whose composition rests on uncertain labels; carry that
  mark into composition and neighbourhood analyses.

## Outputs and completion

Keep outputs versioned by annotation version and parameters (`run_info.json`,
`label_map_used.csv`, `lineage_markers.json`). A run is complete when cell counts
reconcile with the labels table, every label has a status with reasons, the annotation
version and owner are recorded, and the limits are stated: markers and the classifier
are learned from the labels under test (internal consistency, not truth), thinning
models depth but not segmentation, and group depth partly reflects composition.
Figures and reports go through [xenium-figures](../xenium-figures/SKILL.md) and
[xenium-reporting](../xenium-reporting/SKILL.md).

`tests/test_annotation_qc.py` exercises the CLI on synthetic native outputs; the
real-data evidence for the defaults is in [skill trials](../../docs/skill-trials.md).
