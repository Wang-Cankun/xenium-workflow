"""Exercise the checker CLI with synthetic files; no research data or scheduler."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import h5py
import numpy as np


CHECKER = Path(__file__).resolve().parents[1] / 'skills/xenium-analysis-input-check/scripts/check_h5ad.py'


class CheckerCLI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'fixture.h5ad'
        with h5py.File(self.source, 'w') as f:
            for frame, ids in [('obs', ['a', 'a', 'c']), ('var', ['g1', 'g2'])]:
                group = f.create_group(frame)
                group.attrs['_index'] = '_index'
                group.create_dataset('_index', data=ids)
            f['obs'].create_dataset('core', data=['one', 'two', 'two'])
            f.create_dataset('X', data=[[1., 0.], [0., 0.], [0., -0.5]])
        self.original = self.source.read_bytes()

    def run_cli(self, *args, stub=None):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
        if stub:
            modules = self.root / 'stub'
            modules.mkdir(exist_ok=True)
            for name, text in stub.items():
                (modules / (name + '.py')).write_text(text)
            env['PYTHONPATH'] = str(modules)
        return subprocess.run([sys.executable, str(CHECKER), *map(str, args)],
                              cwd=self.root, env=env, text=True, capture_output=True)

    def inspect(self, *args, stub=None):
        output = self.root / ('report-' + str(len(list(self.root.glob('report-*')))) + '.json')
        result = self.run_cli(self.source, '--output', output, *args, stub=stub)
        self.assertTrue(output.exists(), result.stderr)
        parsed = json.loads(output.read_text(), parse_constant=lambda value: self.fail('Nonstandard JSON: ' + value))
        return result, parsed

    def test_metadata_and_full_coverage(self):
        result, metadata = self.inspect('--specimen-key', 'core', '--id-column', '_index')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(metadata['matrix_scope'], 'metadata only')
        self.assertNotIn('negative', metadata['matrices']['X'])
        self.assertFalse(metadata['spatial']['present'])
        self.assertEqual(metadata['identity_checks']['_index']['duplicate_rows'], 1)
        self.assertEqual(metadata['identity_checks']['_index']['within_specimen_duplicate_rows'], 0)
        result, full = self.inspect('--matrix-scan', 'full')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(full['matrices']['X']['empty_rows'], 1)
        self.assertEqual(full['matrices']['X']['negative'], 1)
        self.assertEqual(full['matrices']['X']['fractional'], 1)
        self.assertFalse(full['matrices']['X']['purported_counts'])
        self.assertEqual(self.source.read_bytes(), self.original)

    def test_output_protection(self):
        result = self.run_cli(self.source, '--output', self.source)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.source.read_bytes(), self.original)
        symlink = self.root / 'input-link.h5ad'
        symlink.symlink_to(self.source)
        self.assertEqual(self.run_cli(self.source, '--output', symlink).returncode, 2)
        self.assertEqual(self.source.read_bytes(), self.original)
        existing = self.root / 'existing.json'
        existing.write_text('keep this evidence')
        self.assertEqual(self.run_cli(self.source, '--output', existing).returncode, 2)
        self.assertEqual(existing.read_text(), 'keep this evidence')

    def test_sparse_failure_keeps_parseable_evidence(self):
        with h5py.File(self.source, 'r+') as f:
            del f['X']
            x = f.create_group('X')
            x.attrs['encoding-type'] = 'csr_matrix'
            x.attrs['shape'] = [3, 2]
            x.create_dataset('data', data=[1.])
            x.create_dataset('indices', data=[0])
            x.create_dataset('indptr', data=[0, 1, 1, 99])
        before = self.source.read_bytes()
        result, report = self.inspect('--matrix-scan', 'full')
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(report['matrices']['X']['structure_valid'])
        self.assertTrue(report['errors'])
        self.assertEqual(self.source.read_bytes(), before)

    def test_runtime_imports_and_failure_exit(self):
        result = self.run_cli('--check-runtime')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(all(x['success'] for x in json.loads(result.stdout)['imports'].values()))
        result = self.run_cli('--check-runtime', stub={'numpy': 'raise ImportError("fixture import failure")\n'})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(json.loads(result.stdout)['imports']['numpy']['success'])

    def test_reader_failure_keeps_parseable_evidence(self):
        result, report = self.inspect('--check-anndata', stub={
            'anndata': 'def read_h5ad(*args, **kwargs):\n    raise RuntimeError("fixture reader failure")\n'})
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(report['anndata_read']['success'])
        self.assertIn('anndata_read: fixture reader failure', report['errors'])

    def test_nonfinite_metadata_is_preserved_in_strict_json(self):
        with h5py.File(self.source, 'r+') as f:
            f['X'].attrs['nested'] = np.array([[np.nan, np.inf], [-np.inf, 1.]])
            u = f.create_group('uns')
            u.create_dataset('undefined', data=np.nan)
            u.create_dataset('limits', data=[np.inf, -np.inf])
            u.create_dataset('missing', data=h5py.Empty('f'))
            f['X'].attrs['limits'] = [np.inf, -np.inf]
        before = self.source.read_bytes()
        result, report = self.inspect()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(report['uns']['undefined'], {'nonfinite': 'NaN'})
        self.assertEqual(report['uns']['limits'], [{'nonfinite': 'Infinity'}, {'nonfinite': '-Infinity'}])
        self.assertIsNone(report['uns']['missing'])
        self.assertEqual(report['inventory']['X']['attrs']['limits'], [{'nonfinite': 'Infinity'}, {'nonfinite': '-Infinity'}])
        self.assertEqual(report['inventory']['X']['attrs']['nested'], [
            [{'nonfinite': 'NaN'}, {'nonfinite': 'Infinity'}], [{'nonfinite': '-Infinity'}, 1.]])
        self.assertEqual(self.source.read_bytes(), before)

    def test_unsupported_metadata_does_not_leave_partial_report(self):
        with h5py.File(self.source, 'r+') as f:
            f.create_group('uns').create_dataset('unsupported_complex', data=1 + 2j)
        before = self.source.read_bytes()
        output = self.root / 'unsupported.json'
        result = self.run_cli(self.source, '--output', output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists(), 'Serialization failure left a partial report')
        self.assertEqual(self.source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main(verbosity=2)
