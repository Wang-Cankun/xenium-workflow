---
name: xenium-data-download
description: Download shared research data from a cloud share or transfer service into BioHPC storage—choose the route for the source, set up access and run a resumable transfer as a compute job. OneDrive/SharePoint links are the bundled route. Use for a OneDrive/SharePoint link to fetch, a failed or slow browser download, or refreshing a copy after the owner uploads more; completeness against a delivery agreement belongs to xenium-data-intake.
---

# Xenium data download

Move data that someone has shared into BioHPC storage reliably and repeatably. The
result is a mirrored copy, a rerunnable transfer command and a record of what was
fetched. Whether the copy matches what was promised is an
[intake](../xenium-data-intake/SKILL.md) question.

## Establish the transfer

Read project instructions and the personal profile
([locate it](../xenium-biohpc-setup/SKILL.md#locate-the-profile)). Identify:

- **Source:** the link as the sender gave it, the folder in scope and whether the
  sender is still uploading. A listing that grows between runs means uploads are
  in progress; plan a refresh rather than treating the first pass as final.
- **Destination:** the path the requester named. Mirror the source's folder structure
  there. A destination in shared storage holds data only. Pre-existing files
  (another person's partial zip, earlier batches) stay untouched; report them and
  leave removal to their owner.

List the source before downloading: file count and total size, compared with free
capacity at the destination. Inbound transfer along the link the data owner provided
is the authorized route; re-sharing it elsewhere is a separate decision for the user.

## Resolve settings

Each user keeps personal settings in their profile. Use the profile's value; where it
has none, use the default below, tell the user which defaults you applied, and save
the choices they keep to their profile. Ask only when neither source settles
something the transfer needs, such as the destination.

| Setting | Default when the profile has none |
|---|---|
| Transfer scripts, file lists and logs | The project's owned workspace: `scripts/` and `logs/<transfer>/` |
| Credential files | `~/.config/secrets/` (directory 700, files 600) on the local machine and on BioHPC |
| rclone | Static binary from [rclone.org](https://rclone.org/downloads/) in the user's owned tools directory on PATH (`~/bin` if none is recorded) |
| Listing and one-file trial | The interactive route; without one, a short `sbatch` job |
| Full transfer | `sbatch` with the cluster's default partition, 4 CPUs, 8G and a wall time from the listed size |
| Login-node transfers | Not used unless the user asks |

## Select the route

| Source | Route |
|---|---|
| OneDrive for Business or SharePoint link (`*-my.sharepoint.com/personal/…`, `*.sharepoint.com/sites/…`, `/:f:/` sharing links) | [OneDrive/SharePoint](references/onedrive-sharepoint.md) |
| Globus, FTP/SFTP, S3, Box or public HTTP | Not bundled yet. Use the established tool for that protocol (rclone backend, Globus CLI, lftp, wget) under the same settings, credential and execution rules |

When a source resists automation (credentials expire faster than the transfer, or
the tenant blocks every programmatic route), ask the sender for a machine-friendly
channel instead: guest access in their tenant, an upload to BioHPC
[Flash FTP](https://portal.biohpc.swmed.edu/content/guides/flash-ftp-guide/), or Globus.

## Handle credentials

Browser-session credentials such as cookies are the user's secrets. Ask the user to
copy them from their browser and save them to the credential file with a command
they run themselves, so the value never appears in the conversation. On macOS, for
example: `printf 'FedAuth=%s' "$(pbpaste)" > <credential-file> && chmod 600 <credential-file>`
(in an agent client with a shell escape, such as a `!` prefix, use that). Do not read browser cookie stores or keychains
yourself; the agent's permission checks treat that as credential exploration, and
working around a denial is not acceptable.

Copy the file to the server without exposing it
(`ssh <host> 'umask 077; cat > <path>' < <credential-file>`). Keep credentials out of
shared folders, project directories, job scripts and anything echoed to logs;
scripts read them from the file at run time.

## Run as a compute job

A multi-hour download is unattended network and disk work, so the full transfer runs
as a batch job. BioHPC compute nodes have reached external HTTPS hosts directly,
without a proxy, at the same throughput as the login node; the listing step confirms
access for this source before the long job starts. Size the wall time from the listed
total at a conservative rate with margin, send `--output`/`--error` to the transfer's
log directory, and record the submit command next to the script so a refresh is one
command.

Login nodes are shared, and BioHPC terminates processes that burden them. When the
user asks for a login-node transfer, run it inside `screen` so it survives
disconnection (tmux may be absent). A transfer inside an interactive allocation stops
when the allocation ends; resumable tooling makes resubmission the recovery path.

## Verify and hand off

A transfer is complete when the run reports every listed file present at its listed
size with no failures. Report the destination, file count and size, failures and
their cause, leftover partial files, credential expiry and the rerun command.
Checksums run only on explicit request; size agreement is not byte identity.

Record in the project documentation the input location, the transfer script and
submit command, and how to refresh. For completeness against what the sender
promised, or a manifest comparison, continue with
[xenium-data-intake](../xenium-data-intake/SKILL.md).
