#!/usr/bin/env python
"""Calibrated kNN label transfer for low-information Xenium cells (GPU; cuML + CuPy).

Takes a counts H5AD, the embedding written by cluster_analysis_h5ad.py (embedding_model.npz,
pcs_uncorrected.npy, pcs_corrected.npy, cells.parquet) and a per-cell label table that marks reference
cells and their QC-level type. Every query cell gets a type and lineage vote from its nearest reference
cells in the corrected (e.g. Harmony) space; vote thresholds are calibrated on reference cells binomially
thinned to fixed depths.

Cells
  embedded   rows of cells.parquet; labelled from corrected PCs. Reference cells are left out of their own
             neighbour set (leave-one-out).
  projected  query cells that were not embedded: Pearson residuals with the saved gene frequencies, theta
             and clip, projected with the saved loadings and mean, plus the mean Harmony offset (corrected
             minus uncorrected PCs) of their --offset-k nearest embedded cells of the same batch.
  not query  cells outside --query-column (or below --min-counts/--min-genes): status below_floor.

Calibration: --thin-n reference cells, each assigned one target depth from --thin-depths or left unthinned
(control); counts over all genes are binomially thinned to the target, cells falling below the floor are
dropped, the rest re-projected (offset and transfer both exclude the parent cell). The type (lineage)
threshold is the smallest --thresholds value whose accuracy on thinned cells below --target-below
transcripts reaches --type-target (--lineage-target) with at least 50 cells; if none does, the strictest
value is used and the achieved accuracy is reported.

Status: reference; rescued_type (type vote >= type threshold); rescued_lineage (only the lineage vote meets
its threshold); unresolved; unresolved_no_signal (< --min-signal counts on the embedding genes);
unresolved_failed_group (--hold-column True, e.g. whole-group failures; never reference or rescued);
below_floor. The best-guess type is kept for every labelled cell.

Independent checks: spatial agreement of each cell's best-guess lineage/type with its reference neighbours
(up to --spatial-k within --spatial-radius um, same --region-key group) against labels permuted within
region and status; pseudobulk correlation of rescued cells per type with reference profiles.

Label table (--labels, parquet or csv): obs_name, own_type (QC-level type of the cell's cluster; may be a
non-transferable value such as 'ambiguous'), reference (bool), optionally the --hold-column (bool). The hold
column is read from the label table and from the H5AD obs; a cell is held when either is True (label tables often
list only embedded cells, while cells of failed groups are mostly projected). Type map (--type-map, csv): type,
lineage; only these types are transferred, and every reference cell must carry one of them.

Outputs (--out-dir): labels.parquet, thinning_calibration.csv, thinning_accuracy_by_type.csv,
thinning_cells.parquet, thresholds.json, spatial_consistency.csv, pseudobulk_corr.csv, run_info.json.

Example:
  python rescue_labels.py --h5ad counts.h5ad --embedding-dir cluster/v1 --labels ref_labels.parquet \\
      --type-map type_map.csv --query-column pass_floor --batch-key run --region-key core_id --out-dir rescue/v1
"""
import argparse, json, os, time

import numpy as np
import pandas as pd
import scipy.sparse as sp

VERSION = "1.1"


def assign_status(type_vote, lineage_vote, signal, labelled, is_ref, hold, t_type, t_lin, min_signal):
    """Per-cell status from votes. Held cells (for example whole-group failures) are neither reference nor
    rescued: their groups have no calibrated reference, and on a real TMA transfer from other cores still
    gave most of a failed core's cells a rescued label. Votes and best guesses stay in their own columns."""
    s = np.where(type_vote >= t_type, "rescued_type", np.where(lineage_vote >= t_lin, "rescued_lineage", "unresolved"))
    s = np.where(signal < min_signal, "unresolved_no_signal", s).astype(object)
    s[hold] = "unresolved_failed_group"
    status = np.full(len(s), "below_floor", dtype=object)
    status[labelled] = s[labelled]
    status[is_ref & ~hold] = "reference"
    return status


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h5ad", required=True, help="counts H5AD (layers[--layer], obs_names match cells.parquet)")
    ap.add_argument("--layer", default="counts", help="raw counts layer, or X [counts]")
    ap.add_argument("--embedding-dir", required=True, help="output directory of cluster_analysis_h5ad.py")
    ap.add_argument("--labels", required=True, help="table: obs_name, own_type, reference")
    ap.add_argument("--type-map", required=True, help="csv: type, lineage")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--query-column", default=None, help="boolean obs column: cells to label (e.g. pass_floor)")
    ap.add_argument("--hold-column", default="flag_group_low_depth",
                    help="boolean column of the label table and/or H5AD obs; True cells are neither reference nor "
                         "rescued (status unresolved_failed_group); ignored when absent from both [flag_group_low_depth]")
    ap.add_argument("--min-counts", type=float, default=10, help="floor on gene counts for query cells [10]")
    ap.add_argument("--min-genes", type=int, default=5, help="floor on genes detected for query cells [5]")
    ap.add_argument("--batch-key", default=None, help="obs column used for Harmony [from embedding_model.npz]")
    ap.add_argument("--region-key", default="region_id", help="obs column grouping cells for the spatial check")
    ap.add_argument("--spatial-key", default="spatial", help="obsm key with x, y in um [spatial]")
    ap.add_argument("--k", type=int, default=30, help="reference neighbours for the vote [30]")
    ap.add_argument("--offset-k", type=int, default=15, help="embedded neighbours for the Harmony offset [15]")
    ap.add_argument("--min-signal", type=float, default=5, help="minimum counts on embedding genes [5]")
    ap.add_argument("--thin-depths", default="10,15,20,30,50,80,120", help="target depths for thinning")
    ap.add_argument("--thin-n", type=int, default=80000, help="reference cells used for calibration [80000]")
    ap.add_argument("--thresholds", default="0.30:0.95:0.05", help="vote threshold grid start:stop:step")
    ap.add_argument("--type-target", type=float, default=0.90); ap.add_argument("--lineage-target", type=float, default=0.95)
    ap.add_argument("--target-below", type=float, default=50, help="calibrate on thinned cells below this depth [50]")
    ap.add_argument("--spatial-radius", type=float, default=30.0); ap.add_argument("--spatial-k", type=int, default=10)
    ap.add_argument("--seed", type=int, default=0); ap.add_argument("--chunk", type=int, default=100_000)
    return ap.parse_args()


def read_table(p):
    return pd.read_parquet(p) if p.endswith(".parquet") else pd.read_csv(p)


def as_bool(s):
    return s.values.astype(bool) if s.dtype == bool else s.astype(str).str.lower().isin(["true", "1", "1.0"]).values


def hold_mask(lab, obs, column):
    """Held cells: `column` True in the label table or in the H5AD obs (both indexed like the H5AD). Returns the
    mask and the sources found; label tables often list only embedded cells, while cells of failed groups are
    mostly projected, so the obs column is needed to hold them."""
    m = np.zeros(len(obs), bool); src = []
    for name, tab in (("labels", lab), ("h5ad_obs", obs)):
        if column and column in tab.columns:
            s = tab[column].astype(object)
            m |= as_bool(s.where(s.notna(), False)); src.append(name)
    return m, src


def main():
    args = parse_args()
    import anndata as ad
    import cupy as cp
    from cuml.neighbors import NearestNeighbors
    from scipy.spatial import cKDTree

    t0 = time.time(); os.makedirs(args.out_dir, exist_ok=True)
    O = lambda f: os.path.join(args.out_dir, f)
    def log(*a): print(f"[{time.time() - t0:7.1f}s]", *a, flush=True)
    rng = np.random.default_rng(args.seed); K, KO, CH = args.k, args.offset_k, args.chunk
    INFO = {"script": "rescue_labels.py", "script_version": VERSION, "params": vars(args)}

    # ---------------- type map and labels
    tm = pd.read_csv(args.type_map).astype(str)
    assert {"type", "lineage"} <= set(tm.columns) and tm.type.is_unique, "type map needs unique type, lineage"
    TYPES = list(tm.type); LINS = sorted(set(tm.lineage)); tcode = {t: i for i, t in enumerate(TYPES)}
    T2L = np.array([LINS.index(l) for l in tm.lineage]); LIN = dict(zip(tm.type, tm.lineage))

    # ---------------- embedding
    E = args.embedding_dir
    cells = pd.read_parquet(os.path.join(E, "cells.parquet"), columns=["obs_name"])
    M = np.load(os.path.join(E, "embedding_model.npz"), allow_pickle=True)
    Vld, mu, genes_m = M["loadings"].astype(np.float32), M["mean"].astype(np.float32), M["genes"].astype(str)
    pg, THETA, CLIP = M["gene_frequency"].astype(np.float32), float(M["theta"]), float(M["clip"])
    NPC = Vld.shape[1]
    Zu_saved = np.load(os.path.join(E, "pcs_uncorrected.npy")); Zh = np.load(os.path.join(E, "pcs_corrected.npy")).astype(np.float32)
    assert Zh.shape == (len(cells), NPC) == Zu_saved.shape
    batch_key = args.batch_key or (str(M["batch_key"]) if "batch_key" in M and str(M["batch_key"]) != "None" else None)

    # ---------------- counts
    A = ad.read_h5ad(args.h5ad)
    obs = A.obs; obs.index = obs.index.astype(str); names = obs.index.values
    Call = sp.csr_matrix(A.X if args.layer == "X" else A.layers[args.layer], dtype=np.float32)
    Call.eliminate_zeros(); Call.sort_indices()
    xy_all = np.asarray(A.obsm[args.spatial_key])[:, :2].astype(float)
    genes = np.asarray(A.var_names).astype(str); del A
    lib = np.asarray(Call.sum(1)).ravel(); ng = np.diff(Call.indptr)
    query = (lib >= args.min_counts) & (ng >= args.min_genes)
    if args.query_column: query &= as_bool(obs[args.query_column])
    pos_e = obs.index.get_indexer(cells.obs_name.astype(str))
    assert (pos_e >= 0).all(), "embedded cells missing from the H5AD"
    in_emb = np.zeros(len(obs), bool); in_emb[pos_e] = True
    pos_x = np.where(query & ~in_emb)[0]
    nE, nX = len(pos_e), len(pos_x)
    batch = obs[batch_key].astype(str).values if batch_key else np.full(len(obs), "all")
    region = obs[args.region_key].astype(str).values if args.region_key in obs else np.full(len(obs), "all")
    gi = pd.Index(genes).get_indexer(genes_m); assert (gi >= 0).all(), "model genes missing from the H5AD"
    Cs = Call[:, gi].tocsr(); nsel = np.asarray(Cs.sum(1)).ravel()
    INFO.update(h5ad_cells=len(obs), embedded=nE, projected=nX, not_query=int((~query & ~in_emb).sum()),
                embedded_not_query=int((in_emb & ~query).sum()), model_genes=len(genes_m), n_pcs=NPC, batch_key=batch_key)
    log("cells", len(obs), "embedded", nE, "projected", nX, "genes", len(genes_m), "PCs", NPC)

    lab = read_table(args.labels); lab["obs_name"] = lab.obs_name.astype(str)
    assert lab.obs_name.is_unique
    lab = lab.set_index("obs_name").reindex(names)
    own = lab["own_type"].fillna("none").astype(str).values
    is_ref = as_bool(lab["reference"].fillna(False)) & in_emb
    hold, hold_src = hold_mask(lab, obs, args.hold_column)
    INFO["hold"] = {"column": args.hold_column if hold_src else None, "sources": hold_src, "held_cells": int(hold.sum()),
                    "reference_cells_held": int((is_ref & hold).sum())}
    log("held", int(hold.sum()), "from", hold_src or "none")
    is_ref &= ~hold
    bad = is_ref & ~np.isin(own, TYPES)
    assert not bad.any(), f"{int(bad.sum())} reference cells with a type outside the type map"
    ref_idx = np.where(is_ref)[0]                        # H5AD rows
    emb_row = -np.ones(len(obs), np.int64); emb_row[pos_e] = np.arange(nE)
    ref_rows = emb_row[ref_idx]                          # embedding rows
    ref_type = np.array([tcode[t] for t in own[ref_idx]]); ref_lin = T2L[ref_type]
    INFO["reference_cells"] = int(len(ref_idx))
    INFO["reference_by_type"] = pd.Series(own[ref_idx]).value_counts().to_dict()
    log("reference cells", len(ref_idx))

    # ---------------- projection
    pg_g, V_g, mu_g = cp.asarray(pg), cp.asarray(Vld), cp.asarray(mu)
    def project(Cq):
        n = Cq.shape[0]; Z = np.empty((n, NPC), np.float32); nc = np.asarray(Cq.sum(1)).ravel()
        for i0 in range(0, n, CH):
            i1 = min(i0 + CH, n); D = cp.asarray(Cq[i0:i1].toarray(), dtype=cp.float32)
            m = cp.asarray(nc[i0:i1], cp.float32)[:, None] * pg_g[None, :]
            den = cp.sqrt(m + m * m / THETA)
            R = cp.where(m > 0, (D - m) / cp.where(m > 0, den, 1), 0)
            Z[i0:i1] = cp.asnumpy((cp.clip(R, -CLIP, CLIP).astype(cp.float32) - mu_g) @ V_g)
        return Z
    Zu = project(Cs[pos_e])
    err = np.abs(Zu - Zu_saved).max(); delta = Zh - Zu_saved
    INFO["projection_check"] = {"max_abs_diff_reprojected_vs_saved_uncorrected": float(err),
                                "per_pc_corr_min": float(min(np.corrcoef(Zu[:, j], Zu_saved[:, j])[0, 1] for j in range(NPC))),
                                "harmony_offset_norm_median": float(np.median(np.linalg.norm(delta, axis=1))),
                                "corrected_norm_median": float(np.median(np.linalg.norm(Zh, axis=1)))}
    log("projection check", INFO["projection_check"])
    Zu = Zu_saved.astype(np.float32); batch_e = batch[pos_e]

    def offset(Zq, bq, exclude=None):
        out = Zq.copy()
        for b in np.unique(bq):
            qi = np.where(bq == b)[0]; ri = np.where(batch_e == b)[0]
            assert len(ri) > KO, f"batch {b}: too few embedded cells for the offset"
            nn = NearestNeighbors(n_neighbors=KO + 1).fit(cp.asarray(Zu[ri]))
            for c0 in range(0, len(qi), CH):
                qc = qi[c0:c0 + CH]; _, ind = nn.kneighbors(cp.asarray(Zq[qc])); g = ri[cp.asnumpy(ind)]
                drop = (g == exclude[qc][:, None]) if exclude is not None else np.zeros(g.shape, bool)
                o = np.argsort(drop, axis=1, kind="stable")[:, :KO]
                out[qc] = Zq[qc] + delta[np.take_along_axis(g, o, 1)].mean(1)
            del nn
        return out

    nnR = NearestNeighbors(n_neighbors=K + 1).fit(cp.asarray(Zh[ref_rows]))
    refpos = -np.ones(nE, np.int64); refpos[ref_rows] = np.arange(len(ref_rows))
    def transfer(Zq, exclude=None):
        n = len(Zq); ty = np.empty(n, np.int16); vt_ = np.empty(n, np.float32); li = np.empty(n, np.int16)
        vl_ = np.empty(n, np.float32); dm = np.empty(n, np.float32)
        for c0 in range(0, n, CH):
            c1 = min(c0 + CH, n); d, ind = nnR.kneighbors(cp.asarray(Zq[c0:c1])); d, ind = cp.asnumpy(d), cp.asnumpy(ind)
            drop = (ind == exclude[c0:c1][:, None]) if exclude is not None else np.zeros(ind.shape, bool)
            o = np.argsort(drop, axis=1, kind="stable")[:, :K]
            ind = np.take_along_axis(ind, o, 1); d = np.take_along_axis(d, o, 1)
            tl, ll = ref_type[ind], ref_lin[ind]
            vt = np.stack([(tl == t).sum(1) for t in range(len(TYPES))], 1)
            vl = np.stack([(ll == l).sum(1) for l in range(len(LINS))], 1)
            ty[c0:c1] = vt.argmax(1); vt_[c0:c1] = vt.max(1) / K; li[c0:c1] = vl.argmax(1); vl_[c0:c1] = vl.max(1) / K
            dm[c0:c1] = d.mean(1)
        return ty, vt_, li, vl_, dm

    log("transfer: embedded cells")
    ty_e, vt_e, li_e, vl_e, dm_e = transfer(Zh, exclude=refpos)
    INFO["reference_loo"] = {"type_accuracy": float((ty_e[ref_rows] == ref_type).mean()),
                             "lineage_accuracy": float((li_e[ref_rows] == ref_lin).mean())}
    log("projection + transfer:", nX, "cells")
    if nX:
        Zx = offset(project(Cs[pos_x]), batch[pos_x]); ty_x, vt_x, li_x, vl_x, dm_x = transfer(Zx)
    else:
        ty_x = li_x = np.empty(0, np.int16); vt_x = vl_x = dm_x = np.empty(0, np.float32)

    # ---------------- thinning calibration
    depths = np.array([int(x) for x in args.thin_depths.split(",")] + [-1])
    n_thin = min(args.thin_n, len(ref_idx))
    par = np.sort(rng.choice(len(ref_idx), n_thin, replace=False))     # index into ref arrays
    tgt = rng.choice(depths, n_thin)
    ph = ref_idx[par]; Cp = Call[ph].copy()
    p = np.where(tgt < 0, 1.0, np.minimum(tgt / lib[ph], 1.0))
    Cp.data = rng.binomial(Cp.data.astype(np.int64), np.repeat(p, np.diff(Cp.indptr))).astype(np.float32)
    Cp.eliminate_zeros(); tl_ = np.asarray(Cp.sum(1)).ravel(); tg_ = np.diff(Cp.indptr)
    ok = (tl_ >= args.min_counts) & (tg_ >= args.min_genes)
    INFO["thinning"] = {"sampled": int(n_thin), "dropped_below_floor": int((~ok).sum()),
                        "dropped_by_target": pd.Series(tgt[~ok]).value_counts().sort_index().to_dict()}
    par, tgt, Cp, tl_ = par[ok], tgt[ok], Cp[ok], tl_[ok]
    Cpm = Cp[:, gi].tocsr(); nsel_t = np.asarray(Cpm.sum(1)).ravel()
    log("thinning: projecting", len(par))
    Zt = offset(project(Cpm), batch[ref_idx[par]], exclude=ref_rows[par])
    ty_t, vt_t, li_t, vl_t, dm_t = transfer(Zt, exclude=par)
    tt, tl = ref_type[par], ref_lin[par]; ctrl = tgt < 0
    INFO["unthinned_control"] = {"cells": int(ctrl.sum()),
                                 "embedding_error_median": float(np.median(np.linalg.norm(Zt[ctrl] - Zh[ref_rows[par[ctrl]]], axis=1))),
                                 "type_accuracy": float((ty_t[ctrl] == tt[ctrl]).mean()),
                                 "lineage_accuracy": float((li_t[ctrl] == tl[ctrl]).mean())}
    log("unthinned control", INFO["unthinned_control"])
    edges = [0] + sorted(set(int(d) for d in depths if d > 0)) + [np.inf]
    lbl = [f"{int(edges[i])}-{int(edges[i + 1]) - 1}" if np.isfinite(edges[i + 1]) else f">={int(edges[i])}"
           for i in range(len(edges) - 1)]
    dbin = pd.cut(tl_, edges, right=False, labels=lbl)
    cal = pd.DataFrame({"obs_name": names[ref_idx[par]], "target_depth": tgt, "thinned_depth": tl_, "depth_bin": dbin,
                        "control": ctrl, "embedding_gene_counts": nsel_t, "true_type": np.array(TYPES)[tt],
                        "true_lineage": np.array(LINS)[tl], "best_type": np.array(TYPES)[ty_t], "type_vote": vt_t,
                        "best_lineage": np.array(LINS)[li_t], "lineage_vote": vl_t,
                        "type_ok": ty_t == tt, "lineage_ok": li_t == tl})
    cal.to_parquet(O("thinning_cells.parquet"), index=False)
    t0_, t1_, st_ = (float(x) for x in args.thresholds.split(":"))
    grid = np.round(np.arange(t0_, t1_ + st_ / 2, st_), 4)
    rows = []
    for (db, cc), g in cal.groupby(["depth_bin", "control"], observed=True):
        for thr in np.r_[0.0, grid]:
            mt, ml = g.type_vote >= thr, g.lineage_vote >= thr
            rows.append({"depth_bin": db, "control": cc, "threshold": thr, "cells": len(g),
                         "type_retained": float(mt.mean()), "type_accuracy_retained": float(g.type_ok[mt].mean()) if mt.any() else np.nan,
                         "lineage_retained": float(ml.mean()), "lineage_accuracy_retained": float(g.lineage_ok[ml].mean()) if ml.any() else np.nan})
    pd.DataFrame(rows).to_csv(O("thinning_calibration.csv"), index=False)
    cal.groupby(["depth_bin", "true_type"], observed=True).agg(cells=("type_ok", "size"), type_accuracy=("type_ok", "mean"),
        lineage_accuracy=("lineage_ok", "mean")).reset_index().to_csv(O("thinning_accuracy_by_type.csv"), index=False)
    low = (~ctrl) & (tl_ < args.target_below)
    def pick(vote, okv, target):
        for thr in grid:
            m = low & (vote >= thr)
            if m.sum() >= 50 and okv[m].mean() >= target: return float(thr), True
        return float(grid[-1]), False
    T_TYPE, met_t = pick(vt_t, cal.type_ok.values, args.type_target)
    T_LIN, met_l = pick(vl_t, cal.lineage_ok.values, args.lineage_target)
    thr = {"type_threshold": T_TYPE, "type_target_met": met_t, "lineage_threshold": T_LIN, "lineage_target_met": met_l,
           "rule": f"smallest vote with accuracy >= {args.type_target} (type) / {args.lineage_target} (lineage) on thinned "
                   f"cells below {args.target_below:g} transcripts (>= 50 cells); else the strictest grid value",
           "low_depth_cells": int(low.sum()),
           "low_depth_type_accuracy_unfiltered": float(cal.type_ok[low].mean()),
           "low_depth_lineage_accuracy_unfiltered": float(cal.lineage_ok[low].mean()),
           "low_depth_type_accuracy_at_threshold": float(cal.type_ok[low & (vt_t >= T_TYPE)].mean()),
           "low_depth_type_retained": float((vt_t[low] >= T_TYPE).mean()),
           "low_depth_lineage_accuracy_at_threshold": float(cal.lineage_ok[low & (vl_t >= T_LIN)].mean()),
           "low_depth_lineage_retained": float((vl_t[low] >= T_LIN).mean())}
    json.dump(thr, open(O("thresholds.json"), "w"), indent=1); INFO["thresholds"] = thr
    log("thresholds", thr)

    # ---------------- statuses
    n = len(obs)
    bt = np.full(n, -1, np.int32); vt = np.full(n, np.nan, np.float32); bl = np.full(n, -1, np.int32)
    vl = np.full(n, np.nan, np.float32); dm = np.full(n, np.nan, np.float32)
    for rows_, a_, b_, c_, d_, e_ in ((pos_e, ty_e, vt_e, li_e, vl_e, dm_e), (pos_x, ty_x, vt_x, li_x, vl_x, dm_x)):
        bt[rows_], vt[rows_], bl[rows_], vl[rows_], dm[rows_] = a_, b_, c_, d_, e_
    labelled = in_emb | query
    status = assign_status(vt, vl, nsel, labelled, is_ref, hold, T_TYPE, T_LIN, args.min_signal)
    TY, LI = np.array(TYPES + ["none"], dtype=object), np.array(LINS + ["none"], dtype=object)
    best_type = TY[bt]; best_lin = LI[bl]
    best_type[is_ref] = own[is_ref]; best_lin[is_ref] = [LIN[t] for t in own[is_ref]]
    label_type = np.where(np.isin(status, ["reference", "rescued_type"]), best_type, "unresolved")
    label_lin = np.where(np.isin(status, ["reference", "rescued_type"]), best_lin,
                         np.where(status == "rescued_lineage", best_lin, "unresolved"))
    label_type, label_lin = label_type.astype(object), label_lin.astype(object)
    label_type[status == "below_floor"] = "below_floor"; label_lin[status == "below_floor"] = "below_floor"
    best_type[~labelled] = "none"; best_lin[~labelled] = "none"
    R = pd.DataFrame({"obs_name": names, "batch": batch, "region": region,
                      "source": np.where(in_emb, "embedded", np.where(query, "projected", "not_query")),
                      "gene_counts": lib, "genes_detected": ng, "embedding_gene_counts": nsel, "own_type": own,
                      "is_reference": is_ref, "best_type": best_type, "type_vote": vt, "best_lineage": best_lin,
                      "lineage_vote": vl, "knn_dist_mean": dm, "status": status, "label_type": label_type,
                      "label_lineage": label_lin})
    R.to_parquet(O("labels.parquet"), index=False)
    INFO["status_counts"] = R.status.value_counts().to_dict()
    INFO["status_by_source"] = {k: v for k, v in pd.crosstab(R.source, R.status).to_dict(orient="index").items()}
    log("status", INFO["status_counts"])

    # ---------------- spatial check (coordinates only)
    log("spatial check")
    grp = np.where(is_ref, "reference", status)
    acc = []
    for rg in np.unique(region[labelled]):
        ir = np.where(labelled & (region == rg))[0]; rr = ir[is_ref[ir]]
        if len(rr) < 50: continue
        d, j = cKDTree(xy_all[rr]).query(xy_all[ir], k=args.spatial_k + 1, distance_upper_bound=args.spatial_radius)
        valid = np.isfinite(d); nb = rr[np.where(valid, j, 0)]; valid &= nb != ir[:, None]
        # keep at most spatial_k valid neighbours
        valid &= np.cumsum(valid, 1) <= args.spatial_k
        nt, nl = best_type[nb], best_lin[nb]
        pt, pl = best_type[ir].copy(), best_lin[ir].copy()
        for gname in np.unique(grp[ir]):
            w = np.where(grp[ir] == gname)[0]; pr = rng.permutation(w); pt[w] = pt[pr]; pl[w] = pl[pr]
        for kind, lt, ll in (("observed", best_type[ir], best_lin[ir]), ("permuted", pt, pl)):
            acc.append(pd.DataFrame({"i": ir, "kind": kind, "nv": valid.sum(1),
                                     "n_t": ((nt == lt[:, None]) & valid).sum(1), "n_l": ((nl == ll[:, None]) & valid).sum(1)}))
    rows = []
    if acc:
        Aall = pd.concat(acc); Aall = Aall[Aall.nv >= 3]
        Aall["type_agree"] = Aall.n_t / Aall.nv; Aall["lineage_agree"] = Aall.n_l / Aall.nv
        Aall["status"] = grp[Aall.i.values]; Aall["source"] = R.source.values[Aall.i.values]
        for (g, src, kind), B in Aall.groupby(["status", "source", "kind"]):
            rows.append({"status": g, "source": src, "kind": kind, "cells_scored": len(B),
                         "type_agreement": B.type_agree.mean(), "lineage_agreement": B.lineage_agree.mean()})
    pd.DataFrame(rows).to_csv(O("spatial_consistency.csv"), index=False)

    # ---------------- pseudobulk correlation (all genes)
    def pbulk(mask):
        out = {}
        for t in TYPES:
            sel = np.where(mask & (best_type == t))[0]
            if len(sel) < 20: continue
            v = np.asarray(Call[sel].sum(0)).ravel(); out[t] = np.log1p(v / v.sum() * 1e6)
        return pd.DataFrame(out)
    pr_ = pbulk(is_ref); rows = []
    for g in ["rescued_type", "rescued_lineage", "unresolved"]:
        q_ = pbulk(status == g)
        if q_.empty: continue
        cm = pd.DataFrame(np.corrcoef(q_.T.values, pr_.T.values)[:q_.shape[1], q_.shape[1]:], index=q_.columns, columns=pr_.columns)
        for t in cm.index:
            rows.append({"status": g, "best_type": t, "corr_same_type": float(cm.loc[t, t]) if t in cm.columns else np.nan,
                         "best_reference_type": cm.loc[t].idxmax(), "corr_best": float(cm.loc[t].max()),
                         "corr_second": float(cm.loc[t].nlargest(2).iloc[-1])})
    pd.DataFrame(rows).to_csv(O("pseudobulk_corr.csv"), index=False)
    INFO["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(INFO, open(O("run_info.json"), "w"), indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
    log("done")


if __name__ == "__main__":
    main()
