#!/usr/bin/env python3
"""Post-annotation QC for Xenium cell labels: per-label and per-group evidence and a status with reasons.

Nothing is relabelled or removed. Every label receives a status (supported, review, unsupported,
not_a_type) and a semicolon-separated reason string; every cell keeps its label and gains evidence
columns.

Inputs
  --labels     table (csv/parquet) with region_id, cell_id and --label-column; optional --group-column
               (e.g. TMA core) and --species-column
  --label-map  csv: label, lineage; or --lineage-column to take each label's most common value of
               another column (e.g. main_type for detailed types). Lineage 'none' marks a non-type label;
               labels or lineages matching --none-pattern (unresolved, unknown, low-RNA, doublet, mixed,
               excluded ...) become 'none'. Labels missing from a supplied map are their own lineage.
  counts from native outputs (--manifest csv: region_id, path; cell_feature_matrix.h5 gene rows and
  cells.parquet centroids) or from --h5ad (raw counts in --layer or X; obs columns region_id and
  cell_id; obsm[--spatial-key] in um).
  Optional: --cell-qc (region_id, cell_id, boolean flag columns, dist_to_edge_um), --qc-labels
  (region_id, cell_id, qc_lineage[, qc_status]) from xenium-cell-qc, --label-species (label,
  expected species), --markers (lineage, gene) to replace data-driven lineage markers.

Checks per label (thresholds are options; see references/checks.md)
  lineage support   own-lineage marker detection in the label vs cells of other lineages
  distinctness      genes separating the label from other labels of its lineage
  depth             enrichment among low-depth cells; label share vs group depth across groups
  qc flags          share of the label's cells carrying any cell-QC flag vs all cells
  foreign markers   foreign-lineage marker share vs the lineage median, and its neighbour dose-response;
                    whether the label's distinguishing genes are foreign-lineage markers
  thinning          accuracy of a kNN label classifier on held-out cells thinned to lower depth
  qc agreement      QC-level lineage of confidently labelled cells vs the label's lineage
  spatial           top-group share, spatial homophily, tissue-edge enrichment (edge needs --cell-qc)
  species           species mix vs --label-species

Outputs (new --out-dir): label_qc.csv, label_map_used.csv, label_group.csv, group_qc.csv,
thinning_accuracy.csv, lineage_markers.json, cell_annotation_qc.parquet, run_info.json.
"""
import argparse, json, sys, time
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sp

NONE = "none"
STRONG = {"lineage_marker_unsupported", "defined_by_foreign_markers"}
# moderate reasons grouped by the evidence they share; each family counts once towards 'unsupported'
FAMILY = {"low_depth_enriched": "depth", "share_tracks_group_depth": "depth", "label_fragile_at_its_depth": "depth",
          "qc_flag_enriched": "depth", "foreign_marker_high": "contamination",
          "foreign_markers_among_distinct_genes": "contamination", "not_distinct_within_lineage": "distinctness",
          "not_recoverable": "distinctness", "single_gene_defined": "distinctness",
          "qc_lineage_disagrees": "agreement", "edge_enriched": "spatial", "species_inconsistent": "species",
          "failed_group_enriched": "unit"}
INFO = {"single_group_dominated", "few_cells", "no_lineage_markers"}


def fail(msg):
    print(f"error: {msg}", file=sys.stderr); sys.exit(2)


def read_table(p):
    p = Path(p)
    return pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p, low_memory=False)


# ---------------------------------------------------------------- loading

def native_region(path, ids):
    import h5py, pyarrow.parquet as pq
    d = Path(path)
    with h5py.File(d / "cell_feature_matrix.h5", "r") as f:
        m = f["matrix"]
        gene = np.asarray(m["features/feature_type"]).astype(str) == "Gene Expression"
        names = np.asarray(m["features/name"]).astype(str)
        bc = np.asarray(m["barcodes"]).astype(str)
        shape = tuple(int(s) for s in np.asarray(m["shape"]))
        X = sp.csc_matrix((np.asarray(m["data"]), np.asarray(m["indices"]), np.asarray(m["indptr"])),
                          shape=shape).T.tocsr()                               # cells x features
    X = X[:, np.flatnonzero(gene)]
    pos = pd.Series(np.arange(len(bc)), index=bc)
    miss = ~pd.Index(ids).isin(pos.index)
    c = pq.read_table(d / "cells.parquet", columns=["cell_id", "x_centroid", "y_centroid"]).to_pandas()
    c["cell_id"] = c.cell_id.map(lambda x: x.decode() if isinstance(x, bytes) else str(x))
    c = c.drop_duplicates("cell_id").set_index("cell_id").reindex(ids)
    rows = pos.reindex(ids).fillna(-1).astype(int).to_numpy()
    Xr = X[np.clip(rows, 0, None)]
    if miss.any():
        Xr = sp.diags((~miss).astype(float)) @ Xr
    return Xr.tocsr(), list(names[gene]), c[["x_centroid", "y_centroid"]].to_numpy(float), np.asarray(miss)


def load_native(manifest, lab):
    man = pd.read_csv(manifest, dtype=str)
    if not {"region_id", "path"} <= set(man.columns):
        fail("manifest needs region_id and path")
    paths = dict(zip(man.region_id, man.path))
    parts, genes, order = [], None, []
    for rid, g in lab.groupby("region_id", sort=False):
        if rid not in paths:
            fail(f"region {rid} not in manifest")
        X, names, xy, miss = native_region(paths[rid], g.cell_id.tolist())
        if genes is None:
            genes = names
        elif names != genes:
            fail(f"gene list of {rid} differs from the first region")
        parts.append((X, xy, miss)); order.append(g.index.to_numpy())
    idx = np.concatenate(order)
    X = sp.vstack([p[0] for p in parts]).tocsr(); xy = np.vstack([p[1] for p in parts])
    miss = np.concatenate([p[2] for p in parts])
    inv = np.empty(len(idx), int); inv[idx] = np.arange(len(idx))
    return X[inv], genes, xy[inv], miss[inv]


def load_h5ad(path, layer, spatial_key, lab):
    import anndata as ad
    a = ad.read_h5ad(path)
    for c in ("region_id", "cell_id"):
        if c not in a.obs:
            fail(f"--h5ad obs needs column {c}")
    key = a.obs.region_id.astype(str) + "\t" + a.obs.cell_id.astype(str)
    pos = pd.Series(np.arange(a.n_obs), index=key.to_numpy())
    want = (lab.region_id.astype(str) + "\t" + lab.cell_id.astype(str)).to_numpy()
    miss = ~pd.Index(want).isin(pos.index)
    rows = pos.reindex(want).fillna(0).astype(int).to_numpy()
    X = a.layers[layer] if layer and layer != "X" else a.X
    X = sp.csr_matrix(X)[rows]
    if miss.any():
        X = sp.diags((~miss).astype(float)) @ X
    xy = np.asarray(a.obsm[spatial_key], float)[rows, :2] if spatial_key in a.obsm else np.full((len(lab), 2), np.nan)
    xy[miss] = np.nan
    return X.tocsr(), list(map(str, a.var_names)), xy, np.asarray(miss)


# ---------------------------------------------------------------- helpers

def indicator(codes, n):
    """Sparse (n_levels x n_cells) indicator for integer codes (negative codes are skipped)."""
    ok = codes >= 0
    return sp.csr_matrix((np.ones(ok.sum()), (codes[ok], np.flatnonzero(ok))), shape=(n, len(codes)))


def detection(ind, B):
    """Per-level mean of every gene column of B: (levels x genes), and cells per level."""
    n = np.asarray(ind.sum(1)).ravel()
    return np.asarray((ind @ B).todense()) / np.maximum(n, 1)[:, None], n


def spearman(x, y):
    from scipy.stats import spearmanr
    if len(x) < 3 or np.nanstd(x) == 0 or np.nanstd(y) == 0:
        return np.nan, np.nan
    r = spearmanr(x, y)
    return float(r[0]), float(r[1])


def lineage_markers(det_lin, lineages, n_per, min_det, min_gap=0.2, min_ratio=2.0):
    """Lineage-exclusive markers: detection >= min_det in the lineage, at least min_gap above and min_ratio
    times the highest detection in any other lineage; top n_per by that gap."""
    sets = {}
    for i, L in enumerate(lineages):
        other = np.delete(det_lin, i, axis=0).max(0) if len(lineages) > 1 else np.zeros(det_lin.shape[1])
        gap = det_lin[i] - other
        ok = (det_lin[i] >= min_det) & (gap >= min_gap) & (det_lin[i] >= min_ratio * other)
        sets[L] = [j for j in np.argsort(-gap) if ok[j]][:n_per]
    return sets


def thin(X, target, rng):
    """Binomial thinning of each row of a CSR count matrix to about `target` counts."""
    tot = np.asarray(X.sum(1)).ravel()
    p = np.clip(target / np.maximum(tot, 1), 0, 1)
    Y = X.copy().astype(np.float64)
    Y.data = rng.binomial(Y.data.astype(np.int64), np.repeat(p, np.diff(Y.indptr))).astype(np.float64)
    Y.eliminate_zeros()
    return Y


def lognorm(X):
    tot = np.asarray(X.sum(1)).ravel()
    Y = (sp.diags(1e4 / np.maximum(tot, 1)) @ X).tocsr()
    Y.data = np.log1p(Y.data)
    return Y


def ratio(a, b):
    return float(a / b) if b and b > 0 else (np.inf if a and a > 0 else np.nan)


# ---------------------------------------------------------------- main

def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True); ap.add_argument("--label-column", required=True)
    ap.add_argument("--label-map", default=None, help="csv: label, lineage")
    ap.add_argument("--lineage-column", default=None,
                    help="derive each label's lineage as its most common value of this column (when no --label-map)")
    ap.add_argument("--none-pattern", default=r"(?i)unresolved|unknown|low[-_ ]?rna|low[-_ ]?info|doublet|mixed|exclude|artifact|artefact|unassigned|ambiguous|low[-_ ]?quality|^nan$|^none$",
                    help="labels or lineages matching this regex are non-type labels (lineage 'none')")
    ap.add_argument("--group-column", default=None); ap.add_argument("--species-column", default=None)
    ap.add_argument("--manifest", default=None); ap.add_argument("--h5ad", default=None)
    ap.add_argument("--layer", default="counts"); ap.add_argument("--spatial-key", default="spatial")
    ap.add_argument("--cell-qc", default=None)
    ap.add_argument("--flag-columns", default="", help="comma-separated boolean columns of --cell-qc [all flag_* columns]")
    ap.add_argument("--qc-labels", default=None); ap.add_argument("--label-species", default=None)
    ap.add_argument("--markers", default=None, help="csv: lineage, gene (replaces data-driven lineage markers)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--ref-min-counts", type=float, default=100, help="depth of cells used for markers and training [100]")
    ap.add_argument("--low-depth", type=float, default=50, help="low-depth band upper bound [50]")
    ap.add_argument("--markers-per-lineage", type=int, default=15); ap.add_argument("--min-detection", type=float, default=0.2)
    ap.add_argument("--min-label-cells", type=int, default=50)
    ap.add_argument("--distinct-fold", type=float, default=2.0, help="fold of mean count share over the closest label [2]")
    ap.add_argument("--single-gene-fold", type=float, default=3.0,
                    help="specificity fold of a label's top gene over every other label for the single-gene check [3]")
    ap.add_argument("--single-gene-similarity", type=float, default=0.95,
                    help="cosine similarity to another label without that gene [0.95]")
    ap.add_argument("--failed-group-share", type=float, default=0.1,
                    help="share of a label's cells in whole-group-failure groups (flag_group_low_depth) [0.1]")
    ap.add_argument("--lineage-enrichment", type=float, default=1.5); ap.add_argument("--depth-enrichment", type=float, default=3.0)
    ap.add_argument("--flag-enrichment", type=float, default=2.0); ap.add_argument("--foreign-ratio", type=float, default=2.0)
    ap.add_argument("--dose-ratio", type=float, default=1.5); ap.add_argument("--thin-accuracy", type=float, default=0.5)
    ap.add_argument("--agreement", type=float, default=0.5); ap.add_argument("--edge-um", type=float, default=20.0)
    ap.add_argument("--edge-enrichment", type=float, default=3.0); ap.add_argument("--species-minority", type=float, default=0.10)
    ap.add_argument("--min-group-cells", type=int, default=200); ap.add_argument("--min-groups", type=int, default=8)
    ap.add_argument("--min-lineage-cells", type=int, default=50, help="lineage cells per group for the depth-tracking check [50]")
    ap.add_argument("--depth-rho", type=float, default=0.6)
    ap.add_argument("--moderate-to-unsupported", type=int, default=3)
    ap.add_argument("--strong-lineage-support", type=float, default=3.0,
                    help="lineage-marker enrichment at or above which moderate failures alone give 'review' [3]")
    ap.add_argument("--review-group-share", type=float, default=0.2)
    ap.add_argument("--thin-depths", default="20,50,100"); ap.add_argument("--train-per-label", type=int, default=2000)
    ap.add_argument("--test-per-label", type=int, default=300); ap.add_argument("--k", type=int, default=15)
    ap.add_argument("--neighbours", type=int, default=10); ap.add_argument("--seed", type=int, default=0)
    return ap.parse_args()


def main():
    a = parse_args(); t0 = time.time(); rng = np.random.default_rng(a.seed)
    out = Path(a.out_dir)
    if out.exists():
        fail(f"output exists: {out}")
    if (a.manifest is None) == (a.h5ad is None):
        fail("give exactly one of --manifest or --h5ad")

    lab = read_table(a.labels)
    need = {"region_id", "cell_id", a.label_column} | ({a.group_column} if a.group_column else set())
    if not need <= set(lab.columns):
        fail(f"--labels needs columns {sorted(need)}")
    lab = lab.reset_index(drop=True)
    lab["region_id"] = lab.region_id.astype(str); lab["cell_id"] = lab.cell_id.astype(str)
    if lab.duplicated(["region_id", "cell_id"]).any():
        fail("--labels has duplicate region_id + cell_id rows")
    lab["label"] = lab[a.label_column].astype(str)
    lab["group"] = lab[a.group_column].astype(str) if a.group_column else "all"
    if a.label_map:
        lmap = pd.read_csv(a.label_map, dtype=str, keep_default_na=False)
        if not {"label", "lineage"} <= set(lmap.columns):
            fail("--label-map needs label and lineage")
        lin_of = dict(zip(lmap.label, lmap.lineage)); map_source = "supplied"
    elif a.lineage_column:
        if a.lineage_column not in lab.columns:
            fail(f"--labels has no column {a.lineage_column}")
        lin_of = (lab.assign(_lin=lab[a.lineage_column].astype(str)).groupby("label")._lin
                  .agg(lambda v: v.value_counts().index[0]).to_dict()); map_source = f"modal {a.lineage_column}"
    else:
        fail("give --label-map or --lineage-column")
    import re
    pat = re.compile(a.none_pattern) if a.none_pattern else None
    if pat:
        lin_of = {l: (NONE if pat.search(l) or pat.search(str(v)) else v) for l, v in lin_of.items()}
    unmapped = sorted(set(lab.label) - set(lin_of))
    for l in unmapped:
        lin_of[l] = l
    lab["lineage"] = lab.label.map(lin_of)

    if a.manifest:
        X, genes, xy, miss = load_native(a.manifest, lab)
    else:
        X, genes, xy, miss = load_h5ad(a.h5ad, a.layer, a.spatial_key, lab)
    X.data = np.round(X.data)
    depth = np.asarray(X.sum(1)).ravel()
    B = X.copy(); B.data = (B.data > 0).astype(np.float32)
    G = len(genes); gname = np.array(genes)

    labels = sorted(lab.label.unique())
    lcode = lab.label.map({l: i for i, l in enumerate(labels)}).to_numpy()
    is_type = (lab.lineage != NONE).to_numpy() & ~miss
    lineages = sorted(set(lab.lineage[is_type]))
    lin_code = lab.lineage.map({l: i for i, l in enumerate(lineages)}).fillna(-1).astype(int).to_numpy()
    lin_code[~is_type] = -1
    ref = is_type & (depth >= a.ref_min_counts)

    # lineage markers: supplied, or data-driven on reference-depth cells
    if a.markers:
        mk = pd.read_csv(a.markers, dtype=str); gi = {g: j for j, g in enumerate(genes)}
        msets = {L: [gi[g] for g in mk.gene[mk.lineage == L] if g in gi] for L in lineages}
        marker_source = "supplied"
    else:
        dl, _ = detection(indicator(np.where(ref, lin_code, -1), len(lineages)), B)
        msets = lineage_markers(dl, lineages, a.markers_per_lineage, a.min_detection)
        marker_source = "data-driven"
    own_hit = np.zeros(len(lab), bool); own_share = np.full(len(lab), np.nan); foreign_share = np.full(len(lab), np.nan)
    other_share = {}
    Xc, Bc = X.tocsc(), B.tocsc(); dnorm = 1.0 / np.maximum(depth, 1)
    for i, L in enumerate(lineages):
        cells = lin_code == i
        own = msets.get(L, [])
        foreign = sorted({j for M, v in msets.items() if M != L for j in v})
        if own:
            s_own = np.asarray(Xc[:, own].sum(1)).ravel() * dnorm
            own_hit[cells] = (np.asarray(Bc[:, own].sum(1)).ravel() > 0)[cells]
            own_share[cells] = s_own[cells]
            oth = (lin_code >= 0) & ~cells
            other_share[L] = float(s_own[oth].mean()) if oth.any() else np.nan
        if foreign:
            foreign_share[cells] = (np.asarray(Xc[:, foreign].sum(1)).ravel() * dnorm)[cells]
    del Xc, Bc
    fs_by_label = pd.Series(foreign_share[~miss]).groupby(lcode[~miss]).mean()

    # per label on reference-depth cells: detection and mean count share of each gene (distinctness)
    ind_ref = indicator(np.where(ref, lcode, -1), len(labels))
    dlab, nref = detection(ind_ref, B)
    elab, _ = detection(ind_ref, (sp.diags(1.0 / np.maximum(depth, 1)) @ X).tocsr())

    # spatial neighbours within each region
    from scipy.spatial import cKDTree
    nb_same = np.full(len(lab), np.nan); nb_foreign = np.full(len(lab), np.nan)
    for _, g in lab.groupby("region_id", sort=False):
        ii = g.index.to_numpy(); ii = ii[np.isfinite(xy[ii]).all(1)]
        if len(ii) <= a.neighbours:
            continue
        _, nn = cKDTree(xy[ii]).query(xy[ii], k=a.neighbours + 1)
        nn = ii[nn[:, 1:]]
        nb_same[ii] = (lcode[nn] == lcode[ii][:, None]).mean(1)
        lc = lin_code[nn]; valid = lc >= 0; nv = valid.sum(1)
        nf = ((lc != lin_code[ii][:, None]) & valid).sum(1) / np.maximum(nv, 1)
        nb_foreign[ii] = np.where(nv > 0, nf, np.nan)

    # optional evidence tables
    anyflag = edge = failed_grp = None; fcols = []
    if a.cell_qc:
        cq = read_table(a.cell_qc); cq["region_id"] = cq.region_id.astype(str); cq["cell_id"] = cq.cell_id.astype(str)
        cq = lab[["region_id", "cell_id"]].merge(cq.drop_duplicates(["region_id", "cell_id"]), on=["region_id", "cell_id"], how="left")
        fcols = [c for c in a.flag_columns.split(",") if c] or [c for c in cq.columns if c.startswith("flag_")]
        anyflag = cq[fcols].fillna(False).astype(bool).any(axis=1).to_numpy() if fcols else np.zeros(len(lab), bool)
        if "dist_to_edge_um" in cq:
            edge = cq["dist_to_edge_um"].to_numpy(float) < a.edge_um
        if "flag_group_low_depth" in cq:
            failed_grp = cq["flag_group_low_depth"].fillna(False).astype(bool).to_numpy()
    ql = conf = None
    if a.qc_labels:
        q = read_table(a.qc_labels); q["region_id"] = q.region_id.astype(str); q["cell_id"] = q.cell_id.astype(str)
        ql = lab[["region_id", "cell_id"]].merge(q.drop_duplicates(["region_id", "cell_id"]), on=["region_id", "cell_id"], how="left")
        conf = ql.qc_lineage.notna().to_numpy()
        if "qc_status" in ql:
            conf &= ql.qc_status.isin(["reference", "rescued_type", "rescued_lineage"]).to_numpy()
    sp_exp = None
    if a.label_species:
        s = pd.read_csv(a.label_species, dtype=str); sp_exp = dict(zip(s.iloc[:, 0], s.iloc[:, 1]))

    # thinning stability: kNN label classifier trained on reference-depth cells of type labels
    thin_rows = []
    tr_idx, te_idx = [], []
    for i, l in enumerate(labels):
        if lin_of[l] == NONE:
            continue
        cand = np.flatnonzero(ref & (lcode == i))
        if len(cand) < 30:
            continue
        cand = rng.permutation(cand); nte = min(a.test_per_label, len(cand) // 3)
        te_idx.append(cand[:nte]); tr_idx.append(cand[nte:nte + a.train_per_label])
    depths = [float(d) for d in a.thin_depths.split(",") if d]
    if len(tr_idx) >= 2:
        from sklearn.decomposition import PCA
        from sklearn.neighbors import KNeighborsClassifier
        tr = np.concatenate(tr_idx); te = np.concatenate(te_idx)
        lab_lin = np.array([lineages.index(lin_of[l]) if lin_of[l] in lineages else -1 for l in labels])  # label -> lineage
        Ztr = lognorm(X[tr]).toarray()
        pca = PCA(n_components=min(30, G - 1, len(tr) - 1), random_state=a.seed).fit(Ztr)
        knn = KNeighborsClassifier(n_neighbors=min(a.k, len(tr))).fit(pca.transform(Ztr), lcode[tr])
        for dpt in depths + [np.inf]:
            Xt = X[te] if not np.isfinite(dpt) else thin(X[te], dpt, rng)
            pred = knn.predict(pca.transform(lognorm(Xt).toarray()))
            ok = pred == lcode[te]; lin_ok = lab_lin[pred] == lab_lin[lcode[te]]
            for i in np.unique(lcode[te]):
                m = lcode[te] == i
                thin_rows.append({"label": labels[i], "depth": "full" if not np.isfinite(dpt) else dpt,
                                  "cells": int(m.sum()), "label_accuracy": round(float(ok[m].mean()), 4),
                                  "lineage_accuracy": round(float(lin_ok[m].mean()), 4),
                                  "test_median_depth": float(np.median(depth[te][m]))})
    thin_df = pd.DataFrame(thin_rows, columns=["label", "depth", "cells", "label_accuracy", "lineage_accuracy",
                                               "test_median_depth"])

    # groups: depth and label shares
    gdf = pd.DataFrame({"group": lab.group, "depth": depth, "label": lab.label})
    gstats = gdf[~miss].groupby("group").agg(cells=("depth", "size"), median_depth=("depth", "median"))
    big = gstats.index[gstats.cells >= a.min_group_cells]
    lg = gdf[~miss].groupby(["label", "group"]).size().rename("cells").reset_index()
    lg["share"] = lg.cells / lg.group.map(gstats.cells)
    gl_lin = pd.DataFrame({"group": lab.group, "lineage": lab.lineage})[~miss].value_counts().rename("n")   # (group, lineage)

    lowband = depth < a.low_depth; highband = depth >= 2 * a.low_depth
    base_flag = anyflag[~miss].mean() if anyflag is not None else np.nan
    base_edge = np.nanmean(edge[~miss]) if edge is not None else np.nan
    base_failed = failed_grp[~miss].mean() if failed_grp is not None else np.nan
    type_ref = [j for j in range(len(labels)) if nref[j] >= 20 and lin_of[labels[j]] != NONE]
    rows = []
    for i, l in enumerate(labels):
        m = (lcode == i) & ~miss
        L = lin_of[l]; reasons = []
        r = {"label": l, "lineage": L, "cells": int(m.sum()), "cells_missing_counts": int(((lcode == i) & miss).sum())}
        r["median_depth"] = float(np.median(depth[m])) if m.any() else np.nan
        r["share_below_low_depth"] = round(float(lowband[m].mean()), 4) if m.any() else np.nan
        r["low_depth_enrichment"] = round(ratio(m[lowband].mean() if lowband.any() else np.nan,
                                                m[highband].mean() if highband.any() else np.nan), 3)
        # share of the label within its lineage, per group with enough cells of that lineage
        nl = gl_lin.xs(L, level="lineage") if L in gl_lin.index.get_level_values("lineage") else pd.Series(dtype=float)
        gg = nl.index[(nl >= a.min_lineage_cells) & nl.index.isin(big)]
        cnt = lg[lg.label == l].set_index("group").cells.reindex(gg).fillna(0)
        rho, p = (spearman((cnt / nl.reindex(gg)).to_numpy(), gstats.median_depth.reindex(gg).to_numpy())
                  if len(gg) >= a.min_groups else (np.nan, np.nan))
        r["groups_tested_for_depth"] = int(len(gg))
        r["groups_with_label"] = int((lg.label == l).sum()); r["depth_rho_across_groups"] = rho; r["depth_rho_p"] = p
        top = lg[lg.label == l].sort_values("cells", ascending=False)
        r["top_group"] = top.group.iloc[0] if len(top) else ""
        r["top_group_share"] = round(float(top.cells.iloc[0] / max(m.sum(), 1)), 4) if len(top) else np.nan
        r["spatial_homophily"] = round(float(np.nanmean(nb_same[m])), 4) if m.any() and np.isfinite(nb_same[m]).any() else np.nan
        r["label_share"] = round(float(m.sum() / max((~miss).sum(), 1)), 6)
        if L == NONE:
            r["status"] = "not_a_type"; r["reasons"] = ""; rows.append(r); continue
        if r["cells"] < a.min_label_cells:
            reasons.append("few_cells")
        own = msets.get(L, [])
        r["lineage_markers"] = len(own)
        if not own:
            reasons.append("no_lineage_markers")
        if own and m.any() and other_share.get(L) == other_share.get(L):
            r["own_marker_detected"] = round(float(own_hit[m].mean()), 4)
            r["own_marker_share"] = round(float(np.nanmean(own_share[m])), 5)
            r["own_marker_share_other_lineages"] = round(other_share[L], 5)
            enr = ratio(r["own_marker_share"], other_share[L]); r["lineage_marker_enrichment"] = round(enr, 3)
            if enr == enr and enr < a.lineage_enrichment:
                reasons.append("lineage_marker_unsupported")
        foreign_top = False
        if nref[i] >= 20:
            same_lin = [j for j, k in enumerate(labels) if lin_of[k] == L and j != i and nref[j] >= 20]
            others = [j for j in range(len(labels)) if j != i and nref[j] >= 20 and lin_of[labels[j]] != NONE]
            base = elab[same_lin].max(0) if same_lin else (elab[others].max(0) if others else np.zeros(G))
            fc = elab[i] / np.maximum(base, 1e-6)
            ok = (elab[i] >= a.distinct_fold * base) & (elab[i] >= 0.5 / G) & (dlab[i] >= a.min_detection)
            topg = [j for j in np.argsort(-fc) if ok[j]][:5]              # top distinct genes only
            fset = {j for M, v in msets.items() if M != L for j in v}
            nf = int(sum(j in fset for j in topg))
            r["distinct_genes"] = int(ok.sum()); r["top_distinct_genes"] = ",".join(gname[topg])
            r["top_genes_foreign"] = nf
            if same_lin and not ok.any():
                reasons.append("not_distinct_within_lineage")
            foreign_top = nf >= 3 and nf >= 0.6 * len(topg)
            # single-gene-defined: one strongly specific gene; without it the profile matches another label
            oth = [j for j in type_ref if j != i]
            if oth:
                spec = elab[i] / np.maximum(elab[oth].max(0), 1e-6)
                spec[dlab[i] < a.min_detection] = 0
                gstar = int(np.argmax(spec))
                if spec[gstar] >= a.single_gene_fold:
                    keep_g = np.ones(G, bool); keep_g[gstar] = False
                    u = elab[i, keep_g]; V = elab[np.ix_(oth, keep_g)]
                    sims = (V @ u) / np.maximum(np.linalg.norm(V, axis=1) * np.linalg.norm(u), 1e-12)
                    jb = oth[int(np.argmax(sims))]; sim = float(sims.max())
                    dvc = (elab[i] >= a.distinct_fold * elab[jb]) & (elab[i] >= 0.5 / G) & (dlab[i] >= a.min_detection)
                    r["top_specific_gene"] = gname[gstar]; r["top_specific_fold"] = round(float(spec[gstar]), 2)
                    r["closest_label_without_it"] = labels[jb]; r["closest_similarity"] = round(sim, 4)
                    if sim >= a.single_gene_similarity and int(dvc.sum()) <= 1:
                        reasons.append("single_gene_defined")
        if r["low_depth_enrichment"] == r["low_depth_enrichment"] and r["low_depth_enrichment"] >= a.depth_enrichment:
            reasons.append("low_depth_enriched")
        if rho == rho and abs(rho) >= a.depth_rho and p < 0.01:
            reasons.append("share_tracks_group_depth")
        if anyflag is not None and m.any():
            fr = float(anyflag[m].mean())
            r["qc_flagged_share"] = round(fr, 4); r["qc_flag_enrichment"] = round(ratio(fr, base_flag), 3)
            if fr >= 0.2 and r["qc_flag_enrichment"] >= a.flag_enrichment:
                reasons.append("qc_flag_enriched")
        if edge is not None and m.any():
            r["edge_enrichment"] = round(ratio(float(np.nanmean(edge[m])), base_edge), 3)
            if r["edge_enrichment"] >= a.edge_enrichment:
                reasons.append("edge_enriched")
        if failed_grp is not None and m.any():
            fg = float(failed_grp[m].mean()); r["share_in_failed_groups"] = round(fg, 4)
            if fg >= a.failed_group_share and fg >= a.flag_enrichment * max(base_failed, 1e-6):
                reasons.append("failed_group_enriched")
        fs = foreign_share[m]
        if np.isfinite(fs).any():
            sib = [fs_by_label.get(j, np.nan) for j, k in enumerate(labels) if lin_of[k] == L and j != i]
            if not np.isfinite(sib).any():
                sib = [fs_by_label.get(j, np.nan) for j, k in enumerate(labels) if lin_of[k] != NONE and j != i]
            med = float(np.nanmedian(sib)) if np.isfinite(sib).any() else np.nan
            r["foreign_marker_share"] = round(float(np.nanmean(fs)), 4); r["foreign_share_sibling_median"] = round(med, 4)
            hi = m & (nb_foreign >= 0.5); lo = m & (nb_foreign <= 0.1)
            dose = ratio(float(np.nanmean(foreign_share[hi])), float(np.nanmean(foreign_share[lo]))) if hi.sum() >= 20 and lo.sum() >= 20 else np.nan
            r["foreign_dose_ratio"] = round(dose, 3) if dose == dose else np.nan
            fhigh = bool(med == med and r["foreign_marker_share"] >= a.foreign_ratio * max(med, 1e-6))
            if fhigh and dose == dose and dose >= a.dose_ratio:
                reasons.append("foreign_marker_high")
        else:
            fhigh = False
        if foreign_top:
            reasons.append("defined_by_foreign_markers" if fhigh else "foreign_markers_among_distinct_genes")
        t = thin_df[thin_df.label == l]
        if len(t) and m.any():
            full = t[t.depth == "full"]; tt = t[t.depth != "full"]
            facc = float(full.label_accuracy.iloc[0]); r["label_accuracy_full_depth"] = round(facc, 4)
            dd = np.r_[tt.depth.astype(float).to_numpy(), float(full.test_median_depth.iloc[0])]
            acc = np.r_[tt.label_accuracy.to_numpy(), facc]; o = np.argsort(dd)
            at = float(np.interp(np.clip(r["median_depth"], dd.min(), dd.max()), dd[o], acc[o]))
            r["label_accuracy_at_median_depth"] = round(at, 4)
            if facc < a.thin_accuracy:
                reasons.append("not_recoverable")
            elif at < a.thin_accuracy:
                reasons.append("label_fragile_at_its_depth")
        if ql is not None and m.any():
            mm = m & conf
            if mm.sum() >= 20:
                agr = float((ql.qc_lineage.astype(str).to_numpy()[mm] == L).mean()); r["qc_lineage_agreement"] = round(agr, 4)
                if agr < a.agreement:
                    reasons.append("qc_lineage_disagrees")
        if a.species_column and sp_exp and l in sp_exp and m.any():
            minority = float((lab.loc[m, a.species_column].astype(str) != sp_exp[l]).mean())
            r["species_mismatch_share"] = round(minority, 4)
            if minority >= a.species_minority:
                reasons.append("species_inconsistent")
        if r["groups_with_label"] >= 3 and r["top_group_share"] >= 0.9:
            reasons.append("single_group_dominated")
        strong = [x for x in reasons if x in STRONG]; fams = sorted({FAMILY[x] for x in reasons if x in FAMILY})
        r["failed_families"] = ",".join(fams)
        enr = r.get("lineage_marker_enrichment", np.nan)
        well_supported = enr == enr and enr >= a.strong_lineage_support
        r["status"] = ("unsupported" if strong or (len(fams) >= a.moderate_to_unsupported and not well_supported)
                       else "review" if fams or "few_cells" in reasons else "supported")
        r["reasons"] = ";".join(reasons)
        rows.append(r)
    lq = pd.DataFrame(rows)

    status_of = dict(zip(lq.label, lq.status))
    lab["label_status"] = lab.label.map(status_of)
    lg["label_status"] = lg.label.map(status_of)
    s = lab.label_status[~miss]; grp_key = lab.group[~miss]
    gq = pd.DataFrame({"cells": grp_key.value_counts()})
    for st in ("review", "unsupported", "not_a_type"):
        gq[f"share_{st}"] = (s == st).groupby(grp_key).mean()
    gq["median_depth"] = gstats.median_depth
    gq["uncertain_share"] = gq.share_review + gq.share_unsupported
    gq["group_status"] = np.where(gq.uncertain_share >= a.review_group_share, "review", "ok")
    gq = gq.rename_axis("group").reset_index()

    cell = lab[["region_id", "cell_id", "group", "label", "lineage", "label_status"]].copy()
    cell["depth"] = depth.astype(np.float32); cell["counts_missing"] = miss
    cell["own_marker_detected"] = pd.array(np.where(lin_code >= 0, own_hit, False), dtype="boolean")
    cell.loc[lin_code < 0, "own_marker_detected"] = pd.NA
    cell["own_marker_share"] = own_share.astype(np.float32)
    cell["foreign_marker_share"] = foreign_share.astype(np.float32)
    cell["foreign_neighbour_share"] = nb_foreign.astype(np.float32)
    R = np.where(cell.label_status.isin(["review", "unsupported"]), "label_" + cell.label_status.astype(str), "").astype(object)
    for name, mask in (("counts_missing", miss), ("low_depth", lowband & ~miss),
                       ("no_own_marker", (lin_code >= 0) & ~own_hit & ~miss),
                       ("qc_flagged", anyflag if anyflag is not None else np.zeros(len(lab), bool))):
        mask = np.asarray(mask, bool)
        R[mask] = np.where(R[mask] == "", name, R[mask] + ";" + name)
    cell["cell_reasons"] = R

    out.mkdir(parents=True)
    lq.to_csv(out / "label_qc.csv", index=False)
    pd.DataFrame({"label": labels, "lineage": [lin_of[l] for l in labels]}).to_csv(out / "label_map_used.csv", index=False)
    lg.to_csv(out / "label_group.csv", index=False)
    gq.to_csv(out / "group_qc.csv", index=False)
    thin_df.to_csv(out / "thinning_accuracy.csv", index=False)
    (out / "lineage_markers.json").write_text(json.dumps(
        {"source": marker_source, "sets": {L: [genes[j] for j in v] for L, v in msets.items()}}, indent=1))
    cell.to_parquet(out / "cell_annotation_qc.parquet", index=False)
    info = {"labels_table": str(a.labels), "label_column": a.label_column, "group_column": a.group_column,
            "cells": int(len(lab)), "cells_missing_counts": int(miss.sum()), "genes": G, "labels": len(labels),
            "lineages": lineages, "unmapped_labels": unmapped, "label_map_source": map_source,
            "marker_source": marker_source, "flag_columns": fcols,
            "status_counts": lq.status.value_counts().to_dict(),
            "cells_by_status": cell.label_status.value_counts().to_dict(),
            "parameters": {k: v for k, v in vars(a).items() if k not in ("labels", "out_dir")},
            "versions": {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__},
            "elapsed_s": round(time.time() - t0, 1)}
    (out / "run_info.json").write_text(json.dumps(info, indent=1, default=str))
    print(json.dumps({"labels": info["status_counts"], "cells": info["cells_by_status"]}))


if __name__ == "__main__":
    main()
