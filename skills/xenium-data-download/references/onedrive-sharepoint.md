# OneDrive and SharePoint route

Read this for links on `*-my.sharepoint.com` (OneDrive for Business) or
`*.sharepoint.com/sites/…` (SharePoint document libraries). Browser "Download" of a
large folder builds one zip on the fly and restarts from zero on any interruption;
use a file-by-file, resumable transfer instead.

## Read the link

A browse link looks like
`https://<tenant>-my.sharepoint.com/personal/<user>/_layouts/15/onedrive.aspx?id=%2Fpersonal%2F<user>%2FDocuments%2F<folder>&ga=1`.
Derive:

| Value | Example |
|---|---|
| Site | `https://<tenant>-my.sharepoint.com/personal/<user>` |
| Library | `Documents` (the segment after the site in the decoded `id`) |
| Folder | everything after the library in the decoded `id` |

`ga=1` marks guest access from another organization. A `/:f:/…` sharing link
redirects to a browse URL once opened; derive the values from that.

## Identify the access type

| Access | Sign | Route |
|---|---|---|
| Member of the tenant, or an Entra (B2B) guest account in it | rclone OAuth sign-in against the tenant succeeds | A: rclone OneDrive backend |
| "Specific people" link verified by an emailed code, no guest account | OAuth fails with "Selected user account does not exist in tenant … needs to be added as an external user" | B: browser cookie |
| "Anyone with the link" | opens without sign-in | B, using the session from opening the link |

Try A first when the user may have a guest account; it gives refreshable tokens.
Shares sent outside the owning organization usually fall in the second row.

## Route A: rclone OneDrive backend

The default rclone sign-in targets the user's home tenant. For a guest in another
tenant, authorize against that tenant's endpoints on a machine with a browser:

```sh
blob=$(printf '%s' '{"auth_url":"https://login.microsoftonline.com/<tenant-domain>/oauth2/v2.0/authorize","token_url":"https://login.microsoftonline.com/<tenant-domain>/oauth2/v2.0/token","access_scopes":"Files.Read Files.Read.All Sites.Read.All offline_access"}' \
  | base64 | tr -d '\n=' | tr '+/' '-_')
rclone authorize onedrive "$blob"
```

The blob must be unpadded URL-safe base64. Admin-consent errors mean the tenant
blocks rclone; switch to B. On success, create the remote with that token and the
site URL option, check it with `rclone lsd <remote>:<folder>`, then
`rclone copy <remote>:<folder> <dest>` with retries runs as the batch job.
Beyond the sign-in step this route has not yet been exercised end to end; verify
listing and a one-file copy before the full job.

## Route B: browser cookie and the bundled script

**Get the cookie.** In the browser session that shows the folder: DevTools →
Application → Storage → Cookies → `https://<tenant>-my.sharepoint.com` → `FedAuth` →
copy Cookie Value. The Network tab often shows no `cookie` request header because
OneDrive pages are served through a service worker. Save and copy it as described in
[Handle credentials](../SKILL.md#handle-credentials). Guest cookies last hours to a
day.

**Why the script is shaped this way.** WebDAV listing (PROPFIND) works with the
cookie, but a plain GET of the file path can hang without response headers, for
rclone and curl alike, whatever the user agent or HTTP version. The
`_layouts/15/download.aspx?SourceUrl=<encoded server-relative path>` endpoint answers
immediately and honors byte ranges, so the script lists with rclone and downloads
each file with `curl -C -` through that endpoint.

**Run** [sharepoint_sync.sh](../scripts/sharepoint_sync.sh) (`--help` for the
interface). Copy it into the transfer's scripts directory on the server (see
[Resolve settings](../SKILL.md#resolve-settings)); it needs rclone, curl ≥ 7.71 and
python3 there. Run it first with `--list-only` (interactive session or a short batch
job) to record the file list and size and confirm access, then submit the full run:

```sh
sbatch -c 4 --mem=8G -t <hh:mm:ss> -J <name>-sync \
  -o <log-dir>/slurm-%j.out -e <log-dir>/slurm-%j.err \
  --wrap 'bash <workspace>/scripts/sharepoint_sync.sh --site <site> --folder "<folder>" \
          --dest "<dest>" --cookie-file <credential-file> --log-dir <log-dir>'
```

**Concurrency.** SharePoint throttles per user. On one guest share, a single stream
reached about 70 MB/s and the total leveled off near 110 MB/s from 8 streams, with
more streams adding only HTTP 429 responses. The default `--parallel 4` gets most of
that ceiling with little throttling; a 429 counts as a failed attempt, and the
script's retries back off between attempts. Throttling can also appear as
requests that hang before any response header, often right after a burst of
concurrent requests. curl's low-speed check does not cover that wait, and curl 7.76
over HTTP/2 did not enforce `--max-time` there either, so the script uses HTTP/1.1,
wraps each attempt in `timeout` (300 s plus 1 s per 5 MB) and retries up to five
times, discarding any error body before resuming. Avoid running extra
download tests against the same share while a transfer is in progress. Measure again with a few streams before raising
concurrency for a different tenant.

Each run writes `filelist.tsv` and its own `sync_*.log` with one `OK` or
`FAIL http=<code>` line per file it touched, and ends with a
`done: N downloaded, M already complete, K failed` line. Exit status 1 means some
files failed.

**Recover.** A batch of `FAIL http=302`, `401` or `403` means the cookie expired:
the user copies a fresh `FedAuth`, replaces the file, and the same submit command
resumes. Complete files are skipped and partial `*.part` files continue. Other
failures (network resets past curl's retries) also clear on rerun. Rerun after the
sender finishes uploading to pick up new files; the script does not delete files
that disappeared from the source.
