---
name: xenium-reporting
description: Write Xenium analysis reports or meeting presentations from existing results and finalized figures. Use for scientific narrative, DOCX/PDF reports and PPTX decks; figure creation and revision belong to xenium-figures.
---

# Xenium reporting

Organize supplied findings for the intended audience and what they need to
understand or decide. The deliverable may be a report or a presentation; retain the
requested audience, purpose, language, length and final format throughout the work.
Read the project's current scope and evidence, including the analysis unit,
sampling, replication, metric coverage and consequential unresolved inputs.

## Prepare the account

Use [scientific writing](references/scientific-writing.md) for results, interpretation
and captions. Establish what was examined, the main observations and their limits.
Select existing evidence to serve the intended use. Preserve denominators, units,
uncertainty, null findings and the distinction between observation and explanation.
Analysis modules own calculations and estimates; reporting owns their explanation.

List the final figure files, supplied captions and supporting tables to be used.
Consume the exports from [Xenium figures](../xenium-figures/SKILL.md). Report code
may position and proportionally resize a whole figure; keep its artwork, labels,
axes, ordering, colors and values unchanged. Use the existing figure file even
when a general document tool prefers editable native charts. Editable report text
and tables remain useful; the figure's editing source is its plotting script.

If an export is missing, unfinished or unreadable at the intended size, identify
the specific need and return it to a separate figure task. Continue independent
writing where useful. Resume assembly with the final export instead of creating
another plot inside the DOCX/PPTX builder.

## Select the deliverable

- For a report or multi-result written narrative, read
  [report structure and DOCX production](references/report-layout.md). The existing
  [builder](scripts/build_report.py) creates native Word text/tables, inserts final
  PNG figures and converts the DOCX to PDF using the selected existing renderer.
- For slides, including revisions and sharing copies, read
  [PPTX production](references/presentation.md) before changing content. It owns
  narrative, audience review and iteration, and routes to slide wording and
  template rebuilding. DOCX and PPTX are alternatives unless both were requested.

Use available document tooling for the selected format; the bundled report builder
and production references describe the required behavior without depending on an
external agent skill. Reuse project runtimes and export to a new output location.

## Complete the requested output

Check that titles, text, tables and figures tell the same scientific account and
match the requested scope. Verify figure inclusion against the declared final
files, rather than considering a separately recreated chart equivalent. On first
implementation or relevant changes, check the produced file and the affected
layout; routine builds reuse their established checks. Word inspection through
computer-use tools requires an explicit user request.

Save the content source, figure references, build command and final document in
the project. Retain limitations that affect use. Completing a narrative draft,
figure bundle or skill update does not complete a task that requested a DOCX or
PPTX; deliver the requested file after the applicable checks.
