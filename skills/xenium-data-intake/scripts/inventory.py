#!/usr/bin/env python3
"""Read-only filesystem metadata inventories; no content reads, hashes or transfers.

Exit codes: 0 complete execution (differences are allowed), 1 partial coverage or
incomparable scopes, 2 failed execution/invalid input. JSON status is authoritative.
Exclusions and skips are exact POSIX relative paths and their subtrees, not globs.
The caller supplies a scope key for the agreed relative-path namespace; a matching
key does not independently establish the delivery agreement or source completeness.
"""

import argparse
import datetime as dt
import json
import ntpath
import os
from pathlib import Path
import stat
import sys


VERSION = 1
INVENTORY = "xenium-file-inventory"
COMPARISON = "xenium-inventory-comparison"
STATES = {"complete", "partial", "failed"}
TYPES = {"file", "directory", "symlink", "other"}
LIMITS = [
    "Metadata only: content identity and local materialization are not verified.",
    "Not an atomic snapshot; concurrent changes may go undetected.",
    "Symlinks are listed but never followed; archives are single files.",
]


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def relative_path(value):
    if (not isinstance(value, str) or not value or "\x00" in value
            or value.startswith("/") or ntpath.isabs(value)
            or any(p in ("", ".", "..") for p in value.split("/"))):
        raise ValueError("Expected an exact nonempty relative path without traversal: " + repr(value))
    return value


def path_list(values):
    values = [relative_path(x) for x in values]
    if len(set(values)) != len(values):
        raise ValueError("Duplicate path in exclusion/skip list")
    return sorted(values)


def within(path, parent):
    return path == parent or path.startswith(parent.rstrip("/") + "/")


def summary(entries):
    return {
        "entries": len(entries),
        "files": sum(e["type"] == "file" for e in entries),
        "directories": sum(e["type"] == "directory" for e in entries),
        "symlinks": sum(e["type"] == "symlink" for e in entries),
        "other": sum(e["type"] == "other" for e in entries),
        "file_bytes": sum(e.get("size_bytes", 0) for e in entries),
    }


def scan(root, scope_key, exclusions=(), skip_paths=()):
    """Scan metadata through non-following directory descriptors on POSIX systems."""
    exclusions, skip_paths = path_list(exclusions), path_list(skip_paths)
    if not isinstance(scope_key, str) or not scope_key.strip():
        raise ValueError("scope key must be nonempty")
    if any(within(a, b) or within(b, a) for a in exclusions for b in skip_paths):
        raise ValueError("Agreed exclusions and scan skips must not overlap")
    root = Path(root).expanduser().absolute()
    result = {
        "schema_version": VERSION, "kind": INVENTORY, "status": "failed",
        "source": {"root": str(root.resolve()), "observed_start": now(), "observed_end": None},
        "scope": {"key": scope_key, "exclusions": exclusions},
        "enumeration": "failed", "entries": [], "errors": [],
        "skips": [{"path": p, "reason": "requested scan skip"} for p in skip_paths],
        "limitations": list(LIMITS),
    }

    def error(path, operation, exc):
        result["errors"].append({"path": path, "operation": operation,
                                 "message": str(exc)})

    def skipped(path, reason):
        result["skips"].append({"path": path, "reason": reason})

    flags = os.O_RDONLY
    if not all(hasattr(os, k) for k in ("O_DIRECTORY", "O_NOFOLLOW")):
        error(".", "open-root", "Non-following directory descriptors unavailable on this platform")
        result["source"]["observed_end"] = now()
        result["summary"] = summary([])
        return result
    flags |= os.O_DIRECTORY | os.O_NOFOLLOW

    def walk(fd, prefix):
        before = os.fstat(fd)
        try:
            with os.scandir(fd) as iterator:
                for item in iterator:
                    path = prefix + item.name
                    if any(within(path, p) for p in exclusions + skip_paths):
                        continue
                    try:
                        relative_path(path)
                    except ValueError as exc:
                        parent = prefix.rstrip("/") or "."
                        error(parent, "represent-entry-path", exc)
                        skipped(parent, "entry path cannot be represented in inventory")
                        continue
                    try:
                        info = os.stat(item.name, dir_fd=fd, follow_symlinks=False)
                    except OSError as exc:
                        error(path, "stat", exc)
                        skipped(path, "entry metadata unavailable")
                        continue
                    mode = info.st_mode
                    kind = ("file" if stat.S_ISREG(mode) else "directory" if stat.S_ISDIR(mode)
                            else "symlink" if stat.S_ISLNK(mode) else "other")
                    entry = {"path": path, "type": kind, "availability": "unknown"}
                    if kind == "file":
                        entry["size_bytes"] = info.st_size
                    result["entries"].append(entry)
                    if kind == "directory":
                        try:
                            child = os.open(item.name, flags, dir_fd=fd)
                            try:
                                current = os.fstat(child)
                                if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
                                    raise OSError("Directory changed between stat and open")
                                walk(child, path + "/")
                            finally:
                                os.close(child)
                        except OSError as exc:
                            error(path, "open-directory", exc)
                            skipped(path, "directory enumeration unavailable")
        except OSError as exc:
            error(prefix.rstrip("/") or ".", "enumerate", exc)
            skipped(prefix.rstrip("/") or ".", "directory enumeration incomplete")
        after = os.fstat(fd)
        if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            error(prefix.rstrip("/") or ".", "changed-during-scan", "Directory metadata changed during enumeration")

    try:
        descriptor = os.open(root, flags)
        try:
            result["source"]["root"] = str(root.resolve())
            walk(descriptor, "")
        finally:
            os.close(descriptor)
        result["enumeration"] = "partial" if result["errors"] or result["skips"] else "complete"
    except OSError as exc:
        error(".", "open-root", exc)
    result["status"] = result["enumeration"]
    result["entries"].sort(key=lambda x: x["path"])
    result["summary"] = summary(result["entries"])
    result["source"]["observed_end"] = now()
    return result


def _object_pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate JSON object key: " + key)
        obj[key] = value
    return obj


def validate_manifest(doc):
    """Validate this tool's format, without opening any paths declared by it."""
    if not isinstance(doc, dict) or type(doc.get("schema_version")) is not int or doc["schema_version"] != VERSION or doc.get("kind") != INVENTORY:
        raise ValueError("Unsupported inventory kind/schema_version")
    state = doc.get("enumeration")
    if state not in STATES or doc.get("status") != state:
        raise ValueError("Invalid enumeration/status")
    source, scope = doc.get("source"), doc.get("scope")
    if not isinstance(source, dict) or not isinstance(source.get("root"), str) or not source["root"].startswith("/") or "\x00" in source["root"]:
        raise ValueError("source.root must be an absolute POSIX root identifier")
    if os.path.normpath(source["root"]) != source["root"]:
        raise ValueError("source.root must not contain traversal/redundant path components")
    for key in ("observed_start", "observed_end"):
        if key not in source or (source[key] is not None and not isinstance(source[key], str)):
            raise ValueError("Missing/invalid observation interval")
        if source[key] is not None:
            try:
                parsed = dt.datetime.fromisoformat(source[key])
                if parsed.tzinfo is None:
                    raise ValueError("Timezone required")
            except ValueError as exc:
                raise ValueError("Invalid observation timestamp") from exc
    if source["observed_start"] and source["observed_end"] and dt.datetime.fromisoformat(source["observed_start"]) > dt.datetime.fromisoformat(source["observed_end"]):
        raise ValueError("Observation interval ends before it starts")
    if not isinstance(scope, dict) or not isinstance(scope.get("key"), str) or not scope["key"].strip() or not isinstance(scope.get("exclusions"), list):
        raise ValueError("Invalid scope key/exclusions")
    exclusions = path_list(scope["exclusions"])
    for key in ("entries", "skips", "errors"):
        if not isinstance(doc.get(key), list):
            raise ValueError("Missing/invalid " + key)
    if state == "complete" and (doc["skips"] or doc["errors"]):
        raise ValueError("Complete enumeration cannot contain errors or scan skips")
    if state == "failed" and not doc["errors"]:
        raise ValueError("Failed enumeration requires error evidence")
    seen = {}
    for entry in doc["entries"]:
        if not isinstance(entry, dict):
            raise ValueError("Invalid entry")
        path = relative_path(entry.get("path"))
        if path in seen:
            raise ValueError("Duplicate entry path: " + path)
        seen[path] = entry
        if any(within(path, p) for p in exclusions):
            raise ValueError("Entry lies in an agreed exclusion: " + path)
        if entry.get("type") not in TYPES or entry.get("availability") != "unknown":
            raise ValueError("Invalid entry type/availability")
        if entry["type"] == "file":
            if type(entry.get("size_bytes")) is not int or entry["size_bytes"] < 0:
                raise ValueError("Regular file requires nonnegative integer size_bytes")
        elif "size_bytes" in entry:
            raise ValueError("Only regular files have size_bytes")
    for path in seen:
        pieces = path.split("/")
        for length in range(1, len(pieces)):
            parent = "/".join(pieces[:length])
            if parent not in seen or seen[parent]["type"] != "directory":
                raise ValueError("Entry ancestor is missing or not a directory: " + path)
    for key, fields in (("skips", ("reason",)), ("errors", ("operation", "message"))):
        for item in doc[key]:
            if not isinstance(item, dict) or any(not isinstance(item.get(f), str) or not item[f] for f in fields):
                raise ValueError("Invalid " + key + " evidence")
            if item.get("path") != ".":
                relative_path(item.get("path"))
    if doc.get("summary") != summary(doc["entries"]):
        raise ValueError("Inventory summary does not match entries")
    return doc


def load_manifest(path):
    with Path(path).open(encoding="utf-8") as handle:
        doc = json.load(handle, object_pairs_hook=_object_pairs,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nonstandard JSON number: " + value)))
    return validate_manifest(doc)


def compare(baseline, recipient):
    baseline, recipient = validate_manifest(baseline), validate_manifest(recipient)
    scopes_comparable = (baseline["scope"]["key"] == recipient["scope"]["key"]
                         and sorted(baseline["scope"]["exclusions"]) == sorted(recipient["scope"]["exclusions"]))
    a = {e["path"]: e for e in baseline["entries"]}
    b = {e["path"]: e for e in recipient["entries"]}
    result = {
        "schema_version": VERSION, "kind": COMPARISON,
        "status": "complete" if scopes_comparable and baseline["enumeration"] == recipient["enumeration"] == "complete" else "partial",
        "scopes_comparable": scopes_comparable,
        "baseline": {k: baseline[k] for k in ("source", "scope", "enumeration", "summary", "skips", "errors")},
        "recipient": {k: recipient[k] for k in ("source", "scope", "enumeration", "summary", "skips", "errors")},
        "missing_confirmed": [], "extra_confirmed": [],
        "baseline_only_unobserved": [], "recipient_only_unobserved": [],
        "type_differences": [], "size_differences": [],
        "same_file_metadata": [], "same_nonfile_type": [],
        "errors": [], "limitations": list(LIMITS) + [
            "Missing/extra refer only to these inventories and compatible selected scopes, not the entire delivery agreement.",
            "Extra means absent from this baseline, not unauthorized or unwanted.",
        ],
    }
    if "failed" in (baseline["enumeration"], recipient["enumeration"]):
        result["status"] = "failed"
        result["errors"].append("At least one input enumeration failed; inspect its retained evidence.")
    for p in sorted(a.keys() - b.keys()):
        key = "missing_confirmed" if scopes_comparable and recipient["enumeration"] == "complete" else "baseline_only_unobserved"
        result[key].append(p)
    for p in sorted(b.keys() - a.keys()):
        key = "extra_confirmed" if scopes_comparable and baseline["enumeration"] == "complete" else "recipient_only_unobserved"
        result[key].append(p)
    for p in sorted(a.keys() & b.keys()):
        if a[p]["type"] != b[p]["type"]:
            result["type_differences"].append({"path": p, "baseline_type": a[p]["type"], "recipient_type": b[p]["type"]})
        elif a[p]["type"] != "file":
            result["same_nonfile_type"].append(p)
        elif a[p]["size_bytes"] != b[p]["size_bytes"]:
            result["size_differences"].append({"path": p, "baseline_bytes": a[p]["size_bytes"], "recipient_bytes": b[p]["size_bytes"]})
        else:
            result["same_file_metadata"].append(p)
    return result


def protect_output(output, input_files=(), roots=()):
    """Declared manifest roots are identifiers only; do not resolve/stat them."""
    output = Path(output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Output already exists; choose a new filename")
    candidates = (str(output), str(output.resolve()))
    for path in input_files:
        if output.resolve() == Path(path).resolve():
            raise ValueError("Output must differ from input manifests")
    for root in roots:
        for candidate in candidates:
            if within(candidate, str(root)):
                raise ValueError("Output must be outside the inventoried input roots")
    return output


def write_output(output, result):
    encoded = json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    with output.open("x", encoding="utf-8") as handle:
        handle.write(encoded)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    scanner = commands.add_parser("scan", help="Inventory filesystem metadata without opening file contents")
    scanner.add_argument("root", type=Path)
    scanner.add_argument("--scope-key", required=True, help="Explicit identity of the agreed relative-path comparison scope")
    scanner.add_argument("--exclude", action="append", default=[], metavar="RELPATH", help="Agreed exclusion, exact path/subtree; repeatable")
    scanner.add_argument("--skip", action="append", default=[], metavar="RELPATH", help="Unexamined path/subtree; repeatable; makes coverage partial")
    scanner.add_argument("--output", required=True, type=Path)
    comparator = commands.add_parser("compare", help="Compare this tool's versioned inventories, never their underlying file contents")
    comparator.add_argument("baseline", type=Path)
    comparator.add_argument("recipient", type=Path)
    comparator.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    output = None
    try:
        if args.command == "scan":
            root = args.root.expanduser().absolute()
            output = protect_output(args.output, roots=(root, root.resolve()))
            result = scan(root, args.scope_key, args.exclude, args.skip)
        else:
            output = protect_output(args.output, input_files=(args.baseline, args.recipient))
            inventories = []
            for path in (args.baseline, args.recipient):
                inventories.append(load_manifest(path))
                protect_output(output, roots=(inventories[-1]["source"]["root"],))
            result = compare(*inventories)
            result["input_manifests"] = {"baseline": str(args.baseline.absolute()), "recipient": str(args.recipient.absolute())}
        write_output(output, result)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {"schema_version": VERSION, "kind": "xenium-inventory-error", "status": "failed", "errors": [str(exc)]}
        # A rejected output location must never be used even for failure evidence.
        print(json.dumps(result), file=sys.stderr)
        return 2
    print(json.dumps({"status": result["status"], "output": str(output)}))
    return {"complete": 0, "partial": 1, "failed": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
