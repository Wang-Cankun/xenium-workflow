# Xenium workflow skills

Reusable agent instructions for researchers working with Xenium data on BioHPC.
The entry skill, `xenium-workflow`, routes a request to independently callable
modules; each module states its runtime, verification and completion requirements.
Scripts and templates are bundled with the modules that use them, and no skill
outside this set is required.

| Skill | Purpose |
|---|---|
| [xenium-workflow](skills/xenium-workflow/SKILL.md) | Route the request to a module and keep the requested deliverable across handoffs |
| [xenium-biohpc-setup](skills/xenium-biohpc-setup/SKILL.md) | Set up a Xenium workspace on BioHPC and keep its local profile |
| [xenium-data-download](skills/xenium-data-download/SKILL.md) | Download shared data from cloud shares into BioHPC storage as resumable jobs |
| [xenium-data-intake](skills/xenium-data-intake/SKILL.md) | Reconcile received files with a delivery agreement or a specified source |
| [xenium-analysis-input-check](skills/xenium-analysis-input-check/SKILL.md) | Explain what supplied objects mean and support; check a claimed-ready package against a project standard |
| [xenium-quality-check](skills/xenium-quality-check/SKILL.md) | Describe dataset scale, coverage and basic quality metrics (no filtering decisions) |
| [xenium-preprocess](skills/xenium-preprocess/SKILL.md) | Build a counts H5AD from native outputs and embed and cluster it on GPU |
| [xenium-cell-qc](skills/xenium-cell-qc/SKILL.md) | Flag low-information and artefactual cells, rescue them by calibrated label transfer and test composition sensitivity |
| [xenium-annotation-qc](skills/xenium-annotation-qc/SKILL.md) | Check existing cell-type annotations against the data and give each label a status with reasons |
| [xenium-composition](skills/xenium-composition/SKILL.md) | Summarize cell composition and fit eligible sccomp comparisons |
| [xenium-quiche](skills/xenium-quiche/SKILL.md) | Analyze local niches and eligible QUICHE differential enrichment |
| [xenium-figures](skills/xenium-figures/SKILL.md) | Render and finalize figures with the shared style ([style.json](skills/xenium-figures/assets/style.json)) |
| [xenium-reporting](skills/xenium-reporting/SKILL.md) | Write results and assemble DOCX/PDF or PPTX from final figures ([builder](skills/xenium-reporting/scripts/build_report.py)) |

## Use the skills

Invoke `$xenium-workflow`, or call a module directly. Keep the skill directories
together under `skills/`: modules refer to their siblings by relative path. Any agent
that reads `SKILL.md` and has the tools a task needs can follow them.

Cloning this repository does not configure a server. The
[BioHPC setup skill](skills/xenium-biohpc-setup/SKILL.md) creates and maintains the
local profile, `skills/xenium-biohpc-setup/profile.md`. The profile is Git-ignored, so
user-specific paths and identities never enter the repository. Data and generated
reports stay in their projects.

## Deploy

This checkout is the only place where skills are edited. Deployed copies are links
or pinned imports of it; never edit them in place.

### Local agents

Make every directory under `skills/` available to the agent's skill location,
preferably as links to this checkout so that a saved edit reaches the agent without
copying. Add the link for a new skill when it is created. If the agent already holds
its own copy of a skill, compare it with this checkout before replacing it.

### Platforms that import from a Git host

Import this repository and select every skill under `skills/`. An import is pinned to
a commit, so import again after each push. Editing and republishing an imported copy
creates a separate same-name skill instead of updating this set. Imports omit the
Git-ignored profile; the importing agent reads it from this checkout through host
access, following
[Locate the profile](skills/xenium-biohpc-setup/SKILL.md#locate-the-profile).

When your checkout's remote is a host the platform cannot import from, such as BioHPC
GitLab, mirror it to GitHub and edit only the source; the mirror serves imports alone.
Give `origin` both push URLs so that one `git push` updates both:

```sh
git remote set-url --add --push origin <source-remote-url>
git remote set-url --add --push origin git@github.com:<owner>/xenium-workflow.git
```

If the source host fails or does not respond, push to the mirror alone with
`git push <mirror-url> main`; the next `git push` brings the source up to date.

## Change a skill

Start with [AGENTS.md](AGENTS.md): it lists the owner file for each behavior, the
authoring conventions and the tests each change needs. Then:

1. Edit here and run the checks AGENTS.md names for the change, plus `git diff --check`.
2. Record behavioral trial evidence and its limits in [trial notes](docs/skill-trials.md).
3. Commit and push; linked local deployments see the change at once, and imported
   copies need a new import.
