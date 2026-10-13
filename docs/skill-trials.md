# Skill behavior trials

Each entry identifies its evidence: static review, isolated behavioral trials,
synthetic execution or live checks. Success at one level does not establish success
at the others.

## Setup with no chosen project

Request: “BioHPC. Do a setup; I don't know which project or directory to use.”

Fixture: verified account; two projects under a readable lab-owned shared root;
a writable owned work root; no project selected; quota and scheduler eligibility
unknown. No literal paths or project purposes were supplied.

Observed: the agent presented a table of options and their known roles, proposed an
owned workspace, and identified shallow project-document inspection as the next step
before asking the user to choose. It did not invent project purposes, paths or compute
eligibility. Its action outline saved unresolved choices to the canonical profile,
read it back and stopped after setup. No installation or job was proposed.

Limit: the simulated action outline did not actually persist or reload a profile.

## Custom processed package

Request: “Check this custom Xenium package to see what I can pick up next; no analysis
chosen.”

Fixture: README plus H5AD; documented log-normalized X and scaled layer with negative
values; cell IDs unique within core but reused across cores; consistent labels and
group metadata; no tumor/animal mapping. Coordinates aligned, finite, varying in both
axes and documented as core-local micrometers; core coordinate ranges overlap. No
raw counts, transcripts, images, masks, controls, native QC or software version.

Observed: the agent treated this as a processed handoff. It accepted negative scaled
values and overlapping local frames, used core plus cell ID as the join key, and kept
future spatial graphs within cores. It reported missing biological replication mapping
as a limit on group comparisons. Missing upstream files were not treated as package
defects. Remaining checks stayed inside README/H5AD, without reannotation or analysis.
It distinguished supplied findings from checks not actually performed.

Limit: no H5AD was opened, no graph or plot was built and no readiness conclusion about
any real package follows from this trial. Real-world performance remains to be tested.

## Structural verification

YAML parsed successfully for all three skill entry points; names match directories
and descriptions are present. Repository-relative Markdown links resolve, active Codex
links resolve to this checkout, and git diff whitespace checks pass. The bundled Python
quick validator could not run because PyYAML was unavailable; YAML parsing used Ruby's
standard YAML library instead. No dependencies were installed for these checks.

## Router entry: profile before project recommendation

Regression request: “$xenium-workflow what we do first”. Prior setup trials began
inside setup and did not establish that the router reads a profile before selecting
a project. This trial used the exact entry request and a deployed symlink into an
isolated canonical skill tree. The independent agent had no parent conversation.

- Missing-profile fixture: the canonical setup directory had no profile, while the
  project overview named a historical project priority. The agent checked profile
  absence before reading setup and project context, then recommended orientation and
  requested the missing connection detail. It did not start package inspection.
- Saved-profile fixture: the profile selected a different project and owned workspace
  from the historical overview. The agent read the canonical sibling profile before
  the overview, stated saved settings and unresolved quota/retention, and recommended
  input checking for the saved project. It asked for the missing package path without
  repeating setup or treating unrelated unknowns as blockers.

Both cases were read-only simulations with synthetic identities and directories.
File-read order was observed; no real connection, persistence or package check was
performed. Structural YAML/link checks passed, and the active local router resolves
to the canonical checkout with an existing sibling profile.

## Self-contained skill set

Development references are not runtime dependencies. The router now selects modules
bundled in this set instead of any matching installed skill. README records the
sibling-directory requirement; repository authoring guidance preserves that boundary.

Verification copied the skill directories into an isolated temporary location without
the private profile. All six local Markdown references resolved within that copy;
no author-specific paths or external skill references were found. YAML and whitespace
checks passed, and all three active Codex links resolve to this checkout. This is a
structural portability check, not an independent agent trial or live BioHPC run.

## Saved profile: settled choices at workflow entry

Migrated the private profile to the fixed template and recorded the user's selected
project/workspace, active-versus-archive storage roles and modules-first strategy.
Readback confirmed all template sections and checklist rows; the profile remains
Git-ignored. Exact runtime and job settings remain task-specific checks.

Independent read-only trial request: "$xenium-workflow what do we do first".
The agent received an isolated copy of the bundled skills and saved profile, with
no conversation history. Files read in order: router, sibling profile, input-check
module. It recommended the selected package's input check, distinguished a selected
workspace from a created directory, and reused the software strategy. It did not
repeat settled setup questions, connect to a server, install software or inspect data.
It explicitly distinguished saved settings from current verification.

The entry behavior passed this simulated case. This does not verify server access,
package readiness or successful job execution. Personal paths and identity details
are kept in the ignored profile rather than these shared trial notes.

## Profile format and state consistency

Static walkthrough of the setup instructions, template and private saved profile:
- A selected package has a dedicated optional field preserving its literal path.
  Setup without a selected package can record “not yet selected” and continue.
- Proposed choices remain pending; confirmed settings are distinct from activation,
  import and job verification. The template owns the state definitions.
- Saved project and software choices precede discovery evidence; the owned workspace
  path is recorded once. Reusable entry behavior remains in the skill instructions.

Readback verified template section order and table-row coverage in the private
profile. Local Markdown links, skill YAML frontmatter and whitespace checks passed.
This was a static walkthrough, not an independent agent trial or server validation.

## Reusable H5AD checker

Added a parameterized read-only checker with metadata/full scan modes, explicit
count-layer and specimen/ID/mapping selection, runtime inventory and optional
AnnData compatibility. Paths and package-specific fields are supplied as arguments.

Synthetic dense, CSR and CSC fixtures passed checks for empty rows, negative and
fractional values, duplicate IDs within specimen scope, nonfinite coordinates,
repeated local coordinates, null HDF5 metadata and malformed sparse pointers.
Run `python tests/test_check_h5ad.py` with h5py and NumPy installed.

A live selected-package run completed on allocated BioHPC compute, including full
expression scans. Existing module libraries supported targeted checks. A shared
runtime failed while importing AnnData through a CuPy/CUDA dependency chain, before
reading the file. The user then selected an owned module-plus-uv runtime. Full
scans, synthetic fixtures and AnnData reading succeeded there. Optional reader
failures are included in errors and cause a nonzero checker exit; runtime checks
verify imports, not just installed-version metadata. Project-local scripts, JSON, mapping evidence and the
Markdown report hold the private findings. Two preliminary inventory failures
(script-name shadowing and null-dataset handling) were superseded by successful
checks; null-dataset and reader-failure cases are covered by the reusable fixture.
A personal-module activation-order issue was corrected by loading the base Python
module explicitly before the personal module; the final run used the owned venv.

Limits: this is one real H5AD plus small synthetic fixtures, not universal format
coverage. Biological provenance, units, cross-file joins and sparse duplicate entries
remain interpretation or targeted-check responsibilities. Squidpy was inventoried
but not needed or executed. Syntax, local links and whitespace checks passed.

## Xenium-only setup trigger

Renamed the setup module to `xenium-biohpc-setup`. Its description requires Xenium
setup context or routing from `xenium-workflow`; general BioHPC administration and
other research workflows are outside scope. Static trigger walkthrough: “set up
Xenium on BioHPC” and the router's setup branch reach it; “check my BioHPC quota”
without Xenium context and “set up an RNA-seq environment” do not. These are intended
branches, not an independent model-invocation test. Canonical deployment, relative
links, frontmatter names and profile Git exclusion were verified; the old broad
deployment was removed and the private profile retained.

## Sender-owned delivery evidence

Static walkthrough: a sender report covering fewer cores/cells than the delivered
object is recorded as subset evidence, not full-delivery validation. Missing spatial
coordinates produce a concrete sender export/join-evidence request when spatial use
is intended. An expression-only handoff does not acquire a raw-image requirement.
Exact-file evidence can be reused after identity and coverage verification, while
missing essential checks remain explicit. Searching neighboring directories or
reconstructing a delivery requires a separate user request. This is a documentation
walkthrough, not an independent agent trial. Project-specific paths and findings
remain in the project handoff note.

## Interactive compute continuity

Static walkthrough: iterative data inspection follows the saved preference for one
bounded interactive allocation; the shell's compute hostname and live allocation
are verified before Python/R checks. A disconnected or expired session requires
state verification and re-entry, not a login-node fallback. Unattended checks use
batch jobs. An orientation-only request records the preference without allocating
resources. These are reviewed instruction paths, not a completed interactive-session
trial; the prior live verification used batch jobs.


## Input-check evidence selection and direct entry

Revised the input-check entry and report template without adding a module, runtime
script or configuration field. Check selection now follows exact-file evidence
coverage; equivalent sender-tool evidence is usable, and absent evidence does not
prevent essential inspection. Direct execution reads the canonical sibling profile
and reaches the existing compute/runtime guide. The final reply leads with data
uses and limits; reports retain flexible prose/tables, actionable unknowns and
linked reproduction evidence.

Compared the pre-edit working copy with the revision in four paired offline trials,
one independent agent per version per fixture. The baseline included the existing
uncommitted sender-acceptance and compute-continuity rules; it was not the older Git
commit. Synthetic sibling profiles supplied an owned environment, output directory
and allocation preferences. No real identity, package path or allocation was used.

| Fixture | Observed comparison |
|---|---|
| Exact-file sender evidence covers all essential checks; recipient identity/read checks already recorded | Both versions reused the evidence without a redundant full scan, accepted the sender's validator and preserved annotation-validity limits |
| Current 12-core delivery lacks coordinates; old coordinate report covers 10 cores | Both versions distinguished cohort coverage from data loss, reported spatial/replicate limits and drafted a consolidated request without searching upstream |
| No sender report or analysis plan; coordinates and replicate fields uninspected | Both versions proposed missing checks without treating unknown fields as absent; only the revision read the saved profile and bundled runtime guide |
| Direct invocation from a login shell, with either a valid saved allocation or an ended allocation plus another suitable live one | Both versions selected suitable live compute before imports/data reads; only the revision read the saved configuration, avoiding questions about environment/module/output choices already recorded there |

Final replies were data-led in the first three paired fixtures. In the direct-entry
fixture, the baseline led with artifact/runtime status while the revision led with
the package's usable entry points and unverified properties. This is a qualitative
observation, not a separately scored post-hoc assertion.

Limits: fixtures supplied simulated tool results; agents wrote reports and ordered
proposed actions. These trials did not execute Slurm attachment, verify actual shell
continuity, read H5ADs or test analysis validity. One run per version per fixture
cannot establish repeatability or a general performance gain. Token/duration metrics
were unavailable. File-read assertions establish retrieval behavior; in the
no-sender-report case the fixture already supplied enough runtime information for
the baseline's proposed execution, so the missed profile read alone did not prove
an incorrect compute choice. In the direct-entry case, the missed read did produce
avoidable unresolved configuration.

Structural verification covered skill YAML names/descriptions, bundled relative
links, active canonical deployment and whitespace. Existing checker code and its
numerical behavior were unchanged by this revision.


## CLI evidence and report serialization

A review after the first multi-core source comparison distinguished project checks
from reusable skill verification. Core-specific ID prefixes, cohort counts, QC
thresholds and coordinate transforms remain in the project. Existing profile,
package-scope and compute-selection trials above remain the behavioral evidence;
this change adds no workflow module or verification skill.

The existing function-level synthetic suite passed. New CLI regressions invoke
`check_h5ad.py` through subprocesses with hand-checkable HDF5 fixtures:

| Recipe | Observable expectation |
|---|---|
| Metadata / full scan | Default output omits unscanned matrix-value statistics; full scan finds the known zero row, negative and fractional entry. Missing spatial data remains explicit, and specimen-scoped IDs are distinguished from global duplicates |
| Output protection | Input, symlink to input and an existing report are preserved when rejected |
| Invalid sparse structure | Exit 2 and complete parseable error evidence |
| Runtime import / simulated import failure | Import success is observed; injected import failure returns 2 with a failed import record |
| Simulated AnnData reader failure | Exit 2 with the reader error preserved in complete JSON |
| Nonfinite metadata | NaN and both infinities in small uns datasets and attributes retain explicit tagged values in strict JSON; HDF5 null remains null |
| Unsupported metadata | Serialization failure returns nonzero without creating a partial report |

Before the repair, a new nonfinite-metadata CLI regression failed with a truncated
JSON report. An independent reproduction also observed this with scalar uns NaN,
uns positive infinity and a negative-infinity attribute; a finite-value control
succeeded. The checker now represents those scalars as `{"nonfinite":"NaN"}`,
`{"nonfinite":"Infinity"}` or `{"nonfinite":"-Infinity"}`, including nested arrays.
It completes JSON serialization before exclusively creating the output, so an
unsupported value cannot leave a partially serialized report. This is not a claim
of atomic publication under disk or process failure.

After repair, all seven CLI tests and the existing dense/CSR/CSC function-level
suite passed. Synthetic inputs are opened read-only and preservation is checked
by direct byte comparison; no checksum procedure was added. Temporary fixtures
are cleaned by the test runner. Run both commands in the repository's
[verification instructions](../AGENTS.md#verification) to reproduce the checks.

Execution used an existing local Python 3.12.14 environment with NumPy and h5py;
no dependencies were installed and no BioHPC job or research-data check was run.
The AnnData and import-failure cases replace only their dependency boundary; they
do not prove real AnnData compatibility. No new independent agent-behavior trial
was run, and a successful CLI exit remains evidence of execution rather than a
package-readiness verdict.

## Composition and QUICHE routing

Representative requests now reach bundled analysis owners from the router. A prepared
H5AD plus core and annotation fields selects composition; missing coordinates do not
block its descriptive branch. Missing confirmed biological-subject IDs stop formal
comparisons. A local-niche request selects QUICHE and requires explicit spatial
units/frame and independent FOV boundaries. Generic BioHPC administration remains
outside the Xenium setup trigger.

Verification uses the actual count CLI and QUICHE adapter, with hand-defined counts
and neighborhoods, source preservation and deliberate invalid inputs. The consuming
project owns its pinned-runtime R/Stan and real-QUICHE execution evidence; package
imports and skipped opt-in tests are not method passes. Skill source, portable
contracts and tests are bundled here; project identities, input paths, result tables
and runtime reservations remain in the consuming project/profile.

## Results writing across completed analyses

A consuming project's combined composition and local-neighborhood report exercised
this writing route with saved outputs: descriptive fractions, compositional model
estimates, local fractions and sampling-sensitive neighborhood selections. The
report preserves their different scales, separates weighting from membership
sensitivity, and moves reading instructions from artwork to captions. The existing
DOCX builder completed after native narrative/table updates and a report-sized
neighborhood export; no model rerun or repeated document inspection was used.

Peer consultations informed the writing principles using fictional examples, not
the project's private results. One peer invented a parameter scale in its draft;
that wording was rejected. This is a documented application of the skill, not an
independent benchmark of agent behavior or new scientific validation.


## Report planning and scientific writing instructions

The existing scientific-figures skill was revised against matched writing tasks:
a collaborator report from saved multi-analysis outputs, and a clearly fictional
annotation comparison with high overall agreement and concentrated disagreement.
Fresh agents used identical source packets and requests with the saved original,
first revision or second revision. No production report, analysis or document
build was run. Trial materials remain with the consuming project, outside the
skill package.

The first revision did not establish an overall improvement. Its text-only writer
missed the report reference, produced a long unsectioned account and imported an
irrelevant biological-transition caveat into the fictional example. The second
revision explicitly routes all reports to structure guidance, organizes that
guidance around reader questions and synthesis, and replaces generic caveats with
qualifications relevant to the comparison. Its writer read the intended reference.

An independent anonymized comparison found stronger orientation, connected
findings and synthesis in the real-data report. The short fictional account had
mixed results; the original reached its central observation sooner. Dense
statistical prose and local repetition remained. These are local qualitative
observations from one run per version and case, not a demonstrated stable win rate.
The final revision consolidates report planning and refines existing clauses for
result connections, numerical detail and timely qualifications. A further fresh
trial on the same inputs put shared model context earlier and reduced a long
coefficient inventory, while retaining some dense scope and potentially
dispensable explanation. This targeted trial does not establish a uniform
concision gain.

An independent reviewing model assessed the instructions and document-level
organization. Its anonymous draft comparison preferred the revised long report but
the original short account's immediate task focus. Its advice informed the revision;
agreement was not treated as behavioral proof. Primary writing references support
reader context and logical development, adapted here to exploratory collaborator
reports rather than a mandatory manuscript structure.

Portable skill metadata, bundled links and whitespace checks passed. Archived
source packets were identical and draft links resolved. The builder and shared
style asset were unchanged by direct byte comparison. No checksum step, software
installation, server action, Word inspection or scientific revalidation was added.


## Data intake and analysis-input migration

Added `xenium-data-intake` for delivery agreements and source/recipient evidence,
and renamed the object-level skill to `xenium-analysis-input-check`. The existing
checker and biological reference were preserved, including pre-existing uncommitted
checker work. The old active name was withdrawn only after the new deployed entries
and their resources resolved correctly; its library entry was reversibly retired.

Four fresh isolated trials executed real checks on small synthetic inputs. They
covered equal-count/equal-size path differences, matrix-label and QC-mask confusion,
source-versus-recipient gaps, scoped joins, normalized/scaled semantics, explicit and
unknown delivery scope, promised specimens/MEX versus a useful H5AD subset, a readable
H5 container without an expression matrix, and contradictory scope claims with partial
source observations. Candidate agents did not receive the coordinator's expected
answers. Reports, commands, criteria and limits are in the
[execution evidence](evidence/data-intake/README.md).

All 10 new inventory tests, the existing dense/CSR/CSC suite and seven H5AD CLI
regressions passed. An independent review found an invalid ancestor-path manifest
case; it was repaired and regression-tested. YAML, repository links, changed Python
syntax and whitespace checks passed. The generic single-skill validator rejects
sibling-module references by design; repository-level link validation covers this
bundled topology, and a generic-validator pass is not claimed.

These are one-run synthetic trials and local deployment checks, not repeated model
benchmarks or research-data validation. Cloud placeholder behavior, remote permissions,
BioHPC execution and real AnnData compatibility were not exercised. No local hashes,
transfers, repair, downstream analysis or outgoing messages were performed. Full
scope/enumeration and read-depth limits remain explicit in the archived reports.


## Descriptive Xenium quality check

Added `xenium-quality-check` for dataset overviews and basic descriptive metrics,
with intake, input semantics and figure styling kept with their existing owners.
The new router entry and README resolve to the bundled module. No standalone
deployment was performed.

A fresh-context trial preserved exact summary values, metric populations, unknown
sample mapping and missing-value coverage without introducing filters or a global
quality verdict. A fixture ambiguity prevented testing an explicit all-cell label;
the candidate appropriately recorded uncertainty. Inputs, outputs, predeclared
criteria and limits are in the [trial record](evidence/quality-check/README.md).
Metadata, changed repository links and whitespace checks passed. This one synthetic
case does not establish raw-data extraction or BioHPC execution reliability.


## Quality check, figures and reporting

Expanded the descriptive check to cover scale, usable inputs, cell signal, native
Q20/assignment, and separate controls/alerts. Split the former combined skill into
`xenium-figures` and `xenium-reporting`. Figures own Python/R rendering and final
exports; reporting consumes those files unchanged. The router carries the requested
final deliverable through module and skill-development work.

A fresh-context agent applied the check to a consuming project's saved evidence.
It produced a regional metric table, field definitions/coverage, observations and a
reproducible extractor, with missing values and different cell populations kept
separate. No new raw-data scan, filtering or biological explanation was introduced.
The project then received its requested four-slide PPTX with English text and
Chinese notes. Both inserted scientific figures matched the declared final PNGs
byte for byte, with no chart reconstruction or cropping. Every final slide was
rendered and inspected. This was not a PowerPoint application test.

DOCX preservation used another consuming project's existing production verifier:
the moved builder produced the native text/table/caption report, and image bytes,
PDF pixels, actual Arial embedding and direct conversion provenance passed. Both
missing-source and missing-column failure cases passed. No new Word visual review
was performed. The shared style was unchanged by direct byte comparison; the
builder changed only its default style path. Seven composition plotting tests
passed using the new default path.

Metadata, repository links, compatibility symlinks and whitespace checks passed.
The generic validator rejects legal sibling-module references, so no generic
validator pass is claimed. Detailed criteria, commands and production receipts
remain with the consuming project; research results were not copied into this
skill repository. These are scoped production/trial observations, not an old/new
performance benchmark. No standalone deployment or checksum step was performed.


## Audience-led presentation content

The reporting presentation branch now uses audience needs and project/QC evidence
to choose content before assembly. When available, an independent agent contributes
the initial outline and then challenges the selected content. This is broader than
reviewing an already fixed deck. Consequential answers and unknowns belong visibly
on slides; lower-priority details belong in a Q&A companion. Speaker notes default
to brief English cues, with source citations separated.

In one consuming-project application, a fresh-context agent proposed an eight-slide,
15-minute account from saved project evidence. The author checked the proposal,
selected its structure and incorporated a second challenge concerning metric
denominators, coverage, alert wording and received-versus-reported modality data.
The final PPTX contains three or four English cues per slide (22–39 words), two
unchanged final PNGs and native summary tables. Added displayed metric values,
image bytes, cue content, package/layout and slide renders were checked. The earlier
four-slide deliverables were preserved.

The planning proposal, challenge and decisions remain with the project. This is a
scoped application, not a controlled improvement benchmark or a PowerPoint app test.
The generic validator still rejects two legal sibling-module links; their targets
resolve in the bundle. Frontmatter, affected links and whitespace were checked.
No scientific reanalysis, new plotting, DOCX-builder change or deployment was needed.

## Evidence-led presentation argument

Failure observed in a prior audience-planned deck: topic headings and a catalog of
metrics left the main answer implicit. Research distinguished primary Minto and
academic guidance, an external skill's design suggestions, and anecdotal user
feedback on AI-generated slides; sources and adaptation limits are in [presentation design](presentation-design.md).

A fresh-context independent planner received the revised reporting branch and a
real project's saved request context, input-check summaries and finalized figure
captions. It did not receive the previous deck, author outline or expected answer. It produced a central audience question, a bounded descriptive
answer, timed claim/evidence sequence, visible unknowns and short English cues.
It preserved matrix-versus-summary coverage and biological-unit uncertainty,
left final plots intact and did not propose filtering or biological conclusions.

The author merged two repetitive qualification pages into the evidence they
qualified and kept threshold/control detail in Q&A. The independent follow-up
challenge caught overbroad missing-file wording, ambiguity about a range of
regional medians and the scope of retained cells; these were corrected before
export. This trial demonstrates content planning in this case, not autonomous
end-to-end deck production or comparative improvement over the old skill.

The resulting parent-built eight-page presentation retained the final figures
unchanged and short English cues. Package/layout, source-value and figure-byte
checks plus rendered inspection cover the revised artifact; planned timing is not
a rehearsal or a PowerPoint application test. No raw analysis or checksum run was
needed. Trial artifacts remain in the consuming project.

Frontmatter and repository-relative links resolve; `git diff --check` passes.
The generic single-package validator reports three links outside the skill root:
two intentional sibling-module resources and the optional repository design note.
These resolve within this repository; the validator does not support its skill-set
topology. No installation, release, DOCX rebuild or unchanged-analysis tests were run.

## Whole-talk narrative before pagination

A subsequent user correction identified local optimization: whole-talk requirements
were becoming a per-slide form. The presentation branch now develops a continuous
account first, allocates coverage across the talk and reviews the listener's
resulting understanding before individual claims. The close follows the meeting
purpose; a descriptive briefing can end with a brief outlook.

In a scoped fresh-context trial, the planner read the revised branch and the
project's saved evidence. It wrote a connected account before a timed outline,
distinguished an initial subset from missing files inside received regions, and
reserved explicit time for the two existing figures. It kept
operational details and supplemental metrics outside the main account. The parent
separated storage from data scale, reduced the closing and asked the planner to
challenge the selected nine-page account. The challenge identified potential
confusion about cohort scope, biological replication and alert/flag meaning.

The final parent-built PPTX has a topic cover and rationale-first account, two
unchanged figure exports, brief English cues and one short outlook page. Source
values, coverage, notes, image bytes/aspect ratios, package/layout and page renders
passed the affected checks. No new raw analysis, checksum verification or storage
policy check was performed. Storage assurance follows explicit user confirmation.
The proposal, selected account, challenge and production receipt remain in the
consuming project.

This demonstrates the content-planning behavior in one case, not an old/new
performance comparison, autonomous end-to-end production, rehearsed timing or
PowerPoint application testing. Frontmatter, affected repository links and
whitespace checks pass. The generic validator retains its three outside-package
link findings for intentional, resolving skill-set/repository references. No
installation, release or unchanged-analysis testing was needed.


## Reproducible template assembly

A supplied-template request exposed another gap: adapting the finished deck with
project-specific rendering code would leave the skill unable to repeat the work.
The template branch now imports a retained native PPTX using a project-owned role
profile and ordered content JSON. Runtime paths and institutional assets remain in
the consuming project; the canonical builder owns assembly, validation and export.
Template-only changes preserve approved narrative decisions and finalized figures.

An independent agent implemented a generic package/content verifier from the input
contract. Its bounded trial passed two valid controls (including multiline table
content), rejected eighteen targeted mutations, and protected inputs from report
overwrite. The parent exercised it through the real project entry command: two builds
from the same content, profile, figures and pinned runtime passed content, notes,
native-table, figure, package and layout checks. All nine rendered page PNGs and
speaker cues compared equal by direct bytes. The original template remained
unchanged. Missing-figure and existing-output cases stopped without producing a
replacement deliverable. These checks cover the observed rebuild behavior, not
PPTX ZIP byte identity or portability across presentation engines.

All initial pages were visually reviewed against the template. The source cover's
embedded preview exposed an import color discrepancy, resolved explicitly in the
profile. A native table-border correction was made in the builder and its affected
pages re-inspected. The final PPTX was generated through the saved project command;
no manual editing of the delivered file was needed. Receipts and input snapshots
remain with the project, outside the reusable skill.

No new scientific analysis, plot generation, checksum calculation or PowerPoint
application test was performed. Planned speaking time remains unrehearsed. This
is one real template application and a second-run comparison, not an old/new
performance benchmark. Registration and deployment remain separate from authoring.


## Completed-check progress briefings

User review found that a prior deck overemphasized general rationale, used
conclusion titles for navigation and scattered abstract qualifications through
results. It also reduced the data-sharing context to a defined subset and omitted
the details a sender would need to locate missing files. The presentation branch
now keeps data-status briefings about completed checks, with concrete sharing
context, subject/activity titles and actionable missing-file details. Needed
explanations accompany their evidence; requests and future work go to next steps.

A real revision followed the user-approved eight-page outline. An independent
reviewer read the revised guidance, content and original project evidence, then
challenged the account without replacing the approved structure. It identified
one substantive error: an existing recovery request was phrased as a new request.
The parent checked the project record and corrected the page to follow-up. No other
material content defect was found; this is a scoped review, not a comparative
performance result.

The project content was rebuilt through the unchanged canonical template builder.
Content, notes, tables, figure bytes, package and layout checks passed. Revised
content pages were rendered and visually inspected; the unchanged cover compared
equal to its previously reviewed render. Final scientific figures were preserved.
No raw analysis, new QC thresholds, checksum calculation or PowerPoint application
test occurred. The brief, review, prior content and production receipts remain in
the consuming project. Frontmatter, affected repository links and whitespace pass;
the generic single-package validator retains its three known, resolving external
skill-set/repository link findings. No deployment or release was performed.


## General cell-information overview

A further user correction showed that technical regional scatterplots did not
answer what listeners should notice about the data. Reporting guidance now chooses
recognizable overview questions and displays a concrete observation beside the
figure even with a subject title. The quality-check aggregation rule explicitly
requires cell values or exact frequencies for a pooled cell median/distribution.

The consuming project generated exact cell-weighted histograms from cell tables
and available H5 matrices, preserving separate coverage. BioHPC connection attempts
failed; the retained local copy was used read-only in the locked project runtime.
Source-region counts, prior medians and per-cell matrix/table gene counts matched.
Small fixtures exercised unequal group sizes, zeros, controls, chunk boundaries
and invalid counts. A fresh independent reviewer recomputed pooled counts and
quantiles from the saved histograms and found no numerical defect; its population
wording correction was retained in separate figure panels.

A standalone Python figure presents count-range percentages, medians and central
50% ranges. Bin totals conserve the populations; PDF fonts, dimensions and SVG
text checks passed, and the figure and affected PPT pages were inspected. The
canonical presentation builder produced the requested deck; earlier technical
plots remain supporting material. No sample exclusion, acceptance threshold,
checksum, server-side run or PowerPoint application test is claimed. This is a
scoped application, not evidence that the selected summaries establish overall
sample quality. Scripts, methods, histogram evidence and review remain with the
project. Affected links/frontmatter and whitespace checks pass.

## Presentation revision consolidation

Reviewed recent Claude Code and Codex session JSONL, retrieved relevant passages
through memory search, and compared the existing presentation guidance with an
uncommitted working copy used during slide production. Read the project content
generator, rebuild entry, delivery/source instructions and the bundled template
builder. Private transcripts, project artifacts and source paths remain outside
this public repository.

The user corrections support preserving the agreed main thread, explaining the
audience's missing premises, reducing reading load across text and figures,
applying general corrections throughout a deck, removing defensive footnotes, and
checking the actual rendered revision. The working copy also supplied the slide-text
branch and notes-removal utility. Its automatic figure-approval gate, compulsory
number registry and universal removal of method scores were not retained. Project
examples, exact typography and filenames remain project choices.

**Behavioral walkthrough (author self-review).** Starting at README and the reporting
skill, traced these requests through the revised branch:

- Revise a teaching deck whose local example has displaced its purpose: recover the
  approved brief, inspect transitions and display selection, and check audience
  understanding separately from claim accuracy.
- Correct one overloaded page: identify whether the correction generalizes, inspect
  all matching pages, retain meaningful qualifications in claims/displays, and review
  full-size renders after updating the owning source.
- Change only a template: reuse approved content and use the existing rebuild route.
- Produce a sharing edition: choose its pages in the content source, preserve the
  presenter build, remove notes into a new file, and retain visible interpretive
  context. The sharing script does not remove appendix slides.

**Script check.** `tests/test_share_copy.py` ran in an existing python-pptx runtime on
a disposable PPTX containing text, a native table, an image and speaker notes. The
CLI removed note parts, set author/title properties, preserved slide XML, image and
layout/master bytes and the original file, and refused an existing destination.
No checksums were calculated.

**Limits.** This is a retrospective consolidation and a self-reviewed instruction
walkthrough, not a fresh-agent comprehension trial or an old/new benchmark. The
synthetic sharing check does not establish preservation of every advanced PowerPoint
feature. No research analysis, new deck rendering or native PowerPoint test was run.
The separate working checkout was read without modifying its uncommitted edits.

Subsequent source review covered the later collaboration-meeting JSONL and project
records on the working machine. Direct corrections called for rebriefing after a
partner analysis changed the presenter's expected role, removing unagreed grant-level
plans, distinguishing tool capability from actual use, and explaining mismatched
inventory populations. A formatting complaint remained unresolved after XML-only
inspection. These findings added scoped guidance and an explicit limit on editability
claims. Final deliverable discovery also found a later manually saved file beyond
the numbered builds; version suffixes alone did not identify the final deck.

A fresh-context skill reviewer, without the final decks, checked the revised route
against criteria from these corrections. It identified two cross-branch conflicts:
shared writing guidance fixed the audience/language to biological collaborators and
English, and method examples unconditionally required a population distribution.
The first now follows the agreed brief, with a biological-results default only when
needed; the second applies when an observation represents a larger dataset. The
reviewer rechecked both repairs and found the route ready for a production trial.
Explanatory-diagram editability remained a non-blocking observation for that trial.

## Independent presentation production

After the instruction review above, a fresh-context author received a frozen skill
snapshot, the original teaching brief, a native template and selected source evidence.
It did not receive the finished reference deck, refinement history or review criteria.
It produced a 22-page presenter deck with English cues, a notes-free sharing copy,
source files, final figures, full-page renders and a contact sheet. Planned duration
was about 29 minutes; no rehearsal measured it. Content, package and geometry checks
passed. The author inspected every page of the first build and the four changed pages
of its final build; the other rendered pages were unchanged. The output was frozen
before comparative feedback.

Two further fresh-context reviewers received neutrally labelled decks, the brief,
criteria and evidence, without an identity key or each other's conclusions. The
audience reviewer inspected all 22 candidate pages and all 19 reference main-talk
pages, with the reference's four appendices reviewed separately. The claims reviewer
traced consequential statements to the supplied records and official sources.

The candidate better connected the recurring task, environment failures, cross-session
handoff and maintenance, and preserved the limits of its local trial evidence. The
reference better showed concrete instruction and script examples and used a stable,
progressively highlighted architecture diagram. The candidate's abstract construction
pages lacked an excerpt listeners could adapt. The reference omitted the requested
speaking cues and compressed some local trial, assay and caching claims beyond what
their sources support. Neither deck was treated as an infallible answer key.

Author adjudication also found internal source paths in candidate footers despite the
existing slide-text rule, and explanatory sentences embedded in diagram images. These
are execution or editability limitations, not evidence that more duplicate rules are
needed. The instruction repair is limited to showing a small worked artifact when
teaching construction. That post-trial wording did not produce the frozen candidate;
its effect has not been tested in another generation. The reference deck was unchanged.

This is partial transmission of the revision lessons, not demonstrated parity with
the finished reference. It is one production task, with separate contexts from the
same model family, not independent model families or an old/new controlled trial.
The reference benefited from repeated human feedback and additional project context.
The skill itself was informed by that project's feedback, so this is not held-out
generalization. No native PowerPoint editing, audience comprehension experiment,
live research analysis or timed delivery was tested. Private decks, raw history and
detailed comparison reports remain in the consuming project.

### Follow-up: recurring writing failures

The user challenged treating repeated violations solely as execution failures.
Re-read the original technical-talk requests and later direct corrections, then
compared them with the frozen candidate's text, diagrams and authoring brief. The
brief conveyed the initial purpose but omitted later accepted visual and closing
choices. The revised production branch now carries those decisions into new-session
briefs and makes the accepted-correction review part of delivery. The slide-text
branch specifies concrete wording and explicit destinations for internal provenance.

**Editorial walkthrough, not a new generation:**

| Observed case | Action under the revised instructions | Evidence needed to close it |
|---|---|---|
| Internal repository paths repeatedly appear in source footers | Move internal provenance to notes/source records; leave only necessary direct URLs visible | Inspect every affected rendered footer, including image text |
| Script construction is shown as generic project/script/check stages | Show a small source-backed command or output contract and the decision it implements | A listener can locate what to adapt, not only name the stages |
| A page says different information needs different homes | Name the information, storage decision and practical consequence | Wording and display explain how the next session continues |
| Multiple tables classify checks, limits and responsibilities | Keep comparisons whose dimensions serve the audience question; move secondary explanations to cues or split the account | Read the displayed labels while following the cues; preserve necessary claim scope |
| A fresh author returns to a general advice ending after a later closing choice | Recover the latest accepted closing choice into the brief | The final sequence and correction record account for that choice |

The walkthrough locates failures in existing artifacts and specifies their repairs;
it does not claim that a fresh agent followed the new wording. No frozen deck or
earlier trial input was changed. Repository link, frontmatter, privacy and whitespace
checks cover the edited guidance, not comprehension or PowerPoint behavior.

### Second independent production

A new-context author repeated the technical-talk task with the revised instructions
and a brief carrying the later accepted visual and closing decisions. It received
the original template and source evidence, with prior reporting-trial conclusions
removed from supporting documents. It did not see earlier decks or reviewers' findings.
It produced and froze a 24-page presenter deck, a notes-free sharing edition, cues,
source files, full renders and a correction-to-page record. Planned duration was
about 28 minutes, not rehearsed. The author reviewed all pages and rechecked changes;
content, package and layout checks passed.

Two fresh-context reviewers compared this output with the prior independent draft
and the finished reference under neutral labels, without the identity key or each
other's findings. They found more concrete instruction, command and handoff examples,
a continuous architecture diagram with the execution foundation visible, internal
provenance moved out of footers, native slide explanations and the agreed project
closing. The audience reviewer preferred this output as the basis for further work,
while retaining a reading-load concern for several consecutive tables. The reference's
skill-file example remained more direct.

Both reviewers independently found the same remaining scope error: a closing path
made a final figure an obligatory step between metric evidence and the report,
although the source task requires figures only when requested. The frozen output
retains this finding; an optional figure branch is the specific proposed repair.
The author's completed correction checklist did not detect it. Sharing checks found
no notes, equivalent normalized slide XML and preserved media; native application
editing was not tested.

This trial changed both the skill and the brief, so it cannot isolate a skill-only
effect. The older independent author had not received all the later decisions now
in the brief. Separate contexts came from the same model family. There was no
audience experiment, timed delivery, live research execution or new universal quality
score. The trial outputs remain private project artifacts; the runtime guidance
was not changed again in response to this comparison.

## Imported copies and user-managed reservations

A live QC run from an imported copy exposed three gaps: imported copies omit the ignored
profile, so the sibling lookup always failed; the usage reference had the agent
acquire interactive sessions itself; and `runtime-state.json` held a stale node and
job. Profile resolution now has one owner (setup, “Locate the profile”) that covers
imported copies; the other modules point to it. The profile records interactive and
batch routes; live allocation state is read from Slurm and not saved.

Dry-run behavioral trials: fresh agents, blind to version, read either the prior
commit's skill copy or the candidate copy, both without ignored files, and wrote
planned actions for three prompts: QC on a reserved node, a reservation whose alias
no longer resolves, and first setup for a user who reserves nodes. The candidate met
13 of 13 predeclared expectations; the prior copy met 9 of 13. Its failures were
reading or writing `runtime-state.json` in all three prompts and, for the lost
reservation, planning `srun --overlap` or an agent-requested allocation. Both
versions found the canonical profile when user memory named its path, so these
trials do not discriminate the profile-location change; they show only that the
new wording does not regress it. No agent connected to BioHPC or read the real
profile, and one grader who also wrote the change scored the plans; runtime
behavior and portability to other users remain untested.

## Checks against a project package standard

In multi-sender projects, senders may assemble packages and call them ready while
the recipient only checks them. Analysis input checking now reports each item
of a project-supplied package standard as met, not met or not confirmed, groups gaps
by the named owner into the single sender request, and keeps the no-overall-verdict
rule. Without a standard it behaves as before. A generic template lives under the
module's references; each project keeps its own standard.

Report-from-evidence trials: fresh agents read either the prior commit's copy or the
candidate copy and the same pre-collected real-data evidence from the consuming
project (checker metadata scans and obs summaries of delivered objects, plus a draft
project standard). An independent
grader, blind to version, scored predeclared expectations: candidate 15 of 16,
prior 14 of 16. Both versions produced item tables when the prompt named the
standard, so those expectations did not discriminate. The prior copy gave overall
not-ready verdicts in both standard prompts; the candidate did so once, in its
closing reply to a direct “can it be used” question, contradicting its own report.
Qualitatively, the candidate kept the three-state status vocabulary and routed items
to the standard's owners, where the prior copy added a partial state and sent some
items to a generic sender. No output contradicted the evidence. One run per
configuration, no timing capture and a draft standard limit these results; whether a
direct usability question should receive a one-line answer remains open.

## Durable-only profile

The saved profile had drifted: it described a finished task as the current focus,
cited individual job IDs as evidence and omitted environments created later. Setup
now saves only settings expected to stay valid across sessions and projects;
project status, job and node identifiers, version readings and individual
verification runs stay in project docs, dependency records or live Slurm output.
The template gains a project table (workspace, selected input, docs link), an
environment table and a standing-preferences section, and drops the next-action
field. The router takes current status from the linked project docs.

Static walkthrough only: the migrated private profile kept every template heading
and checklist row, and a "what do we do first?" request routes through the profile
to the linked project docs for status. No fresh-agent trial was run.

## Data download

`xenium-data-download` captures a guest OneDrive for Business transfer of a large,
externally shared data folder into BioHPC. Tenant OAuth failed because the share used
emailed-code access without a guest account, so the route uses the browser `FedAuth`
cookie. WebDAV listing worked, but direct-path GETs hung for rclone and curl alike;
`download.aspx` answered immediately with range support, which shaped the bundled
script. A first run on the login node stalled when four connections stopped sending
bytes, which added connect and low-speed limits; the rerun went to a batch job on
compute. A compute node reached SharePoint directly at login-node throughput. Stream
counts 1–16 on that share leveled off near 110 MB/s with rising HTTP 429s, which set
the default of four. The first batch run then hung again: four requests waited over
20 minutes for response headers after a concurrent benchmark, which the low-speed
limit does not cover, so each attempt now has a size-based time limit. The
resubmitted job hung the same way with `--max-time` present: curl 7.76 over HTTP/2
did not enforce it. Attempts now run over HTTP/1.1 under an external `timeout`, with
the script's own retry loop trimming error bodies (a throttled-then-successful case
is unit-tested); the next job resumed downloading within a minute.

Unit tests with fake rclone/curl cover mirroring, skip and resume, expired-cookie
failure, list-only and usage errors; they caught log reuse between runs started in
the same second. Route A (rclone OAuth against another tenant) was exercised only to
the sign-in refusal. No fresh-agent trial was run.

## Cell QC

`xenium-cell-qc` comes from an exploration on a whole-transcriptome (Xenium Prime 5K)
cohort run as BioHPC batch jobs. The flag rules, the Pearson-residual preprocessing,
the reference/label-transfer procedure with thinning calibration, the
composition-sensitivity comparison and the contamination diagnostics were each
executed on the full cohort by project scripts; the figures and report were built
with the existing figure and report modules. The bundled `cell_qc_flags.py` is a
consolidated rewrite of the project feature and rule scripts. Besides the synthetic
fixtures in `tests/test_cell_qc_flags.py`, it ran on a subset of cohort regions (two
XOA versions, one region without a matrix) in a BioHPC batch job: floor, all four
flags, gene transcripts, genes detected, nuclear fraction and edge distance matched
the exploration outputs for every cell. The full cohort was not rerun with it at
that point. No fresh-agent trial was run.

### Targeted-panel TMA trial

The module was then run on a second cohort unlike the first: a custom targeted panel
on TMA runs with cores from more than one species. Stage 1 ran with the bundled flag
script unchanged; stages 2-5 ran through the preprocessing module's scripts and three
new generic scripts (`rescue_labels.py`, `composition_sensitivity.py`,
`contamination_diagnostics.py`) on GPU batch jobs. The per-cell status table
reconciled with the native cell counts. The trial changed the defaults to grouping by
core with a between-core check, a control-count condition for the control flag,
low-depth clusters read by markers, a species check for mixed-species designs and a
cell-count guard for composition distances; the 50-transcript reference cut held.
Their basis is in [evidence](../skills/xenium-cell-qc/references/evidence.md#basis-of-the-defaults);
the real-data results stay in the consuming project.

The revised flag script (`--groups`, between-group check, control rule) then ran in two
batch jobs: on the TMA runs with the core table it reproduced the trial's core-level
depth, density and binomial control flags for every cell and the trial's failed cores;
on the first cohort it reproduced the floor, depth, density and nucleus-expansion flags
of the exploration for every cell, and changed the control flag as the new rule
intends. `tests/test_cell_qc_flags.py` covers groups, the between-group check and both
control rules. The rescue, composition and contamination scripts were exercised only in
the TMA trial. `species_check.py` was written afterwards from the trial's species check;
on the trial's counts H5AD and rescue labels it reproduced the trial's per-status probe
shares by species and the counts of cells labelled as an unexpected species in
single-species groups, and `tests/test_species_check.py` covers calls, agreement,
expected-species groups and errors. No fresh-agent trial was run.

### Cross-cohort evaluation

The module then ran on all runs of the targeted panel (several multi-million-cell runs
across XOA versions and species designs) under a protocol fixed before the analysis,
in parallel tracks of BioHPC CPU and GPU batch jobs. Comparators were fixed floors,
per-run MAD, SpotSweeper- and SpaceTrooper-style rules implemented from the papers (the
SpotSweeper Python package agreed on the runs where it was tried), regional low-RNA
metrics, resolVI and ovrlpy, and the QC, labels, MisTIC and SPLIT outputs of existing
project analyses. The Bioconductor SpotSweeper and SpaceTrooper packages could not be
installed (the R 4.5.1 image lacks ImageMagick). Stage 1 ran with the bundled flag
script on every run; stages 2-5 used the preprocessing and cell-QC scripts. The changed
guidance and its basis are in
[evidence](../skills/xenium-cell-qc/references/evidence.md#basis-of-the-defaults); the
real-data results stay in the consuming project.

The evaluation found two script defects; a GPU verification on the project data
confirmed both fixes. The clustering script's GPU cluster sums undercounted
detections: on multi-million-cell inputs from both panels the largest clusters lost
part of their detections. Version 1.2 computes exact sums, equal to a SciPy recount on
both inputs, and stops when they do not reconcile. A project clustering script with the
same product had produced a delivered marker table from undercounted sums; an exact
recount changed the top markers of many clusters, and the same product summed over
row chunks was exact. Synthetic tests located the error: in one output row of 33.5
million products (about half a million cells, 70 detections per cell), entries fed by more than
41,986 products came back short and the row kept 5.4%, with float64 values and with
64-bit indices alike. The same design at 16.8 million products, a single entry fed by
one million products and sparse x dense products were exact. Label transfer gave
rescued labels to cells of failed cores; `rescue_labels.py` 1.1 holds them and reads
the hold flag from the label table and the H5AD obs. The first verification run held
no cell, because the label table listed only embedded cells while failed-core cells
are projected; after the fix, every cell of the failed cores was held: cells above the
floor became `unresolved_failed_group` (whether previously rescued or unresolved),
cells below it stayed `below_floor`, and every cell outside those cores kept its
status. `tests/test_gpu_script_helpers.py` covers the sums, status and hold rules on
CPU. No fresh-agent trial was run.

## Annotation QC

`xenium-annotation-qc` was written during the cross-cohort evaluation and run on the
existing label sets of the project analyses (main and detailed levels) on BioHPC CPU
nodes, in under two minutes per set. Main-level labels were supported except low-RNA
lineages flagged for low depth; detailed labels were more often returned for review,
mainly for depth and distinctness, and some were unsupported. The single-gene check
reproduced the evaluation's single-gene cluster finding on labels, but its one-gene
condition missed a label that differs by several genes. Agreement, spatial and
species checks were not exercised on real data. `tests/test_annotation_qc.py` covers
the checks on synthetic native outputs. No fresh-agent trial was run.

## Preprocessing

`xenium-preprocess` generalises the build and clustering scripts of the first cohort's
project. In a GPU batch job the build script rebuilt that project's counts H5AD
identically (same cells, order, genes, nonzeros and per-cell counts; regions without a
matrix reported), and the clustering script reproduced the exploration's preferred
embedding numerically (same 2,000 genes, per-PC correlation above 0.999999). Leiden at
resolution 1.0 agreed with the exploration more closely than the exploration's own
seed-to-seed runs agreed with each other; a same-seed rerun did not match exactly, so
GPU kNN/Leiden is not bitwise reproducible. Clustering a multi-million-cell object took
minutes on one GPU. The TMA trial exercised the all-genes branch on the targeted panel
unchanged. `tests/test_build_analysis_h5ad.py` passed on BioHPC with the GPU runtime's
Python on a CPU node. No fresh-agent trial was run.

## Descriptive QC script

`qc_describe.py` in `xenium-quality-check` generalises a project script used for one TMA
run (optional groups or curated cores, parquet or CSV cell table, optional native files,
output protection). Rerun on that run in a batch job, it reproduced the earlier native
metrics, panel, signal, segmentation and per-core tables and every per-cell row.
`tests/test_qc_describe.py` covers the options on synthetic folders.

## Figure titles, selection and colour

A two-panel cluster-depth figure from a consuming project (per-cluster depth; gene
detection by depth decile) was redrawn under two general-purpose figure skills for
comparison with the house output. A single-figure checklist reduced many cluster
colours to one highlighted group and grey, italicised genes, used plain-number log
ticks and tested both titles against every row; its generic tick size fell below
the house 7 pt minimum. A claim-led multi-panel procedure with an adversarial
reviewer found content problems the house review had not: some plotted genes were
top markers of only one highlighted cluster while a more frequent one was absent, a
proposed "small but nucleated" title failed for one cluster and did not separate the
groups, and the panel had no comparator for the "not cell type" reading. Its
composition produced PNG only and missed the panel-letter font. The house rules gained
row-tested titles, a stated selection rule, the comparator check, colour economy,
italic genes and a text-overlap check; style, size minimum and export requirements
are unchanged. One figure was reviewed; no user study or repeated trial was run.

## Execution route choice

An agent running in a separate runtime was asked to begin a CPU-only input check and
descriptive QC on a new multiplexed-imaging delivery. No reservation was running.
Following the old rule ("ask the user to reserve; do not self-allocate"), it stopped
and asked the user to reserve a 24-hour GPU node. The same kind of step had already
finished as a two-minute batch job on the default CPU partition. The usage reference,
profile template and setup checklist now route scriptable steps to batch, which the
agent submits and monitors itself, and keep the interactive route for live
iteration. The ban on self-allocating interactive sessions is unchanged. The revised
wording has not yet been re-run with that agent.

## Agent-held interactive node

`scripts/node-reserve` holds one node with a placeholder job and runs commands on it
through `srun --overlap` from the login host, so an agent without the user's local
reservation tool or SSH alias can still keep data reads off the login node. On the
target cluster it was run twice from the login host: start on the default CPU
partition (10-minute limit), `run hostname` returned the compute node, `stop`
cancelled the job and `status` came back empty; the second run used the installed
skill copy with `NODE_RESERVE_REUSE` set. Reuse of a running user reservation, the
pending-job guard and the time limits were not exercised live.
