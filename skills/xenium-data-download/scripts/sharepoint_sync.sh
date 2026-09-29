#!/usr/bin/env bash
# Mirror a OneDrive/SharePoint folder using a browser-session cookie.
# rclone lists the folder over WebDAV; files come through _layouts/15/download.aspx,
# because direct-path GETs on these drives can hang without response headers.
# Each file gets up to five time-limited attempts that resume its *.part file.
# Complete files are skipped, so re-running is the recovery path after cookie
# expiry, interruptions or new uploads.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: sharepoint_sync.sh --site URL --folder PATH --dest DIR --cookie-file FILE --log-dir DIR
                          [--library NAME] [--parallel N] [--list-only]

  --site         https://<tenant>-my.sharepoint.com/personal/<user> or .../sites/<site>
  --folder       folder inside the library, e.g. "Delivery" or "Shared/Run 1"
  --dest         destination directory; receives the folder's contents, mirrored
  --cookie-file  file holding one line "FedAuth=..." (keep it mode 600)
  --log-dir      where filelist.tsv and sync_<timestamp>_<pid>.log are written
  --library      document library path segment (default: Documents)
  --parallel     concurrent downloads (default: 4)
  --list-only    write filelist.tsv, print file count and size, download nothing

Exit status: 0 when every listed file is complete, 1 if any download failed,
2 on usage errors. Requires rclone, curl >= 7.71 and python3.
EOF
}

SITE= FOLDER= DEST= COOKIE_FILE= LOG_DIR= LIBRARY=Documents PARALLEL=4 LIST_ONLY=0
while [[ $# -gt 0 ]]; do
  case $1 in
    --site) SITE=${2%/}; shift 2 ;;
    --folder) FOLDER=${2#/}; FOLDER=${FOLDER%/}; shift 2 ;;
    --dest) DEST=$2; shift 2 ;;
    --cookie-file) COOKIE_FILE=$2; shift 2 ;;
    --log-dir) LOG_DIR=$2; shift 2 ;;
    --library) LIBRARY=$2; shift 2 ;;
    --parallel) PARALLEL=$2; shift 2 ;;
    --list-only) LIST_ONLY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done
for v in SITE FOLDER DEST COOKIE_FILE LOG_DIR; do
  [[ -n ${!v} ]] || { echo "missing --$(tr '_A-Z' '-a-z' <<<"$v")" >&2; exit 2; }
done
[[ $SITE == https://*/* ]] || { echo "--site must look like https://<host>/personal/<user>" >&2; exit 2; }
[[ -r $COOKIE_FILE ]] || { echo "cookie file not readable: $COOKIE_FILE" >&2; exit 2; }

HOST=${SITE#https://}; HOST=${HOST%%/*}
DRIVE=/${SITE#https://*/}/$LIBRARY          # server-relative library path
COOKIE=$(<"$COOKIE_FILE")
LIST=$LOG_DIR/filelist.tsv
LOG=$LOG_DIR/sync_$(date +%Y%m%d_%H%M%S)_$$.log   # one log per run; counts come from it
mkdir -p "$LOG_DIR"
TIMEOUT_CMD=$(command -v timeout || command -v gtimeout || true)
RETRY_DELAY=${RETRY_DELAY:-30}
export COOKIE SITE DRIVE FOLDER DEST TIMEOUT_CMD RETRY_DELAY

log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

rclone lsf -R --files-only --format sp --separator $'\t' \
  ":webdav,url='https://$HOST$DRIVE',vendor=other:$FOLDER" \
  --webdav-headers "Cookie,$COOKIE" > "$LIST"
total=$(wc -l < "$LIST" | tr -d ' ')
log "listed $total files, $(awk -F'\t' '{s+=$1} END {printf "%.1f GiB", s/2^30}' "$LIST") in $FOLDER"
[[ $LIST_ONLY == 1 ]] && exit 0
mkdir -p "$DEST"

fetch() {
  local size=${1%%$'\t'*} rel=${1#*$'\t'}
  local out=$DEST/$rel part=$DEST/$rel.part url code before attempt limit
  fsize() { stat -c %s "$1" 2>/dev/null || stat -f %z "$1"; }
  [[ -f $out && $(fsize "$out") == "$size" ]] && return 0
  mkdir -p "$(dirname "$out")"
  [[ -f $part && $(fsize "$part") -gt $size ]] && rm -f "$part"
  url="$SITE/_layouts/15/download.aspx?SourceUrl=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$DRIVE/$FOLDER/$rel")"
  limit=$((300 + size / 5000000))            # per attempt: 300 s + 1 s per 5 MB
  for attempt in 1 2 3 4 5; do
    before=0; [[ -f $part ]] && before=$(fsize "$part")
    # Throttled requests can hang before any response header. curl 7.76 over HTTP/2
    # ignored its own time limits there, so an external timeout backs them up.
    code=$(${TIMEOUT_CMD:+$TIMEOUT_CMD $((limit + 30))} curl -sS --http1.1 -H "Cookie: $COOKIE" \
      --connect-timeout 30 --speed-limit 1024 --speed-time 120 --max-time "$limit" \
      -C - -o "$part" -w '%{http_code}' "$url" 2>/dev/null) || true
    # Keep only bytes from a 200/206 body; drop error pages (429, sign-in redirects).
    if [[ $code != 20[06] && -f $part ]]; then
      if [[ $before -eq 0 ]]; then rm -f "$part"
      else python3 -c 'import os, sys; os.truncate(sys.argv[1], int(sys.argv[2]))' "$part" "$before"; fi
    fi
    if [[ -f $part && $(fsize "$part") == "$size" ]]; then
      mv "$part" "$out"
      echo "OK   $rel"
      return 0
    fi
    case $code in 302|401|403) break ;; esac   # expired cookie: retrying cannot help
    sleep $((attempt * RETRY_DELAY))
  done
  echo "FAIL http=${code:-timeout} $rel"
}
export -f fetch

tr '\n' '\0' < "$LIST" | xargs -0 -P "$PARALLEL" -I{} bash -c 'fetch "$1"' _ {} >> "$LOG" 2>&1 || true
ok=$(grep -c '^OK' "$LOG" || true)
fail=$(grep -c '^FAIL' "$LOG" || true)
log "done: $ok downloaded, $((total - ok - fail)) already complete, $fail failed (log: $LOG)"
[[ $fail -eq 0 ]]
