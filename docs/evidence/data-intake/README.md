# Data intake and analysis-input migration evidence

These are small synthetic execution trials and local deployment checks. No research
inputs, production profile, cloud account, BioHPC job or email service were used.
Candidate reports and logs are preserved, including their historical temporary paths.
Their conclusions apply to the fixtures and observed commands, not all future use.

## Independent behavioral trials

Each candidate began without the parent conversation and without expected answers.
Coordinator criteria were held outside the candidate workspace. One run per case does
not establish repeatability or comparative superiority over the previous skill.

| Trial | Evidence and observed distinction |
|---|---|
| Native receipt | [Report](trial-intake/outputs/intake-report.md): equal file count and total bytes hid a different path set; source and recipient gaps stayed distinct; matrix labels and a same-basename QC mask were not accepted as counts or original morphology |
| Analytical objects | [Report](trial-analysis/outputs/report.md): reordered annotation keys matched; one wrong coordinate key did not; repeated cell IDs were scoped by core and transformed matrix semantics were preserved |
| Delivery scope | [Report](trial-scope/outputs/report.md): the same curated object supported an agreed subset, an unknown delivery, and an incomplete larger contract; an H5 candidate without a matrix remained an expression gap |
| Conflicting evidence | [Report](trial-conflict/outputs/report.md): contradictory sender/email and package-scope claims and partial source observation were considered separately |

[Coordinator criteria](coordinator/criteria/README.md), the [archive audit](AUDIT.md)
and [trial artifact manifest](manifest.json) record evaluation and preservation scope.
Per-trial archive READMEs describe included synthetic inputs, saved commands and replay
limits. Supplied sender checksum text was not treated as permission to compute local
hashes. No files were repaired or redownloaded and no downstream scientific method was
run. The scope and conflict trials performed small actual matrix reads; the intake
trial was limited to receipt evidence. Reports distinguish h5py reads from untested
AnnData compatibility.

## Tool and implementation verification

- All 10 inventory tests passed; see [captured output](test-data-intake.log) and
  [executable tests](../../../tests/test_data_intake.py). Real CLI tests cover path-based
  comparison, equal-size identity limits, zero-byte files, symlinks, output protection,
  incompatible scopes, exclusions, skipped scope, asymmetric partial comparisons and
  invalid manifests. Permission/stat/mid-enumeration failures are explicitly mocked
  because privileged local test accounts do not reliably reproduce those failures.
- Independent review found that an impossible manifest could declare a file or symlink
  as the parent of another entry. Parent-chain validation now rejects both; the
  regression suite includes these counterexamples.
- The existing [dense/CSR/CSC tests](../../../tests/test_check_h5ad.py) and all seven
  [H5AD CLI regressions](../../../tests/test_check_h5ad_cli.py) passed after migration.
  The renamed checker and biological reference equal their pre-edit working-copy
  bytes, including the user's existing uncommitted checker repair. This comparison
  did not compute a checksum.
- Execution used local Python 3.14.7; NumPy 2.5.3 and h5py 3.16.0 were installed into
  the existing agent-tools environment for these synthetic checks. The inventory
  helper itself uses only the standard library and supports macOS/Linux.
- Skill YAML names/descriptions, bundled Markdown links, changed Python syntax and
  `git diff --check` passed. The generic single-package skill validator flags required
  sibling-module links as leaving one package; this repository deliberately bundles
  siblings. Repository-level resolution verifies that arrangement; no pass of that
  generic validator is claimed.

No live cloud-placeholder hydration, remote permissions, scheduler behavior or real
AnnData reading was tested. Local inventories retain availability as unknown;
ordinary filesystem metadata does not prove content materialization. Source web
observations in the fixtures are supplied, bounded notes rather than browser checks.

## Deployment and retirement

[Pre-retirement checks](deployment-before-retirement.json) resolved both new Codex
entries to the canonical repository, read their required resources and exercised
`scan --help`, `compare --help` and the analysis checker's `--help` through deployed
paths. The old source forwarder reached the new canonical module and its resources
before the old active link was removed. The saved profile remained available by
canonical sibling resolution; its contents are not archived here.

[Final manager state](deployment-final.json) records two active linked entries with
no drift. `skl drop xenium-input-check --agent codex --global` removed the old active
entry; `skl retire xenium-input-check` moved its library link into `_retired`.
`skl where` still says `inLibrary: true` for this retired entry but shows no sites;
retired-location and filesystem checks establish its inactive state. Its tiny source
forwarder remains so reversible retirement does not leave a dangling link. The router
selects only the two new current names. Runtime/module names and historical project
outputs were not renamed.

The working tree contained unrelated work. Changes to scientific-figures and earlier
trial notes observed during execution were preserved; the final note was appended to
the then-current trial file. No commit or push was performed.
