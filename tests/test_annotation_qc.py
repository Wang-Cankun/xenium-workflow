"""Synthetic labelled Xenium outputs for the annotation-QC CLI: no scheduler or real data required."""
import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

SCRIPT = Path(os.environ.get("ANNOTATION_QC_SCRIPT", Path(__file__).resolve().parents[1]
                             / "skills/xenium-annotation-qc/scripts/annotation_qc.py"))
LIN = {"Epi": range(0, 12), "Imm": range(12, 24), "Str": range(24, 36)}
HK = list(range(36, 48))                      # shared genes
G = 48
# label -> (lineage in the map, expression profile, depth range)
DESIGN = {
    "Epi_A": ("Epi", {"Epi": 1.0, "own": [8, 9]}, (120, 220)),
    "Epi_B": ("Epi", {"Epi": 1.0, "own": [10, 11]}, (120, 220)),
    "Imm_T": ("Imm", {"Imm": 1.0}, (120, 220)),
    "Str_F": ("Str", {"Str": 1.0}, (120, 220)),
    "Epi_ghost": ("Epi", {}, (60, 90)),                        # no lineage markers at all
    "Imm_spill": ("Imm", {"Epi": 0.8, "Imm": 0.25}, (120, 220)),  # epithelial cells called immune
    "Epi_lowdepth": ("Epi", {"Epi": 1.0, "own": [8, 9]}, (15, 40)),
    "Epi_C": ("Epi", {"Epi": 1.0}, (120, 220)),                   # lineage profile without own genes
    "Epi_g44": ("Epi", {"Epi": 1.0, "own": [44]}, (120, 220)),    # Epi_C plus one extra gene
    "LowRNA": ("none", {}, (10, 30)),
}
N_PER = {"Epi_A": 400, "Epi_B": 400, "Imm_T": 400, "Str_F": 400, "Epi_ghost": 150,
         "Imm_spill": 150, "Epi_lowdepth": 300, "LowRNA": 150, "Epi_C": 300, "Epi_g44": 150}


def profile(spec):
    w = np.full(G, 0.02); w[HK] = 1.0
    for L, idx in LIN.items():
        if L in spec:
            w[list(idx)[:8]] += 6.0 * spec[L]
    for j in spec.get("own", []):
        w[j] += 8.0
    return w / w.sum()


def write_region(d, rows, seed):
    rng = np.random.default_rng(seed); d.mkdir(parents=True)
    n = len(rows); ids = [f"c{i:05d}-1" for i in range(n)]
    X = np.zeros((n, G), int)
    for i, (lab, dep) in enumerate(zip(rows.label, rows.depth)):
        X[i] = rng.multinomial(int(dep), profile(DESIGN[lab][1]))
    cells = pd.DataFrame({"cell_id": ids, "x_centroid": rows.x.to_numpy(), "y_centroid": rows.y.to_numpy(),
                          "transcript_counts": X.sum(1), "cell_area": 60.0})
    cells.to_parquet(d / "cells.parquet", index=False)
    C = X.T  # genes x cells, CSC over cells
    data, indices, indptr = [], [], [0]
    for j in range(n):
        nz = np.flatnonzero(C[:, j]); data += list(C[nz, j]); indices += list(nz); indptr.append(len(data))
    with h5py.File(d / "cell_feature_matrix.h5", "w") as f:
        m = f.create_group("matrix"); m["data"] = np.array(data, np.int32); m["indices"] = np.array(indices, np.int64)
        m["indptr"] = np.array(indptr, np.int64); m["shape"] = [G, n]; m["barcodes"] = np.array(ids, dtype="S")
        ft = m.create_group("features"); ft["name"] = np.array([f"g{j}" for j in range(G)], dtype="S")
        ft["id"] = ft["name"][()]; ft["feature_type"] = np.array(["Gene Expression"] * G, dtype="S")
    return ids


class AnnotationQC(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(); root = Path(cls.tmp.name); rng = np.random.default_rng(0)
        recs = []
        for lab, n in N_PER.items():
            for k in range(n):
                recs.append({"label": lab})
        df = pd.DataFrame(recs).sample(frac=1, random_state=0).reset_index(drop=True)
        df["depth"] = [rng.integers(*DESIGN[l][2]) for l in df.label]
        df["region_id"] = np.where(np.arange(len(df)) % 2 == 0, "R1", "R2")
        df["core"] = [f"core{(i // 2) % 10}" for i in range(len(df))]
        # immune spill cells sit next to immune cells: place both in a shared patch
        df["x"] = rng.uniform(0, 400, len(df)); df["y"] = rng.uniform(0, 400, len(df))
        patch = df.label.isin(["Imm_T", "Imm_spill"]).to_numpy()
        df.loc[patch, "x"] = rng.uniform(500, 560, patch.sum()); df.loc[patch, "y"] = rng.uniform(500, 560, patch.sum())
        man = []
        for rid, g in df.groupby("region_id"):
            ids = write_region(root / rid, g, seed=1 if rid == "R1" else 2)
            df.loc[g.index, "cell_id"] = ids
            man.append({"region_id": rid, "path": str(root / rid)})
        pd.DataFrame(man).to_csv(root / "manifest.csv", index=False)
        df[["region_id", "cell_id", "label", "core"]].to_csv(root / "labels.csv", index=False)
        pd.DataFrame({"label": list(DESIGN), "lineage": [v[0] for v in DESIGN.values()]}).to_csv(root / "map.csv", index=False)
        cq = df[["region_id", "cell_id"]].copy(); cq["flag_low_depth_mad"] = df.label.eq("Epi_ghost").to_numpy()
        cq["flag_group_low_depth"] = df.label.eq("Epi_lowdepth").to_numpy()
        cq["dist_to_edge_um"] = 100.0
        cq.to_csv(root / "cell_qc.csv", index=False)
        ql = df[["region_id", "cell_id"]].copy()
        ql["qc_lineage"] = [DESIGN[l][0] if l not in ("Imm_spill", "LowRNA", "Epi_ghost") else ("Epi" if l == "Imm_spill" else None)
                            for l in df.label]
        ql["qc_status"] = "reference"
        ql.to_csv(root / "qc_labels.csv", index=False)
        cls.root, cls.df = root, df
        cls.out = root / "out"
        cls.proc = subprocess.run([sys.executable, str(SCRIPT), "--labels", str(root / "labels.csv"), "--label-column", "label",
                                  "--label-map", str(root / "map.csv"), "--group-column", "core",
                                  "--manifest", str(root / "manifest.csv"), "--cell-qc", str(root / "cell_qc.csv"),
                                  "--qc-labels", str(root / "qc_labels.csv"), "--out-dir", str(cls.out),
                                  "--min-groups", "5", "--min-group-cells", "50"], capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_runs(self):
        self.assertEqual(self.proc.returncode, 0, self.proc.stderr)
        for f in ("label_qc.csv", "label_group.csv", "group_qc.csv", "thinning_accuracy.csv", "lineage_markers.json",
                  "cell_annotation_qc.parquet", "run_info.json"):
            self.assertTrue((self.out / f).exists(), f)

    def status(self):
        return pd.read_csv(self.out / "label_qc.csv").set_index("label")

    def test_statuses(self):
        q = self.status()
        for l in ("Epi_A", "Epi_B", "Imm_T", "Str_F"):
            self.assertEqual(q.loc[l, "status"], "supported", (l, q.loc[l, "reasons"]))
        self.assertEqual(q.loc["LowRNA", "status"], "not_a_type")
        self.assertEqual(q.loc["Epi_ghost", "status"], "unsupported")
        self.assertIn("lineage_marker_unsupported", q.loc["Epi_ghost", "reasons"])
        self.assertIn("qc_flag_enriched", q.loc["Epi_ghost", "reasons"])
        self.assertEqual(q.loc["Imm_spill", "status"], "unsupported")
        self.assertIn("defined_by_foreign_markers", q.loc["Imm_spill", "reasons"])
        self.assertIn("qc_lineage_disagrees", q.loc["Imm_spill", "reasons"])
        self.assertEqual(q.loc["Epi_lowdepth", "status"], "review")
        self.assertIn("low_depth_enriched", q.loc["Epi_lowdepth", "reasons"])
        self.assertIn("failed_group_enriched", q.loc["Epi_lowdepth", "reasons"])
        self.assertIn("single_gene_defined", q.loc["Epi_g44", "reasons"])
        self.assertEqual(q.loc["Epi_g44", "top_specific_gene"], "g44")
        self.assertEqual(q.loc["Epi_g44", "closest_label_without_it"], "Epi_C")
        for l in ("Epi_A", "Epi_B", "Epi_C"):
            self.assertNotIn("single_gene_defined", str(q.loc[l, "reasons"]), l)

    def test_cells_kept_and_reasoned(self):
        c = pd.read_parquet(self.out / "cell_annotation_qc.parquet")
        self.assertEqual(len(c), len(self.df))                       # nothing removed
        self.assertTrue((c.label.to_numpy() == self.df.label.to_numpy()).all())  # labels unchanged, same order
        ghost = c[c.label == "Epi_ghost"]
        self.assertTrue(ghost.cell_reasons.str.contains("label_unsupported").all())
        self.assertTrue(ghost.cell_reasons.str.contains("qc_flagged").all())
        self.assertFalse(c.counts_missing.any())
        self.assertTrue((c.depth.to_numpy() == self.df.depth.to_numpy()).all())

    def test_thinning_and_groups(self):
        t = pd.read_csv(self.out / "thinning_accuracy.csv")
        self.assertEqual(set(t.depth.astype(str)), {"20.0", "50.0", "100.0", "full"})
        full = t[t.depth.astype(str) == "full"].set_index("label")
        self.assertGreater(full.loc["Imm_T", "label_accuracy"], 0.9)
        # a correct label implies a correct lineage
        self.assertTrue((t.lineage_accuracy >= t.label_accuracy - 1e-9).all())
        g = pd.read_csv(self.out / "group_qc.csv")
        self.assertEqual(g.cells.sum(), len(self.df)); self.assertEqual(len(g), 10)
        info = json.loads((self.out / "run_info.json").read_text())
        self.assertEqual(info["marker_source"], "data-driven"); self.assertEqual(info["unmapped_labels"], [])

    def test_lineage_column_map(self):
        lab = self.df[["region_id", "cell_id", "label", "core"]].copy()
        lab["main"] = [DESIGN[l][0] if l != "LowRNA" else "Unresolved" for l in lab.label]
        p = self.root / "labels_main.csv"; lab.to_csv(p, index=False); out = self.root / "out_main"
        r = subprocess.run([sys.executable, str(SCRIPT), "--labels", str(p), "--label-column", "label", "--lineage-column", "main",
                            "--group-column", "core", "--manifest", str(self.root / "manifest.csv"), "--out-dir", str(out),
                            "--min-groups", "5", "--min-group-cells", "50"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        used = pd.read_csv(out / "label_map_used.csv", keep_default_na=False).set_index("label").lineage
        self.assertEqual(used["LowRNA"], "none"); self.assertEqual(used["Imm_spill"], "Imm")
        q = pd.read_csv(out / "label_qc.csv").set_index("label")
        self.assertEqual(q.loc["Epi_ghost", "status"], "unsupported"); self.assertEqual(q.loc["Epi_A", "status"], "supported")
        self.assertEqual(json.loads((out / "run_info.json").read_text())["label_map_source"], "modal main")

    def test_output_protection_and_inputs(self):
        r = subprocess.run([sys.executable, str(SCRIPT), "--labels", str(self.root / "labels.csv"), "--label-column", "label",
                            "--label-map", str(self.root / "map.csv"), "--manifest", str(self.root / "manifest.csv"),
                            "--out-dir", str(self.out)], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("exists", r.stderr)
        dup = self.root / "dup.csv"
        pd.concat([self.df[["region_id", "cell_id", "label"]]] * 2).to_csv(dup, index=False)
        r = subprocess.run([sys.executable, str(SCRIPT), "--labels", str(dup), "--label-column", "label",
                            "--label-map", str(self.root / "map.csv"), "--manifest", str(self.root / "manifest.csv"),
                            "--out-dir", str(self.root / "o2")], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0); self.assertIn("duplicate", r.stderr)


if __name__ == "__main__":
    unittest.main()
