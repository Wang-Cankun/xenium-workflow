# Working on Xenium workflow skills

This repository develops reusable agent instructions. Editing a skill is distinct
from invoking it on research data or configuring a server.

## Authoring conventions

- Trust the model's general capabilities. Keep project conventions, consequential
  boundaries and completion criteria; remove generic tutorials and repeated rules.
- Keep essential checks inline when every invocation needs them. Disclose guidance
  used only by a branch through a pointer that says when to read it.
- Add scripts, reference splits and analysis modules when actual use justifies them.
  Preserve the plain Markdown report format unless a task explicitly changes it.
- Keep agent documentation free of timestamp boilerplate. Project findings and live
  server state belong outside reusable guidance.
- Bundle required instructions and references. Use official sources for supplementary
  detail. Verify portability without relying on the author's filesystem or other
  personal skills. Skills consulted during development are not runtime dependencies:
  include any necessary conventions here and keep runtime module routes within this set.
- The repository is public, including docs, evidence and Git history. User-specific
  paths and identities belong in the ignored profile; every other mention of people,
  accounts, hosts, personal paths, research projects, samples or collaborators is a
  placeholder or neutral label. Enable the private-term hook once per clone with
  `git config core.hooksPath .githooks` and keep the ignored `.private-terms` list
  current; before pushing, `.githooks/pre-commit --all` scans the whole tree.

## Owners and update triggers

The skill files own intended agent behavior; they are not proof of runtime success.

| When changing | Read/edit the owner | Update when |
|---|---|---|
| Project identity, entry points, deployment | [README](README.md) | Identity, entry or deployment procedure changes |
| Authoring conventions and validation | This file | Repository-wide practice changes |
| Task selection and module routes | [Router](skills/xenium-workflow/SKILL.md) | A usable route changes |
| Setup actions and profile lifecycle | [BioHPC setup](skills/xenium-biohpc-setup/SKILL.md) | Setup behavior changes |
| Profile sections and saved checklist | [Profile template](skills/xenium-biohpc-setup/references/profile-template.md) | Required setup record changes |
| BioHPC operational guidance | [Usage reference](skills/xenium-biohpc-setup/references/biohpc-usage.md) | Supported procedure or source changes |
| Download routes, credentials and transfer execution | [Data download](skills/xenium-data-download/SKILL.md) | A supported source or execution rule changes |
| OneDrive/SharePoint access types and sync behavior | [SharePoint route](skills/xenium-data-download/references/onedrive-sharepoint.md) and [sync script](skills/xenium-data-download/scripts/sharepoint_sync.sh) | Access, endpoint, throttling or resume behavior changes |
| Delivery scope, inventories, source/recipient comparison | [Data intake](skills/xenium-data-intake/SKILL.md) | Receiving behavior or evidence semantics change |
| Inventory CLI, JSON and failure semantics | [Inventory tool](skills/xenium-data-intake/scripts/inventory.py) | Filesystem scanning or comparison behavior changes |
| Package scope, essential checks, completion | [Analysis input check](skills/xenium-analysis-input-check/SKILL.md) | Inspection behavior changes |
| Dataset overview, descriptive metrics and coverage | [Quality check](skills/xenium-quality-check/SKILL.md) and [describe script](skills/xenium-quality-check/scripts/qc_describe.py) | Overview scope or metric-summary behavior changes |
| Counts H5AD build, GPU embedding and clustering, projection model | [Preprocess](skills/xenium-preprocess/SKILL.md), [build script](skills/xenium-preprocess/scripts/build_analysis_h5ad.py) and [cluster script](skills/xenium-preprocess/scripts/cluster_analysis_h5ad.py) | Build fields, embedding defaults or saved projection model change |
| Cell-level flags, label rescue, composition sensitivity and contamination diagnostics | [Cell QC](skills/xenium-cell-qc/SKILL.md), [flag script](skills/xenium-cell-qc/scripts/cell_qc_flags.py) and the rescue, composition and contamination scripts beside it | Flag definitions, defaults or rescue procedure change |
| Checks of existing annotations, label statuses and reasons | [Annotation QC](skills/xenium-annotation-qc/SKILL.md), [checks](skills/xenium-annotation-qc/references/checks.md) and [script](skills/xenium-annotation-qc/scripts/annotation_qc.py) | Check definitions, thresholds or status rules change |
| Xenium assay/QC interpretation | [Biological checks](skills/xenium-analysis-input-check/references/xenium-biological-qc.md) | Assay definitions or interpretation guidance changes |
| Intake report presentation | [Intake outline](skills/xenium-data-intake/references/report-template.md) | Receipt report layout changes |
| Analysis input report presentation | [Analysis outline](skills/xenium-analysis-input-check/references/report-template.md) | Input report layout changes |
| Generic ready-package standard items | [Package standard template](skills/xenium-analysis-input-check/references/package-standard-template.md) | Standard structure or item set changes; project standards stay in projects |
| Cell composition inputs, denominator and model branches | [Composition](skills/xenium-composition/SKILL.md) | Count, plot or sccomp behavior changes |
| Figure design, shared style, captions and final exports | [Xenium figures](skills/xenium-figures/SKILL.md) | Plotting or final-figure behavior changes |
| Scientific narrative and DOCX/PPTX assembly | [Xenium reporting](skills/xenium-reporting/SKILL.md) | Report wording, production or figure-consumption behavior changes |
| Local niches and differential enrichment | [QUICHE](skills/xenium-quiche/SKILL.md) | Coordinate boundary, backend or DA behavior changes |
| Private-term check on commits and tree scans | [Pre-commit hook](.githooks/pre-commit) | Matching or scan scope changes |

These are current instruction owners. Keep detailed answers there, and route to them
from other documents. The local profile's Git exclusion is owned by
[its ignore file](skills/xenium-biohpc-setup/.gitignore).

## Verification

Trust established deterministic production scripts on routine runs. First
implementation, relevant logic/dependency changes, actual failures or explicit
requests trigger focused verification of the affected behavior. Avoid repeating
manual output checks after an unchanged, successful production path.

Run `git diff --check`; resolve repository-relative Markdown links from the checkout.
Check that each skill's YAML frontmatter has a name matching its directory and a
concise description. Syntax and link checks do not prove runtime behavior.

For checker changes, use an available Python with NumPy and h5py to run both
`python tests/test_check_h5ad.py` and `python tests/test_check_h5ad_cli.py`.
The first covers inspection values; the second exercises the actual CLI, scan
coverage, output protection and error evidence using disposable synthetic files.
These tests do not require BioHPC or AnnData; reader-failure coverage uses a stub.
Actual AnnData compatibility and scheduler behavior need their own execution evidence.

Inventory changes use `python tests/test_data_intake.py` with the Python standard
library. Exercise the real scan/compare CLI, partial evidence, malformed manifests,
scope compatibility and output protection. Metadata agreement does not establish
byte identity; these tests use synthetic files and do not compute data checksums.

For behavioral changes, walk a representative request through the affected skill
and inspect its proposed action and completion evidence. Use a small isolated
fixture when execution is needed. Documentation checks do not require live research
analysis. For route changes, start at README and confirm the task reaches its owner.
Keep useful behavioral trial evidence and its limits in [trial notes](docs/skill-trials.md).

The deployment model lives in README. After a deployment change, confirm that each
deployed skill resolves into this checkout.

Descriptive QC script changes use `python tests/test_qc_describe.py` with NumPy, pandas,
pyarrow and h5py on synthetic output directories (parquet and CSV cell tables, groups,
layout join, missing native files, output protection).
Analysis-H5AD build changes use `python tests/test_build_analysis_h5ad.py` with anndata,
h5py, pandas and pyarrow (for example the project GPU runtime on a CPU node); clustering,
rescue, composition and contamination scripts need the GPU single-cell runtime and their
own execution evidence on real data.
Species-check changes use `python tests/test_species_check.py` with h5py, pandas and
pyarrow (a minimal synthetic H5AD; anndata is used for index reading when installed).
Cell-QC flag changes use `python tests/test_cell_qc_flags.py` with NumPy, pandas, pyarrow,
SciPy and h5py on synthetic output directories; rescue and calibration run in the
project's GPU runtime and need their own execution evidence. The NumPy-compatible helpers
inside the GPU scripts (exact per-cluster sums, rescue status and hold rules) use
`python tests/test_gpu_script_helpers.py` with NumPy, SciPy and pandas.
Annotation-QC changes use `python tests/test_annotation_qc.py` with NumPy, pandas,
pyarrow, SciPy, scikit-learn and h5py on synthetic labelled output directories.
Composition count changes use `python tests/test_composition_cli.py` with NumPy/h5py.
Composition figure changes use `python tests/test_plot_composition.py` with the
existing Matplotlib/NumPy/pandas plotting runtime; project export and visual review
remain separate checks.
QUICHE contract changes use `python tests/test_quiche_workflow.py`; actual backend
smokes in `tests/test_quiche_backend.py` require their explicit environment flags
and the pinned runtime. Skipped backend tests are not passes. R/sccomp and real-data
verification belong to the consuming project's reproducible recipes and evidence.
