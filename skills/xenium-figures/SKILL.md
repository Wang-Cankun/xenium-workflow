---
name: xenium-figures
description: Generate and finalize Xenium scientific figures from documented analysis outputs using Python or R and the shared figure style. Use for plot design, captions and export; assemble DOCX or PPTX with xenium-reporting.
---

# Xenium figures

Produce independently usable scientific figures from existing results. Analysis
modules own metric definitions, transformations and estimates; this module owns
visual encoding, figure style, captions and final exports. Use the project's
existing Python/R plotting environment and preserve its locked dependencies.

## Choose the display

Read the analysis question, plotted table, units, region/sample hierarchy, coverage
and filtering history. For a quality-check task, consume the metric table and
observations from [quality check](../xenium-quality-check/SKILL.md). For other
analyses, use their documented outputs. Resolve ambiguous quantities with the
analysis owner before plotting them.

Read [figure design and review](references/figure-review.md). Show observations
alongside summaries where available, with a visible unit and denominator. Keep
missing and excluded observations distinct. Quantile summaries support quantile
plots, not reconstructed cell distributions. Source folders are display labels
unless their biological meaning is established. Complete specimen inventories can
remain in companion tables.

Use [style.json](assets/style.json) for fonts, dimensions and semantic colors.
Preserve category meanings across plots; use separate documented colors for labels
outside the supplied cell-family palette. Establish the intended physical size
before rendering. If a figure is for slides, choose readable dimensions and text
in this plotting task, then finalize the exported artwork.

Keep axes, units, category keys, panel letters and scale bars in the artwork.
Write a self-contained caption with the quantity, panels, n and its unit,
aggregation, symbols, coverage, filtering and any intervals/tests. A figure title
may describe a result only when the displayed evidence supports it: test result
titles and group descriptions against every plotted row, and qualify or describe
when one row contradicts them. State the rule that selected plotted genes, clusters
or regions. Interpretation stays within the analysis findings.

## Render and finalize

1. Use a reproducible Python/R plotting script. Record the source table, selection,
   ordering, limits, dimensions and effective style. Resolve Helvetica regular and
   bold; use an existing environment with the font rather than substituting it.
2. Export PDF and SVG with editable text plus a 300 dpi PNG from the same figure.
   Preserve physical dimensions; dense spatial layers may be rasterized while
   labels, axes and scale bars remain vector objects. Record plotting versions.
3. For first implementation, relevant changes, failures or an explicit request,
   verify values, coverage, label mappings, export completeness and embedded fonts;
   check rendered text boxes for overlaps and canvas overflow; inspect the actual
   exports for clipping, readability and visible comparisons.
   Reuse successful deterministic checks for unchanged routine runs.
4. Save final figure paths, caption, script, plotted data and parameter record in
   the project. Identify the final exports that downstream reports may use.

A complete figure has a supported scientific meaning, legible artwork and a
traceable regeneration path. [Reporting](../xenium-reporting/SKILL.md) places these
final exports without redrawing them. If a reporting task identifies an unsuitable
figure, handle the requested change as a separate plotting task and provide a new
final export before report assembly resumes. Finalization does not itself imply a
new user-approval gate; honor checkpoints the user actually requested.
