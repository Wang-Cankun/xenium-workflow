# Encodings and review

## Composition

Show broad cell families as stacked proportions; keep a common zero-to-100% scale.
Twenty or more stacked colors impede comparisons: use a labeled heatmap or focused
facets for detailed types. Use the analysis-defined aggregation and weighting.
State separately how observations are combined within units and how units contribute
to group summaries. A source sample/block can be a descriptive observation without
a claim of independent biological replication. Core-level details remain available in supplements.

For heatmaps show actual units and a labeled colorbar. Saturating a scale is an
explicit display choice: mark values above the upper limit and retain exact values
in the source table. Row z-scores answer a different question and require their own
label and reason. Equal colors must encode equal values in compared panels.

## Effects and uncertainty

Prefer an estimate with a named interval and a zero/reference line. Show the comparison
and effect scale, identifying any supplied inferential summaries separately. A
model coefficient is not automatically a percentage-point change. Include relevant
estimates on both sides of a selection threshold, describing their magnitude and
uncertainty. Descriptive means get no invented uncertainty or significance stars.
State what n counts; distinguish analysis units from independent biological
replicates, preserving any unresolved independence assumption.

## Spatial maps and niches

Use equal x/y aspect and an explicit length unit and scale bar. Keep per-core
frames separate; shared coordinates across cores do not imply physical adjacency.
Display-only subsampling must not change the analysis; preserve sampling specified
by the analysis module. For display subsampling, record the strategy, seed, plotted
count and total count. Use a stable named label palette across maps
and summaries. Neighborhood radius and excluded focal centers belong in the caption.
Neighborhood fractions describe local composition; dominant-type summaries or
clustering labels must not be relabeled as differential QUICHE niches.

## Titles, labels and colour

A result title states what the panel shows and holds for every plotted row; words
such as "small", "all" or "rises" are checked against the table before rendering.
Choose displayed genes, clusters or regions by a stated rule (for example how many
of the highlighted clusters list a gene among their top markers) and give the rule
in the caption. A claim that a group differs from others needs a comparator in the
panel, or the caption says the comparison is not shown.

Every mark is identifiable from the figure; n, fixed settings, abbreviations and
caveats go to the caption. Label lines at their ends where space allows. Use colour
for a distinction the figure makes: when one group is the subject, draw it in one
saturated colour and the rest in neutral grey, keep one colour per entity across
panels, and do not give unordered categories a sequential ramp. Italicise gene
symbols. Log axes use plain-number ticks (30, 100, 300); filled bars do not go on a
log axis. Text stays at or above `minimum_font_size` in the style file.

## Review evidence

Automated checks can establish: plotted count/denominator conservation; explicit
category mappings; finite valid fractions; exported dimensions; font sizes,
overlapping text boxes and out-of-canvas text; correct uncertainty schema; and
core-isolated spatial edges. Visual review establishes: readable comparison,
balanced information density, usable legend placement and legible labels. For a
multi-panel figure, also ask whether each panel supports the figure's one claim and
whether its selection and comparator hold up. Neither substitutes for the other.

Our default colors were selected by the user from two real Joshi previews. They
are a house style, not a certified color-vision-safe palette. Use labels, ordering,
facets and marker/line distinctions so color is not the only means of reading data.

## Sources considered

- [K-Dense scientific-visualization](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scientific-visualization), MIT: source-aware plotting, scoped style and export inspection informed this original implementation.
- [Nature figure guide](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications): journal-specific dimensions and preparation requirements must be checked at submission.
- General-purpose figure-style and figure-composer skills of an agent platform: row-tested claim titles, colour economy, text-overlap checks and claim-level panel review informed "Titles, labels and colour". Their generic size ladder and PNG-only composition are not adopted.

The upstream repository is a development reference, not a runtime dependency. No
upstream skill is automatically installed or invoked by this skill.

## Figure submission references

- [Nature initial submission](https://www.nature.com/nature/for-authors/initial-submission): brief figure titles and self-contained legends; exact n, replicate and uncertainty definitions.
- [Nature final submission](https://www.nature.com/nature/for-authors/final-submission): consistent sans-serif lettering, with Helvetica or Arial preferred. Helvetica is our selected font, not the publisher's only permitted font.
- [Community nature-skills](https://github.com/Yuan1z0825/nature-skills), including nature-writing/nature-polishing: a development reference for evidence-matched wording, not Nature-endorsed instructions. Its own Results–Discussion reference describes corpus-derived guidance. The workflow remains self-contained.

Journal requirements apply to the selected journal and submission stage. Use the
[scientific account guidance](../../xenium-reporting/references/scientific-writing.md) for wording
and captions; use the shared style asset for this project’s typography and sizes.
