# Scientific report structure and production

Use this guidance when writing an analysis report, including a text-only draft.
The [scientific account guidance](scientific-writing.md) owns
paragraphs, terminology and captions. Use the production branch below when the
requested deliverable includes an editable DOCX and its converted PDF.

## Shape the report

Plan the account around what the collaborator needs to understand or decide.
A useful report makes these answers easy to find:

- **Purpose and main findings:** what the analysis asks and the main answer so far.
  An exploratory report can describe patterns and open questions without claiming
  to test a prespecified hypothesis.
- **Data and scope:** the material, group definitions and analysis units needed to
  interpret the comparisons, with any shared constraint that changes their scope.
- **Evidence:** the observations supporting the answer, including relevant null,
  small, mixed or sampling-sensitive results. Explain the basis for highlighting a
  subset and give a real link to the complete results.
- **Interpretation:** what the observations together suggest, what remains open,
  and any concrete next question or decision arising from them. Keep proposed
  explanations or follow-up distinct from established findings.
- **Methods and supporting material:** how the reported quantities were obtained,
  with details and reproducible outputs available without interrupting the account.

These are content needs, not compulsory headings. For a multi-result report, a
short opening synopsis, question-based results sections, a synthesis and compact
methods/supporting links are a useful starting point. Place enough data context
before the results to make them intelligible. A brief report can combine these
functions in connected paragraphs; it need not repeat an opening summary at the
end. Use headings to make a longer account navigable.

Let each results section answer a discernible question. Develop the observation
with its figure or table, and explain how it relates to the other results. Related
analyses may disagree or answer different questions; the synthesis should preserve
that distinction. Keep procedure details with methods unless the reader needs
them at that point to understand the observation. End with what the work adds to
the reader's understanding; propose further work only when it addresses a specific
unresolved question.

This structure adapts [Nature Education's scientific-paper guidance](https://www.nature.com/scitable/topicpage/scientific-papers-13815490/)
and [Mensh and Kording's reader-oriented organization](https://doi.org/10.1371/journal.pcbi.1005619)
to collaborator reports; it is not a journal submission template.

## Production

The [builder](../scripts/build_report.py) writes native Word paragraphs, tables and
captions, embeds report-sized PNG figures, then invokes an explicitly selected
DOCX converter. It formats existing numeric columns; it does not fit models,
calculate FDR or redefine denominators. Analysis-specific table preparation stays
with the analysis/project.

```sh
"$DOCX_PYTHON" scripts/build_report.py \
  --content /project/report.json \
  --output-dir /project/new-build \
  --renderer /environment/render_docx.py
```

Run from this skill directory, or use the absolute builder path. The runtime needs
`python-docx`, Pillow and pypdf. The selected renderer implements the
`render_docx.py INPUT --output_dir DIR --emit_pdf --verbose --dpi 144` interface and
needs its existing LibreOffice/Poppler tools. Its path is an execution dependency,
not a requirement to load another agent skill. Use environment-provided document
tools; an analysis request does not authorize automatic software installation.

Use a new output directory. `--docx-only` is an explicit authoring/debug option;
the requested report workflow includes conversion of the generated DOCX. The PDF
retained by the renderer is the one used for page previews. Do not separately lay
out a PDF or replace its images after conversion.

`--fontconfig EXISTING_FILE` supplies a process-local font-discovery configuration
when the converter cannot see installed fonts. It installs no fonts and changes
no global settings. Font substitution, a repaired input or an ODT conversion
fallback causes the production build to fail with its evidence retained.

## Content source

`report.json` contains a `title`, optional `short_title`, optional `provenance`
source paths, and ordered `blocks`. Paths resolve relative to this content file.

| Block | Fields |
|---|---|
| `heading` | `level` 1 or 2; `text` |
| `paragraph` | `text` |
| `table` | `source`, `title`, `columns`, optional `delimiter`, `note`, `expected_rows` |
| `figure` | PNG `source`, separate `caption`, optional `width_mm`, `alt` |
| `page_break` | No additional fields |

A table column names its source `key`, reader-facing `label`, width weight and
`format` (`text`, `integer`, `fixed2` or `fixed3`). Every source row is included;
if a display needs aggregation or selection, prepare and document that table
upstream. Numeric fields reject nonfinite or malformed values rather than silently
showing zero. Explicit missing/not-applicable markers can be text columns with a
table-note definition. Prose is plain text; this is not a Markdown converter.

DOCX is an editable output, while this source owns regeneration. Reflect accepted
manual wording edits in the source before rebuilding. No automatic Word-to-source
round trip is implied. Figures remain images in Word; keep their plot code, data
and independent vector PDF/SVG masters.

## Shared style and information placement

[shared style](../../xenium-figures/assets/style.json) owns exact dimensions and type sizes.
`report.font_family` is Arial for native Word content; scientific figure text keeps
Helvetica. The report page and figure widths agree, so figure labels are generated
at their final placed size rather than shrunk to fit. Publication widths remain
available as separate figure settings.

Use a short document title, at most two heading levels, native numeric tables and
adjacent captions. Keep table labels left aligned, numeric columns right aligned,
long labels wrapped and precision meaningful. Use restrained horizontal rules
without decorative shading or a full cell grid.

## Trust and verification

Trust the established deterministic build and its internal source/font/conversion
guards on routine runs. Successful production emits the DOCX, its PDF, page
previews and a manifest with inputs, commands, versions and effective style.
Additional verification is for first implementation, relevant logic/dependency
changes, actual failures or an explicit request; check only the affected behavior.
Routine reports do not trigger manual numeric reconciliation, ZIP/XML inspection,
page-by-page review or computer-use interaction with Word.

For a new design or a changed rendering implementation, a representative short
report can establish source-bound values, native text/table structure, actual
font use, readable placed labels, caption placement and conversion fidelity.
Retain that evidence and use it subsequently. An expensive model rerun is not a
report-layout test. No checksum step is part of this workflow.

## Design sources

- [Nature figure specifications](https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/):
  legibility, units and editable figure masters; publication sizes are not internal
  report defaults.
- [Communications Medicine formatting](https://www.nature.com/commsmed/submit/formatting-guidelines):
  native editable tables and explanations outside artwork; its submission-specific
  caption placement does not determine a collaborator report's layout.
