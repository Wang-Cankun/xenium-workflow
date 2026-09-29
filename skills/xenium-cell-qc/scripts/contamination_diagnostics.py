#!/usr/bin/env python
"""Contamination / spillover diagnostics on reference cells (CPU).

Inputs: labels.parquet from rescue_labels.py (reference cells and their types), the counts H5AD
(obsm spatial in um, obs region and cell_id columns), the type map (type, lineage) and a manifest
(region_id, path) pointing at the native output folders with transcripts.parquet.

A. Lineage-exclusive marker sets: per type, the top --markers-per-type genes by detection in the type
   minus mean detection in other types (detection >= --min-detection); pooled per lineage; genes selected
   by more than one lineage and --exclude-genes are dropped.
B. Neighbour dose-response: share of each foreign lineage's marker counts in a cell, binned by the fraction
   of its reference neighbours (up to --neighbour-k within --radius um, same region) from that lineage.
   --foreign-set NAME=g1,g2@typeA|typeB adds a custom set (e.g. species-specific probes) scored in cells
   not of the listed types against the fraction of neighbours of those types.
C. Mutually exclusive pairs (--pairs A+B,C+D): observed vs independence-expected co-detection among
   reference cells, all and with >= 0.8 own-lineage neighbours.
D. Nuclear localisation (transcripts.parquet, qv >= --min-qv): per region and pooled, nuclear fraction of
   own- vs foreign-lineage marker transcripts, the foreign share with whole-cell vs nuclear-only counting,
   and a gene x lineage table of nuclear fractions (to spot a signature that is nuclear in every lineage).
Gene names: exact var name, or a var name whose '/'-separated parts include the given name.

Outputs (--out-dir): lineage_marker_sets.json, neighbour_dose_response.csv, neighbour_dose_summary.csv,
exclusive_pairs.csv, nuclear_localisation_by_region.csv, nuclear_localisation_pooled.csv,
gene_nuclear_fraction_by_lineage.csv, contamination_info.json.
"""
import argparse, json, os, time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd
import scipy.sparse as sp


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True); ap.add_argument("--h5ad", required=True)
    ap.add_argument("--type-map", required=True); ap.add_argument("--manifest", required=True, help="csv: region_id, path")
    ap.add_argument("--region-column", default="region_id", help="obs column matching manifest region_id")
    ap.add_argument("--cell-id-column", default="cell_id"); ap.add_argument("--spatial-key", default="spatial")
    ap.add_argument("--layer", default="counts")
    ap.add_argument("--markers-per-type", type=int, default=15); ap.add_argument("--min-detection", type=float, default=0.2)
    ap.add_argument("--exclude-genes", default=""); ap.add_argument("--pairs", default="")
    ap.add_argument("--foreign-set", action="append", default=[])
    ap.add_argument("--radius", type=float, default=30.0); ap.add_argument("--neighbour-k", type=int, default=15)
    ap.add_argument("--min-qv", type=float, default=20); ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--out-dir", required=True)
    return ap.parse_args()


def resolve(g, genes):
    if g in genes: return g
    hit = [v for v in genes if g in v.split("/")]
    return hit[0] if len(hit) == 1 else None


def nuclear_counts(task):
    rid, path, cells, g2i, min_qv = task
    import pyarrow as pa, pyarrow.compute as pc, pyarrow.parquet as pq
    t = pq.read_table(os.path.join(path, "transcripts.parquet"), columns=["cell_id", "feature_name", "overlaps_nucleus", "qv"])
    fn = pc.cast(t["feature_name"], pa.string()); cid = pc.cast(t["cell_id"], pa.string())
    m = pc.and_(pc.greater_equal(t["qv"], min_qv), pc.is_in(cid, value_set=pa.array(cells.cell_id.values)))
    d = pa.table({"cell_id": pc.filter(cid, m), "feature_name": pc.filter(fn, m),
                  "nuc": pc.filter(t["overlaps_nucleus"], m)}).to_pandas()
    del t
    d["nuc"] = d.nuc.astype(np.int64)
    d = d.merge(cells, on="cell_id", how="inner")
    g = d.groupby(["lineage", "feature_name"]).agg(tx=("nuc", "size"), nuclear=("nuc", "sum")).reset_index()
    g["region_id"] = rid
    return g


def main():
    a = parse_args(); t0 = time.time(); os.makedirs(a.out_dir, exist_ok=True)
    O = lambda f: os.path.join(a.out_dir, f)
    def log(*x): print(f"[{time.time() - t0:7.1f}s]", *x, flush=True)
    import anndata as ad
    from scipy.spatial import cKDTree
    tm = pd.read_csv(a.type_map).astype(str); LIN = dict(zip(tm.type, tm.lineage)); TYPES = list(tm.type)
    LINS = sorted(set(LIN.values()))
    R = pd.read_parquet(a.labels, columns=["obs_name", "status", "own_type"])
    R = R[R.status == "reference"].reset_index(drop=True); R["lineage"] = R.own_type.map(LIN)
    assert R.lineage.notna().all()
    A = ad.read_h5ad(a.h5ad); names = pd.Index(np.asarray(A.obs_names).astype(str))
    genes = np.asarray(A.var_names).astype(str); gset = set(genes)
    rows = names.get_indexer(R.obs_name); assert (rows >= 0).all()
    C = sp.csr_matrix(A.layers[a.layer] if a.layer != "X" else A.X, dtype=np.float32)[rows]
    xy = np.asarray(A.obsm[a.spatial_key])[rows, :2]
    region = np.asarray(A.obs[a.region_column].astype(str).values, dtype=object)[rows]
    cellid = np.asarray(A.obs[a.cell_id_column].astype(str).values, dtype=object)[rows]
    del A
    lib = np.asarray(C.sum(1)).ravel()
    tcode = np.asarray(R.own_type.map({t: i for i, t in enumerate(TYPES)}).values, dtype=np.int64)
    Xb = C.copy(); Xb.data[:] = 1
    ind = sp.csr_matrix((np.ones(len(R)), (tcode, np.arange(len(R)))), shape=(len(TYPES), len(R)))
    pct = np.asarray((ind @ Xb).todense()) / np.maximum(np.bincount(tcode, minlength=len(TYPES)), 1)[:, None]
    excl = {resolve(g, gset) for g in a.exclude_genes.split(",") if g} - {None}
    lin_genes = {l: set() for l in LINS}
    for t in range(len(TYPES)):
        if (tcode == t).sum() < 20: continue
        sc = pct[t] - np.delete(pct, t, 0).mean(0); o = np.argsort(-sc)
        sel = [genes[g] for g in o if pct[t, g] >= a.min_detection and genes[g] not in excl][:a.markers_per_type]
        lin_genes[LIN[TYPES[t]]] |= set(sel)
    cnt = pd.Series([g for s in lin_genes.values() for g in s]).value_counts()
    LM = {l: sorted(g for g in s if cnt[g] == 1) for l, s in lin_genes.items()}
    FS = {}
    for spec in a.foreign_set:
        nm, rest = spec.split("=", 1); gs, ts = rest.split("@")
        FS[nm] = ([resolve(g, gset) for g in gs.split(",") if resolve(g, gset)], ts.split("|"))
    json.dump({"lineage_markers": LM, "foreign_sets": {k: {"genes": v[0], "types": v[1]} for k, v in FS.items()},
               "excluded_genes": sorted(excl)}, open(O("lineage_marker_sets.json"), "w"), indent=1)
    gix = {g: i for i, g in enumerate(genes)}
    share = pd.DataFrame({l: np.asarray(C[:, [gix[g] for g in LM[l]]].sum(1)).ravel() / lib for l in LINS})
    log("reference cells", len(R), {l: len(v) for l, v in LM.items()})

    # neighbour fractions
    lcode = np.asarray(R.lineage.map({l: i for i, l in enumerate(LINS)}).values, dtype=np.int64)
    nbf = np.zeros((len(R), len(LINS)), np.float32); nbt = {}
    typ = np.asarray(R.own_type.values, dtype=object); nv = np.zeros(len(R), np.int32)
    nb_all = np.full((len(R), a.neighbour_k), -1, np.int64)
    for rg in np.unique(region):
        ir = np.where(region == rg)[0]
        d, j = cKDTree(xy[ir]).query(xy[ir], k=a.neighbour_k + 1, distance_upper_bound=a.radius)
        d, j = d[:, 1:], j[:, 1:]; v = np.isfinite(d); jj = ir[np.where(v, j, 0)]
        nb_all[ir] = np.where(v, jj, -1); nv[ir] = v.sum(1)
    valid = nb_all >= 0; nbl = np.where(valid, lcode[np.maximum(nb_all, 0)], -1)
    for k in range(len(LINS)): nbf[:, k] = (nbl == k).sum(1) / np.maximum(nv, 1)
    ok = nv >= 3
    bins = [-0.01, 0.0, 0.2, 0.4, 0.6, 1.0]; blab = ["0", "0-0.2", "0.2-0.4", "0.4-0.6", ">0.6"]
    D = []
    def add(cell_label, foreign, m, frac, fshare, own):
        g = pd.DataFrame({"b": pd.cut(frac, bins, labels=blab), "s": fshare, "own": own}).groupby("b", observed=True)
        for bb, gg in g:
            D.append({"cell_lineage": cell_label, "foreign_lineage": foreign, "neighbour_fraction_bin": bb, "cells": len(gg),
                      "foreign_share_mean": gg.s.mean(), "foreign_detected_fraction": (gg.s > 0).mean(), "own_share_mean": gg.own.mean()})
    for i, L in enumerate(LINS):
        m = ok & (lcode == i)
        for k, F in enumerate(LINS):
            if F != L: add(L, F, m, nbf[m, k], share[F].values[m], share[L].values[m])
    for nm, (gs, ts) in FS.items():
        s_ = np.asarray(C[:, [gix[g] for g in gs]].sum(1)).ravel() / lib
        nbt_ = np.where(valid, np.isin(typ[np.maximum(nb_all, 0)], ts), False).sum(1) / np.maximum(nv, 1)
        for i, L in enumerate(LINS):
            m = ok & (lcode == i) & ~np.isin(typ, ts)
            if m.sum() >= 50: add(L, nm, m, nbt_[m], s_[m], share[L].values[m])
    D = pd.DataFrame(D); D.to_csv(O("neighbour_dose_response.csv"), index=False)
    S = D.pivot_table(index=["cell_lineage", "foreign_lineage"], columns="neighbour_fraction_bin", values="foreign_share_mean", observed=True)
    own_ref = {L: share[L].values[ok & (lcode == i)].mean() for i, L in enumerate(LINS)}
    S["foreign_markers_share_in_own_lineage"] = [own_ref.get(f, np.nan) for _, f in S.index]
    S["fold_high_vs_zero_neighbours"] = S.get(">0.6", np.nan) / S["0"]
    S.to_csv(O("neighbour_dose_summary.csv")); log("dose-response done")

    # exclusive pairs
    P = []
    own_frac = nbf[np.arange(len(R)), lcode]
    for pr in [p for p in a.pairs.split(",") if p]:
        g1, g2 = (resolve(x, gset) for x in pr.split("+"))
        if not g1 or not g2: P.append({"pair": pr, "stratum": "not_on_panel"}); continue
        d1 = C[:, gix[g1]].toarray().ravel() > 0; d2 = C[:, gix[g2]].toarray().ravel() > 0
        for sname, msk in [("all", ok), ("own_lineage_neighbours_ge_0.8", ok & (own_frac >= 0.8))]:
            p1, p2, p12 = d1[msk].mean(), d2[msk].mean(), (d1 & d2)[msk].mean()
            P.append({"pair": pr, "gene1": g1, "gene2": g2, "stratum": sname, "cells": int(msk.sum()), "p1": p1, "p2": p2,
                      "co_observed": p12, "co_expected_independent": p1 * p2, "obs_over_exp": p12 / max(p1 * p2, 1e-12)})
    pd.DataFrame(P).to_csv(O("exclusive_pairs.csv"), index=False); log("pairs done")

    # nuclear localisation
    man = pd.read_csv(a.manifest, dtype=str).set_index("region_id")
    tasks = []
    for rg in np.unique(region):
        p = man.loc[rg, "path"]
        if not os.path.exists(os.path.join(p, "transcripts.parquet")): continue
        m = region == rg
        tasks.append((rg, p, pd.DataFrame({"cell_id": cellid[m], "lineage": np.asarray(R.lineage.values, dtype=object)[m]}), None, a.min_qv))
    with ProcessPoolExecutor(max_workers=max(1, min(a.workers, len(tasks)))) as ex:
        parts = list(ex.map(nuclear_counts, tasks))
    G = pd.concat(parts, ignore_index=True)
    Gp = G.groupby(["lineage", "feature_name"])[["tx", "nuclear"]].sum().reset_index()
    Gp["nuclear_fraction"] = Gp.nuclear / Gp.tx
    Gp.pivot_table(index="feature_name", columns="lineage", values=["nuclear_fraction", "tx"]).to_csv(O("gene_nuclear_fraction_by_lineage.csv"))
    g2l = {g: l for l, v in LM.items() for g in v}
    G = G[G.feature_name.isin(g2l)].assign(marker_lineage=lambda d: d.feature_name.map(g2l))
    B = G.groupby(["region_id", "lineage", "marker_lineage"])[["tx", "nuclear"]].sum().reset_index()
    B["nuclear_fraction"] = B.nuclear / B.tx; B["own"] = B.lineage == B.marker_lineage
    B.to_csv(O("nuclear_localisation_by_region.csv"), index=False)
    Bp = B.groupby(["lineage", "marker_lineage"])[["tx", "nuclear"]].sum().reset_index()
    Bp["nuclear_fraction"] = Bp.nuclear / Bp.tx; Bp["own"] = Bp.lineage == Bp.marker_lineage
    Bp["own_marker_nuclear_fraction_same_cells"] = Bp.lineage.map(Bp[Bp.own].set_index("lineage").nuclear_fraction)
    Bp["share_whole_cell"] = Bp.tx / Bp.lineage.map(Bp.groupby("lineage").tx.sum())
    Bp["share_nuclear_only"] = Bp.nuclear / Bp.lineage.map(Bp.groupby("lineage").nuclear.sum())
    Bp.to_csv(O("nuclear_localisation_pooled.csv"), index=False)
    fo, ow = Bp[~Bp.own], Bp[Bp.own]
    info = {"reference_cells": int(len(R)), "cells_with_3_neighbours": int(ok.sum()), "regions_with_transcripts": len(parts),
            "lineage_marker_counts": {l: len(v) for l, v in LM.items()},
            "foreign_marker_nuclear_fraction_pooled": float(fo.nuclear.sum() / fo.tx.sum()),
            "own_marker_nuclear_fraction_pooled": float(ow.nuclear.sum() / ow.tx.sum()),
            "foreign_share_of_marker_tx_whole_cell": float(fo.tx.sum() / Bp.tx.sum()),
            "foreign_share_of_marker_tx_nuclear_only": float(fo.nuclear.sum() / Bp.nuclear.sum()),
            "elapsed_s": round(time.time() - t0, 1)}
    json.dump(info, open(O("contamination_info.json"), "w"), indent=1)
    log("done", info)


if __name__ == "__main__":
    main()
