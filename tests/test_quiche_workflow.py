"""Synthetic H5AD/contract tests; no QUICHE substitute and no R or scheduler."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-quiche/scripts/quiche_workflow.py"
spec = importlib.util.spec_from_file_location("quiche_workflow", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


def fixture():
    cells = pd.DataFrame({"label": ["A", "A", "B", "B", "B", "A"],
                          "fov": ["core1"] * 3 + ["core2"] * 3},
                         index=pd.Index(["a1", "a2", "a3", "b1", "b2", "b3"], name="cell_id"))
    xy = np.array([[0., 0.], [1., 0.], [0., 1.]] * 2)
    return cells, xy


class PreparationTests(unittest.TestCase):
    def test_backend_metadata_normalization_preserves_values_and_labels(self):
        frame = pd.DataFrame({
            "neighbor_flag": pd.Series([1, 0], dtype=object),
            "distance": pd.Series([1.25, None], dtype=object),
            "bool_flag": pd.Series([True, False], dtype=object),
            "numeric_id": pd.Series(["001", "002"], dtype=object),
            "label": pd.Categorical(["T cell", "Unknown"]),
        })
        original = frame.copy(deep=True)
        normalized, changes = workflow.normalize_metadata_table(frame)
        self.assertTrue(pd.api.types.is_integer_dtype(normalized.neighbor_flag))
        self.assertTrue(pd.api.types.is_float_dtype(normalized.distance))
        self.assertTrue(pd.api.types.is_bool_dtype(normalized.bool_flag))
        self.assertEqual(normalized.numeric_id.tolist(), ["001", "002"])
        self.assertTrue(pd.isna(normalized.distance.iloc[1]))
        pd.testing.assert_series_equal(normalized.label, original.label)
        pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(normalized.columns.tolist(), original.columns.tolist())
        self.assertTrue({"neighbor_flag", "distance", "bool_flag"}.issubset({x["column"] for x in changes}))

    def test_coordinate_contract(self):
        cells, xy = fixture()
        result = workflow.validate_cells(cells, xy, "micrometer", "core-local", 1.1, 1)
        self.assertEqual((result["cells"], result["fovs"]), (6, 2))
        for units, frame in [(None, "local"), ("unknown", "local"), ("micrometer", "")]:
            with self.assertRaises(ValueError):
                workflow.validate_cells(cells, xy, units, frame, 1.1, 1)
        for value in [np.nan, np.inf, -np.inf]:
            bad = xy.copy(); bad[0, 0] = value
            with self.subTest(coordinate=value), self.assertRaisesRegex(ValueError, "nonfinite"):
                workflow.validate_cells(cells, bad, "pixel", "image", 1.1, 1)
        missing = cells.copy(); missing.loc["a1", "label"] = None
        with self.assertRaisesRegex(ValueError, "Missing metadata"):
            workflow.validate_cells(missing, xy, "pixel", "image", 1.1, 1)

    def test_graph_isolation_and_radius(self):
        cells, xy = fixture()
        rows, cols = [0, 0, 1, 2, 3, 3, 4, 5], [1, 2, 0, 0, 4, 5, 3, 3]
        graph = csr_matrix((np.ones(8), (rows, cols)), shape=(6, 6))
        audit = workflow.audit_graph(cells, xy, graph, 1.1)
        self.assertEqual(audit["directed_edges"], 8)
        bad = graph.tolil(); bad[0, 3] = 1
        with self.assertRaisesRegex(ValueError, "cross-FOV"):
            workflow.audit_graph(cells, xy, bad.tocsr(), 1.1)
        bad = graph.tolil(); bad[1, 2] = 1
        with self.assertRaisesRegex(ValueError, "radius"):
            workflow.audit_graph(cells, xy, bad.tocsr(), 1.1)
        order = [4, 2, 0, 5, 1, 3]
        self.assertEqual(audit, workflow.audit_graph(cells.iloc[order], xy[order], graph[order][:, order], 1.1))

    def test_biological_identity_gates(self):
        cells, xy = fixture()
        args = (cells, xy, "micrometer", "local", 2., 1)
        with self.assertRaisesRegex(ValueError, "subject"):
            workflow.validate_cells(*args, da=True, reference="A", comparison="B")
        # Four genuine synthetic subjects, each with two cores, two subjects per condition.
        cells = pd.concat([cells.assign(fov=lambda x: x.fov + str(i), subject="s"+str(i),
                                       condition="A" if i < 2 else "B").rename(index=lambda x: x+str(i))
                           for i in range(4)])
        xy = np.tile(xy, (4, 1))
        params = dict(da=True, reference="A", comparison="B", biological_identity_confirmed=True)
        workflow.validate_cells(cells, xy, "micrometer", "local", 2., 1, **params)
        params["biological_identity_confirmed"] = False
        with self.assertRaisesRegex(ValueError, "Confirm biological"):
            workflow.validate_cells(cells, xy, "micrometer", "local", 2., 1, **params)
        params["biological_identity_confirmed"] = True
        conflicting = cells.copy(); conflicting.iloc[0, conflicting.columns.get_loc("condition")] = "B"
        with self.assertRaisesRegex(ValueError, "one condition"):
            workflow.validate_cells(conflicting, xy, "micrometer", "local", 2., 1, **params)

    def test_categorical_and_nullable_metadata_are_aligned(self):
        cells, xy = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "encoded.h5ad"
            with h5py.File(path, "w") as f:
                obs = f.create_group("obs"); obs.attrs["_index"] = "cell_id"
                obs.create_dataset("cell_id", data=cells.index.to_list())
                labels = obs.create_group("label")
                labels.create_dataset("categories", data=["A", "B", "Unknown"])
                labels.create_dataset("codes", data=[0, 2, 1, 1, 1, 0])
                fovs = obs.create_group("fov")
                fovs.create_dataset("values", data=cells.fov.to_list())
                fovs.create_dataset("mask", data=np.zeros(6, dtype=bool))
                f.create_group("obsm").create_dataset("xy", data=xy)
            decoded, positions = workflow.read_cells(path, "label", "fov", "xy")
            self.assertEqual(decoded.label.to_list(), ["A", "Unknown", "B", "B", "B", "A"])
            pd.testing.assert_series_equal(decoded.fov, cells.fov)
            np.testing.assert_array_equal(positions, xy)
            workflow.validate_cells(decoded, positions, "pixel", "image", 1.1, 1)
            with h5py.File(path, "r+") as f:
                f["obs/label/codes"][1] = -1
                f["obs/fov/mask"][4] = True
            decoded, positions = workflow.read_cells(path, "label", "fov", "xy")
            self.assertTrue(pd.isna(decoded.label.iloc[1]))
            self.assertTrue(pd.isna(decoded.fov.iloc[4]))
            with self.assertRaisesRegex(ValueError, "Missing metadata"):
                workflow.validate_cells(decoded, positions, "pixel", "image", 1.1, 1)
            with h5py.File(path, "r+") as f:
                f["obs/label/codes"][0] = 99
            with self.assertRaisesRegex(ValueError, "categorical codes"):
                workflow.read_cells(path, "label", "fov", "xy")

    def test_cli_invalid_inputs_stop_before_backend_loading(self):
        cells, xy = fixture()
        cells = pd.concat([cells.assign(fov=lambda x: x.fov + str(i), subject="s"+str(i),
                                       condition="A" if i < 2 else "B").rename(index=lambda x: x+str(i))
                           for i in range(4)])
        xy = np.tile(xy, (4, 1))
        cases = [("empty_fov", "nonempty string labels"),
                 ("missing_label", "Missing metadata: label"),
                 ("nonfinite", "nonfinite"),
                 ("duplicate_cell", "globally unique"),
                 ("mixed_subject_in_core", "one biological subject"),
                 ("mixed_condition_in_subject", "one condition per subject"),
                 ("insufficient_subjects", "two independent subjects"),
                 ("missing_units", "--units"),
                 ("unconfirmed_identity", "Confirm biological")]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for case, message in cases:
                with self.subTest(case=case):
                    current, positions = cells.copy(), xy.copy()
                    if case == "empty_fov": current.iloc[0, current.columns.get_loc("fov")] = ""
                    if case == "nonfinite": positions[0, 1] = np.inf
                    if case == "duplicate_cell": current.index = [current.index[1], *current.index[1:]]
                    if case == "mixed_subject_in_core": current.iloc[0, current.columns.get_loc("subject")] = "s1"
                    if case == "mixed_condition_in_subject": current.iloc[0, current.columns.get_loc("condition")] = "B"
                    if case == "insufficient_subjects": current.loc[current.subject == "s1", "subject"] = "s0"
                    path, output = root / (case + ".h5ad"), root / (case + "-output")
                    with h5py.File(path, "w") as f:
                        obs = f.create_group("obs"); obs.attrs["_index"] = "cell_id"
                        obs.create_dataset("cell_id", data=current.index.to_list())
                        for key in ["fov", "subject", "condition"]:
                            obs.create_dataset(key, data=current[key].to_list())
                        label = obs.create_group("label")
                        label.create_dataset("categories", data=["A", "B"])
                        codes = current.label.map({"A": 0, "B": 1}).to_numpy(copy=True)
                        if case == "missing_label": codes[0] = -1
                        label.create_dataset("codes", data=codes)
                        f.create_group("obsm").create_dataset("xy", data=positions)
                    original = path.read_bytes()
                    command = [sys.executable, str(SCRIPT), "da", str(path), "--output", str(output),
                        "--labels-key", "label", "--fov-key", "fov", "--spatial-key", "xy",
                        "--frame", "validated core-local", "--radius", "1.1", "--min-neighbors", "1",
                        "--subject-key", "subject", "--condition-key", "condition", "--reference", "A", "--comparison", "B"]
                    if case != "missing_units": command += ["--units", "micrometer"]
                    if case != "unconfirmed_identity": command += ["--biological-identity-confirmed"]
                    run = subprocess.run(command, capture_output=True, text=True,
                                         env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                    self.assertNotEqual(run.returncode, 0)
                    self.assertIn(message, run.stderr)
                    self.assertNotIn("PackageNotFoundError", run.stderr)
                    self.assertFalse(output.exists())
                    self.assertEqual(original, path.read_bytes())

    def test_prepare_cli_reads_h5ad_preserves_input_and_order(self):
        cells, xy = fixture()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outputs = []
            for number, order in enumerate([list(range(6)), [4, 1, 5, 0, 3, 2]]):
                path = root / (str(number) + ".h5ad")
                with h5py.File(path, "w") as f:
                    obs = f.create_group("obs"); obs.attrs["_index"] = "cell_id"
                    obs.create_dataset("cell_id", data=cells.index[order].to_list())
                    for key in ["label", "fov"]:
                        obs.create_dataset(key, data=cells.iloc[order][key].to_list())
                    f.create_group("obsm").create_dataset("spatial_relative", data=xy[order])
                    f.create_dataset("X", data=np.arange(12).reshape(6, 2))
                before = path.read_bytes()
                out = root / ("out"+str(number))
                command = [sys.executable, str(SCRIPT), "prepare", str(path), "--output", str(out),
                    "--labels-key", "label", "--fov-key", "fov", "--spatial-key", "spatial_relative",
                    "--units", "micrometer", "--frame", "validated core-local", "--radius", "1.1", "--min-neighbors", "1"]
                run = subprocess.run(command, capture_output=True, text=True,
                                     env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(before, path.read_bytes())
                manifest = json.loads((out/"manifest.json").read_text())
                self.assertEqual(manifest["status"], "complete")
                self.assertTrue(manifest["execution"]["hostname"])
                self.assertEqual(manifest["execution"]["slurm_job_id"], os.environ.get("SLURM_JOB_ID"))
                self.assertEqual(manifest["execution"]["slurm_cpus_per_task"], os.environ.get("SLURM_CPUS_PER_TASK"))
                self.assertIn("no spatial graph", (out/"report.md").read_text())
                outputs.append((out/"cells.tsv").read_text())
                self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertEqual(outputs[0], outputs[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
