#!/usr/bin/env python3
"""Summarize annotated cells from one prepared H5AD without changing the input."""
import argparse
import csv
import json
import os
from pathlib import Path
import socket
import sys

import h5py
import numpy as np


def read_column(node):
    if isinstance(node, h5py.Group):
        kind = node.attrs.get("encoding-type", "")
        if kind == "categorical" or ("codes" in node and "categories" in node):
            cats = read_column(node["categories"])
            codes = node["codes"][:]
            if np.any(codes < -1) or np.any(codes >= len(cats)):
                raise ValueError("Invalid categorical codes")
            return np.array([None if k == -1 else cats[k] for k in codes], dtype=object)
        if "values" in node and "mask" in node:
            values = read_column(node["values"]).astype(object)
            values[node["mask"][:]] = None
            return values
        raise ValueError("Unsupported observation encoding: " + str(kind))
    return np.asarray(node.asstr()[:] if h5py.check_string_dtype(node.dtype) else node[:])


def missing(x):
    return x is None or (isinstance(x, (float, np.floating)) and np.isnan(x)) or str(x).strip() == ""


def text_value(x):
    return "" if missing(x) else str(x)


def table(path, fields, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def summarize(input_path, output, sample_key, cell_type_key, metadata_keys=(), exclude_labels=(), missing_label="__missing__"):
    input_path, output = Path(input_path).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Output already exists: " + str(output))
    if not missing_label or not missing_label.strip():
        raise ValueError("Missing-label display value cannot be empty")
    metadata_keys = list(dict.fromkeys(metadata_keys))
    reserved = {"sample_id", "input_cells", "included_cells", "excluded_cells"}
    if reserved.intersection(metadata_keys):
        raise ValueError("Metadata keys collide with output columns")
    with h5py.File(input_path, "r") as f:
        obs = f["obs"]
        keys = list(dict.fromkeys([sample_key, cell_type_key] + metadata_keys))
        absent = set(keys) - set(obs.keys())
        if absent:
            raise ValueError("Missing obs fields: " + ", ".join(sorted(absent)))
        index_key = obs.attrs["_index"]
        ids = read_column(obs[index_key])
        n = len(ids)
        if n == 0 or len(set(map(str, ids))) != n or any(missing(x) for x in ids):
            raise ValueError("Input cell index must be nonempty, unique and nonmissing")
        values = {k: read_column(obs[k]) for k in keys}
    if any(len(v) != n for v in values.values()):
        raise ValueError("Observation lengths disagree")
    if any(missing(x) for x in values[sample_key]):
        raise ValueError("Observation/sample IDs must not be missing")
    samples = np.array([str(x) for x in values[sample_key]], dtype=object)
    raw_labels = values[cell_type_key]
    present = {str(x) for x in raw_labels if not missing(x)}
    if missing_label in present:
        raise ValueError("Missing-label display value collides with an existing annotation")
    labels = np.array([missing_label if missing(x) else str(x) for x in raw_labels], dtype=object)
    excluded_set = set(exclude_labels)
    unknown_exclusions = excluded_set - set(labels)
    if unknown_exclusions:
        raise ValueError("Excluded labels absent from input: " + ", ".join(sorted(unknown_exclusions)))
    keep = ~np.isin(labels, sorted(excluded_set))
    sample_ids = sorted(set(samples))
    cell_types = sorted(set(labels[keep]))
    if not cell_types:
        raise ValueError("No cells remain under the requested denominator policy")
    si = {v:i for i,v in enumerate(sample_ids)}
    ci = {v:i for i,v in enumerate(cell_types)}
    counts = np.zeros((len(sample_ids), len(cell_types)), dtype=np.int64)
    for sample, label in zip(samples[keep], labels[keep]):
        counts[si[sample],ci[label]] += 1
    sample_rows, rows, exclusions = [], [], []
    for sample in sample_ids:
        mask = samples == sample
        total = int(mask.sum())
        denominator = int(counts[si[sample]].sum())
        meta = {"sample_id":sample, "input_cells":total, "included_cells":denominator, "excluded_cells":total-denominator}
        for k in metadata_keys:
            distinct = {text_value(x) for x in values[k][mask]}
            if len(distinct) != 1:
                raise ValueError(f"Metadata {k!r} is not constant within sample {sample!r}")
            meta[k] = next(iter(distinct))
        sample_rows.append(meta)
        for label in cell_types:
            count = int(counts[si[sample],ci[label]])
            rows.append({"sample_id":sample,"cell_type":label,"count":count,"denominator":denominator,
                         "proportion":count/denominator if denominator else ""})
        for label in sorted(excluded_set):
            exclusions.append({"sample_id":sample,"cell_type":label,"reason":"explicit_label_exclusion",
                               "count":int(np.count_nonzero(mask & (labels == label)))})
    included = int(keep.sum())
    assert int(counts.sum()) == included
    assert included + sum(r["excluded_cells"] for r in sample_rows) == n
    output.mkdir(parents=True, exist_ok=False)
    # Success manifest is written last; an interrupted directory is never a completed result.
    table(output/"counts.tsv", ["sample_id","cell_type","count","denominator","proportion"], rows)
    table(output/"sample_metadata.tsv", ["sample_id","input_cells","included_cells","excluded_cells"]+metadata_keys, sample_rows)
    table(output/"exclusions.tsv", ["sample_id","cell_type","reason","count"], exclusions)
    manifest = {"schema":"xenium-composition-summary/v1", "status":"complete", "input":str(input_path),
                "sample_key":sample_key,"cell_type_key":cell_type_key,"metadata_keys":metadata_keys,
                "missing_label":missing_label,"excluded_labels":sorted(excluded_set),
                "input_cells":n,"included_cells":included,"excluded_cells":n-included,
                "samples":len(sample_ids),"cell_types":len(cell_types),
                "zero_denominator_samples":[r["sample_id"] for r in sample_rows if not r["included_cells"]],
                "python":sys.version.split()[0],"numpy":np.__version__,"h5py":h5py.__version__,
                "hostname":socket.gethostname(),"slurm_job_id":os.environ.get("SLURM_JOB_ID"),
                "denominator":"retained annotated cells per observation, including missing/Unknown unless explicitly excluded",
                "interpretation":"descriptive cell composition; no independent-subject or group-effect inference"}
    (output/"report.md").write_text(
        "# Cell-type composition\n\n"
        f"Input: `{input_path}`\n\n"
        f"Observation field: `{sample_key}`; annotation field: `{cell_type_key}`.\n\n"
        f"{included:,} of {n:,} input cells included across {len(sample_ids)} observations; "
        f"{n-included:,} explicitly excluded. Missing annotations appear as `{missing_label}`. "
        "Unknown annotations remain in the denominator unless listed as exclusions.\n\n"
        "[Counts and proportions](counts.tsv), [sample metadata](sample_metadata.tsv), "
        "[exclusions](exclusions.tsv), [run record](run.json).\n\n"
        "These are descriptive proportions among retained cells, not cell densities or "
        "biological-replicate group comparisons. Sample/core counts do not establish the number of independent experimental units. "
        "No spatial graph, expression reprocessing or annotation changes were performed.\n")
    (output/"run.json").write_text(json.dumps(manifest, indent=2)+"\n")
    return manifest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True)
    p.add_argument("--output",required=True)
    p.add_argument("--sample-key",required=True)
    p.add_argument("--cell-type-key",required=True)
    p.add_argument("--metadata-key",action="append",default=[])
    p.add_argument("--exclude-label",action="append",default=[])
    p.add_argument("--missing-label",default="__missing__")
    a=p.parse_args()
    try:
        r=summarize(a.input,a.output,a.sample_key,a.cell_type_key,a.metadata_key,a.exclude_label,a.missing_label)
    except Exception as e:
        print(f"ERROR: {e}",file=sys.stderr)
        return 2
    print(json.dumps({k:r[k] for k in ("status","input_cells","included_cells","samples","cell_types")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
