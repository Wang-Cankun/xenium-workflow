#!/usr/bin/env python3
"""Per-cell QC features and flags from native Xenium outputs. Flags and reasons only; nothing is removed.

Input: a CSV manifest with columns region_id and path (a Xenium output directory holding cells.parquet;
cell_feature_matrix.h5, cell/nucleus boundaries and transcripts.parquet are used when present).
Output (new directory): cell_qc.parquet, region_qc_summary.csv, qc_checks.json, and
group_qc_summary.csv when --groups is given.

Grouping unit: MAD flags are computed per region, or per region x group when --groups
supplies a cell -> group table (for example TMA cores; cells without a group form one
'ungrouped' group per region). MAD is scaled by 1.4826; groups with MAD 0 are not flagged.

Flags:
  pass_floor                  matrix gene transcripts >= --floor-transcripts and genes >= --floor-genes
  flag_low_depth_mad          log10(transcript_counts + 1) < median - NMAD * MAD
  flag_low_density_mad        log10((transcript_counts + 1) / cell_area) < median - NMAD * MAD
  flag_control_fraction_high  cells with >= 1 control count and a high control fraction,
                              control = probe + codeword + genomic + unassigned (deprecated codewords excluded).
                              Rule per region (--control-rule auto): 'mad' when at least --control-min-share
                              of cells carry any control count, log2((control + 0.5) / (transcripts + control + 1))
                              > median + NMAD * MAD; otherwise 'binomial', P(X >= control | n = transcripts +
                              control, p = region control rate) < --control-p.
  flag_nucleus_expansion      segmentation_method mentions nucleus expansion
  flag_group_low_depth        (with --groups) the cell's whole group has a median log10 depth below the
                              median over the region's groups - NMAD * MAD (groups with >= --min-group-cells)
  reference_candidate         pass_floor, >= --reference-min-transcripts, none of the flags above and,
                              with --groups, inside a named group
  low_information             pass_floor but not reference_candidate

Evidence only (not flags, no effect on reference_candidate):
  in_low_rna_bin              the cell's --bin-um square within its unit (named group with --groups, otherwise
                              region) has a median transcript count below --bin-ratio times the unit median
                              (squares with >= --bin-min-cells cells): regional signal loss, which per-unit MAD
                              confuses with low-quality cells
  group_qc_summary.csv        (with --groups) per group: median transcripts, nucleus-free share, share of cells below the
                              region-level MAD cut, share in low-RNA squares, and failure_evidence = the number
                              of whole-group failure detectors that agree (between-group flag, nucleus-free share
                              > 0.5, share below the region cut > 0.5, median transcripts < --abs-low-median)
"""
import argparse, json, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np, pandas as pd

K = 1.4826
CTRL = ["control_probe_counts", "control_codeword_counts", "genomic_control_counts", "unassigned_codeword_counts"]
FLAGS = ["flag_low_depth_mad", "flag_low_density_mad", "flag_control_fraction_high", "flag_nucleus_expansion",
         "flag_group_low_depth"]
UNGROUPED = "ungrouped"


def fail(msg):
    print(f"error: {msg}", file=sys.stderr); sys.exit(2)


def read_matrix_counts(h5):
    """Gene transcripts and genes detected per barcode from a 10x-style cell_feature_matrix.h5."""
    import h5py
    with h5py.File(h5, "r") as f:
        m = f["matrix"]
        gene = np.asarray(m["features/feature_type"]).astype(str) == "Gene Expression"
        data, ind, ptr = np.asarray(m["data"]), np.asarray(m["indices"]), np.asarray(m["indptr"])
        bc = np.asarray(m["barcodes"]).astype(str)
    keep = gene[ind]; col = np.repeat(np.arange(len(bc)), np.diff(ptr))
    tx = np.bincount(col[keep], weights=data[keep], minlength=len(bc))
    ng = np.bincount(col[keep & (data > 0)], minlength=len(bc))
    return pd.DataFrame({"cell_id": bc, "gene_transcripts": tx.astype(np.int64), "genes_detected": ng.astype(np.int64)})


def poly_stats(path):
    import pyarrow.parquet as pq
    t = pq.read_table(path, columns=["cell_id", "vertex_x", "vertex_y"]).to_pandas()
    cid = t.cell_id.astype(str).values
    brk = np.flatnonzero(np.r_[True, cid[1:] != cid[:-1]])
    x, y = t.vertex_x.values.astype(float), t.vertex_y.values.astype(float)
    xn, yn = np.roll(x, -1), np.roll(y, -1); last = np.r_[brk[1:], len(cid)] - 1
    xn[last], yn[last] = x[brk], y[brk]
    area = np.abs(np.add.reduceat(x * yn - xn * y, brk)) / 2; per = np.add.reduceat(np.hypot(xn - x, yn - y), brk)
    return pd.DataFrame({"cell_id": cid[brk], "poly_area": area, "circularity": 4 * np.pi * area / np.maximum(per, 1e-9) ** 2})


def tissue_distance(x, y, grid, close_um):
    """Distance to the tissue edge: centroid raster, morphological closing, hole filling, EDT."""
    from scipy import ndimage
    x0, y0 = x.min() - 5 * grid, y.min() - 5 * grid
    ix, iy = ((x - x0) / grid).astype(int), ((y - y0) / grid).astype(int)
    m = np.zeros((ix.max() + 6, iy.max() + 6), bool); m[ix, iy] = True
    m = ndimage.binary_closing(m, structure=ndimage.generate_binary_structure(2, 1), iterations=max(1, int(round(close_um / grid))))
    m = ndimage.binary_fill_holes(m)
    return ndimage.distance_transform_edt(m)[ix, iy] * grid


def one_region(job):
    import pyarrow.parquet as pq
    from scipy.spatial import cKDTree
    rid, path, a = job
    d = Path(path)
    c = pq.read_table(d / "cells.parquet").to_pandas()
    c["cell_id"] = c.cell_id.astype(str)
    if "segmentation_method" in c: c["segmentation_method"] = c.segmentation_method.astype(str)
    if (d / "cell_feature_matrix.h5").exists():
        c = c.merge(read_matrix_counts(d / "cell_feature_matrix.h5"), on="cell_id", how="left")
        c["has_matrix"] = c.gene_transcripts.notna()
    else:
        c["gene_transcripts"] = np.nan; c["genes_detected"] = np.nan; c["has_matrix"] = False
    for f, tag in (("cell_boundaries.parquet", "cell"), ("nucleus_boundaries.parquet", "nuc")):
        if (d / f).exists():
            s = poly_stats(d / f)
            if tag == "nuc": s = s.sort_values("poly_area").groupby("cell_id").tail(1)   # largest nucleus
            c = c.merge(s.add_prefix(f"{tag}_").rename(columns={f"{tag}_cell_id": "cell_id"}), on="cell_id", how="left")
    use_tx = (d / "transcripts.parquet").exists() and not a["skip_transcripts"]
    c["has_transcripts"] = use_tx
    if use_tx and len(c):
        t = pq.read_table(d / "transcripts.parquet", columns=["cell_id", "overlaps_nucleus", "qv", "is_gene"],
                          filters=[("is_gene", "==", True), ("qv", ">=", 20)]).to_pandas()
        t["cell_id"] = t.cell_id.astype(str); t = t[t.cell_id != "UNASSIGNED"]
        g = t.groupby("cell_id").overlaps_nucleus
        c = c.merge(pd.DataFrame({"tx_q20_gene": g.size(), "tx_nuclear_fraction": g.mean()}),
                    left_on="cell_id", right_index=True, how="left")
    if len(c):
        x, y = c.x_centroid.values.astype(float), c.y_centroid.values.astype(float)
        c["dist_to_edge_um"] = tissue_distance(x, y, a["grid_um"], a["close_um"])
        c["neighbours"] = [len(v) - 1 for v in cKDTree(np.c_[x, y]).query_ball_point(np.c_[x, y], a["neighbour_um"])]
    c.insert(0, "region_id", str(rid))
    return c


def region_outlier(x, reg, nmad, side):
    s = pd.Series(x); med = s.groupby(reg).transform("median"); mad = K * (s - med).abs().groupby(reg).transform("median")
    f = (s < med - nmad * mad) if side == "lower" else (s > med + nmad * mad)
    return (f & (mad > 0) & s.notna()).values


def read_groups(path, column):
    t = pd.read_parquet(path) if str(path).endswith(".parquet") else pd.read_csv(path, dtype=str)
    need = {"region_id", "cell_id", column}
    if not need <= set(t.columns): fail(f"--groups needs columns {sorted(need)}")
    t = t[["region_id", "cell_id", column]].astype(str).rename(columns={column: "group"})
    if t.duplicated(["region_id", "cell_id"]).any(): fail("--groups has duplicate region_id + cell_id rows")
    return t


def group_low_depth(df, nmad, min_cells):
    """Whole-group failure: group median log10 depth below the region's median over groups - NMAD * MAD."""
    named = df[df.group != UNGROUPED]
    g = (named.assign(log_tx=np.log10(named.transcript_counts.astype(float) + 1))
         .groupby(["region_id", "group"]).agg(cells=("log_tx", "size"), median_log_tx=("log_tx", "median")).reset_index())
    g["flag_group_low_depth"] = False
    for _, d in g[g.cells >= min_cells].groupby("region_id"):
        m = d.median_log_tx.median(); s = K * (d.median_log_tx - m).abs().median()
        if s > 0: g.loc[d.index, "flag_group_low_depth"] = d.median_log_tx < m - nmad * s
    bad = set(map(tuple, g.loc[g.flag_group_low_depth, ["region_id", "group"]].values))
    return np.array([(r, k) in bad for r, k in zip(df.region_id, df.group)], bool), g


def low_rna_bins(df, tx, key, use, bin_um, ratio, min_cells):
    """Cells whose square (bin_um) within their unit (key: region, or region x named group) has a median depth
    below ratio x the unit median; only cells in `use` are considered."""
    out = np.zeros(len(df), bool)
    named = use & np.isfinite(df.x_centroid.values) & np.isfinite(df.y_centroid.values)
    if not named.any():
        return out
    d = pd.DataFrame({"g": key[named], "tx": tx[named],
                      "bx": np.floor(df.x_centroid.values[named] / bin_um).astype(np.int64),
                      "by": np.floor(df.y_centroid.values[named] / bin_um).astype(np.int64)})
    gmed = d.groupby("g").tx.transform("median")
    b = d.groupby(["g", "bx", "by"]).tx
    low = (b.transform("median") < ratio * gmed) & (b.transform("size") >= min_cells) & (gmed > 0)
    out[np.flatnonzero(named)] = low.values
    return out


def control_flags(df, ctrl, tx, key, a):
    """High control fraction among cells with >= 1 control count; rule chosen per region (see --help)."""
    from scipy.stats import binom
    reg = df.region_id.values; share = pd.Series(ctrl > 0).groupby(reg).transform("mean").values
    rule_mad = (a.control_rule == "mad") | ((a.control_rule == "auto") & (share >= a.control_min_share))
    mad_flag = region_outlier(np.log2((ctrl + 0.5) / (tx + ctrl + 1)), key, a.nmad, "upper")
    tot = pd.Series(ctrl + tx).groupby(reg).transform("sum").values
    p = pd.Series(ctrl).groupby(reg).transform("sum").values / np.maximum(tot, 1)
    with np.errstate(invalid="ignore"):
        pv = binom.sf(ctrl - 1, (tx + ctrl).astype(np.int64), np.clip(p, 1e-12, 1))
    flag = (ctrl > 0) & np.where(rule_mad, mad_flag, pv < a.control_p)
    rules = pd.Series(np.where(rule_mad, "mad", "binomial")).groupby(reg).first()
    return flag, rules


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True, type=Path, help="CSV with region_id,path")
    ap.add_argument("--output", required=True, type=Path, help="New output directory")
    ap.add_argument("--nproc", type=int, default=4)
    ap.add_argument("--floor-transcripts", type=int, default=10); ap.add_argument("--floor-genes", type=int, default=5)
    ap.add_argument("--nmad", type=float, default=3.0); ap.add_argument("--reference-min-transcripts", type=int, default=50)
    ap.add_argument("--skip-transcripts", action="store_true", help="Do not read transcripts.parquet")
    ap.add_argument("--grid-um", type=float, default=20.0); ap.add_argument("--close-um", type=float, default=60.0)
    ap.add_argument("--neighbour-um", type=float, default=30.0)
    ap.add_argument("--groups", type=Path, help="CSV/parquet with region_id, cell_id and a group column (e.g. TMA core)")
    ap.add_argument("--group-column", default="group", help="Group column in --groups (default: group)")
    ap.add_argument("--min-group-cells", type=int, default=20, help="Minimum cells for a group to enter the between-group check")
    ap.add_argument("--control-rule", choices=["auto", "mad", "binomial"], default="auto")
    ap.add_argument("--control-min-share", type=float, default=0.05,
                    help="auto: use the MAD rule when at least this share of a region's cells has any control count")
    ap.add_argument("--control-p", type=float, default=1e-3, help="binomial rule p-value threshold")
    ap.add_argument("--bin-um", type=float, default=50.0, help="square size for the low-RNA square evidence [50]")
    ap.add_argument("--bin-ratio", type=float, default=0.5, help="square median below this x group median [0.5]")
    ap.add_argument("--bin-min-cells", type=int, default=5, help="cells needed in a square [5]")
    ap.add_argument("--abs-low-median", type=float, default=20.0,
                    help="group median transcripts below this counts as whole-group failure evidence [20]")
    a = ap.parse_args(); t0 = time.time()
    if a.output.exists(): fail(f"output exists: {a.output} (use a new directory)")
    man = pd.read_csv(a.manifest, dtype=str)
    if not {"region_id", "path"} <= set(man.columns): fail("manifest needs columns region_id and path")
    if man.region_id.duplicated().any(): fail("duplicate region_id in manifest")
    miss = [p for p in man.path if not (Path(p) / "cells.parquet").exists()]
    if miss: fail(f"cells.parquet missing in: {miss[:5]}")
    groups = read_groups(a.groups, a.group_column) if a.groups else None
    opts = {"skip_transcripts": a.skip_transcripts, "grid_um": a.grid_um, "close_um": a.close_um, "neighbour_um": a.neighbour_um}
    jobs = [(r.region_id, r.path, opts) for r in man.itertuples()]
    if a.nproc > 1 and len(jobs) > 1:
        with Pool(min(a.nproc, len(jobs))) as p: parts = p.map(one_region, jobs, chunksize=1)
    else:
        parts = [one_region(j) for j in jobs]
    df = pd.concat(parts, ignore_index=True)
    df["obs_name"] = df.region_id + "_" + df.cell_id
    if groups is not None:
        n0 = len(df); df = df.merge(groups, on=["region_id", "cell_id"], how="left", validate="one_to_one")
        assert len(df) == n0
        unmatched = int((~groups.set_index(["region_id", "cell_id"]).index.isin(df.set_index(["region_id", "cell_id"]).index)).sum())
        df["group"] = df.group.fillna(UNGROUPED)
    else:
        df["group"] = UNGROUPED; unmatched = 0
    key = (df.region_id + "|" + df.group).values
    tx = df.transcript_counts.astype(float).values
    area = df.cell_area.astype(float).clip(lower=1).values
    ctrl_cols = [c for c in CTRL if c in df]
    ctrl = df[ctrl_cols].sum(1).astype(float).values if ctrl_cols else np.zeros(len(df))
    df["density_tx_per_um2"] = tx / area; df["control_fraction"] = ctrl / np.maximum(ctrl + tx, 1)
    df["pass_floor"] = (df.has_matrix & (df.gene_transcripts >= a.floor_transcripts) & (df.genes_detected >= a.floor_genes)).astype(bool)
    df["flag_low_depth_mad"] = region_outlier(np.log10(tx + 1), key, a.nmad, "lower")
    df["flag_low_density_mad"] = region_outlier(np.log10((tx + 1) / area), key, a.nmad, "lower")
    df["flag_control_fraction_high"], control_rules = control_flags(df, ctrl, tx, key, a)
    df["flag_nucleus_expansion"] = (df.segmentation_method.str.contains("expansion", case=False).values
                                    if "segmentation_method" in df else np.zeros(len(df), bool))
    if groups is not None:
        df["flag_group_low_depth"], gsum = group_low_depth(df, a.nmad, a.min_group_cells)
        df["in_low_rna_bin"] = low_rna_bins(df, tx, key, (df.group != UNGROUPED).values, a.bin_um, a.bin_ratio, a.bin_min_cells)
        below_region_cut = region_outlier(np.log10(tx + 1), df.region_id.values, a.nmad, "lower")
    else:
        df["flag_group_low_depth"] = False; gsum = None
        df["in_low_rna_bin"] = low_rna_bins(df, tx, key, np.ones(len(df), bool), a.bin_um, a.bin_ratio, a.bin_min_cells)
    outside = (df.group == UNGROUPED).values if groups is not None else np.zeros(len(df), bool)
    df["reference_candidate"] = (df.pass_floor & (df.gene_transcripts >= a.reference_min_transcripts)
                                 & ~df[FLAGS].any(axis=1) & ~outside)
    df["low_information"] = df.pass_floor & ~df.reference_candidate
    R = np.full(len(df), "", dtype=object)
    for name, m in [("no_matrix", ~df.has_matrix), ("below_floor", df.has_matrix & ~df.pass_floor),
                    (f"lt{a.reference_min_transcripts}_transcripts", df.pass_floor & (df.gene_transcripts < a.reference_min_transcripts)),
                    ("low_depth_mad", df.flag_low_depth_mad), ("low_density_mad", df.flag_low_density_mad),
                    ("control_fraction_high", df.flag_control_fraction_high), ("nucleus_expansion", df.flag_nucleus_expansion),
                    ("group_low_depth", df.flag_group_low_depth), ("outside_group", outside)]:
        m = np.asarray(m, bool); R[m] = np.where(R[m] == "", name, R[m] + ";" + name)
    df["qc_reasons"] = R
    a.output.mkdir(parents=True)
    df.to_parquet(a.output / "cell_qc.parquet", index=False)
    if gsum is not None:
        gg = df.assign(_below_region_cut=below_region_cut).groupby(["region_id", "group"])
        extra = pd.DataFrame({"median_transcripts": gg.transcript_counts.median(),
                              "frac_no_nucleus": gg.nucleus_count.apply(lambda s: float((s == 0).mean())) if "nucleus_count" in df else np.nan,
                              "share_below_region_cut": gg._below_region_cut.mean(), "share_low_rna_bins": gg.in_low_rna_bin.mean(),
                              "pass_floor": gg.pass_floor.sum(), "reference_candidate": gg.reference_candidate.sum(),
                              **{k.replace("flag_", ""): gg[k].sum() for k in FLAGS[:4]}}).reset_index()
        gq = gsum.merge(extra, on=["region_id", "group"], how="right")
        gq["flag_group_low_depth"] = gq.flag_group_low_depth.fillna(False).astype(bool)
        gq["failure_evidence"] = (gq.flag_group_low_depth.astype(int) + (gq.frac_no_nucleus.fillna(0) > 0.5).astype(int)
                                  + (gq.share_below_region_cut > 0.5).astype(int) + (gq.median_transcripts < a.abs_low_median).astype(int))
        gq.loc[gq.group == UNGROUPED, "failure_evidence"] = 0
        gq.to_csv(a.output / "group_qc_summary.csv", index=False)
    g = df.groupby("region_id")
    summ = pd.DataFrame({"cells": g.size(), "matrix_cells": g.has_matrix.sum(), "median_transcripts": g.transcript_counts.median(),
                         "median_density": g.density_tx_per_um2.median(), "pass_floor": g.pass_floor.sum(),
                         **{k.replace("flag_", ""): g[k].sum() for k in FLAGS},
                         "reference_candidate": g.reference_candidate.sum(), "low_information": g.low_information.sum(),
                         "low_rna_bin_cells": g.in_low_rna_bin.sum()})
    summ["reference_fraction_of_matrix"] = summ.reference_candidate / summ.matrix_cells.replace(0, np.nan)
    summ["control_rule"] = control_rules.reindex(summ.index)
    summ["frac_any_control"] = pd.Series(ctrl > 0).groupby(df.region_id.values).mean().reindex(summ.index)
    summ.reset_index().to_csv(a.output / "region_qc_summary.csv", index=False)
    e = df[df.has_matrix]
    chk = {"manifest": str(a.manifest.resolve()), "regions": int(df.region_id.nunique()), "cells": int(len(df)),
           "matrix_cells": int(len(e)), "matrix_regions": int(e.region_id.nunique()),
           "matrix_equals_native_transcripts": float((e.gene_transcripts == e.transcript_counts).mean()) if len(e) else None,
           "control_columns": ctrl_cols, "control_rule_by_region": control_rules.to_dict(),
           "groups": None if groups is None else {
               "table": str(a.groups), "column": a.group_column, "named_groups": int((gsum.group != UNGROUPED).sum()),
               "ungrouped_cells": int(outside.sum()), "group_rows_not_in_outputs": unmatched,
               "low_depth_groups": gsum.loc[gsum.flag_group_low_depth, ["region_id", "group"]].values.tolist(),
               "groups_with_2plus_failure_evidence": gq.loc[gq.failure_evidence >= 2, ["region_id", "group"]].values.tolist(),
               "cells_in_low_rna_bins": int(df.in_low_rna_bin.sum())},
           "cells_in_low_rna_bins": int(df.in_low_rna_bin.sum()),
           "transcript_feature_cells": int(df["tx_q20_gene"].notna().sum()) if "tx_q20_gene" in df else 0,
           "counts": {k: int(df[k].sum()) for k in ["pass_floor", *FLAGS, "reference_candidate", "low_information"]},
           "parameters": {k: v for k, v in vars(a).items() if k not in ("manifest", "output")},
           "versions": {"python": sys.version.split()[0], "pandas": pd.__version__, "numpy": np.__version__},
           "elapsed_s": round(time.time() - t0, 1)}
    (a.output / "qc_checks.json").write_text(json.dumps(chk, indent=1, default=str))
    print(json.dumps(chk["counts"]))


if __name__ == "__main__":
    main()
