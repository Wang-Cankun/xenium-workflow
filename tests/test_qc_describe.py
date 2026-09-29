"""Synthetic Xenium output for the descriptive QC CLI: no scheduler or real data required."""
import json, subprocess, sys, tempfile, unittest
from pathlib import Path
import h5py
import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-quality-check/scripts/qc_describe.py"
G = 8


def write_run(d, tx, csv=False, native=True):
    d.mkdir(parents=True)
    n = len(tx); ids = [f"c{i:03d}-1" for i in range(n)]
    cells = pd.DataFrame({"cell_id": ids, "x_centroid": np.arange(n) * 5.0, "y_centroid": 0.0,
                          "transcript_counts": tx, "control_probe_counts": 1, "genomic_control_counts": 0,
                          "control_codeword_counts": 0, "unassigned_codeword_counts": 0,
                          "deprecated_codeword_counts": 0, "total_counts": np.asarray(tx) + 1,
                          "cell_area": 60.0, "nucleus_area": 20.0, "nucleus_count": [0] + [1] * (n - 1),
                          "segmentation_method": ["Segmented by boundary stain"] * (n - 1) + ["Segmented by nucleus expansion of 5.0um"]})
    if csv:
        cells.to_csv(d / "cells.csv.gz", index=False, compression="gzip")
    else:
        cells.to_parquet(d / "cells.parquet", index=False)
    rows, cols, vals = [], [], []
    for j, t in enumerate(tx):  # t transcripts spread over min(t, G) genes, plus one control count
        k = min(int(t), G)
        if k:
            base = np.full(k, t // k); base[: t - base.sum()] += 1
            rows += list(range(k)); vals += list(base); cols += [j] * k
        rows += [G]; vals += [1]; cols += [j]
    M = pd.DataFrame({"r": rows, "c": cols, "v": vals}).sort_values(["c", "r"])
    with h5py.File(d / "cell_feature_matrix.h5", "w") as f:
        m = f.create_group("matrix"); m["data"] = M.v.values.astype(np.int32); m["indices"] = M.r.values.astype(np.int64)
        m["indptr"] = np.r_[0, np.cumsum(np.bincount(M.c, minlength=n))].astype(np.int64)
        m["shape"] = [G + 1, n]; m["barcodes"] = np.array(ids, dtype="S")
        ft = m.create_group("features"); ft["name"] = np.array([f"g{i}" for i in range(G + 1)], dtype="S")
        ft["feature_type"] = np.array(["Gene Expression"] * G + ["Negative Control Probe"], dtype="S")
    if native:
        pd.DataFrame({"num_cells_detected": [n], "fraction_transcripts_assigned": [0.8], "empty_metric": [None]}).to_csv(d / "metrics_summary.csv", index=False)
        (d / "experiment.xenium").write_text(json.dumps({"panel_name": "test_panel", "analysis_sw_version": "xenium-4.0.1.0", "images": {"n": 2}}))
        (d / "gene_panel.json").write_text(json.dumps({"payload": {"targets": [{"type": {"descriptor": "gene"}}] * G + [{"type": {"descriptor": "negative_control_probe"}}]}}))
        (d / "analysis_summary.html").write_text('<script>var d = {"alerts": [{"name": "low_q20", "level": "warn"}]};</script>')
    return ids


class QCDescribe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.root = Path(self.tmp.name)
        self.tx = [0, 5, 12, 40, 80, 120]

    def tearDown(self): self.tmp.cleanup()

    def run_cli(self, *args, code=0):
        p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
        self.assertEqual(p.returncode, code, p.stderr); return p

    def test_native_summary_with_groups(self):
        ids = write_run(self.root / "run", self.tx)
        groups = self.root / "groups.csv"
        pd.DataFrame({"cell_id": ids[:4] + [ids[3]], "core": ["A", "A", "B", "B", "A"]}).to_csv(groups, index=False)
        lay = self.root / "layout.csv"; pd.DataFrame({"core_id": ["A", "B", "C"], "row": [1, 1, 2]}).to_csv(lay, index=False)
        out = self.root / "qc"
        self.run_cli(self.root / "run", out, "--groups", groups, "--group-column", "core", "--layout", lay)
        log = json.loads((out / "run_log.json").read_text())
        self.assertEqual(log["join"]["matrix_cells"], 6)
        self.assertEqual(log["join"]["transcript_counts_equals_matrix_gene_sum_frac"], 1.0)
        self.assertEqual(log["group_membership"]["cells_in_multiple_groups"], 1)  # ids[3] is ambiguous
        self.assertEqual(log["layout"]["layout_without_cells"], ["C"])
        self.assertEqual(log["alerts"]["n_alert_records"], 1)
        self.assertEqual(log["missing_native_metrics"], ["empty_metric"])
        s = pd.read_csv(out / "tables/cell_signal_summary.csv").set_index("population")
        self.assertEqual(s.loc["all native cells", "n_cells"], 6)
        self.assertEqual(s.loc["cells in groups", "n_cells"], 3)
        self.assertAlmostEqual(s.loc["all native cells", "frac_lt10_gene_transcripts"], 2 / 6)
        self.assertAlmostEqual(s.loc["all native cells", "frac_no_nucleus"], 1 / 6)
        per = pd.read_csv(out / "tables/group_summary.csv").set_index("group")
        self.assertEqual(per.loc["A", "n_cells"], 2); self.assertEqual(per.loc["B", "row"], 1)
        panel = pd.read_csv(out / "tables/panel_features.csv").set_index("feature_type")
        self.assertEqual(panel.loc["Gene Expression", "matrix_total_counts"], sum(self.tx))
        self.assertEqual(panel.loc["gene_panel.json:gene", "n_features"], G)
        cq = pd.read_csv(out / "cell_qc.csv.gz")
        self.assertEqual(len(cq), 6); self.assertEqual(cq.genes_detected.tolist(), [0, 5, 8, 8, 8, 8])
        seg = pd.read_csv(out / "tables/segmentation_summary.csv")
        self.assertEqual(seg.n_cells.sum(), 6)

    def test_csv_cells_without_native_files_and_output_protection(self):
        write_run(self.root / "run", self.tx, csv=True, native=False)
        out = self.root / "qc"
        self.run_cli(self.root / "run", out)
        log = json.loads((out / "run_log.json").read_text())
        self.assertEqual(log["cells_source"], "cells.csv.gz")
        self.assertEqual(log["alerts"]["parse_status"], "analysis_summary.html absent")
        self.assertFalse(log["native_files"]["metrics_summary.csv"])
        self.assertFalse((out / "tables/group_summary.csv").exists())
        self.run_cli(self.root / "run", out, code=1)  # existing output is refused
        self.run_cli(self.root / "run", out, "--overwrite")


if __name__ == "__main__":
    unittest.main()
