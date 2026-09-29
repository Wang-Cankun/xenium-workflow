"""Descriptive (non-filtering) QC summary for one Xenium Onboard Analysis output.

Reads native outputs only: cell_feature_matrix.h5 and cells.parquet or cells.csv.gz
(required); metrics_summary.csv, experiment.xenium, gene_panel.json and
analysis_summary.html when present. Optional cell groups (for example TMA cores)
come from a mapping table (--groups) or from curated per-core crops (--cores-dir
with an optional --layout). No cells are removed or modified; the count threshold
reported (--low-count) is descriptive only.

Outputs in OUT_DIR (must not exist unless --overwrite):
  tables/native_metrics.csv       metrics_summary.csv and experiment.xenium values
  tables/native_alerts.csv        alerts parsed from analysis_summary.html
  tables/panel_features.csv       feature classes and matrix totals; gene_panel.json classes
  tables/cell_signal_summary.csv  all cells / grouped / ungrouped / nonzero-gene cells
  tables/group_summary.csv        per group (when groups are supplied)
  tables/segmentation_summary.csv
  cell_qc.csv.gz                  per-cell descriptive fields
  run_log.json                    inputs, joins, coverage and parse status
"""
import argparse
import datetime
import glob
import json
import os
import platform
import re
import shutil
import sys

import h5py
import numpy as np
import pandas as pd

CONTROL_COLS = ["control_probe_counts", "genomic_control_counts", "control_codeword_counts",
                "unassigned_codeword_counts", "deprecated_codeword_counts"]
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("run_dir", help="Xenium output directory")
    p.add_argument("out_dir", help="New output directory")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--groups", help="CSV or parquet with cell_id and a group column (see --group-column)")
    g.add_argument("--cores-dir", help="Curated TMA crops: <dir>/<core>-<pos>-<block>/<same>.h5ad; obs index = cell_id")
    p.add_argument("--group-column", default="group", help="Group column in --groups (default: group)")
    p.add_argument("--layout", help="Optional layout CSV with core_id (joined to per-group summaries)")
    p.add_argument("--low-count", type=int, default=10,
                   help="Descriptive threshold for the fraction of cells below N gene transcripts (default 10)")
    p.add_argument("--overwrite", action="store_true", help="Allow an existing OUT_DIR")
    return p.parse_args(argv)


def finfo(path):
    s = os.stat(path)
    return {"path": path, "bytes": s.st_size,
            "mtime": datetime.datetime.fromtimestamp(s.st_mtime).isoformat(timespec="seconds")}


def native_metrics(run, log):
    rows, missing = [], []
    ms_path = os.path.join(run, "metrics_summary.csv")
    if os.path.exists(ms_path):
        ms = pd.read_csv(ms_path).iloc[0]
        rows += [{"metric": k, "value": v, "source": "metrics_summary.csv"}
                 for k, v in ms.items() if pd.notna(v) and str(v) != ""]
        missing = [k for k, v in ms.items() if pd.isna(v) or str(v) == ""]
    exp_path = os.path.join(run, "experiment.xenium")
    if os.path.exists(exp_path):
        exp = json.load(open(exp_path))
        for k, v in exp.items():
            if isinstance(v, (str, int, float, bool)) and v != "":
                rows.append({"metric": k, "value": v, "source": "experiment.xenium"})
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    if isinstance(v2, (str, int, float, bool)) and v2 != "":
                        rows.append({"metric": f"{k}.{k2}", "value": v2, "source": "experiment.xenium"})
    log["native_files"] = {"metrics_summary.csv": os.path.exists(ms_path),
                           "experiment.xenium": os.path.exists(exp_path)}
    log["missing_native_metrics"] = missing
    return pd.DataFrame(rows, columns=["metric", "value", "source"])


def native_alerts(run, log):
    path = os.path.join(run, "analysis_summary.html")
    alerts, status = [], "analysis_summary.html absent"
    if os.path.exists(path):
        status = "no 'alerts' key found"
        html = open(path, encoding="utf-8", errors="replace").read()
        dec = json.JSONDecoder()
        for m in re.finditer(r'"alerts"\s*:\s*', html):
            try:
                obj, _ = dec.raw_decode(html, m.end())
                status = "parsed"
                if isinstance(obj, list):
                    alerts += [a if isinstance(a, dict) else {"alert": a} for a in obj]
                elif isinstance(obj, dict):
                    for k, a in obj.items():
                        items = a if isinstance(a, list) else [a]
                        alerts += [{"group": k, **(x if isinstance(x, dict) else {"alert": x})} for x in items]
            except Exception as e:  # keep going; record why
                status = f"decode failed: {type(e).__name__}"
    log["alerts"] = {"parse_status": status, "n_alert_records": len(alerts)}
    return pd.DataFrame(alerts)


def read_matrix(run, log):
    with h5py.File(os.path.join(run, "cell_feature_matrix.h5"), "r") as f:
        m = f["matrix"]
        data, ind, ptr, shape = m["data"][:], m["indices"][:], m["indptr"][:], m["shape"][:]
        bc = m["barcodes"][:].astype(str)
        ftype = m["features/feature_type"][:].astype(str)
    nfeat, ncell = int(shape[0]), int(shape[1])
    assert len(ptr) == ncell + 1 and len(bc) == ncell, (shape, len(ptr), len(bc))
    col = np.repeat(np.arange(ncell), np.diff(ptr))
    gmask = (ftype == "Gene Expression")[ind]
    gene_counts = np.bincount(col, weights=np.where(gmask, data, 0), minlength=ncell).astype(np.int64)
    genes_det = np.bincount(col, weights=(gmask & (data > 0)).astype(np.int64), minlength=ncell).astype(np.int64)
    ft_tot = pd.Series(np.bincount(ind, weights=data, minlength=nfeat)).groupby(ftype).sum()
    panel = [{"feature_type": k, "n_features": int((ftype == k).sum()),
              "matrix_total_counts": int(ft_tot.get(k, 0))} for k in sorted(set(ftype))]
    try:
        gp = json.load(open(os.path.join(run, "gene_panel.json")))
        desc = pd.Series([str(t.get("type", {}).get("descriptor", "unknown"))
                          for t in gp["payload"]["targets"]]).value_counts()
        panel += [{"feature_type": f"gene_panel.json:{k}", "n_features": int(v), "matrix_total_counts": None}
                  for k, v in desc.items()]
        log["gene_panel_json"] = "parsed payload.targets"
    except Exception as e:
        log["gene_panel_json"] = f"not parsed: {type(e).__name__}"
    mx = pd.DataFrame({"cell_id": bc, "matrix_gene_counts": gene_counts, "genes_detected": genes_det})
    return mx, pd.DataFrame(panel), ncell


def read_cells(run, log):
    pq, csv = os.path.join(run, "cells.parquet"), os.path.join(run, "cells.csv.gz")
    if os.path.exists(pq):
        try:
            cells, src = pd.read_parquet(pq), "cells.parquet"
        except ImportError:
            if not os.path.exists(csv):
                raise
            cells, src = pd.read_csv(csv), "cells.csv.gz (parquet reader unavailable)"
    elif os.path.exists(csv):
        cells, src = pd.read_csv(csv), "cells.csv.gz"
    else:
        sys.exit("No cells.parquet or cells.csv.gz in run directory")
    cells["cell_id"] = cells["cell_id"].astype(str)
    log["cells_source"] = src
    return cells


def groups_from_table(path, column):
    t = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    if "cell_id" not in t.columns or column not in t.columns:
        sys.exit(f"--groups needs columns cell_id and {column}")
    return t[["cell_id", column]].rename(columns={column: "group"}).astype({"cell_id": str})


def groups_from_cores(cores_dir):
    memb = []
    for p in sorted(glob.glob(os.path.join(cores_dir, "*", "*.h5ad"))):
        folder = os.path.basename(os.path.dirname(p))
        with h5py.File(p, "r") as f:
            o = f["obs"]
            ids = o[o.attrs.get("_index", "_index")][:].astype(str)
        mm = re.match(r"^(.*)-([A-Z]+\d+)-(.+)$", folder)
        core_id, pos = (mm.group(1), mm.group(2)) if mm else (folder, "")
        memb.append(pd.DataFrame({"cell_id": ids, "group": core_id, "core_position": pos}))
    return (pd.concat(memb, ignore_index=True) if memb
            else pd.DataFrame(columns=["cell_id", "group", "core_position"]))


def summarise(df, low_count):
    r = {"n_cells": len(df), "gene_transcripts_total": int(df["transcript_counts"].sum())}
    for c in ["transcript_counts", "genes_detected", "cell_area", "nucleus_area"]:
        if c in df:
            for q, v in zip(QUANTILES, df[c].quantile(QUANTILES)):
                r[f"{c}_q{int(q * 100)}"] = float(v)
    r["frac_zero_gene_transcripts"] = float((df["transcript_counts"] == 0).mean())
    r[f"frac_lt{low_count}_gene_transcripts"] = float((df["transcript_counts"] < low_count).mean())
    if "nucleus_count" in df:
        r["frac_no_nucleus"] = float((df["nucleus_count"] == 0).mean())
        r["frac_multi_nucleus"] = float((df["nucleus_count"] > 1).mean())
    for c in CONTROL_COLS:
        if c in df:
            r[f"{c}_total"] = int(df[c].sum())
    return r


def main(argv=None):
    a = parse_args(argv)
    if os.path.exists(a.out_dir):
        if not a.overwrite:
            sys.exit(f"Output directory exists: {a.out_dir} (use --overwrite)")
        shutil.rmtree(a.out_dir)
    tables = os.path.join(a.out_dir, "tables")
    os.makedirs(tables)
    log = {"python": platform.python_version(), "numpy": np.__version__, "pandas": pd.__version__,
           "h5py": h5py.__version__, "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
           "run_dir": a.run_dir, "out_dir": a.out_dir, "groups": a.groups, "cores_dir": a.cores_dir,
           "layout": a.layout, "low_count_descriptive_only": a.low_count}
    names = ["metrics_summary.csv", "experiment.xenium", "gene_panel.json", "cells.parquet",
             "cells.csv.gz", "cell_feature_matrix.h5", "analysis_summary.html"]
    log["inputs"] = [finfo(os.path.join(a.run_dir, f)) for f in names if os.path.exists(os.path.join(a.run_dir, f))]

    native_metrics(a.run_dir, log).to_csv(os.path.join(tables, "native_metrics.csv"), index=False)
    native_alerts(a.run_dir, log).to_csv(os.path.join(tables, "native_alerts.csv"), index=False)
    mx, panel, ncell = read_matrix(a.run_dir, log)
    panel.to_csv(os.path.join(tables, "panel_features.csv"), index=False)

    cells = read_cells(a.run_dir, log).merge(mx, on="cell_id", how="outer", indicator=True)
    both = cells["_merge"] == "both"
    log["join"] = {"cells_table_rows": int(cells["_merge"].isin(["both", "left_only"]).sum()),
                   "matrix_cells": ncell,
                   "merge": {str(k): int(v) for k, v in cells["_merge"].value_counts().items()},
                   "transcript_counts_equals_matrix_gene_sum_frac":
                       float((cells.loc[both, "transcript_counts"] == cells.loc[both, "matrix_gene_counts"]).mean())
                       if both.any() else None}
    cells = cells.drop(columns="_merge")

    memb = None
    if a.groups:
        memb = groups_from_table(a.groups, a.group_column)
    elif a.cores_dir:
        memb = groups_from_cores(a.cores_dir)
    if memb is not None:
        dup = memb["cell_id"].duplicated(keep=False)
        log["group_membership"] = {"n_groups": int(memb["group"].nunique()),
                                   "cells_in_groups": int(memb["cell_id"].nunique()),
                                   "cells_in_multiple_groups": int(memb.loc[dup, "cell_id"].nunique()),
                                   "group_cells_not_in_native": int((~memb["cell_id"].isin(cells["cell_id"])).sum())}
        cells = cells.merge(memb[~dup], on="cell_id", how="left")  # ambiguous cells stay unassigned

    base = cells[cells["transcript_counts"].notna()]
    rows = [{"population": "all native cells", **summarise(base, a.low_count)}]
    if memb is not None:
        rows += [{"population": "cells in groups", **summarise(base[base["group"].notna()], a.low_count)},
                 {"population": "cells outside groups", **summarise(base[base["group"].isna()], a.low_count)}]
    rows.append({"population": "nonzero-gene cells", **summarise(base[base["transcript_counts"] > 0], a.low_count)})
    pd.DataFrame(rows).to_csv(os.path.join(tables, "cell_signal_summary.csv"), index=False)

    if memb is not None:
        keys = ["group"] + (["core_position"] if "core_position" in base else [])
        per = pd.DataFrame([{**dict(zip(keys, k if isinstance(k, tuple) else (k,))), **summarise(d, a.low_count)}
                            for k, d in base[base["group"].notna()].groupby(keys)])
        if a.layout:
            lay = pd.read_csv(a.layout)
            log["layout"] = {"layout_cores": int(lay["core_id"].nunique()),
                             "layout_without_cells": sorted(set(lay["core_id"]) - set(memb["group"])),
                             "groups_not_in_layout": sorted(set(memb["group"]) - set(lay["core_id"]))}
            per = per.merge(lay, left_on="group", right_on="core_id", how="left")
        per.to_csv(os.path.join(tables, "group_summary.csv"), index=False)

    if "segmentation_method" in base:
        seg = (base.groupby("segmentation_method", dropna=False)
               .agg(n_cells=("cell_id", "size"), median_gene_transcripts=("transcript_counts", "median"),
                    median_cell_area=("cell_area", "median")).reset_index())
        seg["frac_cells"] = seg["n_cells"] / len(base)
        seg.to_csv(os.path.join(tables, "segmentation_summary.csv"), index=False)

    keep = ["cell_id", "group", "core_position", "x_centroid", "y_centroid", "transcript_counts",
            "matrix_gene_counts", "genes_detected", *CONTROL_COLS, "total_counts", "cell_area",
            "nucleus_area", "nucleus_count", "segmentation_method"]
    cells[[c for c in keep if c in cells]].to_csv(os.path.join(a.out_dir, "cell_qc.csv.gz"),
                                                  index=False, compression="gzip")
    log["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    json.dump(log, open(os.path.join(a.out_dir, "run_log.json"), "w"), indent=2, default=str)
    print(json.dumps({k: log.get(k) for k in ["cells_source", "join", "group_membership", "alerts"]}, default=str))


if __name__ == "__main__":
    main()
