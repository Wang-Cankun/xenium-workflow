"""Synthetic Xenium output directories for the cell-QC flag CLI: no scheduler or real data required."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import h5py
import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-cell-qc/scripts/cell_qc_flags.py"
G = 20  # genes


def write_region(d, n, special, matrix=True, transcripts=True, seed=0):
    rng = np.random.default_rng(seed); d.mkdir(parents=True)
    ids = [f"c{i:04d}-1" for i in range(n)]
    tx = rng.integers(100, 200, n); area = rng.uniform(50, 70, n); ctrl = np.zeros(n, int)
    seg = np.array(["Segmented by boundary stain (ATP1A1+CD45+E-Cadherin)"] * n, dtype=object)
    for i, kind in special.items():
        if kind == "low_density": area[i] = 5000.0
        if kind == "control": ctrl[i] = 60
        if kind == "floor": tx[i] = 8
        if kind == "low_tx": tx[i] = 30
        if kind == "nucleus_expansion": seg[i] = "Segmented by nucleus expansion of 5.0um"
    xs, ys = np.meshgrid(np.arange(15) * 10.0, np.arange(int(np.ceil(n / 15))) * 10.0)
    cells = pd.DataFrame({"cell_id": ids, "x_centroid": xs.ravel()[:n], "y_centroid": ys.ravel()[:n],
                          "transcript_counts": tx, "control_probe_counts": ctrl, "genomic_control_counts": 0,
                          "control_codeword_counts": 0, "unassigned_codeword_counts": 0, "deprecated_codeword_counts": 3,
                          "total_counts": tx + ctrl, "cell_area": area, "nucleus_area": area / 3, "nucleus_count": 1,
                          "segmentation_method": seg})
    cells.to_parquet(d / "cells.parquet", index=False)
    if matrix:  # gene counts split over genes; genes_detected = min(tx, G) by construction; two control rows
        cols, rows, vals = [], [], []
        for j, t in enumerate(tx):
            k = min(int(t), G); base = np.full(k, t // k); base[: t - base.sum()] += 1
            rows += list(range(k)); vals += list(base); cols += [j] * k
            rows += [G]; vals += [5]; cols += [j]                   # control feature, must be ignored
        M = pd.DataFrame({"r": rows, "c": cols, "v": vals}).sort_values(["c", "r"])
        ptr = np.r_[0, np.cumsum(np.bincount(M.c, minlength=n))]
        with h5py.File(d / "cell_feature_matrix.h5", "w") as f:
            m = f.create_group("matrix"); m["data"] = M.v.values.astype(np.int32); m["indices"] = M.r.values.astype(np.int64)
            m["indptr"] = ptr.astype(np.int64); m["shape"] = [G + 1, n]; m["barcodes"] = np.array(ids, dtype="S")
            ft = m.create_group("features"); ft["id"] = np.array([f"g{i}" for i in range(G + 1)], dtype="S")
            ft["name"] = ft["id"][()]; ft["feature_type"] = np.array(["Gene Expression"] * G + ["Negative Control Probe"], dtype="S")
    sq = np.array([[-3, -3], [3, -3], [3, 3], [-3, 3], [-3, -3]], float)
    bd = pd.DataFrame([(cid, x + dx, y + dy) for cid, x, y in zip(ids, cells.x_centroid, cells.y_centroid) for dx, dy in sq],
                      columns=["cell_id", "vertex_x", "vertex_y"])
    bd.to_parquet(d / "cell_boundaries.parquet", index=False); bd.to_parquet(d / "nucleus_boundaries.parquet", index=False)
    if transcripts:  # cell 0: 4 gene transcripts, 3 in nucleus; one low-qv and one control transcript ignored
        pd.DataFrame({"cell_id": [ids[0]] * 6 + ["UNASSIGNED"], "overlaps_nucleus": [1, 1, 1, 0, 1, 1, 1],
                      "qv": [30, 30, 30, 30, 10, 30, 30], "is_gene": [True] * 5 + [False, True]}).to_parquet(d / "transcripts.parquet", index=False)
    return ids


class CellQCFlags(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.special = {3: "low_density", 5: "control", 7: "floor", 9: "low_tx", 11: "nucleus_expansion"}
        self.ids = write_region(self.root / "A", 150, self.special)
        write_region(self.root / "B", 30, {}, matrix=False, transcripts=False, seed=1)
        self.man = self.root / "manifest.csv"
        pd.DataFrame({"region_id": ["RA", "RB"], "path": [str(self.root / "A"), str(self.root / "B")]}).to_csv(self.man, index=False)

    def tearDown(self): self.tmp.cleanup()

    def run_cli(self, out, *extra, code=0, manifest=None):
        p = subprocess.run([sys.executable, str(SCRIPT), "--manifest", str(manifest or self.man), "--output", str(out), "--nproc", "1", *extra],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr); return p

    def test_flags_reasons_and_summary(self):
        out = self.root / "qc"; self.run_cli(out)
        df = pd.read_parquet(out / "cell_qc.parquet").set_index("obs_name")
        a = df[df.region_id == "RA"]; row = lambda i: a.loc["RA_" + self.ids[i]]
        self.assertEqual(len(df), 180)
        self.assertTrue(bool(row(3).flag_low_density_mad)); self.assertFalse(bool(row(3).reference_candidate))
        self.assertTrue(bool(row(5).flag_control_fraction_high))
        self.assertFalse(bool(row(7).pass_floor)); self.assertIn("below_floor", row(7).qc_reasons)
        self.assertTrue(bool(row(9).pass_floor)); self.assertTrue(bool(row(9).low_information)); self.assertIn("lt50_transcripts", row(9).qc_reasons)
        self.assertTrue(bool(row(11).flag_nucleus_expansion))
        normal = [i for i in range(20, 150)]
        self.assertTrue(a.loc[["RA_" + self.ids[i] for i in normal]].reference_candidate.all())
        self.assertEqual(row(20).qc_reasons, "")
        self.assertEqual(int(row(9).genes_detected), 20); self.assertEqual(int(row(7).genes_detected), 8)
        self.assertEqual(int(row(0).tx_q20_gene), 4); self.assertAlmostEqual(float(row(0).tx_nuclear_fraction), 0.75)
        b = df[df.region_id == "RB"]
        self.assertFalse(b.has_matrix.any()); self.assertFalse(b.pass_floor.any()); self.assertTrue((b.qc_reasons.str.startswith("no_matrix")).all())
        chk = json.loads((out / "qc_checks.json").read_text())
        self.assertEqual(chk["matrix_equals_native_transcripts"], 1.0); self.assertEqual(chk["matrix_regions"], 1)
        s = pd.read_csv(out / "region_qc_summary.csv").set_index("region_id")
        self.assertEqual(int(s.loc["RA", "pass_floor"]), 149); self.assertEqual(int(s.loc["RB", "matrix_cells"]), 0)
        self.assertEqual(int(s.loc["RA", "reference_candidate"]), int(a.reference_candidate.sum()))
        # without groups the low-RNA square evidence is computed per region
        self.assertEqual(df.in_low_rna_bin.dtype, bool)
        self.assertEqual(int(s.low_rna_bin_cells.sum()), int(df.in_low_rna_bin.sum()))
        self.assertEqual(chk["cells_in_low_rna_bins"], int(df.in_low_rna_bin.sum()))

    def test_groups_between_group_check_and_control_rule(self):
        # region C: four 40-cell groups; group G3 is uniformly shallow (whole-group failure), last 10 cells ungrouped
        ids = write_region(self.root / "C", 170, {}, transcripts=False, seed=2)
        cells = pd.read_parquet(self.root / "C/cells.parquet")
        cells.loc[120:159, "transcript_counts"] = 25
        cells.loc[5, "control_probe_counts"] = 40          # the only control-bearing cell -> binomial rule
        patch = [i for i in range(40) if cells.x_centroid[i] >= 100 and cells.y_centroid[i] < 50]  # low-RNA square in G0
        cells.loc[patch, "transcript_counts"] = 20
        cells.to_parquet(self.root / "C/cells.parquet", index=False)
        grp = pd.DataFrame({"region_id": "RC", "cell_id": ids[:160], "core": [f"G{i // 40}" for i in range(160)]})
        gpath = self.root / "groups.csv"; grp.to_csv(gpath, index=False)
        man = self.root / "man_c.csv"; pd.DataFrame({"region_id": ["RC"], "path": [str(self.root / "C")]}).to_csv(man, index=False)
        out = self.root / "qc_groups"
        self.run_cli(out, "--groups", str(gpath), "--group-column", "core", "--skip-transcripts", manifest=man)
        df = pd.read_parquet(out / "cell_qc.parquet").set_index("cell_id")
        self.assertTrue(df.loc[ids[120:160], "flag_group_low_depth"].all())
        self.assertFalse(df.loc[ids[:120], "flag_group_low_depth"].any())
        self.assertFalse(df.loc[ids[120:160], "reference_candidate"].any())
        self.assertFalse(df.loc[ids[120:160], "flag_low_depth_mad"].any())  # within-group MAD does not flag a uniform group
        self.assertTrue((df.loc[ids[160:], "group"] == "ungrouped").all())
        self.assertFalse(df.loc[ids[160:], "reference_candidate"].any())
        self.assertIn("outside_group", df.loc[ids[165], "qc_reasons"])
        self.assertTrue(bool(df.loc[ids[5], "flag_control_fraction_high"]))
        self.assertEqual(int(df.flag_control_fraction_high.sum()), 1)       # zero-control cells are never flagged
        chk = json.loads((out / "qc_checks.json").read_text())
        self.assertEqual(chk["control_rule_by_region"], {"RC": "binomial"})
        self.assertEqual(chk["groups"]["low_depth_groups"], [["RC", "G3"]])
        self.assertEqual(chk["groups"]["ungrouped_cells"], 10)
        gs = pd.read_csv(out / "group_qc_summary.csv").set_index("group")
        self.assertTrue(bool(gs.loc["G3", "flag_group_low_depth"])); self.assertEqual(int(gs.loc["G0", "cells"]), 40)
        # evidence only: low-RNA square in G0, agreeing failure detectors for G3; flags and reference unchanged
        self.assertTrue(df.loc[[ids[i] for i in patch], "in_low_rna_bin"].all())
        self.assertFalse(df.loc[[ids[i] for i in range(40, 120)], "in_low_rna_bin"].any())
        self.assertFalse(df.loc[ids[120:160], "in_low_rna_bin"].any())    # a uniformly shallow group has no low square
        self.assertAlmostEqual(float(gs.loc["G0", "share_low_rna_bins"]), len(patch) / 40)
        self.assertEqual(int(gs.loc["G3", "failure_evidence"]), 2)       # between-group flag + below the region cut
        self.assertAlmostEqual(float(gs.loc["G3", "share_below_region_cut"]), 1.0)
        self.assertEqual(int(gs.loc["G1", "failure_evidence"]), 0)
        self.assertEqual(float(gs.loc["G3", "median_transcripts"]), 25.0)
        self.assertEqual(chk["groups"]["groups_with_2plus_failure_evidence"], [["RC", "G3"]])
        out2 = self.root / "qc_mad"
        self.run_cli(out2, "--control-rule", "mad", "--skip-transcripts", manifest=man)
        self.assertEqual(json.loads((out2 / "qc_checks.json").read_text())["control_rule_by_region"], {"RC": "mad"})
        # per region, the uniformly shallow G3 cells (25 transcripts) sit in squares below half the region median
        d2 = pd.read_parquet(out2 / "cell_qc.parquet").set_index("cell_id")
        self.assertGreater(float(d2.loc[ids[120:160], "in_low_rna_bin"].mean()), float(d2.loc[ids[40:120], "in_low_rna_bin"].mean()))

    def test_output_protection_and_bad_manifest(self):
        out = self.root / "qc"; self.run_cli(out, "--skip-transcripts")
        self.assertIn("output exists", self.run_cli(out, code=2).stderr)
        bad = self.root / "bad.csv"; pd.DataFrame({"region_id": ["X"], "path": [str(self.root / "missing")]}).to_csv(bad, index=False)
        self.assertIn("cells.parquet missing", self.run_cli(self.root / "qc2", code=2, manifest=bad).stderr)
        self.assertFalse((self.root / "qc2").exists())


if __name__ == "__main__":
    unittest.main()
