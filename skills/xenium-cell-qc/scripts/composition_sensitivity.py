#!/usr/bin/env python
"""Composition sensitivity of QC-level cell types to the cell-QC definition (CPU).

Reads labels.parquet from rescue_labels.py and a per-cell table with the grouping column (region, core, ...)
and stage-1 flags. Per group, type proportions under six definitions:
  S0_floor_own_cluster      embedded cells with a transferable own-cluster type
  S1_fixed_threshold_own    S0 and gene counts >= --fixed-threshold
  S2_floor_minus_flags_own  S0 and none of --flag-columns
  S3_reference_only         reference cells
  S4_reference_rescued      reference + rescued_type (recommended; label_type)
  S5_all_best_guess         reference, rescued_type, rescued_lineage and unresolved cells with their best guess
Per group: total-variation (TV) distance of each definition from S4 against group depth (median gene
counts of all cells in the group); per type: median and IQR over groups of log2 ratios vs S4 (pseudocount
--pseudocount), and cohort proportions.

Outputs (--out-dir): composition_by_group.csv, tv_by_group.csv, composition_sensitivity.csv,
composition_cohort.csv, composition_info.json.

Example:
  python composition_sensitivity.py --labels rescue/labels.parquet --cells cell_table.parquet \\
      --group-column core_id --flag-columns flag_low_depth,flag_low_density --type-map type_map.csv --out-dir comp
"""
import argparse, json, os

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def as_bool(s):
    return s.values.astype(bool) if s.dtype == bool else s.astype(str).str.lower().isin(["true", "1", "1.0"]).values


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--labels", required=True); ap.add_argument("--cells", required=True,
                    help="parquet/csv keyed by obs_name with --group-column and --flag-columns")
    ap.add_argument("--type-map", required=True, help="csv: type, lineage (transferable types)")
    ap.add_argument("--group-column", required=True); ap.add_argument("--flag-columns", default="")
    ap.add_argument("--exclude-groups", default="", help="comma-separated group values to leave out")
    ap.add_argument("--fixed-threshold", type=float, default=50); ap.add_argument("--pseudocount", type=float, default=1e-3)
    ap.add_argument("--min-group-cells", type=int, default=200, help="groups with fewer S4 cells are not scored [200]")
    ap.add_argument("--min-scenario-cells", type=int, default=50,
                    help="a definition is not scored in a group where it keeps fewer cells [50]")
    ap.add_argument("--out-dir", required=True)
    a = ap.parse_args(); os.makedirs(a.out_dir, exist_ok=True); O = lambda f: os.path.join(a.out_dir, f)
    TYPES = list(pd.read_csv(a.type_map).type.astype(str))
    R = pd.read_parquet(a.labels)
    X = pd.read_parquet(a.cells) if a.cells.endswith(".parquet") else pd.read_csv(a.cells)
    X = X.set_index(X.obs_name.astype(str)).reindex(R.obs_name.astype(str))
    assert X[a.group_column].notna().all(), "cells table does not cover all labelled cells"
    grp = X[a.group_column].astype(str).values
    flags = [f for f in a.flag_columns.split(",") if f]
    anyflag = np.zeros(len(R), bool)
    for f in flags: anyflag |= as_bool(X[f].fillna(False))
    st = R.status.values; emb = (R.source == "embedded").values; own_ok = R.own_type.isin(TYPES).values
    isref = st == "reference"
    SC = {"S0_floor_own_cluster": (emb & own_ok, R.own_type.values),
          "S1_fixed_threshold_own": (emb & own_ok & (R.gene_counts.values >= a.fixed_threshold), R.own_type.values),
          "S2_floor_minus_flags_own": (emb & own_ok & ~anyflag, R.own_type.values),
          "S3_reference_only": (isref, R.own_type.values),
          "S4_reference_rescued": (isref | (st == "rescued_type"), R.label_type.values),
          "S5_all_best_guess": (np.isin(st, ["reference", "rescued_type", "rescued_lineage", "unresolved"]), R.best_type.values)}
    excl = set(x for x in a.exclude_groups.split(",") if x)
    keepg = ~np.isin(grp, list(excl))
    depth = pd.Series(R.gene_counts.values[keepg]).groupby(grp[keepg]).median()
    comp = []
    for s, (m, labv) in SC.items():
        m = m & keepg
        ct = pd.crosstab(grp[m], labv[m]).reindex(columns=TYPES, fill_value=0)
        pr = ct.div(ct.sum(1), axis=0)
        for g in ct.index:
            for t in TYPES:
                comp.append({"scenario": s, "group": g, "type": t, "cells": int(ct.loc[g, t]), "proportion": float(pr.loc[g, t])})
    comp = pd.DataFrame(comp); comp.to_csv(O("composition_by_group.csv"), index=False)
    n4 = comp[comp.scenario == "S4_reference_rescued"].groupby("group").cells.sum()
    ok = n4[n4 >= a.min_group_cells].index
    W = comp[comp.group.isin(ok)].pivot_table(index=["group", "type"], columns="scenario", values="proportion").fillna(0)
    ncell = comp.groupby(["scenario", "group"]).cells.sum()
    ref = "S4_reference_rescued"; tv_rows, rows = [], []
    for s in SC:
        if s == ref or s not in W: continue
        d = (W[s] - W[ref]).abs().groupby(level=0).sum() / 2
        ns = ncell.xs(s).reindex(d.index).fillna(0)
        d = d[ns >= a.min_scenario_cells]      # a definition with (almost) no cells in a group is not scored
        rho = spearmanr(d.values, depth.reindex(d.index).values)
        for g, v in d.items():
            tv_rows.append({"scenario": s, "group": g, "tv_vs_S4": float(v), "group_median_gene_counts": float(depth[g]),
                            "S4_cells": int(n4[g]), "scenario_cells": int(ns[g])})
        lr = np.log2((W[s] + a.pseudocount) / (W[ref] + a.pseudocount)).groupby(level=1)
        for t in TYPES:
            x = lr.get_group(t)
            x = x[x.index.get_level_values(0).isin(d.index)]
            rows.append({"scenario": s, "type": t, "median_log2_ratio_vs_S4": float(x.median()),
                         "iqr_log2_ratio": float(x.quantile(.75) - x.quantile(.25)),
                         "group_tv_median": float(d.median()), "group_tv_max": float(d.max()),
                         "tv_vs_group_depth_spearman": float(rho.correlation), "tv_vs_group_depth_p": float(rho.pvalue),
                         "groups_scored": int(len(d))})
    pd.DataFrame(tv_rows).to_csv(O("tv_by_group.csv"), index=False)
    pd.DataFrame(rows).to_csv(O("composition_sensitivity.csv"), index=False)
    coh = comp[comp.group.isin(ok)].groupby(["scenario", "type"]).cells.sum().unstack(0)
    (coh / coh.sum()).to_csv(O("composition_cohort.csv"))
    json.dump({"groups_scored": int(len(ok)), "groups_total": int(len(n4)), "excluded_groups": sorted(excl),
               "flag_columns": flags, "scenario_cells": {s: int((m & keepg).sum()) for s, (m, _) in SC.items()}},
              open(O("composition_info.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
