---
name: xenium-quality-check
description: Summarize supplied Xenium data and basic quality metrics to understand its scale, variation and limitations. Use for descriptive quality checks and preparing metrics for presentation overviews; filtering decisions and biological interpretation require a separate analysis scope.
---

# Xenium quality check

Describe the data received and its basic measurement properties. This quality check
produces observations and limitations. Choosing and applying acceptance or filtering
rules is a separate task for [cell QC](../xenium-cell-qc/SKILL.md). Keep the supplied cells and values unchanged
unless the user has separately requested such decisions. A basic overview ends before
segmentation investigation, biological interpretation or downstream analysis.

## Establish the evidence

Read the personal profile
([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile)). Reuse the saved workspace,
software and execution choices. For new BioHPC data reads or imports, follow
[compute guidance](../xenium-biohpc-setup/references/biohpc-usage.md#select-compute-resources)
and verify the live allocation and execution hostname.

Use existing inventories, input checks and native summaries when their file/version
and cell-cohort coverage match this request. Recompute only missing or inconsistent
evidence needed for the overview. Record which observations were reused and which
were measured now; a filtered-subset report does not describe all supplied cells.

For one native output directory, [qc_describe.py](scripts/qc_describe.py) extracts the
native metrics and alerts, feature classes, the matrix/cell-table join, per-cell signal,
control and segmentation summaries, optionally per group such as TMA cores (`--help`
owns the options). Run it on compute, one output directory per run, and keep its
`run_log.json` with the tables; it removes nothing.

Use [data intake](../xenium-data-intake/SKILL.md) for source/recipient completeness
questions and [analysis input check](../xenium-analysis-input-check/SKILL.md) for
unresolved matrix meanings, cell joins or coordinate semantics. These are independent
tasks, not prerequisites to finish before describing available data. Carry forward
relevant missing-file findings briefly instead of repeating the delivery audit.

## Define the overview

Start with the intended audience and available evidence. For a basic presentation,
prioritize dataset scale and a few understandable metrics. Choose from the following
according to the supplied representation; missing native outputs do not prevent a
useful overview of a curated export.

| Check | Evidence and coverage to record |
|---|---|
| Dataset and coverage | Regions/specimens, slides/runs, cell counts, panel and software version; keep patient mapping unknown when absent |
| Input usability | Reuse available matrix/cell correspondence checks and scoped missing-file records; route unresolved object semantics to analysis input check |
| Cell signal | Gene-transcript and detected-gene summaries by region, and zero-gene-count cell fractions, where confirmed count inputs support them |
| Native detection metrics | Q20 fraction and cell-assigned transcript fraction, with their separate denominators and software definitions |
| Controls and alerts | Available probe, codeword and genomic-control metrics separately, plus native alerts |
| Groups across runs | For TMA cores or other groups: median depth and nucleus-free share per group, its robust z within the run, and agreement between replicate groups of one block. Replicate cores shared depth on a 20-run lung TMA (intraclass correlation 0.84), and 20 of 31 failed cores were replicates of failed blocks, so report block-level patterns, not only single groups |

Review each category when its evidence exists. Mark unavailable metrics and reasons
explicitly; absence is not a zero or a failed sample. Preserve all available values
in a companion metric table. A short talk may select a smaller subset for figures,
without narrowing the underlying descriptive check to only the plotted metrics.

For each chosen metric, establish its source, definition, units, denominator and
covered cells/regions before comparing values. In particular:

- **Count meaning:** distinguish gene transcripts from totals including controls.
  Describe transformed matrices on their documented scale; integer-looking values
  and layer names do not establish transcript-count semantics.
- **Cell population:** distinguish all-cell summaries from nonzero-cell summaries
  and previously filtered exports. Check native median definitions before combining
  them with recomputed medians. Keep incompatible definitions separate.
- **Aggregation:** show regional variation where available. Label whether an overall
  summary weights cells or regions; missing metrics are not zeros. Quantiles support
  quantile plots, not reconstructed cell distributions. A requested pooled cell
  median or distribution needs actual cell values or exact frequency counts;
  regional medians cannot supply it. Preserve separate coverage for metrics with
  missing matrices, even when placing their summaries side by side.
- **Study units:** region, slide and patient counts describe different units. Use
  supplied sample mappings; source folders are organizational labels unless their
  biological meaning is documented. Software, panel and tissue differences limit
  cross-region comparisons.

For Xenium metric interpretation, read the relevant sections of the existing
[assay guidance](../xenium-analysis-input-check/references/xenium-biological-qc.md).
Match definitions to the recorded assay/software version. Keep control classes
separate when reported. A native alert is an observation; an empty alert list is not
a universal quality verdict. Describe ranges and unusual values without assigning
causes or importing universal exclusion thresholds. If reporting cells below a
descriptive count threshold, state explicitly that no filtering was performed.

## Save the check and hand off

Save the metric table, definitions, cell/region coverage, evidence paths,
extraction command and concise observations in the project. Include unavailable
items and consequential interpretation limits. Descriptive checking ends with this
evidence, without cell exclusion, segmentation investigation or causal biology.

For requested plots, pass the table and scientific questions to the separate
[Xenium figures](../xenium-figures/SKILL.md) task. The plot selection is specific to
the audience and available evidence; a small overview need not plot every checked
metric. For DOCX/PPTX, [Xenium reporting](../xenium-reporting/SKILL.md) consumes the
check and finalized figures. If the overall request includes a report, slides or
skill development, retain those deliverables after this module completes.
