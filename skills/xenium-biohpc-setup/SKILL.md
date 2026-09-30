---
name: xenium-biohpc-setup
description: Set up or resume a Xenium project on BioHPC—choose its workspace, software and execution settings, and save its personal profile. Use when Xenium setup is requested or xenium-workflow routes here; not for general BioHPC administration or other research workflows.
---

# Xenium setup on BioHPC

Default setup establishes a working context and personal profile. Create directories,
install software or submit jobs when the requested task needs those actions; an
unspecified setup request ends with recorded settings and open choices.

Use the [profile template](references/profile-template.md) for every saved profile.
For connection, storage, software selection or scheduler discovery, consult the
relevant sections of [BioHPC usage](references/biohpc-usage.md).

## Setup checklist

Use this as a short conversational checklist; use the states defined in the profile
template and keep its checklist rows and sections.
On updates, reuse settled context and inspect only
what the request or changed conditions require.

- [ ] **Resume and connect.** Read the profile as described in
  [Locate the profile](#locate-the-profile). Confirm the intended host
  and account before reusing settings. Use a separate user-owned checkout for another
  user's profile.
- [ ] **Orient the user.** From the current project, profile and lightweight inspection
  of known accessible roots, summarize relevant projects/directories: purpose, path,
  source data versus owned workspace, and observed access. Mark inferred purposes and
  incomplete coverage; directory visibility or group membership alone is not ownership.
  Stay within relevant roots rather than recursively cataloguing shared storage.
- [ ] **Guide the choice.** Before asking which project or directory to use, show the
  discovered options, explain what each supports and recommend a choice with reasons.
  Reuse choices already made. If discovery is blocked, explain the gap and ask for the
  smallest missing detail. Keep the user oriented as findings change, rather than
  saving all context for a final report.
- [ ] **Record the working layout.** Distinguish input locations, owned project work,
  scratch/cache and archive. Record the chosen project and directory conventions, or
  leave them explicitly undecided. Preserve the literal path of a selected input
  package in the template field; selecting a package is optional during setup.
  A proposed path need not be created during setup.
- [ ] **Choose software strategy.** Inspect relevant modules and existing environments
  before proposing installation. If no strategy is selected, explain the available
  options, recommend one for the known task and ask the user to choose or explicitly
  defer. Modules and uv can be complementary; use the manual's decision guidance.
  Save the choice separately from activation/import verification. Missing software
  calls for this discussion, not an automatic install or a silent pending entry.
- [ ] **Establish execution context.** Distinguish login user, storage group and Slurm
  account. Record quota/retention unknowns and scheduler evidence; visible queues do
  not prove allocation. Select dependency versions and job resources when the actual
  task establishes their need; a setup test is not a future analysis default. Record
  both [compute routes](references/biohpc-usage.md#route-each-step-batch-or-interactive):
  the interactive route — how the user obtains a node, how the agent reaches it and
  who renews it — and the batch route's submission host and default partitions.
  Reuse them for the requested work. Live allocation state is read from Slurm when
  needed, not saved.
- [ ] **Save and hand off.** Persist findings and decisions using the profile rules
  below, read the saved file back, and link its actual location. Summarize what is
  settled, what remains open and the next useful action. A suggested next step does
  not itself start package inspection or analysis.

## Locate the profile

The canonical profile is `profile.md` in this skill's folder of the user's own
checkout; resolve deployment links to reach it. Imported or packaged copies, such as
a skill import from a Git host, omit Git-ignored files, so a missing sibling there
does not mean that no profile exists. Use the canonical location recorded in the
user's agent memory, project notes or configuration and request access to that
path — read access to use it, write access to update it. If no location is recorded,
ask the user where their checkout is before starting a new setup. The handoff
section records the canonical location so sessions reached through another copy can
find it.

## Persistent profile

Create or update `profile.md` in this skill's canonical folder using the template.
When migrating an existing profile, retain useful evidence and decisions under its
fixed sections. Label observations, recommendations and user decisions. Omit
credentials and transient resource usage. User-confirmed removal of an old environment
retires that entry; it is not a reason to reconstruct it.

Save only what should stay true across sessions and projects: identity, storage
roles and paths, directory conventions, owned environments and tools with their
entry points, execution routes, and the user's standing preferences and rules. Leave
out anything that expires with a task or is cheaper to read live: current focus or
project status, job, reservation and node identifiers, usage and quota readings,
package versions already held in a lockfile or environment README, and individual
verification runs. Those belong in project docs, dependency records or live Slurm
output; the profile lists each project with its workspace and a link to its docs,
without summarizing them. Record a pending choice with the options already
explained so the next session does not repeat discovery. Correct a saved fact in
place when it proves wrong. A temporary file or chat-only summary is not a saved
profile. If the
canonical folder cannot be written, report persistence as incomplete and resolve a
persistent user-owned location with a discoverable pointer before claiming completion.

The profile is local and Git-ignored. Preserve it during skill updates or replacement;
if moving the skill, carry it over separately. An ignored file is not backed up by Git.

Before handoff, compare the saved profile with every template row and section and
read it back. Missing workspace or software choices must have been presented to the
user with options; keep the setup marked as awaiting choices until answered or
explicitly deferred. Settings can be recorded before task-specific runtime validation.
Report that distinction rather than an unqualified “setup complete”.
