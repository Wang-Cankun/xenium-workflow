# BioHPC usage

Use this guide to establish a user's BioHPC profile. Values in angle brackets are
placeholders; obtain the actual account, storage allocation and resource access
from that user's configuration or BioHPC. A fresh installation needs an activated
BioHPC account and a reachable cluster, not an existing profile.

## Connect

Use an existing working SSH alias, or connect with the user's BioHPC login:

```sh
ssh <username>@nucleus.biohpc.swmed.edu
```

The [BioHPC portal](https://portal.biohpc.utsw.edu/) also provides a Nucleus web
terminal. Once connected, `whoami`, `hostname` and `id` establish the current login,
host and groups. Record the working connection in `profile.md`.

For account activation or an unresolved access problem, use the portal's account
instructions or contact `biohpc-help@utsouthwestern.edu`.
[Official introduction](https://portal.biohpc.utsw.edu/content/guides/introduction-to-biohpc/).

## Choose storage

Typical allocation patterns are:

| Location | Role |
|---|---|
| `/home2/<username>` | Shell configuration and small personal files |
| `/project/<department>/<group>/<username>` | Active project data |
| `/work/<department>/<username>` | Temporary or frequently accessed working data |
| `/archive/<department>/<group>/<username>` | Inactive data retained under the assigned storage policy |

Treat these as patterns, not guaranteed paths. Confirm assigned roots and permissions
with `ls -ld <path>` and, where available, `getfacl <path>`. Shared allocations may use
different paths. Select an owned location for environments, package caches and
results; record actual roots in the profile. Confirm retention and backup coverage
for the selected allocation rather than inferring them from its name.
[Official storage guide](https://portal.biohpc.utsw.edu/content/guides/biohpc-cloud-storage/).

If available, `biohpc_quota` reports storage usage and limits. If absent, consult the
portal or support for the applicable quota tool. `df -h <path>` describes filesystem
capacity, not the user's entitlement. Keep current usage in the task's observations
rather than persisting it as a profile default.
[Official quota guidance](https://portal.biohpc.utsw.edu/content/guides/storage-cheat-sheet/).

## Select compute resources

Use login nodes for connection, lightweight directory/text inspection, editing and
allocation/job management. Run data-reading Python/R checks, runtime import tests,
installations/builds and analysis inside allocated compute resources.

```sh
sinfo
scontrol show partition <partition>
squeue -u <username>
```

Choose partition, CPU count, memory, wall time and any GPU request from the task and
current allocation. Confirm whether a Slurm account is required; it is distinct from
the SSH username or Unix group. A visible partition alone does not prove eligibility.

Nucleus allocates whole nodes on every partition (`select/linear`), and partitions set
no default or maximum wall time: always pass `--time`, which ends the job exactly, and
prefer realistic limits because the backfill scheduler starts shorter jobs sooner.
Partition names do not state node memory reliably; read `sinfo -o "%P %D %c %m %G %f"`
before choosing a memory-bound partition.

For GPU single-cell work (for example rapids-singlecell), choose the partition by GPU
model: `sinfo -o "%P %G %f"` lists each partition's GPU count and model feature. A
GPU partition allocates its node with all of its GPUs, so select the partition and do
not add `--gres`; some partitions reject it. Match the GPU architecture to the
runtime's build and verify it once with an import-and-compute test on that partition;
Pascal-generation cards fall below current RAPIDS support, and an environment built for
newer architectures can fail on Volta. Prefer single-GPU nodes for single-GPU tools:
a multi-GPU node leaves the other GPUs idle, and under-utilised GPU jobs may be
cancelled. Record the verified partitions and the environment entry point in the
profile, not the live node or job.

For iterative inspection or debugging, follow the interactive route saved in the
profile. When the user reserves nodes themselves — for example with a reservation
tool that keeps a placeholder job and a host alias pointing at its node — work through
that alias: confirm the reservation with `squeue -u <username>` and the shell's
`hostname` before activating the environment and reading data. If the alias does not
resolve or no reservation is running, ask the user to start or renew one; do not
allocate a replacement yourself or fall back to login-node Python/R. Acquire an
interactive session through the portal or Slurm only when the profile assigns that
step to the agent; then choose a bounded period and task-sized CPUs/memory, and verify
the running allocation and hostname in the same way. An allocation request alone does
not move a login shell onto compute.

Read live job, node and end-time information from Slurm when it is needed; do not
keep it in a separate state file, because a saved node or job goes stale when the
reservation changes. Follow the profile's allocation lifecycle preference; seeing a
session does not authorize cancelling it.

For unattended work, prepare a batch script with resources, environment activation,
working directory, command and output/error paths. Submit with `sbatch <script.sh>`
and inspect the job state and logs. A job ID confirms submission, not successful
completion. Acquiring either kind of allocation is task execution, not an automatic
part of setup orientation.
[Official Slurm guide](https://portal.biohpc.utsw.edu/content/guides/slurm/).

## Choose software and prepare only what is needed

Discover relevant modules and existing environments during setup, even before an
analysis package is selected. Check the current shell's module initialization and
search paths; an empty search or missing executable in PATH is not a complete
software inventory.

```sh
module list
module avail <software>
module show <software/version>
```

Explain these options using what is actually available:

| Option | When it fits | What remains to check |
|---|---|---|
| Modules alone | Provided software already supplies the needed commands/packages | Exact version, activation and task imports |
| Python module plus owned uv environment | The provided Python is suitable but the project needs its own Python dependencies | Compatible interpreter, owned environment/cache and dependency record |
| Existing Conda/Mamba or collaborator environment | Reproducing an established workflow or its dependency stack | Ownership, activation, compatibility and required packages; keep shared installs unchanged |

`module load` configures the shell to use installed software; it does not imply that
all analysis libraries are included. uv can use that Python to create an isolated
user-owned environment. These are not mutually exclusive choices. Prefer uv when a
new Python dependency environment is needed unless the project requires another
manager; this preference does not require creating an environment for every setup.
[Modules documentation](https://modules.readthedocs.io/en/latest/) and
[uv interpreter selection](https://docs.astral.sh/uv/concepts/python-versions/).

Present relevant candidates, a recommendation and the missing evidence, then obtain
the user's strategy choice if one is not already recorded. An unknown analysis plan
can leave exact packages undecided while still settling the strategy. Read-only
module discovery does not install software. Carry out preparation within the user's
requested scope after the needed choices are settled.

For execution, record exact `module load <software/version>` and environment activation
commands. If using module-provided Python with uv, select that interpreter explicitly
by its resolved executable path; control automatic Python downloads when necessary.
Check module/runtime compatibility on the intended compute node, including OS and
architecture differences from the login node. Prepare dependencies separately from
analysis jobs, preserve project lockfiles, and verify required imports there.
[BioHPC software guide](https://portal.biohpc.utsw.edu/content/software/).

## Code hosting

Copy the SSH clone URL from the user's GitLab project; a BioHPC URL typically has
the form `git@git.biohpc.swmed.edu:<namespace>/<repo>.git`. Confirm the actual namespace
rather than deriving it from the cluster login. Store user-specific defaults only
in the local profile. Use `glab` for GitLab operations when configured.
