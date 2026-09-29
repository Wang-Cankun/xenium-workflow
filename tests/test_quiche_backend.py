"""Opt-in real QUICHE smoke: QUICHE_SMOKE=1; no mocked backend or installations."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-quiche/scripts/quiche_workflow.py"
spec = importlib.util.spec_from_file_location("quiche_workflow", SCRIPT)
workflow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workflow)


@unittest.skipUnless(os.environ.get("QUICHE_SMOKE") == "1", "Requires the pinned QUICHE runtime; not exercised by contract tests")
class ActualQUICHETests(unittest.TestCase):
    def run_cli(self, mode, source, root, radius, min_neighbors, extra=()):
        path, output = root / "prepared.h5ad", root / "run"
        # AnnData writing may categorize strings in place; fixture creation uses a copy.
        source.copy().write_h5ad(path)
        original = path.read_bytes()
        command = [sys.executable, str(SCRIPT), mode, str(path), "--output", str(output),
            "--labels-key", "label", "--fov-key", "fov", "--spatial-key", "spatial",
            "--units", "micrometer", "--frame", "synthetic core-local", "--radius", str(radius),
            "--min-neighbors", str(min_neighbors), "--n-jobs", "1", *extra]
        run = subprocess.run(command, capture_output=True, text=True, timeout=900,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(run.returncode, 0, run.stdout[-6000:] + run.stderr[-6000:])
        self.assertEqual(path.read_bytes(), original)
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual(manifest["status"], "complete")
        self.assertTrue(manifest["execution"]["hostname"])
        self.assertEqual(manifest["execution"]["slurm_job_id"], os.environ.get("SLURM_JOB_ID"))
        self.assertEqual(manifest["execution"]["slurm_cpus_per_task"], os.environ.get("SLURM_CPUS_PER_TASK"))
        self.assertEqual(manifest["execution"]["slurm_job_nodelist"], os.environ.get("SLURM_JOB_NODELIST"))
        self.assertEqual(manifest["graph_audit"]["cross_fov_edges"], 0)
        self.assertTrue((output / "report.md").is_file())
        return output, manifest

    def test_hand_computed_local_niches_and_shuffle(self):
        import anndata
        backend = workflow.load_backend()
        obs = pd.DataFrame({"label": pd.Categorical(["A", "A", "B", "B", "B", "A"]),
                            "fov": pd.Categorical(["core1"]*3+["core2"]*3)},
                           index=["a1", "a2", "a3", "b1", "b2", "b3"])
        xy = np.array([[0., 0.], [1., 0.], [0., 1.]]*2)
        original = anndata.AnnData(obs=obs.copy(), obsm={"spatial": xy.copy()})
        expected = pd.DataFrame([[.5,.5],[1.,0.],[1.,0.],[.5,.5],[0.,1.],[0.,1.]],
                                index=obs.index, columns=["A", "B"])
        for order in [list(range(6)), [4,2,0,5,1,3]]:
            work = original[order].copy()
            spatial, niches, audit, excluded = workflow.compute_niches(work, backend, 1.1, 1)
            pd.testing.assert_frame_equal(niches.to_df().loc[obs.index, ["A", "B"]], expected, check_dtype=False)
            self.assertEqual(audit["cross_fov_edges"], 0)
            self.assertEqual(excluded, [])
            self.assertEqual(list(work.obsp), [])
            np.testing.assert_array_equal(work.obsm["spatial"], xy[order])
        _, filtered, _, excluded = workflow.compute_niches(original, backend, 1.1, 2)
        self.assertEqual(filtered.obs_names.tolist(), ["a1", "b1"])
        self.assertEqual(set(excluded), {"a2", "a3", "b2", "b3"})
        with tempfile.TemporaryDirectory() as tmp:
            output, manifest = self.run_cli("niches", original, Path(tmp), 1.1, 1)
            reloaded = anndata.read_h5ad(output / "local-niches.h5ad")
            pd.testing.assert_frame_equal(reloaded.to_df().loc[obs.index, ["A", "B"]], expected,
                                          check_dtype=False, check_names=False)
            self.assertEqual(manifest["retained_centers"], 6)
            coverage = pd.read_csv(output / "fov-coverage.tsv", sep="\t", index_col=0)
            self.assertEqual(coverage.input_cells.tolist(), [3, 3])
            self.assertEqual(coverage.eligible_centers.tolist(), [3, 3])
        pd.testing.assert_frame_equal(original.obs, obs)
        self.assertEqual(list(original.obsp), [])

    @unittest.skipUnless(os.environ.get("QUICHE_DA_SMOKE") == "1", "Requires working R/edgeR through rpy2")
    def test_real_two_group_da(self):
        import anndata
        import mudata
        rng = np.random.default_rng(7301)
        records, positions = [], []
        for subject in range(8):
            condition = "control" if subject < 4 else "treated"
            for core in range(2):
                for cell in range(36):
                    records.append({"cell_id": f"s{subject}c{core}x{cell}",
                        "label": rng.choice(list("ABCDEF"),
                            p=[.45,.2,.12,.1,.08,.05] if subject < 4 else [.2,.45,.12,.1,.08,.05]),
                        "fov": f"s{subject}c{core}", "subject": f"s{subject}", "condition": condition})
                    positions.append([cell % 6, cell // 6])
        obs = pd.DataFrame(records).set_index("cell_id")
        xy = np.asarray(positions, dtype=float)
        workflow.validate_cells(obs, xy, "micrometer", "synthetic core-local", 2., 2,
            da=True, reference="control", comparison="treated", biological_identity_confirmed=True)
        obs["label"] = pd.Categorical(obs.label)
        obs["fov"] = pd.Categorical(obs.fov)
        source = anndata.AnnData(obs=obs.copy(), obsm={"spatial": xy.copy()})
        with tempfile.TemporaryDirectory() as tmp:
            output, manifest = self.run_cli("da", source, Path(tmp), 2., 2,
                ["--subject-key", "subject", "--condition-key", "condition",
                 "--biological-identity-confirmed", "--reference", "control", "--comparison", "treated",
                 "--k-sim", "20", "--seed", "7301"])
            result = pd.read_csv(output / "differential-niches.tsv", sep="\t", index_col=0)
            mdata = mudata.read_h5mu(output / "quiche.h5mu")
            self.assertTrue({"logFC", "SpatialFDR", "PValue", "quiche_niche"}.issubset(result.columns))
            self.assertGreater(len(result), 0)
            self.assertEqual(mdata["quiche"].n_obs, 8)
            self.assertEqual(set(mdata["quiche"].obs_names), {f"s{i}" for i in range(8)})
            self.assertTrue(np.isfinite(result[["logFC", "PValue", "SpatialFDR"]].to_numpy()).all())
            self.assertTrue(((result[["PValue", "SpatialFDR"]] >= 0) &
                             (result[["PValue", "SpatialFDR"]] <= 1)).to_numpy().all())
            self.assertEqual(manifest["nonfinite_da_rows"], 0)
            self.assertTrue(manifest["runtime"]["R"])
            self.assertTrue(manifest["runtime"]["edgeR"])
            pd.testing.assert_series_equal(mdata["expression"].obs.label.loc[obs.index], obs.label,
                                           check_names=False, check_categorical=False)
            design = pd.read_csv(output / "subject-design.tsv", sep="\t").set_index("subject")
            self.assertEqual(design.loc["s0", "quicheCondition"], "A")
            self.assertEqual(design.loc["s7", "quicheCondition"], "B")
            self.assertEqual(len(design), 8)
        pd.testing.assert_frame_equal(source.obs, obs)
        np.testing.assert_array_equal(source.obsm["spatial"], xy)
        self.assertEqual(list(source.obsp), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
