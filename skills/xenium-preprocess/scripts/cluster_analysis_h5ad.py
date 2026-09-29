#!/usr/bin/env python
"""GPU embedding and clustering of a counts H5AD (rapids-singlecell): Pearson residuals, PCA,
optional Harmony, kNN graph, Leiden, UMAP, markers and per-cluster QC.

Cells: optional boolean obs column (--select-column) and/or minimum gene counts / genes detected
computed from the counts matrix (--min-counts, --min-genes).
Residuals: analytic Pearson residuals (negative binomial, --theta, clip +-sqrt(n cells)), as in
scanpy's normalize_pearson_residuals. If the panel has more genes than --n-top-genes, genes are
ranked by residual variance over all genes (one pass, no batch key) and the top N kept; residuals
are then recomputed on the kept genes (cell totals and gene frequencies on those genes only).
PCA: exact covariance PCA on the residuals (chunked on GPU, centred, --n-pcs components; component
sign fixed so the largest-magnitude loading is positive).
Harmony (rapids-singlecell harmony_integrate) on --batch-key; skipped when the key is not given,
absent, or has one level (corrected PCs = uncorrected PCs).
Graph: --n-neighbors kNN on the corrected PCs; Leiden at each --resolutions value; UMAP on the graph.
Markers use a common scale (normalize_total 1e4 + log1p): per cluster, genes ranked by mean log
difference versus all other cells, strict (detected in >= 20% of the cluster, top 30) and relaxed
(>= 5% and above the rest, top 20). This is a ranking for annotation support, not a test.
Per-cluster sums are exact (chunked bincount); the run stops if cluster detections differ from the
matrix non-zeros or cluster counts from the total (run_info cluster_sum_check). Versions 1.1 and earlier
used a GPU sparse product that undercounted detections (measured on multi-million-cell inputs); their
marker and cluster QC tables should be recomputed.
Cluster QC: size, depth quantiles, genes detected, fraction of cells below half the overall median
depth, low_depth flag (cluster median < 0.5 x overall median = depth-defined cluster), top-count
gene and its share, batch entropy, regions with >= 30 cells.

Outputs (--out-dir): cells.parquet (obs_name, depth, clusters, UMAP), genes.csv, embedding_model.npz
(genes, gene_frequency, theta, clip, loadings, mean, explained variance: enough to project cells
that were not embedded), pcs_uncorrected.npy, pcs_corrected.npy (row order = cells.parquet),
cluster_qc_res<r>.csv, markers_res<r>.csv, markers_relaxed_res<r>.csv,
cluster_gene_summary_res<marker res>.csv.gz, run_info.json, and with --write-h5ad clustered.h5ad
(selected cells: obs + clusters, layers['counts'], obsm spatial/X_pca/X_pca_harmony/X_umap).

Example:
  python cluster_analysis_h5ad.py --h5ad counts.h5ad --out-dir cluster/v1 --select-column pass_floor \\
      --batch-key run_name --resolutions 0.5,1.0,1.5 --write-h5ad
"""
import argparse, json, os, resource, time

import numpy as np
import pandas as pd
import scipy.sparse as sp

VERSION = "1.2"


def cluster_gene_sums(C, lib, lab, ncl, xp=np, chunk=100_000):
    """Per-cluster gene sums of a CSR counts matrix: counts, detections and log1p(1e4 x / lib).

    Works on SciPy/NumPy or CuPy inputs (xp). Chunked COO + bincount, exact for counts and detections.
    Replaces the sparse product indicator @ counts, which undercounted detections on the GPU on
    multi-million-cell inputs."""
    G = C.shape[1]; lab = xp.asarray(lab).astype(xp.int64); lib = xp.asarray(lib, dtype=xp.float64)
    Sc = xp.zeros(ncl * G, xp.float64); NZ = xp.zeros(ncl * G, xp.float64); SL = xp.zeros(ncl * G, xp.float64)
    for i0 in range(0, C.shape[0], chunk):
        Q = C[i0:i0 + chunk].tocoo()
        row = Q.row.astype(xp.int64) + i0
        idx = lab[row] * G + Q.col.astype(xp.int64)
        x = Q.data.astype(xp.float64)
        Sc += xp.bincount(idx, weights=x, minlength=ncl * G)
        NZ += xp.bincount(idx, weights=(x != 0).astype(xp.float64), minlength=ncl * G)
        SL += xp.bincount(idx, weights=xp.log1p(x * (1e4 / lib[row])), minlength=ncl * G)
    return Sc.reshape(ncl, G), NZ.reshape(ncl, G), SL.reshape(ncl, G)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h5ad", required=True, help="counts H5AD (e.g. from build_analysis_h5ad.py)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--layer", default="counts", help="layer with raw counts; 'X' for .X [counts]")
    ap.add_argument("--select-column", default=None, help="boolean obs column; keep cells where True")
    ap.add_argument("--min-counts", type=float, default=0, help="minimum gene counts per cell [0]")
    ap.add_argument("--min-genes", type=int, default=0, help="minimum genes detected per cell [0]")
    ap.add_argument("--n-top-genes", type=int, default=2000,
                    help="residual-variance genes; all genes when the panel has <= this many [2000]")
    ap.add_argument("--theta", type=float, default=100.0, help="NB overdispersion for residuals [100]")
    ap.add_argument("--n-pcs", type=int, default=50)
    ap.add_argument("--batch-key", default=None, help="obs column for Harmony (e.g. run or slide)")
    ap.add_argument("--region-key", default="region_id", help="obs column with region ids [region_id]")
    ap.add_argument("--n-neighbors", type=int, default=15)
    ap.add_argument("--resolutions", default="0.5,1.0,1.5", help="comma-separated Leiden resolutions")
    ap.add_argument("--marker-resolution", type=float, default=None,
                    help="resolution for the full cluster x gene summary [1.0 if listed, else first]")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-umap", action="store_true")
    ap.add_argument("--write-h5ad", action="store_true", help="also write clustered.h5ad")
    ap.add_argument("--chunk", type=int, default=100_000, help="cells per GPU chunk [100000]")
    return ap.parse_args()


def main():
    args = parse_args()
    import anndata as ad
    import cupy as cp
    import cupyx.scipy.sparse as csp
    import rapids_singlecell as rsc

    t0 = time.time(); T = {}; gpu_peak = [0]
    os.makedirs(args.out_dir, exist_ok=True)
    O = lambda f: os.path.join(args.out_dir, f)
    def log(*a): print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)
    def sync():
        cp.cuda.Device().synchronize()
        free, total = cp.cuda.runtime.memGetInfo()   # device-wide (whole-node allocation)
        gpu_peak[0] = max(gpu_peak[0], total - free)
    def to_np(x): return cp.asnumpy(x) if isinstance(x, cp.ndarray) else np.asarray(x)
    def tic(): sync(); return time.time()
    res_list = [float(r) for r in args.resolutions.split(",")]
    mres = args.marker_resolution if args.marker_resolution is not None else (1.0 if 1.0 in res_list else res_list[0])
    assert mres in res_list, "--marker-resolution must be one of --resolutions"
    THETA, NPC, CH, SEED = args.theta, args.n_pcs, args.chunk, args.seed

    # ---------------- data and cell selection
    t = time.time()
    a = ad.read_h5ad(args.h5ad)
    Call = a.X if args.layer == "X" else a.layers[args.layer]
    Call = sp.csr_matrix(Call)
    lib_all = np.asarray(Call.sum(1)).ravel().astype(np.float64)
    Call.eliminate_zeros(); ng_all = np.diff(Call.indptr)
    keep = (lib_all >= args.min_counts) & (ng_all >= args.min_genes)
    if args.select_column:
        sc = a.obs[args.select_column]
        if sc.dtype != bool:   # categorical/str columns from joins: 'True'/'1' count as True
            sc = sc.astype(str).str.lower().isin(["true", "1", "1.0"])
        keep &= sc.values.astype(bool)
    genes = np.asarray(a.var_names).astype(str)
    obs = a.obs.loc[keep].copy()
    C = sp.csr_matrix(Call[keep], dtype=np.float32); C.eliminate_zeros(); C.sort_indices()
    if not args.write_h5ad:
        del a
    del Call
    N, G = C.shape
    lib = lib_all[keep]; ngenes = np.diff(C.indptr)
    MED = float(np.median(lib))
    batch_key = args.batch_key
    harmony_note = "applied"
    if not batch_key:
        harmony_note = "skipped: no --batch-key"
    elif batch_key not in obs:
        harmony_note = f"skipped: obs has no column {batch_key!r}"
    elif obs[batch_key].astype(str).nunique() < 2:
        harmony_note = f"skipped: {batch_key!r} has one level"
    batch = obs[batch_key].astype(str).values if batch_key and batch_key in obs else None
    region = obs[args.region_key].astype(str).values if args.region_key in obs else None
    T["load_s"] = time.time() - t
    log("cells", N, "of", len(keep), "genes", G, "median counts", MED, "harmony", harmony_note)

    Cg = csp.csr_matrix(C); libg = cp.asarray(lib, dtype=cp.float32)
    chunks = [(i, min(i + CH, N)) for i in range(0, N, CH)]
    clip = float(np.sqrt(N))

    def residuals(D, n_c, pg):
        mu = n_c[:, None] * pg[None, :]
        den = cp.sqrt(mu + mu * mu / THETA)
        R = cp.where(mu > 0, (D - mu) / cp.where(mu > 0, den, 1), 0)   # zero-mean cell/gene: residual 0
        return cp.clip(R, -clip, clip).astype(cp.float32)

    # ---------------- gene selection by residual variance
    t = tic()
    rvar = np.full(G, np.nan)
    if G > args.n_top_genes:
        pg_all = (Cg.sum(0).ravel() / Cg.sum()).astype(cp.float32)
        s = cp.zeros(G, cp.float64); ss = cp.zeros(G, cp.float64)
        for i0, i1 in chunks:
            R = residuals(Cg[i0:i1].toarray(), libg[i0:i1], pg_all).astype(cp.float64)
            s += R.sum(0); ss += (R ** 2).sum(0)
        v = (ss - s ** 2 / N) / (N - 1); rvar = to_np(v)
        gidx = np.sort(to_np(cp.argsort(-v)[:args.n_top_genes]))
        del R, s, ss, v
    else:
        gidx = np.arange(G)
    gi = cp.asarray(gidx)
    n_c = cp.zeros(N, cp.float32); colsum = cp.zeros(len(gidx), cp.float64)
    for i0, i1 in chunks:
        D = Cg[i0:i1].toarray()[:, gi]; n_c[i0:i1] = D.sum(1); colsum += D.sum(0)
    pg = (colsum / colsum.sum()).astype(cp.float32)
    f = lambda i0, i1: residuals(Cg[i0:i1].toarray()[:, gi], n_c[i0:i1], pg)
    sel = np.zeros(G, bool); sel[gidx] = True
    gfreq = np.full(G, np.nan); gfreq[gidx] = to_np(pg)
    pd.DataFrame({"gene": genes, "selected": sel, "residual_variance": rvar,
                  "gene_frequency": gfreq}).to_csv(O("genes.csv"), index=False)
    T["gene_selection_s"] = time.time() - t
    log("genes used", len(gidx))

    # ---------------- exact covariance PCA
    t = tic()
    s = None; XtX = None
    for i0, i1 in chunks:
        D = f(i0, i1)
        cs = D.sum(0, dtype=cp.float64); g = (D.T @ D).astype(cp.float64)
        s = cs if s is None else s + cs; XtX = g if XtX is None else XtX + g
    mu = s / N; cov = (XtX - N * cp.outer(mu, mu)) / (N - 1)
    w, V = cp.linalg.eigh(cov); o = cp.argsort(-w); w = w[o]; V = V[:, o[:NPC]]
    sgn = cp.sign(V[cp.argmax(cp.abs(V), 0), cp.arange(NPC)]); V = (V * sgn).astype(cp.float32)
    evr = to_np(w[:NPC] / w.sum()); mu32 = mu.astype(cp.float32)
    Z = cp.empty((N, NPC), cp.float32)
    for i0, i1 in chunks:
        Z[i0:i1] = (f(i0, i1) - mu32) @ V
    Zu = to_np(Z); del Z, D, XtX, cov
    np.savez(O("embedding_model.npz"), genes=genes[gidx], gene_frequency=to_np(pg), theta=THETA, clip=clip,
             n_fit_cells=N, loadings=to_np(V), mean=to_np(mu32), explained_variance_ratio=evr,
             batch_key=str(batch_key))
    np.save(O("pcs_uncorrected.npy"), Zu)
    T["pca_s"] = time.time() - t
    log("pca done, explained variance (sum)", float(evr.sum()))

    # ---------------- Harmony, graph, Leiden, UMAP
    t = tic()
    h = ad.AnnData(obs=pd.DataFrame(index=obs.index.astype(str)))
    h.obsm["X_pca"] = Zu
    if harmony_note == "applied":
        h.obs["batch"] = batch
        rsc.pp.harmony_integrate(h, key="batch", basis="X_pca", adjusted_basis="X_pca_harmony", rng=SEED)
        h.obsm["X_pca_harmony"] = to_np(h.obsm["X_pca_harmony"]).astype(np.float32)
    else:
        h.obsm["X_pca_harmony"] = Zu
    np.save(O("pcs_corrected.npy"), h.obsm["X_pca_harmony"])
    T["harmony_s"] = time.time() - t
    t = tic()
    rsc.pp.neighbors(h, n_neighbors=args.n_neighbors, use_rep="X_pca_harmony", rng=SEED)
    T["neighbors_s"] = time.time() - t
    labs = {}
    for r in res_list:
        t = tic()
        rsc.tl.leiden(h, resolution=r, key_added=f"leiden_{r}", rng=SEED)
        labs[r] = h.obs[f"leiden_{r}"].astype(int).values
        T[f"leiden_{r}_s"] = time.time() - t
    log("clusters", {r: int(labs[r].max()) + 1 for r in res_list})
    U = None
    if not args.no_umap:
        t = tic(); before = set(h.obsm.keys())
        rsc.tl.umap(h, rng=SEED)
        new = [k for k in h.obsm.keys() if k not in before] or ["X_umap"]
        U = to_np(h.obsm[new[0]]).astype(np.float32)
        T["umap_s"] = time.time() - t
    del h
    sync()

    cells = pd.DataFrame({"obs_name": obs.index.astype(str), "gene_counts": lib, "genes_detected": ngenes})
    if region is not None: cells["region_id"] = region
    if batch is not None: cells["batch"] = batch
    for r in res_list: cells[f"leiden_{r}"] = pd.Categorical(labs[r].astype(str))
    if U is not None: cells["umap1"], cells["umap2"] = U[:, 0], U[:, 1]
    cells.to_parquet(O("cells.parquet"), index=False)

    # ---------------- markers and cluster QC
    t = tic()
    total_counts, nnz = float(Cg.data.sum(dtype=cp.float64)), int(Cg.nnz); agg_check = {}
    cellarea = obs["cell_area"].to_numpy(float) if "cell_area" in obs else None
    nucarea = obs["nucleus_area"].to_numpy(float) if "nucleus_area" in obs else None

    def entropy(lab, grp):
        ct = pd.crosstab(lab, grp); share = ct.sum(axis=0) / ct.values.sum()
        p = ct / share; p = p.div(p.sum(axis=1), axis=0)
        ent = -(p * np.log(p.where(p > 0, 1))).sum(axis=1) / np.log(max(ct.shape[1], 2))
        return ent, ct.max(axis=1) / ct.sum(axis=1)

    for r in res_list:
        lab = labs[r]; ncl = int(lab.max()) + 1
        n = cp.asarray(np.bincount(lab, minlength=ncl), dtype=cp.float32)[:, None]
        Sc, NZ, SL = cluster_gene_sums(Cg, libg, lab, ncl, xp=cp, chunk=CH)
        agg_check[str(r)] = {"detections": float(NZ.sum()), "counts": float(Sc.sum())}
        assert agg_check[str(r)]["detections"] == nnz, f"cluster detections {agg_check[str(r)]} != nnz {nnz}"
        assert abs(agg_check[str(r)]["counts"] - total_counts) <= 1e-9 * total_counts + 0.5, "cluster counts != total"
        pin = NZ / n; pout = (NZ.sum(0) - NZ) / cp.maximum(N - n, 1)
        min_ = SL / n; mout = (SL.sum(0) - SL) / cp.maximum(N - n, 1)
        diff = to_np(min_ - mout); pin_h, pout_h = to_np(pin), to_np(pout)
        min_h, mout_h = to_np(min_), to_np(mout)
        strict, relaxed = [], []
        for i in range(ncl):
            order = np.argsort(-diff[i])
            ks = [g for g in order if pin_h[i, g] >= 0.2][:30]
            kr = [g for g in order if pin_h[i, g] >= 0.05 and pin_h[i, g] > pout_h[i, g]][:20]
            for rows, kk in ((strict, ks), (relaxed, kr)):
                rows += [{"cluster": i, "rank": k + 1, "gene": genes[g], "mean_log_in": float(min_h[i, g]),
                          "mean_log_out": float(mout_h[i, g]), "mean_log_diff": float(diff[i, g]),
                          "pct_in": float(pin_h[i, g]), "pct_out": float(pout_h[i, g])} for k, g in enumerate(kk)]
        MKC = ["cluster", "rank", "gene", "mean_log_in", "mean_log_out", "mean_log_diff", "pct_in", "pct_out"]
        mk = pd.DataFrame(strict, columns=MKC); mk.to_csv(O(f"markers_res{r}.csv"), index=False)
        pd.DataFrame(relaxed, columns=MKC).to_csv(O(f"markers_relaxed_res{r}.csv"), index=False)
        df = pd.DataFrame({"lab": lab, "lib": lib, "ng": ngenes, "below": lib < 0.5 * MED})
        if cellarea is not None: df["cell_area"] = cellarea
        if nucarea is not None: df["nucleus_area"] = nucarea
        gb = df.groupby("lab")
        tq = lambda q: gb.lib.quantile(q).values
        Sc_h = to_np(Sc)
        tab = pd.DataFrame({"cluster": np.arange(ncl), "cells": gb.size().values,
                            "cell_fraction": gb.size().values / N,
                            "gene_counts_q25": tq(0.25), "gene_counts_median": tq(0.5), "gene_counts_q75": tq(0.75),
                            "genes_detected_median": gb.ng.median().values,
                            "fraction_below_half_overall_median": gb.below.mean().values,
                            "top_count_gene": genes[Sc_h.argmax(1)],
                            "top_count_gene_share": Sc_h.max(1) / Sc_h.sum(1),
                            "genes_detected_in_20pct": (pin_h >= 0.2).sum(1)})
        tab.insert(7, "low_depth", tab.gene_counts_median < 0.5 * MED)
        if cellarea is not None: tab["cell_area_median"] = gb.cell_area.median().values
        if nucarea is not None: tab["nucleus_area_median"] = gb.nucleus_area.median().values
        if batch is not None:
            ent, top = entropy(lab, batch)
            tab["batch_entropy_normalised"] = ent.values; tab["top_batch_fraction"] = top.values
        if region is not None:
            tab["regions_with_30_cells"] = (pd.crosstab(lab, region) >= 30).sum(axis=1).values
        tab["top_markers"] = [";".join(mk.loc[(mk.cluster == i) & (mk["rank"] <= 10), "gene"]) for i in range(ncl)]
        tab.to_csv(O(f"cluster_qc_res{r}.csv"), index=False)
        if r == mres:
            pd.DataFrame({"cluster": np.repeat(np.arange(ncl), G), "gene": np.tile(genes, ncl),
                          "mean_log": min_h.ravel(), "pct": pin_h.ravel(), "mean_log_rest": mout_h.ravel(),
                          "pct_rest": pout_h.ravel()}).to_csv(O(f"cluster_gene_summary_res{r}.csv.gz"),
                                                              index=False, float_format="%.5g")
        del Sc, NZ, SL
    sync(); T["markers_qc_s"] = time.time() - t
    low = {r: int(pd.read_csv(O(f"cluster_qc_res{r}.csv")).low_depth.sum()) for r in res_list}
    log("markers and cluster QC done; low-depth clusters", low)

    if args.write_h5ad:
        t = time.time()
        b = a[keep].copy(); del a
        for r in res_list: b.obs[f"leiden_{r}"] = pd.Categorical(labs[r].astype(str))
        b.obsm["X_pca"] = Zu; b.obsm["X_pca_harmony"] = np.load(O("pcs_corrected.npy"))
        if U is not None: b.obsm["X_umap"] = U
        b.var["residual_genes"] = sel
        b.uns["clustering"] = {"script": "cluster_analysis_h5ad.py", "script_version": VERSION,
                               "input": os.path.abspath(args.h5ad), "harmony": harmony_note,
                               "params": json.dumps({k: v for k, v in vars(args).items()})}
        b.write_h5ad(O("clustered.h5ad")); del b
        T["write_h5ad_s"] = time.time() - t

    from importlib.metadata import version
    info = {"script": "cluster_analysis_h5ad.py", "script_version": VERSION, "input": os.path.abspath(args.h5ad),
            "params": vars(args), "cells_input": int(len(keep)), "cells_used": int(N), "genes_panel": int(G),
            "genes_used": int(len(gidx)), "median_gene_counts": MED, "residual_clip": clip,
            "pca_explained_variance_sum": float(evr.sum()), "harmony": harmony_note,
            "batch_levels": int(pd.Series(batch).nunique()) if batch is not None else 0,
            "n_clusters": {str(r): int(labs[r].max()) + 1 for r in res_list},
            "n_low_depth_clusters": {str(r): low[r] for r in res_list},
            "cluster_sum_check": {"nnz": nnz, "total_counts": total_counts, "by_resolution": agg_check},
            "versions": {"rapids_singlecell": rsc.__version__, "anndata": version("anndata"),
                         "scanpy": version("scanpy"), "cupy": cp.__version__},
            "timing_s": {k: round(v, 1) for k, v in T.items()}, "elapsed_s": round(time.time() - t0, 1),
            "peak_gpu_device_used_gb_at_checkpoints": round(gpu_peak[0] / 1e9, 2),
            "peak_host_rss_gb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6, 2)}
    json.dump(info, open(O("run_info.json"), "w"), indent=1, default=str)
    log("done", info["timing_s"])


if __name__ == "__main__":
    main()
