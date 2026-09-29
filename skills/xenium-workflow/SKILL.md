---
name: xenium-workflow
description: Read the saved BioHPC profile, then route Xenium tasks to setup, data download, data intake, analysis input checking, descriptive quality checking, cell or annotation QC, or an analysis module included in this skill set.
---

# Xenium workflow

## Read the profile first

On every invocation, before recommending a project, package or next action, read the
personal profile as described in
[Locate the profile](../xenium-biohpc-setup/SKILL.md#locate-the-profile). Check its
canonical location before claiming the profile is absent: an imported copy without
`profile.md` is not evidence that none exists, and project notes are not a substitute
for the personal profile.

Briefly state the saved setup context relevant to the request: host/account, chosen
workspace and unresolved choices. Distinguish recorded settings from checks performed
now; reading the profile does not require reconnecting or rerunning setup. A proposed
workspace is not a settled choice.

For “what do we do first?”, establish profile status before using project notes to
suggest a project. If the profile is missing or the working context is undecided,
start with the setup module's orientation. Otherwise reuse the saved choices, take
current status from the project docs the profile links, and recommend the next
relevant task. For a concrete task, resolve only configuration
gaps that affect it; unrelated unknowns need not block work.

## Select the task

The modules are independently callable; reading the profile is shared entry behavior,
not a requirement to repeat setup before every task.

| Task | Module |
|---|---|
| Discover Xenium project directories on BioHPC, choose a workspace, or update Xenium working settings | [xenium-biohpc-setup](../xenium-biohpc-setup/SKILL.md) |
| Download shared data from a cloud share (OneDrive/SharePoint) into BioHPC storage, or refresh a copy after new uploads | [xenium-data-download](../xenium-data-download/SKILL.md) |
| Receive data, check download completeness, compare source/recipient inventories or locate missing delivery files | [xenium-data-intake](../xenium-data-intake/SKILL.md) |
| Interpret supplied matrices, cell/specimen correspondence, coordinates and usable analytical inputs | [xenium-analysis-input-check](../xenium-analysis-input-check/SKILL.md) |
| Describe dataset scale, coverage and basic quality metrics without making filtering decisions | [xenium-quality-check](../xenium-quality-check/SKILL.md) |
| Build an analysis H5AD of raw counts from native outputs, or embed and cluster it (Pearson residuals, Harmony, Leiden, markers) on GPU | [xenium-preprocess](../xenium-preprocess/SKILL.md) |
| Choose or apply cell-level QC: flag low-information or artefactual cells, rescue low-depth cells by label transfer, check composition sensitivity and contamination | [xenium-cell-qc](../xenium-cell-qc/SKILL.md) |
| Check an existing cell-type annotation (collaborator or project labels) against the data: which labels, groups and cells it supports and why | [xenium-annotation-qc](../xenium-annotation-qc/SKILL.md) |
| Summarize cell-type composition, or fit an eligible two-group sccomp comparison | [xenium-composition](../xenium-composition/SKILL.md) |
| Analyze local spatial niches and eligible differential enrichment with QUICHE | [xenium-quiche](../xenium-quiche/SKILL.md) |
| Generate or revise script-rendered scientific figures and finalize exports | [xenium-figures](../xenium-figures/SKILL.md) |
| Write scientific narratives or assemble DOCX/PDF reports and PPTX decks from finalized figures | [xenium-reporting](../xenium-reporting/SKILL.md) |

When the user is unsure where to begin or which project/path to use, follow the setup
module's discovery and guidance checklist. Use available project context to explain
options before asking them to supply a path. Analysis input checking stays within the
supplied package; intake compares only the receiving and source locations in scope.
Intake, analysis input checking and quality checking accept native outputs or curated
exports. Combine them according to the question: receipt completeness, object meaning,
then descriptive metrics as needed. Reuse existing evidence; none requires the others
to finish first, and a partial delivery can support a useful overview. Quality checking
describes the supplied data; selecting or applying filtering rules belongs to cell QC.

QC spans several modules; each stage answers one question and passes flags, not
deletions, to the next:

| Stage | Question | Module |
|---|---|---|
| Delivery | Are the expected runs and files present and intact? | data intake |
| Input | What do the objects mean, and does every cell join to a native cell and group? | analysis input check |
| Descriptive | How deep and complete is each run, region and group; which stand out between runs? | quality check |
| Before clustering | Which cells carry too little or artefactual signal, and which groups failed as a whole? | cell QC stage 1 |
| After clustering | Which low-information cells can be labelled, and at what level? | cell QC stages 2-3 |
| Downstream | Do compositions, contrasts and contamination estimates depend on the QC choice? | cell QC stages 4-5 |
| After annotation | Which labels does the data support, and are any defined by depth, foreign or single genes? | annotation QC |

Segmentation and image QC have no module yet; handle them directly and treat
segmentation-dependent corrections as sensitivity analyses.

Route to modules included in this skill set using the relative links above; read
their bundled instructions even when only the router is registered with the agent.
For a requested analysis without a bundled module, explain that coverage and handle
the request directly within its authorized scope. Add analysis routes as modules
are included in this set.

## Carry the requested outcome through

Track the user's final deliverables separately from the current module's output.
When skill development is inserted into a data/report task, preserve both accepted
deliverables and use the updated skills for the remaining work. A completed skill
or metric table does not finish a requested PPTX.

Keep metric checking, figure production and report assembly as distinct tasks.
Quality checking supplies evidence; figures supplies final script-rendered artwork;
reporting directly uses those exports. A report may select and place existing figures
but returns figure changes to the separate plotting task. Reuse completed inputs
instead of running each stage again by default.

Keep project documentation concise, without timestamp boilerplate. Give each document
one owning question; link to its owner rather than copying changing facts.
Project-local instructions should point to current work, input locations, execution
commands and evidence. Package-specific findings belong to the project, not these skills.
