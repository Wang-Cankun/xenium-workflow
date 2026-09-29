#!/usr/bin/env python
"""Build one analysis H5AD (raw counts) from native Xenium Onboard Analysis (XOA) output folders.

Each manifest row is one region (one XOA output folder). For every region with a
cell_feature_matrix.h5, gene-expression features go to layers['counts'] (CSR int32, X empty);
every other feature class (negative control probe/codeword, genomic control, unassigned and
deprecated codewords) is summed per cell into obs['matrix_<class>']. Cell metadata come from
cells.parquet (or cells.csv.gz); rows follow the matrix barcode order. obs_names are
'<region_id>_<cell_id>'; obsm['spatial'] holds (x_centroid, y_centroid) in micrometres in each
region's own slide frame. Regions without a matrix are reported and skipped (their cells-table rows
are written to <name>_cells_without_matrix.parquet). No cells are filtered.

Outputs in --out-dir: <name>.h5ad, <name>_region_status.csv, <name>_summary.json and, when
applicable, <name>_cells_without_matrix.parquet. If any region fails to read, the status table is
written and the script exits 1 without writing the H5AD.

Example:
  python build_analysis_h5ad.py --manifest regions.csv --id-col region_id --path-col xoa_dir \\
      --out-dir /path/h5ad/v1 --name cohort_counts \\
      --join cell_flags.parquet --join-cols pass_floor,flag_low_density
"""
import argparse, json, os, resource, sys, time, traceback
from concurrent.futures import ProcessPoolExecutor

import h5py
import numpy as np
import pandas as pd
import scipy.sparse as sp

VERSION = "1.0"
GENE_TYPE = "Gene Expression"


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, help="CSV, one row per region")
    ap.add_argument("--id-col", default="region_id", help="manifest column with a unique region id [region_id]")
    ap.add_argument("--path-col", default="xoa_dir", help="manifest column with the XOA output folder [xoa_dir]")
    ap.add_argument("--input-root", default="", help="prefix for relative paths in --path-col")
    ap.add_argument("--meta-cols", default="all",
                    help="comma-separated manifest columns copied to obs (categorical); 'all' = every column "
                         "except id/path; 'none' = no extra columns [all]")
    ap.add_argument("--join", action="append", default=[],
                    help="per-cell table (parquet/csv) to left-join onto obs; keyed by obs_name, or by "
                         "region_id + cell_id. Repeatable (e.g. QC flags, a cell->group mapping)")
    ap.add_argument("--join-cols", action="append", default=[],
                    help="comma-separated columns to take from the matching --join table (default all)")
    ap.add_argument("--join-prefix", default="", help="prefix added to joined column names")
    ap.add_argument("--gene-mismatch", choices=["error", "intersect"], default="error",
                    help="regions with different gene sets: fail, or keep the common genes [error]")
    ap.add_argument("--check-transcript-counts", action="store_true",
                    help="require matrix gene sums == cells-table transcript_counts (fails the region otherwise)")
    ap.add_argument("--workers", type=int, default=8, help="parallel region readers [8]")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--name", default="analysis_counts", help="output file stem [analysis_counts]")
    return ap.parse_args()


def dec(a):
    return np.array([x.decode() if isinstance(x, bytes) else str(x) for x in a])


def read_cells(p):
    for fn, reader in (("cells.parquet", pd.read_parquet), ("cells.csv.gz", pd.read_csv)):
        f = os.path.join(p, fn)
        if os.path.isfile(f):
            c = reader(f)
            c["cell_id"] = dec(c["cell_id"].values)
            assert c.cell_id.is_unique, f"duplicate cell_id in {fn}"
            return c, fn
    return None, None


def read_experiment(p):
    f = os.path.join(p, "experiment.xenium")
    if not os.path.isfile(f):
        return {}
    d = json.load(open(f))
    keys = ["analysis_sw_version", "panel_name", "panel_design_id", "panel_num_targets_predesigned",
            "panel_num_targets_custom"]
    return {k: d.get(k) for k in keys if k in d}


def read_region(task):
    """Read one region; returns a dict (never raises)."""
    rid, p, check_tx = task
    out = {"region_id": rid, "path": p}
    try:
        out.update(read_experiment(p))
        cells, cfile = read_cells(p)
        out["cells_table"] = cfile
        h5 = os.path.join(p, "cell_feature_matrix.h5")
        if not os.path.isfile(h5):
            out.update(outcome="no matrix", cells=0 if cells is None else len(cells), obs=cells)
            return out
        assert cells is not None, "cell_feature_matrix.h5 present but no cells.parquet / cells.csv.gz"
        with h5py.File(h5, "r") as f:
            g = f["matrix"]
            m = sp.csc_matrix((g["data"][:], g["indices"][:], g["indptr"][:]), shape=tuple(g["shape"][:]))
            ftype, fid, fname = (dec(g[f"features/{k}"][:]) for k in ("feature_type", "id", "name"))
            bc = dec(g["barcodes"][:])
        m = m.T.tocsr()
        assert len(set(bc)) == len(bc), "duplicate matrix barcodes"
        ci = pd.Index(cells.cell_id).get_indexer(bc)
        assert (ci >= 0).all(), f"{int((ci < 0).sum())} matrix barcodes missing from {cfile}"
        gmask = ftype == GENE_TYPE
        assert gmask.any(), f"no '{GENE_TYPE}' features"
        gm = m[:, np.where(gmask)[0]].astype(np.int32).tocsr()
        ob = cells.iloc[ci].reset_index(drop=True)
        for t in sorted(set(ftype[~gmask])):
            ob["matrix_" + t.lower().replace(" ", "_")] = np.asarray(m[:, np.where(ftype == t)[0]].sum(1)).ravel()
        ob["matrix_gene_counts"] = np.asarray(gm.sum(1)).ravel()
        ob["matrix_genes_detected"] = np.diff(gm.indptr)
        if check_tx and "transcript_counts" in ob:
            bad = int((ob.matrix_gene_counts.values != ob.transcript_counts.values).sum())
            assert bad == 0, f"{bad} cells with matrix gene sum != transcript_counts"
        out.update(outcome="in h5ad", cells=len(ob), cells_table_only=int(len(cells) - len(bc)),
                   nnz=int(gm.nnz), n_genes=int(gmask.sum()), obs=ob, X=gm,
                   gene_ids=fid[gmask], gene_symbols=fname[gmask],
                   control_classes=";".join(sorted(set(ftype[~gmask]))))
    except Exception as e:
        out.update(outcome="error", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc())
    return out


def join_tables(obs, args):
    info = []
    cols_per = args.join_cols + [""] * (len(args.join) - len(args.join_cols))
    for path, cols in zip(args.join, cols_per):
        t = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
        if "obs_name" in t:
            key = t["obs_name"].astype(str)
            t = t.drop(columns=[c for c in ("obs_name", "region_id", "cell_id") if c in t])
        elif {"region_id", "cell_id"} <= set(t.columns):
            key = t["region_id"].astype(str) + "_" + t["cell_id"].astype(str)
            t = t.drop(columns=["region_id", "cell_id"])
        else:
            raise ValueError(f"{path}: needs an obs_name column or region_id + cell_id")
        assert key.is_unique, f"{path}: duplicate keys"
        t.index = pd.Index(key.values)
        if cols:
            want = cols.split(",")
            miss = [c for c in want if c not in t]
            assert not miss, f"{path}: missing columns {miss}"
            t = t[want]
        t.columns = [args.join_prefix + c for c in t.columns]
        clash = [c for c in t.columns if c in obs]
        assert not clash, f"{path}: joined columns already in obs {clash}; use --join-prefix"
        t = t.reindex(obs.index)
        n_hit = int(t.notna().any(axis=1).sum())
        for c in t.columns:
            obs[c] = t[c].values
        info.append({"table": path, "columns": list(t.columns), "matched_cells": n_hit,
                     "unmatched_cells": int(len(obs) - n_hit)})
    return info


def peak_rss_gb():
    ru = [resource.getrusage(w).ru_maxrss for w in (resource.RUSAGE_SELF, resource.RUSAGE_CHILDREN)]
    return round(max(ru) / 1e6, 2)   # Linux reports kB


def main():
    args = parse_args()
    t0 = time.time()
    os.makedirs(args.out_dir, exist_ok=True)
    man = pd.read_csv(args.manifest, dtype=str, keep_default_na=False)
    for c in (args.id_col, args.path_col):
        assert c in man, f"manifest has no column {c!r}"
    assert man[args.id_col].is_unique, "region ids are not unique"
    if args.meta_cols == "all":
        meta = [c for c in man.columns if c not in (args.id_col, args.path_col)]
    elif args.meta_cols == "none":
        meta = []
    else:
        meta = args.meta_cols.split(",")
    meta = [c for c in meta if c != "region_id"]
    tasks = [(r[args.id_col], os.path.join(args.input_root, r[args.path_col]), args.check_transcript_counts)
             for _, r in man.iterrows()]
    with ProcessPoolExecutor(max_workers=max(1, args.workers)) as ex:
        res = list(ex.map(read_region, tasks))
    mrow = man.set_index(args.id_col)
    for r in res:
        print(r["region_id"], r["outcome"], r.get("cells"), r.get("error", ""), flush=True)
        if r["outcome"] == "error":
            print(r["trace"], file=sys.stderr)

    keep = ["region_id", "outcome", "cells", "cells_table_only", "nnz", "n_genes", "cells_table",
            "analysis_sw_version", "panel_name", "panel_design_id", "panel_num_targets_predesigned",
            "panel_num_targets_custom", "control_classes", "path", "error"]
    st = pd.DataFrame([{k: r.get(k) for k in keep} for r in res])
    st.to_csv(os.path.join(args.out_dir, f"{args.name}_region_status.csv"), index=False)
    if (st.outcome == "error").any():
        print("region errors:", st.loc[st.outcome == "error", ["region_id", "error"]].to_dict("records"))
        sys.exit(1)
    ok = [r for r in res if r["outcome"] == "in h5ad"]
    assert ok, "no region has a cell_feature_matrix.h5"

    # ---- common gene set (order of the first region)
    ids0 = ok[0]["gene_ids"]
    same = all(len(r["gene_ids"]) == len(ids0) and set(r["gene_ids"]) == set(ids0) for r in ok)
    if same:
        ref_ids = ids0
    elif args.gene_mismatch == "intersect":
        common = set.intersection(*(set(r["gene_ids"]) for r in ok))
        ref_ids = np.array([g for g in ids0 if g in common])
        print("gene sets differ; keeping", len(ref_ids), "common genes", flush=True)
    else:
        sizes = {r["region_id"]: len(r["gene_ids"]) for r in ok}
        sys.exit(f"gene sets differ between regions {sizes}; use --gene-mismatch intersect")
    sym = dict(zip(ok[0]["gene_ids"], ok[0]["gene_symbols"]))
    blocks, obs_parts = [], []
    for r in ok:
        order = pd.Index(r["gene_ids"]).get_indexer(ref_ids)
        blocks.append(r.pop("X")[:, order])
        ob = r.pop("obs")
        ob.insert(0, "region_id", r["region_id"])
        for c in meta:   # a manifest column that clashes with a cells-table column gets 'region_'
            ob[c if c not in ob else "region_" + c] = mrow.at[r["region_id"], c]
        ob.index = pd.Index(r["region_id"] + "_" + ob["cell_id"].values)
        obs_parts.append(ob)
    X = sp.vstack(blocks, format="csr")
    obs = pd.concat(obs_parts, axis=0, join="outer")
    del blocks, obs_parts
    assert obs.index.is_unique, "obs_names not unique (region_id + cell_id)"
    join_info = join_tables(obs, args) if args.join else []
    for c in obs.columns:
        if obs[c].dtype == object:
            obs[c] = obs[c].astype(str) if c == "cell_id" else obs[c].astype(str).astype("category")

    import anndata as ad
    var = pd.DataFrame({"gene_ids": ref_ids, "gene_symbols": [sym[g] for g in ref_ids]})
    var.index = pd.Index(var.gene_symbols if var.gene_symbols.is_unique else var.gene_ids).astype(str)
    spatial = obs[["x_centroid", "y_centroid"]].to_numpy(dtype=np.float64)
    a = ad.AnnData(X=None, obs=obs, var=var, layers={"counts": X}, obsm={"spatial": spatial})
    a.uns["build"] = {
        "script": "build_analysis_h5ad.py", "script_version": VERSION,
        "created": time.strftime("%Y-%m-%d %H:%M:%S"), "manifest": os.path.abspath(args.manifest),
        "input_root": args.input_root, "counts": "cell-assigned gene-expression counts from "
        "cell_feature_matrix.h5 (layers['counts']); other feature classes summed in obs matrix_*",
        "spatial_units": "micrometre", "spatial_frame": "native per-region slide coordinates",
        "filtering": "none", "gene_mismatch": "none" if same else args.gene_mismatch,
        "xoa_versions": sorted(set(st.loc[st.outcome == "in h5ad", "analysis_sw_version"].astype(str))),
        "panel_names": sorted(set(st.loc[st.outcome == "in h5ad", "panel_name"].astype(str))),
        "regions_without_matrix": st.loc[st.outcome == "no matrix", "region_id"].tolist(),
        "joined_tables": json.dumps(join_info)}
    a.uns["build_regions"] = st.drop(columns=["error"]).astype(str)
    out = os.path.join(args.out_dir, f"{args.name}.h5ad")
    a.write_h5ad(out)
    nom = [r["obs"].assign(region_id=r["region_id"]) for r in res
           if r["outcome"] == "no matrix" and r.get("obs") is not None]
    if nom:
        t = pd.concat(nom, axis=0, join="outer")
        for c in t.columns:
            if t[c].dtype == object:
                t[c] = t[c].astype(str)
        t.to_parquet(os.path.join(args.out_dir, f"{args.name}_cells_without_matrix.parquet"), index=False)
    summ = {"h5ad": out, "n_cells": int(a.n_obs), "n_genes": int(a.n_vars), "nnz": int(X.nnz),
            "regions_in_h5ad": len(ok), "regions_without_matrix": int((st.outcome == "no matrix").sum()),
            "cells_without_matrix": int(st.loc[st.outcome == "no matrix", "cells"].astype(float).sum()),
            "xoa_versions": a.uns["build"]["xoa_versions"], "panel_names": a.uns["build"]["panel_names"],
            "obs_columns": list(obs.columns), "joined_tables": join_info,
            "elapsed_s": round(time.time() - t0, 1), "peak_host_rss_gb": peak_rss_gb(),
            "bytes": os.path.getsize(out)}
    json.dump(summ, open(os.path.join(args.out_dir, f"{args.name}_summary.json"), "w"), indent=1, default=str)
    print(json.dumps(summ, default=str))


if __name__ == "__main__":
    main()
