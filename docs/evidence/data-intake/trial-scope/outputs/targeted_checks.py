"""Read-only package-specific checks; run from the isolated workspace root."""
import json
from pathlib import Path
from collections import Counter
import h5py
import numpy as np

root = Path(__file__).resolve().parent.parent
result = {}
for package in ("explicit", "unclear", "additional", "empty-candidate"):
    with h5py.File(root / "deliveries" / package / "expression.h5ad", "r") as f:
        obs = f["obs"]
        ids = obs["_index"].asstr()[()].tolist()
        specimens = obs["specimen"].asstr()[()].tolist()
        cores = obs["core"].asstr()[()].tolist()
        groups = obs["group"].asstr()[()].tolist()
        coords = f["obsm/spatial"][()]
        features = f["var/_index"].asstr()[()].tolist()
        composite = list(zip(specimens, ids))
        frames = {}
        for specimen, core in sorted(set(zip(specimens, cores))):
            mask = np.array([s == specimen and c == core for s, c in zip(specimens, cores)])
            xy = coords[mask]
            frames[f"{specimen}/{core}"] = {
                "cells": int(mask.sum()), "nonfinite_values": int((~np.isfinite(xy)).sum()),
                "axis_min": xy.min(axis=0).tolist(), "axis_max": xy.max(axis=0).tolist(),
                "collapsed_axes": np.flatnonzero(np.ptp(xy, axis=0) == 0).tolist(),
                "duplicate_coordinate_rows": len(xy) - len(np.unique(xy, axis=0)),
            }
        matrices = {}
        names = (["X"] if "X" in f else []) + ["layers/" + key for key in f.get("layers", {})]
        if "raw" in f and "X" in f["raw"]:
            names.append("raw/X")
        for name in names:
            a = f[name][()]
            matrices[name] = {
                "shape": list(a.shape), "all_values": a.tolist(),
                "all_zero": bool(np.all(a == 0)),
                "empty_columns": int(np.all(a == 0, axis=0).sum()),
                "axis_correspondence": list(a.shape) == [len(composite), len(features)],
            }
        result[package] = {
            "file": f"deliveries/{package}/expression.h5ad",
            "root_objects": sorted(f.keys()), "expression_matrix_present": bool(matrices),
            "composite_key": ["specimen", "_index"],
            "composite_key_duplicate_rows": len(composite) - len(set(composite)),
            "composite_keys": [list(key) for key in composite],
            "missing_or_blank_key_components": sum(not isinstance(v, str) or not v.strip() for key in composite for v in key),
            "specimen_counts": dict(Counter(specimens)),
            "specimen_core_group_rows": [list(row) for row in zip(specimens, cores, groups)],
            "feature_labels": features, "matrices": matrices, "coordinate_frames": frames,
            "join_evidence": "Expression, obs, and obsm are internal to one supplied H5 object and have matching cell axes; there are no external per-cell tables to join.",
        }
payload = json.dumps(result, indent=2, allow_nan=False)
with (root / "outputs" / "targeted-checks.json").open("x") as out:
    out.write(payload + "\n")
print(payload)
