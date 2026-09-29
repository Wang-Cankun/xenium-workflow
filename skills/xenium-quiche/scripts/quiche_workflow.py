#!/usr/bin/env python3
"""Validate a prepared H5AD and call pinned QUICHE APIs; never install dependencies."""
import argparse
import importlib
import importlib.metadata
import json
import os
import socket
import sys
from pathlib import Path
import platform

QUICHE_REVISION = "a9077f242ead80577c2aa4aedd46e25798e4475b"


def read_cells(path, labels_key, fov_key, spatial_key, subject_key=None, condition_key=None):
    """Read only the selected metadata and coordinates; expression is not used."""
    import h5py
    import numpy as np
    import pandas as pd

    def text(value):
        return value.decode() if isinstance(value, bytes) else value

    def column(obj):
        if isinstance(obj, h5py.Dataset):
            return obj.asstr()[()] if obj.dtype.kind in "OSU" else obj[()]
        if "categories" in obj and "codes" in obj:
            cats, codes = column(obj["categories"]), obj["codes"][()]
            if np.any((codes < -1) | (codes >= len(cats))):
                raise ValueError("Invalid categorical codes")
            return [None if code == -1 else cats[code] for code in codes]
        if "values" in obj and "mask" in obj:
            values = np.array(column(obj["values"]), dtype=object)
            values[obj["mask"][()]] = None
            return values
        raise ValueError("Unsupported obs column encoding: " + obj.name)

    with h5py.File(path, "r") as f:
        obs = f["obs"]
        index = text(obs.attrs.get("_index", "_index"))
        keys = dict(label=labels_key, fov=fov_key)
        if subject_key:
            keys["subject"] = subject_key
        if condition_key:
            keys["condition"] = condition_key
        data = {name: column(obs[key]) for name, key in keys.items()}
        cells = pd.DataFrame(data, index=pd.Index(column(obs[index]), name="cell_id"))
        coordinates = np.asarray(f["obsm"][spatial_key][()])
    return cells, coordinates


def validate_cells(cells, coordinates, units, frame, radius, min_neighbors=3,
                   n_neighbors=None, da=False, reference=None, comparison=None,
                   biological_identity_confirmed=False):
    import numpy as np
    if units not in ("micrometer", "pixel"):
        raise ValueError("Explicit coordinate units must be micrometer or pixel")
    if not frame or not str(frame).strip():
        raise ValueError("An explicit coordinate frame is required")
    if not np.isfinite(radius) or radius <= 0 or min_neighbors < 1:
        raise ValueError("Radius must be finite/positive and min_neighbors >= 1")
    if cells.empty or not cells.index.is_unique or cells.index.hasnans:
        raise ValueError("Cell IDs must be present and globally unique")
    if any(not isinstance(x, str) or not x.strip() for x in cells.index):
        raise ValueError("Cell IDs must be nonempty strings")
    for key in ["label", "fov"] + (["subject", "condition"] if da else []):
        if key not in cells or cells[key].isna().any():
            raise ValueError("Missing metadata: " + key)
        if any(not isinstance(x, str) or not x.strip() for x in cells[key]):
            raise ValueError("Metadata must contain explicit nonempty string labels: " + key)
    if coordinates.shape != (len(cells), 2) or not np.issubdtype(coordinates.dtype, np.number):
        raise ValueError("Coordinates must be an aligned numeric n_cells x 2 array")
    if not np.isfinite(coordinates).all():
        raise ValueError("Coordinates contain nonfinite values")
    if n_neighbors is not None:
        if n_neighbors < min_neighbors or n_neighbors >= cells.groupby("fov").size().min():
            raise ValueError("k must be >= min_neighbors and smaller than each FOV cell count")
    if da:
        if not biological_identity_confirmed:
            raise ValueError("Confirm biological subject identities before differential analysis")
        if cells.groupby("fov")["subject"].nunique().max() != 1:
            raise ValueError("Each FOV must map to one biological subject")
        if cells.groupby("subject")["condition"].nunique().max() != 1:
            raise ValueError("This two-group recipe requires one condition per subject")
        if reference == comparison or not reference or not comparison:
            raise ValueError("Specify distinct reference and comparison conditions")
        if set(cells.condition) != {reference, comparison}:
            raise ValueError("Input must contain exactly the two requested conditions")
        groups = cells[["subject", "condition"]].drop_duplicates().groupby("condition").size()
        if groups.min() < 2:
            raise ValueError("At least two independent subjects per condition are required")
    return {"cells": len(cells), "fovs": int(cells.fov.nunique()),
            "labels": sorted(cells.label.unique().tolist()), "units": units,
            "frame": frame, "radius": radius, "min_neighbors": min_neighbors,
            "n_neighbors": n_neighbors, "inference": bool(da)}


def audit_graph(cells, coordinates, graph, radius):
    import numpy as np
    g = graph.tocsr(copy=True)
    g.eliminate_zeros()
    if g.shape != (len(cells), len(cells)) or not np.isfinite(g.data).all():
        raise ValueError("Invalid spatial graph shape or values")
    rows, cols = g.nonzero()
    fovs = cells.fov.to_numpy()
    if np.any(fovs[rows] != fovs[cols]):
        raise ValueError("Spatial graph contains cross-FOV edges")
    if np.any(rows == cols):
        raise ValueError("Spatial graph unexpectedly includes focal cells")
    distances = np.linalg.norm(coordinates[rows] - coordinates[cols], axis=1)
    if np.any(distances > radius + max(1., radius) * 1e-7):
        raise ValueError("Spatial graph exceeds the requested coordinate radius")
    return {"directed_edges": len(rows), "cross_fov_edges": 0,
            "isolated_cells": int((g.getnnz(axis=1) == 0).sum())}


def load_backend():
    """Require the reviewed Git revision; no package download or installation."""
    distribution = importlib.metadata.distribution("quiche")
    direct = json.loads(distribution.read_text("direct_url.json") or "{}")
    installed = direct.get("vcs_info", {}).get("commit_id")
    if installed != QUICHE_REVISION:
        raise RuntimeError("QUICHE must be installed from the reviewed Git revision " + QUICHE_REVISION)
    return importlib.import_module("quiche")


def compute_niches(adata, backend, radius, min_neighbors, n_neighbors=None, n_jobs=1):
    """Use QUICHE's graph and composition APIs; audit returned spatial edges."""
    import numpy as np
    spatial = backend.tl.compute_spatial_neighbors(
        adata.copy(), radius=radius, n_neighbors=n_neighbors, spatial_key="spatial",
        fov_key="fov", coord_type="generic", delaunay=False)
    audit = audit_graph(spatial.obs, spatial.obsm["spatial"],
                        spatial.obsp["spatial_connectivities"], radius)
    niches, insufficient = backend.tl.compute_niche_composition(
        spatial, labels_key="label", min_cell_threshold=min_neighbors)
    if not niches.obs_names.equals(spatial.obs_names):
        raise ValueError("QUICHE niche cell order differs from spatial graph")
    # QUICHE reports insufficient-neighbor centers but does not itself remove all of them.
    eligible = ~niches.obs_names.isin(insufficient)
    eligible &= np.isfinite(niches.X).all(axis=1) & (np.asarray(niches.X).sum(axis=1) > 0)
    kept = niches[eligible].copy()
    if len(kept):
        if not np.allclose(np.asarray(kept.X).sum(axis=1), 1.) or np.any(kept.X < 0):
            raise ValueError("QUICHE returned invalid local composition proportions")
    kept.obsm["spatial"] = spatial.obsm["spatial"][eligible].copy()
    return spatial, kept, audit, spatial.obs_names[~eligible].tolist()


def differential(spatial, niches, backend, reference, comparison, sketch_size, k_sim, seed, n_jobs):
    import pandas as pd
    work = spatial[niches.obs_names].copy()
    work.obs["quicheCondition"] = pd.Categorical(
        work.obs.condition.map({reference: "A", comparison: "B"}), categories=["A", "B"])
    # None makes upstream overwrite obs["label"]; keep segmentation identity separate.
    work.obs["quicheSegmentation"] = work.obs_names.to_numpy()
    op = backend.tl.QUICHE(adata=work, labels_key="label", spatial_key="spatial",
                          fov_key="fov", patient_key="subject", segmentation_label_key="quicheSegmentation")
    # Continue QUICHE with its already-computed, audited local niches.
    op.adata_niche = niches.copy()
    op.adata_niche.obs = work.obs.copy()
    op.subsample(sketch_size=sketch_size, sketch_key="subject", frequency_seed=seed, n_jobs=n_jobs)
    if op.adata_niche_subsample.n_obs <= k_sim or k_sim < 2:
        raise ValueError("k_sim must be >= 2 and smaller than the retained niche count")
    retained = op.adata_niche_subsample.obs[["subject", "condition"]].drop_duplicates()
    if retained.groupby("condition").subject.nunique().reindex([reference, comparison], fill_value=0).min() < 2:
        raise ValueError("Niche filtering left fewer than two subjects per condition")
    # Pertpy0.6 adds +0 when a contrast is supplied; putting 0 here misparses it as metadata.
    op.differential_enrichment(k_sim=k_sim, design="~quicheCondition",
        model_contrasts="quicheConditionB-quicheConditionA", solver="edger", n_jobs=n_jobs)
    op.annotate_niches(annotation_key="quiche_niche", extrapolate=False,
                       k_sim=k_sim, n_jobs=n_jobs)
    return op


def normalize_metadata_table(frame):
    """Recover numeric/bool scalar dtypes after upstream heterogeneous .values assignment."""
    normalized = frame.infer_objects()
    changes = [{"column": str(key), "from": str(frame[key].dtype), "to": str(normalized[key].dtype)}
               for key in frame.columns if frame[key].dtype != normalized[key].dtype]
    return normalized, changes


def sampled_unit_policy(policy, confirmed):
    if policy == "source_block_record":
        if confirmed:
            raise ValueError("source_block_record cannot be combined with biological-identity-confirmed")
        return dict(analysis_unit_policy=policy, biological_identity_status="unresolved",
                    between_unit_independence="working_assumption",
                    inference_scope="exploratory_named_group_association")
    if policy != "confirmed_biological_subject" or not confirmed:
        raise ValueError("Confirm biological identities or explicitly select source_block_record")
    return dict(analysis_unit_policy=policy, biological_identity_status="confirmed_by_caller",
                between_unit_independence="model_assumption", inference_scope="confirmed_subject_group_comparison")


def select_precomputed(cells, core_metadata, unit_key, condition_key, reference, comparison,
                       cap, seed, core_key="sample_id"):
    """Select unchanged center IDs uniformly within explicit units; independent of input row order."""
    import numpy as np
    import pandas as pd
    if not 1 <= cap <= 1000 or seed < 0:
        raise ValueError("Uniform cap must be 1..1000 and seed must be nonnegative")
    keys = list(dict.fromkeys([core_key, unit_key, condition_key]))
    if not set(keys).issubset(core_metadata):
        raise ValueError("Core metadata lacks requested core/unit/condition columns")
    if core_metadata[core_key].duplicated().any():
        raise ValueError("Duplicate core metadata mapping")
    for key in keys:
        if core_metadata[key].isna().any() or not core_metadata[key].map(lambda x: isinstance(x, str) and bool(x.strip())).all():
            raise ValueError("Missing/non-string core mapping: " + key)
    if not set(cells.fov).issubset(set(core_metadata[core_key])):
        raise ValueError("Unmapped niche FOV in core metadata")
    if core_metadata.groupby(unit_key)[condition_key].nunique().max() != 1:
        raise ValueError("Each working unit must have one named condition")
    if not reference or not comparison or reference == comparison:
        raise ValueError("Specify two distinct named groups")
    mapping = core_metadata.set_index(core_key)
    selected = cells.copy()
    selected["analysis_unit_id"] = selected.fov.map(mapping[unit_key]).astype(str)
    selected["source_group"] = selected.fov.map(mapping[condition_key]).astype(str)
    selected = selected.loc[selected.source_group.isin([reference, comparison])].copy()
    expected = core_metadata.loc[core_metadata[condition_key].isin([reference, comparison]), unit_key]
    if set(selected.analysis_unit_id) != set(expected):
        raise ValueError("A requested working unit has no eligible centers")
    design = selected[["analysis_unit_id", "source_group"]].drop_duplicates()
    sizes = design.groupby("source_group").size().reindex([reference, comparison], fill_value=0)
    if sizes.min() < 2:
        raise ValueError("At least two working units per named group are required")
    rng = np.random.default_rng(seed)
    ids, rows = [], []
    for unit in sorted(design.analysis_unit_id):
        candidates = sorted(selected.index[selected.analysis_unit_id.eq(unit)])
        chosen = sorted(rng.choice(candidates, size=min(cap, len(candidates)), replace=False).tolist())
        ids.extend(chosen)
        group = selected.loc[candidates[0], "source_group"]
        rows.append(dict(analysis_unit_id=unit, source_group=group, eligible_centers=len(candidates),
                         sampled_centers=len(chosen), seed=seed))
    sampled = selected.loc[ids].copy()
    sampled["subject"] = sampled.analysis_unit_id
    sampled["condition"] = sampled.source_group
    return sampled, pd.DataFrame(rows)


def read_precomputed_selection(args):
    """Validate the canonical niche output and read only sampled matrix rows with h5py."""
    import h5py
    import numpy as np
    import pandas as pd
    policy = sampled_unit_policy(args.analysis_unit_policy, args.biological_identity_confirmed)
    if args.sketch_size is not None:
        raise ValueError("Uniform precomputed DA does not accept native --sketch-size")
    source = json.loads(args.source_manifest.read_text())
    if args.input.resolve() != args.source_manifest.resolve().parent / "local-niches.h5ad":
        raise ValueError("Use local-niches.h5ad beside its source manifest")
    if source.get("status") != "complete" or source.get("configuration", {}).get("mode") != "niches":
        raise ValueError("Require a completed descriptive niches source run")
    if source.get("quiche_revision") != QUICHE_REVISION or source.get("graph_audit", {}).get("cross_fov_edges") != 0:
        raise ValueError("Source revision or core-isolated graph audit is invalid")
    conf = source["configuration"]
    cells, coordinates = read_cells(args.input, "label", "fov", "spatial")
    validate_cells(cells, coordinates, conf["units"], conf["frame"], conf["radius"], conf["min_neighbors"])
    if len(cells) != source.get("retained_centers"):
        raise ValueError("Source manifest and niche row count disagree")
    metadata = pd.read_csv(args.core_metadata, sep="\t", dtype=str, keep_default_na=False)
    sampled, summary = select_precomputed(cells, metadata, args.unit_key, args.condition_key,
        args.reference, args.comparison, args.uniform_per_unit, args.seed, args.core_key)
    if args.k_sim < 2 or args.k_sim >= len(sampled):
        raise ValueError("k-sim must be >=2 and smaller than the sampled center count")
    positions = cells.index.get_indexer(sampled.index)
    # h5py fancy indices must be increasing; restore the stable selected-ID order afterwards.
    order = np.argsort(positions)
    with h5py.File(args.input, "r") as handle:
        matrix = handle["X"]
        if not isinstance(matrix, h5py.Dataset) or matrix.ndim != 2 or matrix.shape[0] != len(cells):
            raise ValueError("Precomputed entry requires the canonical dense local-composition X")
        var = handle["var"]
        index_key = var.attrs.get("_index", "_index")
        if isinstance(index_key, bytes): index_key = index_key.decode()
        labels = var[index_key].asstr()[()].tolist()
        if len(labels) != matrix.shape[1] or len(set(labels)) != len(labels) or any(not label.strip() for label in labels):
            raise ValueError("Invalid or duplicate niche feature identifiers")
        if set(labels) != set(source.get("validation", {}).get("labels", [])):
            raise ValueError("Niche features disagree with the source manifest labels")
        values = np.asarray(matrix[positions[order], :])[np.argsort(order)]
    if not np.isfinite(values).all() or np.any(values < 0) or not np.allclose(values.sum(axis=1), 1, rtol=0, atol=1e-8):
        raise ValueError("Sampled rows are not valid unchanged local compositions")
    return source, policy, sampled, summary, positions, coordinates[positions].copy(), labels, values


def audit_da_counts(op, sampled, output):
    """Independently reconstruct the backend counts from saved membership and unit labels."""
    import numpy as np
    import pandas as pd
    from scipy.sparse import csr_matrix, issparse, save_npz
    local, result = op.mdata["spatial_nhood"], op.mdata["quiche"]
    if not local.obs_names.equals(sampled.index):
        raise ValueError("Backend changed sampled row IDs/order")
    expected_units = sorted(sampled.analysis_unit_id.unique())
    if set(result.obs_names) != set(expected_units) or not result.obs_names.is_unique:
        raise ValueError("DA count rows are not exactly the working units")
    membership = csr_matrix(local.obsm["nhoods"])
    if not np.isin(membership.data, [0, 1]).all():
        raise ValueError("Niche membership must be binary")
    indicator = pd.get_dummies(local.obs.subject).reindex(columns=result.obs_names, fill_value=0)
    expected = (membership.T @ csr_matrix(indicator.to_numpy(dtype=np.int64))).T.toarray()
    actual = result.X.toarray() if issparse(result.X) else np.asarray(result.X)
    centers = local.obs_names[local.obs.nhood_ixs_refined.eq(1)]
    if not np.array_equal(result.var["index_cell"].astype(str).to_numpy(), centers.to_numpy()):
        raise ValueError("DA neighborhood order changed relative to membership columns")
    if not np.array_equal(actual, expected) or not np.isfinite(actual).all() or np.any(actual < 0):
        raise ValueError("Backend DA counts differ from membership.T @ unit indicator")
    group = sampled.groupby("analysis_unit_id").source_group.first()
    design = result.obs.copy()
    if not {"subject", "quicheCondition"}.issubset(design):
        raise ValueError("Backend count-level design columns are missing")
    if not np.array_equal(design.subject.astype(str), result.obs_names):
        raise ValueError("Backend design rows do not align with count units")
    expected_ab = sampled.groupby("analysis_unit_id").quicheCondition.first().reindex(result.obs_names)
    if not np.array_equal(design.quicheCondition.astype(str), expected_ab.astype(str)):
        raise ValueError("Backend A/B design mapping differs from requested contrast")
    design.to_csv(output / "unit-design.tsv", sep="\t")
    pd.DataFrame(actual.T.astype(np.int64), index=result.var_names, columns=result.obs_names).to_csv(
        output / "neighborhood-unit-counts.tsv", sep="\t", index_label="neighborhood_id")
    support = pd.DataFrame({"neighborhood_id": result.var_names, "index_cell": centers,
                            "n_contributing_units": (actual > 0).sum(axis=0),
                            "total_sampled_center_memberships": actual.sum(axis=0).astype(np.int64)})
    for condition in sorted(group.unique()):
        subset = group.reindex(result.obs_names).eq(condition).to_numpy()
        support["units__" + condition] = (actual[subset] > 0).sum(axis=0)
        support["memberships__" + condition] = actual[subset].sum(axis=0).astype(np.int64)
    support.to_csv(output / "neighborhood-support.tsv", sep="\t", index=False)
    save_npz(output / "sampled-niche-membership.npz", membership)
    pd.DataFrame({"cell_id": local.obs_names, "analysis_unit_id": local.obs.subject.astype(str).to_numpy()}).to_csv(
        output / "membership-rows.tsv", sep="\t", index=False)
    return {"oracle": "membership.T @ working-unit one-hot; exact equality", "units": len(expected_units),
            "sampled_centers": len(sampled), "neighborhoods": actual.shape[1],
            "counting_universe": "sampled eligible centers only", "memberships_can_overlap": True}


def da_estimability(result, membership_totals):
    """Explain only the pinned backend's observed all-zero-neighborhood exclusion."""
    import numpy as np
    values = result[["logFC", "PValue", "SpatialFDR"]].to_numpy(dtype=float)
    zero = np.asarray(membership_totals).ravel() == 0
    if len(zero) != len(result):
        raise ValueError("Membership totals and DA rows do not align")
    nonfinite = ~np.isfinite(values).all(axis=1)
    explained = zero & np.isnan(values).all(axis=1)
    ledger = result.loc[nonfinite | zero, ["index_cell", "logFC", "PValue", "SpatialFDR"]].copy()
    ledger["sampled_center_memberships"] = np.asarray(membership_totals).ravel()[nonfinite | zero]
    ledger["reason"] = np.where(explained[nonfinite | zero], "zero_sampled_center_memberships", "unexplained_backend_result")
    summary = dict(neighborhoods=len(result), finite_rows=int((~nonfinite).sum()),
                   nonfinite_rows=int(nonfinite.sum()), zero_membership_rows=int(zero.sum()),
                   explained_zero_membership_rows=int(explained.sum()),
                   unexplained_rows=int(((nonfinite | zero) & ~explained).sum()))
    return summary, ledger


def run_precomputed(args):
    import numpy as np
    import pandas as pd
    source, policy, sampled, summary, positions, xy, labels, values = read_precomputed_selection(args)
    if not args.validate_only:
        if not os.environ.get("SLURM_JOB_ID") or args.n_jobs > int(os.environ.get("SLURM_CPUS_PER_TASK", "1")):
            raise ValueError("Run backend DA within an allocated compute step with sufficient CPUs")
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = dict(status="started", mode="da-precomputed", analysis_policy=policy,
        input=str(args.input.resolve()), source_manifest=str(args.source_manifest.resolve()), source_run=source,
        core_metadata=str(args.core_metadata.resolve()),
        configuration={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        sampling=dict(method="uniform_without_replacement_per_working_unit", cap=args.uniform_per_unit,
                      seed=args.seed, eligible_centers=int(summary.eligible_centers.sum()),
                      sampled_centers=len(sampled), units=len(summary), physical_graph_recomputed=False),
        randomness=dict(uniform_sampling_seed=args.seed, native_sketch_enabled=False,
                        niche_similarity="pinned sklearn NearestNeighbors kd_tree; no stochastic neighbor search",
                        whole_da_bitwise_determinism_claimed=False),
        design=dict(formula="~quicheCondition", backend_appends_no_intercept=True,
                    contrast="quicheConditionB-quicheConditionA", A=args.reference, B=args.comparison),
        quiche_revision=QUICHE_REVISION, counting_universe="sampled eligible centers only",
        execution=dict(hostname=socket.gethostname(), slurm_job_id=os.environ.get("SLURM_JOB_ID"),
                       slurm_cpus_per_task=os.environ.get("SLURM_CPUS_PER_TASK")),
        runtime=dict(python=platform.python_version()))
    def record():
        (args.output / "manifest.json").write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    record()
    try:
        sampled.to_csv(args.output / "sampled-centers.tsv", sep="\t", index_label="cell_id")
        summary.to_csv(args.output / "sampling-summary.tsv", sep="\t", index=False)
        pd.DataFrame(values, index=sampled.index, columns=labels).to_csv(
            args.output / "sampled-local-composition.tsv", sep="\t", index_label="cell_id")
        if args.validate_only:
            evidence.update(status="validated", backend_executed=False)
        else:
            import anndata
            backend = load_backend()
            # Read selected original AnnData rows to preserve all source obs/var fields.
            backed = anndata.read_h5ad(args.input, backed="r")
            try:
                niches = backed[positions, :].to_memory()
            finally:
                backed.file.close()
            if not niches.obs_names.equals(sampled.index) or list(niches.var_names) != labels or not np.array_equal(niches.X, values):
                raise ValueError("AnnData materialization changed selected vectors or identifiers")
            if not np.array_equal(niches.obsm["spatial"], xy):
                raise ValueError("Selected coordinates changed")
            original_obs = niches.obs.copy(deep=True)
            for key in sampled.columns:
                if key in niches.obs and not np.array_equal(niches.obs[key].astype(str), sampled[key].astype(str)):
                    raise ValueError("New mapping conflicts with source metadata: " + key)
                if key not in niches.obs: niches.obs[key] = sampled[key].to_numpy()
            work = anndata.AnnData(obs=niches.obs.copy(), obsm={"spatial": xy.copy()})
            op = differential(work, niches, backend, args.reference, args.comparison,
                              None, args.k_sim, args.seed, args.n_jobs)
            for key in original_obs:
                pd.testing.assert_series_equal(op.mdata["spatial_nhood"].obs[key], original_obs[key],
                                               check_names=False, check_categorical=False)
            if not np.array_equal(np.asarray(op.mdata["spatial_nhood"].X), values):
                raise ValueError("Backend changed original local-composition vectors")
            sampled["quicheCondition"] = pd.Categorical(sampled.condition.map({args.reference: "A", args.comparison: "B"}), categories=["A", "B"])
            evidence["count_audit"] = audit_da_counts(op, sampled, args.output)
            conversions = []
            for modality, obj in [("global", op.mdata), *op.mdata.mod.items()]:
                for axis in ("obs", "var"):
                    normalized, changes = normalize_metadata_table(getattr(obj, axis))
                    setattr(obj, axis, normalized)
                    conversions.extend(dict(modality=modality, axis=axis, **change) for change in changes)
            evidence["metadata_dtype_normalization"] = conversions
            op.mdata.write_h5mu(args.output / "quiche.h5mu")
            result = op.mdata["quiche"].var
            if not {"logFC", "PValue", "SpatialFDR", "quiche_niche"}.issubset(result) or not len(result):
                raise ValueError("DA result schema is incomplete")
            probabilities = result[["PValue", "SpatialFDR"]].to_numpy(dtype=float)
            finite = probabilities[np.isfinite(probabilities)]
            if np.any((finite < 0) | (finite > 1)):
                raise ValueError("DA probabilities outside [0,1]")
            result.to_csv(args.output / "differential-niches.tsv", sep="\t")
            estimability, ledger = da_estimability(result, op.mdata["quiche"].X.sum(axis=0))
            evidence["estimability"] = estimability
            evidence["nonfinite_da_rows"] = estimability["nonfinite_rows"]
            ledger.to_csv(args.output / "nonestimable-niches.tsv", sep="\t", index_label="neighborhood_id")
            if estimability["unexplained_rows"]:
                raise ValueError("Unexplained nonfinite or zero-membership DA output; inspect nonestimable-niches.tsv")
            evidence.update(status="complete", backend_executed=True)
            for package in ["anndata", "quiche", "pertpy", "rpy2", "numpy", "pandas"]:
                evidence["runtime"][package] = importlib.metadata.version(package)
            import rpy2.robjects as ro
            evidence["runtime"]["R"] = str(ro.r("R.version.string")[0])
            evidence["runtime"]["edgeR"] = str(ro.r('as.character(utils::packageVersion("edgeR"))')[0])
    except Exception as exc:
        evidence.update(status="failed", error=str(exc)); record(); raise
    record()
    (args.output / "report.md").write_text(
        "# Precomputed sampled-center DA\n\n"
        + f"State: {evidence['status']}. Working-unit policy: {policy['analysis_unit_policy']}.\n\n"
        + f"Uniformly selected {len(sampled)} of {int(summary.eligible_centers.sum())} eligible centers across {len(summary)} units; seed {args.seed}. "
        + "Original full-neighborhood composition vectors were retained; no physical graph was recomputed. "
        + "The seed controls uniform center selection; whole-run bitwise reproducibility is not claimed.\n\n"
        + ("Validation only; no backend DA executed.\n" if args.validate_only else
           "DA counts use sampled centers only, with overlapping niche memberships. "
           + f"{evidence['estimability']['finite_rows']} neighborhoods have finite statistics; "
           + f"{evidence['estimability']['explained_zero_membership_rows']} have zero memberships and were not tested by the backend. "
           + "See nonestimable-niches.tsv; unexplained nonfinite output fails the run.\n")
        + "Biological identities and independence follow the declared policy, not the technical patient/subject field name.\n")
    print(str(args.output / "report.md"))


def main():
    import numpy as np
    import pandas as pd
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode", choices=["prepare", "niches", "da", "da-precomputed"])
    p.add_argument("input", type=Path, help="New validated prepared H5AD for this task")
    p.add_argument("--output", required=True, type=Path, help="New evidence directory")
    p.add_argument("--labels-key")
    p.add_argument("--fov-key", help="Independent core/FOV spatial boundary")
    p.add_argument("--spatial-key")
    p.add_argument("--units", choices=["micrometer", "pixel"])
    p.add_argument("--frame", help="Accepted frame/source description; record any unverified interpretation")
    p.add_argument("--radius", type=float, help="Radius in the supplied coordinate units")
    p.add_argument("--min-neighbors", type=int, default=3)
    p.add_argument("--n-neighbors", type=int, help="Omit for radius-only neighborhoods")
    p.add_argument("--subject-key")
    p.add_argument("--condition-key")
    p.add_argument("--biological-identity-confirmed", action="store_true")
    p.add_argument("--reference")
    p.add_argument("--comparison")
    p.add_argument("--sketch-size", type=int, help="Niches per subject; omit to retain all")
    p.add_argument("--k-sim", type=int, default=100)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--n-jobs", type=int, default=1)
    p.add_argument("--source-manifest", type=Path, help="da-precomputed: completed manifest beside local-niches.h5ad")
    p.add_argument("--core-metadata", type=Path, help="da-precomputed: explicit core-to-unit/group TSV")
    p.add_argument("--core-key", default="sample_id", help="Core ID column in core-metadata")
    p.add_argument("--unit-key", help="da-precomputed: working-unit column in core-metadata")
    p.add_argument("--analysis-unit-policy", choices=["confirmed_biological_subject", "source_block_record"], default="confirmed_biological_subject")
    p.add_argument("--uniform-per-unit", type=int, default=1000, help="da-precomputed: at most 1000 eligible centers per unit")
    p.add_argument("--validate-only", action="store_true", help="da-precomputed: sample and validate without QUICHE/R")
    args = p.parse_args()
    if args.output.exists():
        p.error("Use a new evidence directory")
    if args.n_jobs < 1 or (args.sketch_size is not None and args.sketch_size < 1):
        p.error("n-jobs and any sketch-size must be positive")
    if args.mode == "da-precomputed":
        required = ["source_manifest", "core_metadata", "unit_key", "condition_key", "reference", "comparison"]
        absent = ["--" + key.replace("_", "-") for key in required if getattr(args, key) is None]
        if absent: p.error("da-precomputed requires " + ", ".join(absent))
        if not any(value == "--seed" or value.startswith("--seed=") for value in sys.argv[1:]):
            p.error("da-precomputed requires an explicit --seed")
        if any(getattr(args, key) is not None for key in ["labels_key", "fov_key", "spatial_key", "units", "frame", "radius", "n_neighbors", "subject_key"]):
            p.error("da-precomputed takes feature/coordinate provenance from its source run, not raw-H5AD overrides")
        if any(value == "--min-neighbors" or value.startswith("--min-neighbors=") for value in sys.argv[1:]):
            p.error("da-precomputed retains the source run's minimum-neighbor threshold")
        run_precomputed(args)
        return
    required = ["labels_key", "fov_key", "spatial_key", "units", "frame", "radius"]
    absent = ["--" + key.replace("_", "-") for key in required if getattr(args, key) is None]
    if absent: p.error("Required: " + ", ".join(absent))
    if args.validate_only or args.analysis_unit_policy != "confirmed_biological_subject":
        p.error("Exploratory policy and validate-only apply to da-precomputed only")
    cells, coordinates = read_cells(args.input, args.labels_key, args.fov_key,
        args.spatial_key, args.subject_key, args.condition_key)
    summary = validate_cells(cells, coordinates, args.units, args.frame, args.radius,
        args.min_neighbors, args.n_neighbors, args.mode == "da", args.reference,
        args.comparison, args.biological_identity_confirmed)
    order = np.argsort(cells.index.to_numpy())
    cells, coordinates = cells.iloc[order].copy(), coordinates[order].copy()
    backend = load_backend() if args.mode != "prepare" else None
    versions = {"python": platform.python_version()}
    for package in ("h5py", "numpy", "pandas", "anndata", "quiche", "squidpy", "pertpy", "rpy2"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    if args.mode == "da":
        import rpy2.robjects as ro
        versions["R"] = str(ro.r("R.version.string")[0])
        versions["edgeR"] = str(ro.r('as.character(utils::packageVersion("edgeR"))')[0])
    args.output.mkdir(parents=True, exist_ok=False)
    evidence = {"status": "started", "input": str(args.input.resolve()),
        "file_bytes": args.input.stat().st_size, "configuration": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
        "quiche_revision": QUICHE_REVISION, "runtime": versions, "validation": summary,
        "execution": {"hostname": socket.gethostname(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_cpus_per_task": os.environ.get("SLURM_CPUS_PER_TASK"),
            "slurm_job_nodelist": os.environ.get("SLURM_JOB_NODELIST")}}
    manifest = args.output / "manifest.json"
    def record():
        manifest.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    record()
    exported = cells.copy()
    exported[["x", "y"]] = coordinates
    exported.to_csv(args.output / "cells.tsv", sep="\t")
    try:
        if backend is not None:
            import anndata
            from scipy.sparse import save_npz
            work = anndata.AnnData(obs=cells.copy(), obsm={"spatial": coordinates.copy()})
            work.obs["label"] = pd.Categorical(work.obs.label)
            work.obs["fov"] = pd.Categorical(work.obs.fov)
            spatial, niches, audit, excluded = compute_niches(work, backend, args.radius,
                args.min_neighbors, args.n_neighbors, args.n_jobs)
            evidence["graph_audit"] = audit
            evidence["retained_centers"] = niches.n_obs
            evidence["excluded_centers"] = len(excluded)
            coverage = cells.groupby("fov", observed=True).size().rename("input_cells").to_frame()
            coverage["eligible_centers"] = niches.obs.groupby("fov", observed=True).size().reindex(coverage.index, fill_value=0)
            coverage.to_csv(args.output / "fov-coverage.tsv", sep="\t")
            save_npz(args.output / "spatial-connectivities.npz", spatial.obsp["spatial_connectivities"])
            niches.write_h5ad(args.output / "local-niches.h5ad")
            niches.to_df().to_csv(args.output / "local-niche-proportions.tsv", sep="\t")
            pd.DataFrame({"cell_id": excluded, "reason": "insufficient_neighbors_or_undefined_niche"}).to_csv(
                args.output / "excluded-centers.tsv", sep="\t", index=False)
            if niches.n_obs == 0:
                raise ValueError("No eligible niche centers; see exclusions")
            if args.mode == "da":
                op = differential(spatial, niches, backend, args.reference, args.comparison,
                    args.sketch_size, args.k_sim, args.seed, args.n_jobs)
                op.adata_niche_subsample.obs[["subject", "condition", "quicheCondition"]].drop_duplicates().to_csv(
                    args.output / "subject-design.tsv", sep="\t", index=False)
                # QUICHE copies heterogeneous obs.values into var, leaving numbers as objects.
                # Infer from actual scalar types; never parse strings or discard columns.
                conversions = []
                for modality, obj in [("global", op.mdata), *op.mdata.mod.items()]:
                    for axis in ("obs", "var"):
                        normalized, changes = normalize_metadata_table(getattr(obj, axis))
                        setattr(obj, axis, normalized)
                        conversions.extend(dict(modality=modality, axis=axis, **change) for change in changes)
                evidence["metadata_dtype_normalization"] = conversions
                op.mdata.write_h5mu(args.output / "quiche.h5mu")
                result = op.mdata["quiche"].var
                if not {"logFC", "PValue", "SpatialFDR", "quiche_niche"}.issubset(result.columns):
                    raise ValueError("QUICHE DA output schema mismatch")
                if not len(result):
                    raise ValueError("QUICHE returned no tested neighborhoods")
                probabilities = result[["PValue", "SpatialFDR"]].to_numpy(dtype=float)
                finite = probabilities[np.isfinite(probabilities)]
                if np.any((finite < 0) | (finite > 1)):
                    raise ValueError("QUICHE returned probabilities outside [0,1]")
                result.to_csv(args.output / "differential-niches.tsv", sep="\t")
                evidence["tested_neighborhoods"] = len(result)
                evidence["nonfinite_da_rows"] = int((~np.isfinite(result[["logFC", "PValue", "SpatialFDR"]].to_numpy(dtype=float)).all(axis=1)).sum())
        evidence["status"] = "complete"
    except Exception as exc:
        evidence.update(status="failed", error=str(exc))
        record()
        raise
    record()
    (args.output / "report.md").write_text(
        "# Spatial niche run\n\n" + f"Mode: {args.mode}. Input: `{args.input.resolve()}`.\n\n"
        + f"Validated {len(cells)} cells across {summary['fovs']} spatial boundaries. "
        + "See manifest.json for configuration, runtime and actual execution coverage.\n\n"
        + ("Preparation only; no spatial graph or QUICHE model was executed.\n" if args.mode == "prepare" else
           "Local edges were audited for FOV isolation and coordinate radius. "
           + ("Descriptive local compositions do not establish differential enrichment.\n" if args.mode == "niches" else
              "Formal output uses B minus A at the confirmed biological-subject level; inspect diagnostics and non-estimable results.\n")))
    print(str(args.output / "report.md"))


if __name__ == "__main__":
    main()
