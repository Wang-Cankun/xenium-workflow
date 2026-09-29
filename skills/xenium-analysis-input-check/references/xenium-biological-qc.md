# Xenium biological and assay checks

Consult a section when interpreting a supplied field, metric or observed issue.
This reference is not an additional mandatory checklist or a request for upstream
files. Native output definitions apply only when provenance supports them; custom
fields may have different meanings. This is not a universal set of QC cutoffs. Match output definitions to the assay and software
version recorded in the package. Missing upstream files limit what can be verified;
they do not automatically make a processed export unusable.

## Panel and biological context

Identify species, tissue, assay/panel and any custom genes from available metadata.
Separate measured targets from features removed during processing. Xenium targets a
selected panel: an absent feature is not evidence of absent biological expression.
Marker support for an existing label is limited to genes actually measured; panel
metadata annotations are gene-level reference information, not verified cell labels.
[10x panel metadata](https://www.10xgenomics.com/support/software/xenium-panel-designer/latest/tutorials/pre-designed-xenium-v1).

## Count semantics and coordinates

Standard XOA matrices contain cell-assigned transcripts passing the default Q20
threshold. Transcript tables can contain other calls; comparing their totals requires
matching quality, assignment, feature and cell filters. `total_counts` can include
controls, whereas `transcript_counts` refers to gene counts. Preserve feature classes
when interpreting yield or background; a gene-only export cannot demonstrate that
controls were clean.

Native cell centroids are in micrometers. Processed exports may use pixels, transformed
coordinates or montage offsets: establish units from provenance, not magnitude or
an assumed conversion factor. When resolving a coordinate alignment concern with supplied images, inspect
representative overlays using the recorded transform and image resolution. Centroids alone cannot establish
correct segmentation or image registration.
[10x output definitions](https://www.10xgenomics.com/support/software/xenium-onboard-analysis/3.4/analysis/xoa-output-understanding-outputs).

## QC signals

When a QC question arises and summaries are provided, consult `analysis_summary.html`,
metrics and alerts before recomputing. The page is a script bundle whose alert labels
also appear in rendering code. In XOA 4.0 output the run's alerts are the embedded
JSON `alarms` list; an empty list means no native alerts were raised. Check the key
for other software versions.
Look at distributions of gene counts, detected genes, empty cells and cell area by
specimen/core; pooled summaries can hide a poor region. Interpret yield in tissue and
panel context, rather than importing whole-transcriptome gene-count or mitochondrial
percentage filters.

Read control-probe, control-codeword and genomic-control metrics separately when
available. They capture different background mechanisms. An elevated adjusted rate
can reflect low gene signal; it is not by itself proof of nonspecific binding.
[10x summary and metric definitions](https://www.10xgenomics.com/support/software/xenium-onboard-analysis/latest/analysis/xoa-output-analysis-summary).

## Segmentation and interpretation limits

When an observed issue calls segmentation into question, review the supplied method,
cell/nucleus areas and transcript-assignment summaries. Supplied images/masks can
support targeted inspection for boundary mismatch, merged cells or fragmented cells;
flag observations without resegmenting. Visualization polygons approximate masks and are not the exact
transcript-assignment geometry.
[10x segmentation output](https://www.10xgenomics.com/support/software/xenium-onboard-analysis/3.4/analysis/xoa-output-understanding-outputs).

Use supplied alerts to target inspection, not to label every low-yield core a failed
sample. Technical and biological explanations may both remain plausible; retain that
uncertainty and avoid automatic exclusion.
[10x alert interpretation](https://www.10xgenomics.com/support/software/xenium-onboard-analysis/latest/analysis/analysis-summary-troubleshooting).
