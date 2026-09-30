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

### Route each step: batch or interactive

Two routes reach compute; pick one per step.

- **Batch** — any step that runs as a script: input checks, QC summaries,
  preprocessing, figure batches. The agent writes the script, submits it with
  `sbatch <script.sh>` from the login host, polls the job, and reads its logs and
  outputs before the next step. The agreed task is the approval; submit without
  asking again. The script sets resources and `--time`, activates the environment
  (sourcing the shell environment file when the job starts clean), and names the
  working directory, command and log paths. A job ID confirms submission; the logs
  and outputs confirm the step.
- **Interactive** — live iteration (debugging, parameter trials judged one result at
  a time) and any data read, import or Python the login node must not carry. The
  profile records who holds the node:
  - *Agent-held*: [`node-reserve`](../scripts/node-reserve), installed in the owned
    tools `bin/`. `node-reserve start [-p <partition>] [-t <time>]` prints
    `JOB NODE`, reusing the user reservation named in `NODE_RESERVE_REUSE` first;
    `node-reserve run '<command>'` runs there through `srun --overlap`;
    `node-reserve stop` ends the node when the step is done. It holds one node at a
    time within its time limits; `node-reserve --help` lists its settings.
  - *User-held*: a user-run reservation behind a host alias. Confirm it with
    `squeue -u <username>` and `hostname` before activating the environment. With
    none running, send scriptable steps to batch and ask the user to reserve for the
    rest.
  A bare allocation request leaves the shell on the login node; work runs through
  `node-reserve run`, the alias or `srun --overlap`.

Send CPU-only steps to a CPU partition: a GPU partition holds the whole node and its
GPUs, and under-utilised GPU jobs may be cancelled.

Read live job, node and end-time information from Slurm when needed; a saved node or
job goes stale when the reservation changes. Allocations end on their owner's
schedule: follow the profile's lifecycle preference and leave other sessions running.
Acquiring an allocation is task execution, not part of setup orientation.
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
