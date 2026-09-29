"""CPU checks of the NumPy-compatible helpers inside the GPU clustering and rescue scripts.

The scripts themselves need the GPU single-cell runtime; these tests cover the exact per-cluster
sums (cluster_analysis_h5ad.py) and the status and hold rules (rescue_labels.py) with NumPy, SciPy and
pandas only.
"""
import importlib.util, unittest
from pathlib import Path

import numpy as np
import scipy.sparse as sp

ROOT = Path(__file__).resolve().parents[1]


def load(rel, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


CLUSTER = load("skills/xenium-preprocess/scripts/cluster_analysis_h5ad.py", "cluster_analysis_h5ad")
RESCUE = load("skills/xenium-cell-qc/scripts/rescue_labels.py", "rescue_labels")


class ClusterGeneSums(unittest.TestCase):
    def test_matches_dense_sums_across_chunks(self):
        rng = np.random.default_rng(0)
        D = rng.poisson(0.4, size=(1003, 17)).astype(np.float32)
        D[5] = 0; D[7, 3] = 250                                  # an empty cell and a large count
        C = sp.csr_matrix(D); C.eliminate_zeros()
        lib = np.maximum(D.sum(1), 1)
        lab = rng.integers(0, 6, size=D.shape[0]); lab[lab == 4] = 5   # cluster 4 has no cells
        Sc, NZ, SL = CLUSTER.cluster_gene_sums(C, lib, lab, 6, xp=np, chunk=97)
        L = np.log1p(D * (1e4 / lib)[:, None])
        for k in range(6):
            m = lab == k
            np.testing.assert_array_equal(Sc[k], D[m].sum(0))
            np.testing.assert_array_equal(NZ[k], (D[m] > 0).sum(0))
            np.testing.assert_allclose(SL[k], L[m].sum(0), rtol=1e-6, atol=1e-6)
        self.assertEqual(NZ.sum(), C.nnz)
        self.assertEqual(Sc.sum(), D.sum())
        self.assertFalse(Sc[4].any())


class RescueStatus(unittest.TestCase):
    def test_held_cells_are_not_reference_or_rescued(self):
        tv = np.array([0.99, 0.99, 0.50, 0.50, 0.99, 0.99, 0.10, 0.99])
        lv = np.array([1.00, 1.00, 0.99, 0.60, 1.00, 1.00, 0.20, 1.00])
        signal = np.array([80, 80, 40, 40, 2, 80, 80, 80])
        labelled = np.array([True, True, True, True, True, True, True, False])
        is_ref = np.array([True, False, False, False, False, True, False, False])
        hold = np.array([False, False, False, False, False, True, True, True])
        st = RESCUE.assign_status(tv, lv, signal, labelled, is_ref, hold, 0.95, 0.95, 5)
        self.assertEqual(list(st), ["reference", "rescued_type", "rescued_lineage", "unresolved",
                                    "unresolved_no_signal", "unresolved_failed_group",
                                    "unresolved_failed_group", "below_floor"])

    def test_no_hold_keeps_previous_rule(self):
        tv = np.array([0.96, np.nan, 0.40]); lv = np.array([0.96, np.nan, 0.97])
        st = RESCUE.assign_status(tv, lv, np.array([10, 10, 10]), np.ones(3, bool), np.zeros(3, bool),
                                  np.zeros(3, bool), 0.95, 0.95, 5)
        self.assertEqual(list(st), ["rescued_type", "unresolved", "rescued_lineage"])

    def test_hold_read_from_labels_and_obs(self):
        import pandas as pd
        idx = pd.Index(["a", "b", "c", "d"])
        lab = pd.DataFrame({"own_type": ["x", "x", None, None],
                            "flag_group_low_depth": [True, False, None, None]}, index=idx)   # c, d not in the label table
        obs = pd.DataFrame({"flag_group_low_depth": pd.Categorical(["False", "False", "True", "False"])}, index=idx)
        m, src = RESCUE.hold_mask(lab, obs, "flag_group_low_depth")
        self.assertEqual(list(m), [True, False, True, False]); self.assertEqual(src, ["labels", "h5ad_obs"])
        m, src = RESCUE.hold_mask(lab.drop(columns="flag_group_low_depth"), obs, "flag_group_low_depth")
        self.assertEqual(list(m), [False, False, True, False]); self.assertEqual(src, ["h5ad_obs"])
        m, src = RESCUE.hold_mask(lab, obs.drop(columns="flag_group_low_depth"), None)
        self.assertFalse(m.any()); self.assertEqual(src, [])


if __name__ == "__main__":
    unittest.main()
