# Profile template

Keep these headings and checklist rows when creating or updating a profile. Fill
fields from evidence or mark them pending; use not applicable where appropriate.
Record settings that remain valid across sessions (see the setup skill's
persistent-profile rules); project status, job identifiers and version readings stay
in project docs, dependency records or live output. Preserve existing choices and
correct facts in place. Record each full path once; refer to its role elsewhere. Keep
personal choices and reasons here; reusable behavior belongs in the skill.

Checklist states describe the named setting or choice: `confirmed` means recorded
with supporting evidence, `pending` means unresolved (including proposals),
`deferred by user` means explicitly postponed, and `not applicable` means outside
this context. Keep the basis column short: who decided or what was checked, not a
run log. Runtime readiness is noted per environment, with the evidence kept in that
environment's README or the project docs. This is Markdown, not a machine-enforced
schema.

```markdown
# BioHPC personal profile

## Setup checklist

States: confirmed, pending, deferred by user, not applicable.
Confirmed settings do not imply verified runtime readiness.

| Item | State | Basis or next decision |
|---|---|---|
| Connection and identity | pending | |
| Project and owned workspace choice | pending | |
| Storage roles and access | pending | |
| Software strategy | pending | |
| Execution route | pending | |
| Persistent save and readback | pending | |

## Connection and identity

- SSH alias/host, login user and storage groups:
- Scheduler account (if any) and how it differs from storage groups:

## Project and working layout

| Role | Path | Access / decision |
|---|---|---|
| Home | | |
| Shared input roots | | |
| Owned project root | | |
| Owned environments | | |
| Owned tools | | |
| Scratch/cache | | |
| Archive | | |

- Path aliases (different mounts of the same directory):
- Shell environment: <startup files, redirected caches, what batch jobs must source>
- Quota, retention and backup: <standing facts, or unresolved and when to check>

| Project | Owned workspace | Selected input (literal path) | Project docs |
|---|---|---|---|
| | | | |

## Software strategy

- User choice and reason, or question awaiting a choice with the options explained:
- Module use and activation conventions:

| Environment | Purpose | Entry point / activation | Dependency record | Runtime |
|---|---|---|---|---|
| | | | | <not checked / established; where evidence is kept> |

- Other owned or user-managed tools and their boundaries:
- Private credentials location (optional; for transfer tokens or cookies):

## Execution route

- Login versus compute use:
- Interactive route: <who holds the node: agent-held (`node-reserve` install path and
  its settings) and/or user-held (reservation tool, host alias, live check)>
- Batch route: <submission host, default CPU and GPU partitions, directives the site
  requires or rejects>
- Standing resource rules: <partitions to prefer or avoid, site and group limits>;
  task resources are chosen per task and not saved.
- Allocation lifecycle: <who starts, renews and ends allocations>

## Standing preferences

- Where data-reading, installation and analysis run:
- Figure, report and verification conventions that apply across projects:

## Open choices and handoff

- Pending user decisions and the options already explained:
- Deferred checks and when they become necessary:
- Canonical profile location:
```
