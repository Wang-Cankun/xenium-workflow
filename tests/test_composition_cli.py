"""Hand-calculated CLI fixtures: no scheduler or R required."""
import csv, json, subprocess, sys, tempfile, unittest
from pathlib import Path
import h5py
import numpy as np

SCRIPT=Path(__file__).resolve().parents[1]/"skills/xenium-composition/scripts/summarize_composition.py"

class CompositionCLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name);self.source=self.root/"input.h5ad"
        with h5py.File(self.source,"w") as f:
            o=f.create_group("obs");o.attrs["_index"]="_index"
            dt=h5py.string_dtype()
            for k,values in {"_index":["c1","c2","c3","c4","c5"],"core":["A","A","A","B","B"],"block":["X","X","X","Y","Y"]}.items():o.create_dataset(k,data=values,dtype=dt)
            c=o.create_group("label");c.attrs["encoding-type"]="categorical";c.create_dataset("categories",data=["T","tumor","Unknown"],dtype=dt);c.create_dataset("codes",data=[0,1,-1,0,2])
        self.original=self.source.read_bytes()
    def tearDown(self):self.tmp.cleanup()
    def run_cli(self,*args,success=True,name="result"):
        out=self.root/name
        p=subprocess.run([sys.executable,str(SCRIPT),"--input",str(self.source),"--output",str(out),"--sample-key","core","--cell-type-key","label",*args],capture_output=True,text=True)
        self.assertEqual(p.returncode,0 if success else 2,p.stderr)
        return out
    def rows(self,out,name):
        with (out/name).open() as f:return list(csv.DictReader(f,delimiter="\t"))
    def test_hand_counts_zeros_denominators_missing_and_unchanged_input(self):
        out=self.run_cli("--metadata-key","block")
        rows={(r["sample_id"],r["cell_type"]):r for r in self.rows(out,"counts.tsv")}
        expected={('A','T'):1,('A','tumor'):1,('A','__missing__'):1,('A','Unknown'):0,('B','T'):1,('B','tumor'):0,('B','__missing__'):0,('B','Unknown'):1}
        self.assertEqual({k:int(v['count']) for k,v in rows.items()},expected)
        for (s,t),r in rows.items():self.assertAlmostEqual(float(r['proportion']),expected[s,t]/(3 if s=='A' else 2))
        self.assertEqual(self.source.read_bytes(),self.original)
        self.assertEqual(json.loads((out/'run.json').read_text())['excluded_cells'],0)
    def test_exclusions_conserve_total(self):
        out=self.run_cli('--exclude-label','Unknown','--exclude-label','__missing__')
        r=json.loads((out/'run.json').read_text());self.assertEqual((r['included_cells'],r['excluded_cells']),(3,2))
        self.assertEqual(sum(int(r['count']) for r in self.rows(out,'exclusions.tsv')),2)
    def test_cell_order_invariance(self):
        out=self.run_cli(name='first');expected=(out/'counts.tsv').read_text()
        with h5py.File(self.source,'r+') as f:
            for k in ['_index','core','block']:f['obs/'+k][:]=f['obs/'+k][:][::-1]
            f['obs/label/codes'][:]=f['obs/label/codes'][:][::-1]
        self.assertEqual((self.run_cli(name='second')/'counts.tsv').read_text(),expected)
    def test_output_cannot_be_overwritten(self):
        out=self.run_cli();original=(out/'counts.tsv').read_text();self.run_cli(success=False);self.assertEqual((out/'counts.tsv').read_text(),original)
    def test_inconsistent_metadata_fails(self):
        with h5py.File(self.source,'r+') as f:f['obs/block'][0]='Z'
        self.assertFalse(self.run_cli('--metadata-key','block',success=False).exists())
    def test_missing_sample_fails(self):
        with h5py.File(self.source,'r+') as f:f['obs/core'][0]=''
        self.run_cli(success=False)
    def test_duplicate_cell_fails(self):
        with h5py.File(self.source,'r+') as f:f['obs/_index'][0]='c2'
        self.run_cli(success=False)
    def test_invalid_categorical_code_fails(self):
        with h5py.File(self.source,'r+') as f:f['obs/label/codes'][0]=99
        self.run_cli(success=False)
    def test_absent_exclusion_and_empty_denominator_policy_fail(self):
        self.run_cli('--exclude-label','not-present',success=False)
        self.run_cli(*sum((["--exclude-label",v] for v in ['T','tumor','Unknown','__missing__']),[]),success=False)
    def test_existing_missing_display_label_collision_fails(self):
        self.run_cli('--missing-label','T',success=False)
    def test_zero_denominator_preserved_explicitly(self):
        out=self.run_cli('--exclude-label','T','--exclude-label','Unknown')
        self.assertEqual(json.loads((out/'run.json').read_text())['zero_denominator_samples'],['B'])
        self.assertTrue(all(r['proportion']=='' for r in self.rows(out,'counts.tsv') if r['sample_id']=='B'))

if __name__=='__main__':unittest.main()
