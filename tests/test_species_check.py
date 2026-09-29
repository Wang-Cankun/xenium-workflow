"""Synthetic H5AD and rescue labels for the species-check CLI (h5py, pandas, pyarrow; no anndata needed)."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import h5py
import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-cell-qc/scripts/species_check.py"
GENES = ["B2M", "B2m", "NACA", "Naca", "Epcam"]


def write_h5ad(path, names, X):
    rows, cols = np.nonzero(X)
    ptr = np.r_[0, np.cumsum(np.bincount(rows, minlength=X.shape[0]))]
    with h5py.File(path, "w") as f:
        for grp, idx in (("obs", names), ("var", GENES)):
            g = f.create_group(grp); g.attrs["_index"] = "_index"; g["_index"] = np.array(idx, dtype="S")
        c = f.create_group("layers").create_group("counts"); c.attrs["encoding-type"] = "csr_matrix"
        c["data"] = X[rows, cols].astype(np.int32); c["indices"] = cols.astype(np.int32); c["indptr"] = ptr.astype(np.int64)


class SpeciesCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        # cells 0-3 human probes; 4-7 mouse probes; 8 no species probe; 9 mixed
        X = np.zeros((10, 5), int); X[:4, 0] = 3; X[:4, 2] = 1; X[4:8, 1] = 2; X[4:8, 3] = 2; X[:, 4] = 5; X[9, 0] = 1; X[9, 1] = 1
        self.names = [f"R{r}_c{i}" for i, r in enumerate([1] * 5 + [2] * 5)]
        write_h5ad(self.root / "c.h5ad", self.names, X)
        lab = ["tumour_h", "tumour_h", "tumour_h", "AT2", "tumour_h", "tumour_m", "tumour_m", "unresolved", "tumour_m", "tumour_h"]
        lin = ["tumour_human"] * 3 + ["epithelial", "tumour_human", "tumour_mouse", "tumour_mouse", "unresolved", "tumour_mouse", "tumour_human"]
        status = ["reference"] * 4 + ["rescued_type", "reference", "rescued_type", "unresolved", "reference", "rescued_type"]
        pd.DataFrame({"obs_name": self.names, "status": status, "label_type": lab, "label_lineage": lin,
                      "best_type": [x if x != "unresolved" else "tumour_h" for x in lab],
                      "best_lineage": [x if x != "unresolved" else "tumour_human" for x in lin],
                      "region": ["R1"] * 5 + ["R2"] * 5}).to_parquet(self.root / "labels.parquet", index=False)

    def tearDown(self): self.tmp.cleanup()

    def run_cli(self, out, *extra, code=0):
        p = subprocess.run([sys.executable, str(SCRIPT), "--h5ad", str(self.root / "c.h5ad"), "--labels", str(self.root / "labels.parquet"),
                            "--species", "human=B2M,NACA", "--species", "mouse=B2m,Naca",
                            "--lineage-species", "tumour_human=human,tumour_mouse=mouse", "--out-dir", str(out), *extra],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr); return p

    def test_calls_agreement_and_unexpected(self):
        exp = self.root / "expected.csv"; pd.DataFrame({"region": ["R1", "R2"], "allowed_species": ["human;mouse", "mouse"]}).to_csv(exp, index=False)
        out = self.root / "sp"; self.run_cli(out, "--group-columns", "region", "--expected", str(exp))
        D = pd.read_parquet(out / "species_cells.parquet").set_index("obs_name")
        self.assertEqual(D.probe_species.tolist()[:9], ["human"] * 4 + ["mouse"] * 4 + ["undetermined"])
        self.assertEqual(D.loc[self.names[9], "probe_species"], "undetermined")       # 50/50 mixed
        self.assertAlmostEqual(float(D.loc[self.names[0], "share_human"]), 1.0)
        self.assertEqual(D.loc[self.names[3], "label_species"], "neutral")           # epithelial is not species-specific
        self.assertEqual(D.loc[self.names[7], "label_species"], "unlabelled")
        self.assertEqual(D.loc[self.names[7], "best_guess_species"], "human")
        self.assertFalse(bool(D.loc[self.names[4], "species_agree"]))                # human label, mouse probes
        info = json.loads((out / "species_info.json").read_text())
        self.assertEqual(info["comparable_cells"], 6)                  # cells 0-2, 4-6
        self.assertAlmostEqual(info["agreement_by_status"]["rescued_type"], 0.5)
        self.assertEqual(info["unexpected_labels_by_status"], {"rescued_type": 1})   # cell 9: human label in mouse-only R2
        sh = pd.read_csv(out / "share_by_label_status.csv")
        row = sh[(sh.label_type == "(all)") & (sh.label_species == "human") & (sh.status == "reference")].iloc[0]
        self.assertEqual(int(row.cells), 3); self.assertAlmostEqual(float(row.share_human), 1.0)

    def test_errors(self):
        out = self.root / "sp"; self.run_cli(out)
        self.assertIn("output exists", self.run_cli(out, code=2).stderr)
        p = subprocess.run([sys.executable, str(SCRIPT), "--h5ad", str(self.root / "c.h5ad"), "--labels", str(self.root / "labels.parquet"),
                            "--species", "human=B2M,XYZ", "--species", "mouse=B2m", "--out-dir", str(self.root / "sp2")], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2); self.assertIn("not in var_names", p.stderr)


if __name__ == "__main__":
    unittest.main()
