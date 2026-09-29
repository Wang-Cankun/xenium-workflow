# Quality-check trial

A fresh-context agent used `xenium-quality-check` on a small supplied native-summary
export. The ordinary request asked for a brief meeting overview, two plot suggestions
and a short missing-items note. It could read the skill and its bundled references,
but was instructed not to read research data or connect to BioHPC. The coordinator's
[criteria](criteria.md) were recorded first and not supplied to the candidate.

The [overview](outputs/overview.md) and [metric table](outputs/metric_table.csv)
preserved 3 regions, 2 slides and 350 cells; unknown patient mapping; separate
reported quantile medians (20/80/0) and native nonzero medians (35/80/10); and missing
Q20/assignment values for C. The candidate retained C's summaries despite its absent
matrix, proposed region-level quantile and proportion plots, and avoided filtering,
biological causes, invented distributions and a global quality verdict. Literal
table values and missing markers were checked by the coordinator.

One criterion assumed the supplied quantiles explicitly covered all cells. The
fixture records no recipient filtering but does not expressly define the upstream
quantile population. The candidate correctly retained that uncertainty. Therefore
this trial supports separation of metric populations, not recognition of a fully
specified all-cell population. Exact Q20/assignment definitions and software version
were also absent from the fixture, and the candidate did not invent them.

This is one independent synthetic trial, not a before/after comparison or reliability
benchmark. It exercises overview planning and metric-table extraction, not figure
rendering, raw-file readers, curated transformed matrices or BioHPC execution. The
input, output and extraction script are preserved here. Project figures and slides
are separately verified in the consuming project and are not reusable skill fixtures.
