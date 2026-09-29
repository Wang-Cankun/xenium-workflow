"""Synthetic Xenium output folders for the analysis-H5AD build CLI (needs anndata, h5py, pandas, pyarrow)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import h5py
import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-preprocess/scripts/build_analysis_h5ad.py"


def write_region(d, n, genes, matrix=True, csv=False, seed=0):
    rng = np.random.default_rng(seed); d.mkdir(parents=True)
    ids = [f"c{i:03d}-1" for i in range(n)]
    X = rng.integers(0, 4, size=(n, len(genes)))
    cells = pd.DataFrame({"cell_id": ids, "x_centroid": rng.uniform(0, 500, n), "y_centroid": rng.uniform(0, 500, n),
                          "transcript_counts": X.sum(1), "cell_area": 50.0, "nucleus_area": 15.0,
                          "segmentation_method": "Segmented by boundary stain"})
    (cells.to_csv(d / "cells.csv.gz", index=False, compression="gzip") if csv else cells.to_parquet(d / "cells.parquet", index=False))
    (d / "experiment.xenium").write_text(json.dumps({"analysis_sw_version": "xenium-4.0.1.0", "panel_name": "test_panel"}))
    if matrix:  # genes plus one negative-control probe row with 2 counts per cell; barcodes in reversed order
        order = np.arange(n)[::-1]
        full = np.c_[X, np.full(n, 2)][order]
        rows, cols = np.nonzero(full.T)
        ptr = np.r_[0, np.cumsum(np.bincount(cols, minlength=n))]
        srt = np.lexsort((rows, cols))
        with h5py.File(d / "cell_feature_matrix.h5", "w") as f:
            m = f.create_group("matrix"); m["data"] = full.T[rows[srt], cols[srt]].astype(np.int32)
            m["indices"] = rows[srt].astype(np.int64); m["indptr"] = ptr.astype(np.int64)
            m["shape"] = [len(genes) + 1, n]; m["barcodes"] = np.array([ids[i] for i in order], dtype="S")
            ft = m.create_group("features"); names = list(genes) + ["NegControlProbe_1"]
            ft["id"] = np.array(names, dtype="S"); ft["name"] = np.array(names, dtype="S")
            ft["feature_type"] = np.array(["Gene Expression"] * len(genes) + ["Negative Control Probe"], dtype="S")
    return ids, X


class BuildAnalysisH5AD(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.genes = [f"G{i}" for i in range(6)]
        self.ids_a, self.X_a = write_region(self.root / "A", 40, self.genes)
        self.ids_b, _ = write_region(self.root / "B", 25, self.genes, csv=True, seed=1)
        write_region(self.root / "C", 10, self.genes, matrix=False, seed=2)
        self.man = self.root / "regions.csv"
        pd.DataFrame({"region_id": ["RA", "RB", "RC"], "xoa_dir": ["A", "B", "C"], "run": ["r1", "r2", "r2"]}).to_csv(self.man, index=False)

    def tearDown(self): self.tmp.cleanup()

    def run_cli(self, *extra, code=0):
        p = subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(self.man), "--input-root", str(self.root),
                            "--workers", "1", *extra], capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr); return p

    def test_build_counts_controls_spatial_join(self):
        import anndata as ad
        flags = self.root / "flags.parquet"
        pd.DataFrame({"region_id": "RA", "cell_id": self.ids_a[:5], "pass_floor": True}).to_parquet(flags, index=False)
        out = self.root / "h5ad"
        self.run_cli("--out-dir", str(out), "--name", "t", "--check-transcript-counts", "--join", str(flags))
        a = ad.read_h5ad(out / "t.h5ad")
        self.assertEqual(a.n_obs, 65); self.assertEqual(list(a.var_names), self.genes)
        self.assertEqual(a.obs_names[0][:3], "RA_")
        cell = "RA_" + self.ids_a[7]
        np.testing.assert_array_equal(np.asarray(a[cell].layers["counts"].todense()).ravel(), self.X_a[7])
        self.assertEqual(int(a.obs.loc[cell, "matrix_gene_counts"]), int(self.X_a[7].sum()))
        self.assertEqual(int(a.obs.loc[cell, "matrix_negative_control_probe"]), 2)
        self.assertEqual(a.obsm["spatial"].shape, (65, 2))
        self.assertEqual(str(a.obs.loc["RB_" + self.ids_b[0], "run"]), "r2")
        self.assertEqual(int(a.obs.pass_floor.notna().sum()), 5)
        st = pd.read_csv(out / "t_region_status.csv").set_index("region_id")
        self.assertEqual(st.loc["RC", "outcome"], "no matrix")
        self.assertEqual(len(pd.read_parquet(out / "t_cells_without_matrix.parquet")), 10)
        summ = json.loads((out / "t_summary.json").read_text())
        self.assertEqual(summ["cells_without_matrix"], 10)

    def test_gene_mismatch(self):
        write_region(self.root / "D", 12, self.genes[:5], seed=3)
        pd.DataFrame({"region_id": ["RA", "RD"], "xoa_dir": ["A", "D"]}).to_csv(self.man, index=False)
        p = self.run_cli("--out-dir", str(self.root / "h1"), code=1)
        self.assertIn("gene sets differ", p.stderr + p.stdout)
        self.run_cli("--out-dir", str(self.root / "h2"), "--gene-mismatch", "intersect", "--name", "t")
        import anndata as ad
        self.assertEqual(ad.read_h5ad(self.root / "h2/t.h5ad").n_vars, 5)


if __name__ == "__main__":
    unittest.main()
