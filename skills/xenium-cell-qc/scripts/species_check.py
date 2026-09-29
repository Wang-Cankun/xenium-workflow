#!/usr/bin/env python3
"""Species check for label rescue in mixed-species designs (CPU; reads the H5AD with h5py).

Scores every cell with species-specific probes and compares the probe-based species with the
species implied by its QC-level label. Needs a counts H5AD (CSR layer, obs_names as in the labels),
labels.parquet from rescue_labels.py, and a map from types or lineages to species. Types or
lineages that are not mapped are treated as species-neutral and are not compared.

Per cell: counts on each species' probes, the share of the first --species (for two species, e.g.
the human share), a probe call (a species when its share >= --call-share of at least
--min-probe-counts probe counts, else 'undetermined'), the label species (from label_type, then
label_lineage; best guesses for unresolved cells are kept separately) and whether they agree.

Outputs (--out-dir, must not exist):
  species_cells.parquet          per-cell probe counts, share, probe call, label species, agreement
  share_by_label_status.csv      probe share per label species (and label type) x status
  agreement_by_status.csv        label species x probe call per status
  labels_by_group.csv            label species x status per --group-columns value (with --cells)
  unexpected_labels.csv          labels of species not allowed in a group (with --expected)
  species_info.json              inputs, parameters and headline counts

Example:
  python species_check.py --h5ad counts.h5ad --labels rescue/labels.parquet \
      --species human=B2M,NACA --species mouse=B2m,Naca --lineage-species tumour_human=human,tumour_mouse=mouse \
      --cells cell_table.parquet --group-columns region_id,species_group --expected expected.csv --out-dir species
"""
import argparse, json, sys
from pathlib import Path
import h5py
import numpy as np
import pandas as pd


def fail(msg):
    print(f"error: {msg}", file=sys.stderr); sys.exit(2)


def dec(a):
    return np.array([x.decode() if isinstance(x, bytes) else str(x) for x in a], dtype=object)


def index_of(group):
    """obs/var names: anndata's reader when installed, else a plain or categorical index array."""
    try:
        from anndata.io import read_elem
    except ImportError:
        try:
            from anndata.experimental import read_elem
        except ImportError:
            read_elem = None
    key = group.attrs.get("_index", "_index")
    key = key.decode() if isinstance(key, bytes) else key
    if read_elem is not None:
        return np.asarray(read_elem(group[key]), dtype=object).astype(str).astype(object)
    el = group[key]
    if isinstance(el, h5py.Group) and {"codes", "categories"} <= set(el):
        return dec(el["categories"][:])[el["codes"][:]]
    return dec(el[:])


def read_probe_counts(path, layer, genes):
    """Per-cell counts for the requested genes from a CSR layer (or X) of an H5AD, without anndata."""
    with h5py.File(path, "r") as f:
        obs, var = index_of(f["obs"]), index_of(f["var"])
        g = f["layers"][layer] if layer != "X" else f["X"]
        if not isinstance(g, h5py.Group) or "indptr" not in g:
            fail(f"layer {layer} is not a sparse matrix group")
        enc = g.attrs.get("encoding-type", b"csr_matrix")
        enc = enc.decode() if isinstance(enc, bytes) else enc
        if enc != "csr_matrix":
            fail(f"layer {layer} is {enc}; a CSR (cells x genes) layer is required")
        pos = {v: i for i, v in enumerate(var)}
        miss = [x for x in genes if x not in pos]
        if miss: fail(f"probes not in var_names: {miss}")
        want = np.array([pos[x] for x in genes]); col_of = {c: k for k, c in enumerate(want)}
        ptr = g["indptr"][:]; out = np.zeros((len(obs), len(genes)), np.int64)
        step = 20_000_000
        for s in range(0, int(ptr[-1]), step):
            e = min(s + step, int(ptr[-1]))
            ind = g["indices"][s:e]; dat = g["data"][s:e]
            hit = np.isin(ind, want)
            if not hit.any(): continue
            rows = np.searchsorted(ptr, np.arange(s, e)[hit], side="right") - 1
            cols = np.array([col_of[c] for c in ind[hit]])
            np.add.at(out, (rows, cols), dat[hit].astype(np.int64))
    return pd.DataFrame(out, index=pd.Index(obs, name="obs_name"), columns=genes)


def parse_sets(items, what):
    sets = {}
    for it in items:
        if "=" not in it: fail(f"{what} needs NAME=a,b: {it}")
        k, v = it.split("=", 1); sets[k] = [x for x in v.split(",") if x]
    return sets


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--h5ad", required=True); ap.add_argument("--layer", default="counts")
    ap.add_argument("--labels", required=True, help="labels.parquet from rescue_labels.py")
    ap.add_argument("--species", action="append", required=True, help="NAME=gene1,gene2 (repeat per species; first one gives the share)")
    ap.add_argument("--type-species", help="CSV with type,species")
    ap.add_argument("--lineage-species", default="", help="lineage=species,... used when the type is not mapped")
    ap.add_argument("--cells", help="table with obs_name and the --group-columns (parquet or CSV)")
    ap.add_argument("--group-columns", default="", help="comma-separated grouping columns (from --cells or labels)")
    ap.add_argument("--expected", help="CSV with the --group-columns and allowed_species (semicolon-separated)")
    ap.add_argument("--min-probe-counts", type=int, default=2)
    ap.add_argument("--call-share", type=float, default=0.8)
    ap.add_argument("--out-dir", required=True, type=Path)
    a = ap.parse_args()
    if a.out_dir.exists(): fail(f"output exists: {a.out_dir}")
    sets = parse_sets(a.species, "--species")
    if len(sets) < 2: fail("give at least two --species sets")
    type_sp = (pd.read_csv(a.type_species, dtype=str).set_index("type").species.to_dict() if a.type_species else {})
    pairs = [x for x in a.lineage_species.split(",") if x]
    if any("=" not in x for x in pairs): fail("--lineage-species needs lineage=species,...")
    lin_sp = dict(x.split("=", 1) for x in pairs)
    unknown = set(type_sp.values()) | set(lin_sp.values()); unknown -= set(sets)
    if unknown: fail(f"mapped species without probes: {sorted(unknown)}")

    L = pd.read_parquet(a.labels).set_index("obs_name")
    genes = [g for v in sets.values() for g in v]
    P = read_probe_counts(a.h5ad, a.layer, genes).reindex(L.index)
    if P.isna().any(axis=None): fail("labels contain obs_names that are not in the H5AD")
    names = list(sets)
    D = pd.DataFrame(index=L.index)
    for s in names: D[f"probe_{s}"] = P[sets[s]].sum(1).astype(np.int64)
    tot = D[[f"probe_{s}" for s in names]].sum(1)
    D["probe_total"] = tot
    D[f"share_{names[0]}"] = D[f"probe_{names[0]}"] / tot.replace(0, np.nan)
    call = np.full(len(D), "undetermined", dtype=object)
    for s in names:
        call[((D[f"probe_{s}"] / tot.replace(0, np.nan)) >= a.call_share).values & (tot >= a.min_probe_counts).values] = s
    D["probe_species"] = call

    def species_of(t, lin):
        if t in type_sp: return type_sp[t]
        if lin in lin_sp: return lin_sp[lin]
        return "neutral"
    D["status"] = L.status.values
    D["label_type"], D["label_lineage"] = L.label_type.values, L.label_lineage.values
    D["label_species"] = [species_of(t, l) for t, l in zip(L.label_type, L.label_lineage)]
    D.loc[D.status.isin(["unresolved", "unresolved_no_signal", "below_floor"]), "label_species"] = "unlabelled"
    if "best_type" in L:
        D["best_guess_species"] = [species_of(t, l) for t, l in zip(L.best_type, L.best_lineage)]
    comparable = D.label_species.isin(names) & (D.probe_species != "undetermined")
    D["species_agree"] = np.where(comparable, D.label_species == D.probe_species, np.nan)

    groups = [c for c in a.group_columns.split(",") if c]
    if groups:
        if a.cells:
            C = pd.read_parquet(a.cells) if a.cells.endswith(".parquet") else pd.read_csv(a.cells, dtype=str)
            miss = [c for c in ["obs_name", *groups] if c not in C]
            if miss: fail(f"--cells lacks columns {miss}")
            C = C.set_index("obs_name")[groups].reindex(D.index)
        else:
            miss = [c for c in groups if c not in L]
            if miss: fail(f"group columns {miss} are not in labels; give --cells")
            C = L[groups]
        for c in groups: D[c] = C[c].astype(str).values
    a.out_dir.mkdir(parents=True)
    D.reset_index().to_parquet(a.out_dir / "species_cells.parquet", index=False)

    pc = [f"probe_{s}" for s in names]
    rows = []
    for keys, d in D.groupby(["label_species", "label_type", "status"], observed=True):
        s = d[pc].sum()
        rows.append({"label_species": keys[0], "label_type": keys[1], "status": keys[2], "cells": len(d),
                     **{c: int(s[c]) for c in pc}, "cells_with_probe": int((d.probe_total > 0).sum()),
                     f"share_{names[0]}": float(s[pc[0]] / s.sum()) if s.sum() else np.nan})
    share = pd.DataFrame(rows)
    pooled = share.groupby(["label_species", "status"], as_index=False)[["cells", *pc, "cells_with_probe"]].sum()
    pooled[f"share_{names[0]}"] = pooled[pc[0]] / pooled[pc].sum(1).replace(0, np.nan); pooled["label_type"] = "(all)"
    pd.concat([pooled, share], ignore_index=True).to_csv(a.out_dir / "share_by_label_status.csv", index=False)
    pd.crosstab([D.status, D.label_species], D.probe_species).to_csv(a.out_dir / "agreement_by_status.csv")

    info = {"h5ad": a.h5ad, "labels": a.labels, "species": sets, "type_species": type_sp, "lineage_species": lin_sp,
            "min_probe_counts": a.min_probe_counts, "call_share": a.call_share, "cells": int(len(D)),
            "cells_with_probe": int((D.probe_total > 0).sum()),
            "comparable_cells": int(comparable.sum()),
            "agreement_by_status": {st: float(d.species_agree.astype(float).mean())
                                    for st, d in D[comparable].groupby("status")}}
    if groups:
        lab = D.groupby([*groups, "status", "label_species"]).size().rename("cells").reset_index()
        lab.to_csv(a.out_dir / "labels_by_group.csv", index=False)
        if a.expected:
            E = pd.read_csv(a.expected, dtype=str)
            miss = [c for c in [*groups, "allowed_species"] if c not in E]
            if miss: fail(f"--expected lacks columns {miss}")
            m = lab.merge(E, on=groups, how="left")
            allowed = m.allowed_species.fillna("").str.split(";")
            bad = m[m.label_species.isin(names).values
                    & ~np.array([s in al for s, al in zip(m.label_species, allowed)])
                    & m.allowed_species.notna().values]
            bad.to_csv(a.out_dir / "unexpected_labels.csv", index=False)
            info["unexpected_labels_by_status"] = bad.groupby("status").cells.sum().astype(int).to_dict()
            info["groups_without_expectation"] = int(m.allowed_species.isna().groupby([m[c] for c in groups]).any().sum())
    (a.out_dir / "species_info.json").write_text(json.dumps(info, indent=1, default=str))
    print(json.dumps({k: info[k] for k in ["cells", "cells_with_probe", "comparable_cells", "agreement_by_status"]}))


if __name__ == "__main__":
    main()
