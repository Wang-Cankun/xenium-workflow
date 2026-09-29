#!/usr/bin/env python3
"""Read-only H5AD checks. Dependencies: h5py, numpy; optional anndata reader check."""
import argparse
import importlib
import importlib.metadata
import json
import math
import platform
from pathlib import Path


def runtime():
    versions = {'python': platform.python_version()}
    for name in ('numpy', 'h5py', 'anndata', 'squidpy'):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def inspect_file(path, full=False, counts_layer=None, specimen_key=None,
                 id_columns=(), mapping_columns=(), spatial_key='spatial', check_anndata=False):
    import h5py
    import numpy as np

    def decode(value):
        if isinstance(value, bytes):
            return value.decode('utf-8')
        if isinstance(value, np.ndarray):
            return decode(value.tolist())
        if isinstance(value, np.generic):
            return decode(value.item())
        if isinstance(value, (list, tuple)):
            return [decode(v) for v in value]
        if isinstance(value, float) and not math.isfinite(value):
            return {'nonfinite': 'NaN' if math.isnan(value) else ('Infinity' if value > 0 else '-Infinity')}
        if isinstance(value, h5py.Empty):
            return None
        return value

    def column(obj):
        if isinstance(obj, h5py.Dataset):
            return obj.asstr()[()] if obj.dtype.kind in 'OSU' else obj[()]
        if 'categories' in obj and 'codes' in obj:
            cats = column(obj['categories']); codes = obj['codes'][()]
            if np.any((codes < -1) | (codes >= len(cats))):
                raise ValueError('invalid categorical codes')
            return np.array([None if i == -1 else cats[i] for i in codes], dtype=object)
        if 'values' in obj and 'mask' in obj:
            values = column(obj['values']).astype(object)
            values[obj['mask'][()]] = None
            return values
        raise ValueError('unsupported column encoding')

    def missing(v):
        return v is None or (isinstance(v, (float, np.floating)) and np.isnan(v))

    def summarize_column(a):
        vals = [v for v in a if not missing(v)]
        unique = set(vals)
        out = {'length': len(a), 'missing': len(a)-len(vals),
               'empty_strings': sum(isinstance(v, str) and not v.strip() for v in vals),
               'unique': len(unique)}
        if len(unique) <= 100:
            from collections import Counter
            out['counts'] = {str(k): int(v) for k, v in Counter(vals).items()}
        if a.dtype.kind in 'fiu' and len(a):
            out['nonfinite'] = int((~np.isfinite(a)).sum())
        return out

    result = {'runtime': runtime(), 'input': str(path), 'file_bytes': path.stat().st_size,
              'matrix_scope': 'full' if full else 'metadata only', 'errors': []}
    with h5py.File(path, 'r') as f:
        result['inventory'] = {}
        def inventory(name, obj):
            result['inventory'][name] = {'shape': decode(getattr(obj, 'shape', None)),
                'attrs': {k: decode(v) for k, v in obj.attrs.items()}}
        f.visititems(inventory)
        frames = {}
        for frame in ('obs', 'var'):
            frames[frame] = {}; result[frame] = {}
            if frame not in f:
                result['errors'].append(frame + ': absent'); continue
            for key, obj in f[frame].items():
                try:
                    a = column(obj); frames[frame][key] = a
                    result[frame][key] = summarize_column(a)
                except Exception as exc:
                    result['errors'].append(frame + '/' + key + ': ' + str(exc))
            index = decode(f[frame].attrs.get('_index', '_index'))
            a = frames[frame].get(index)
            result[frame + '_index'] = {'key': index, 'unique': bool(a is not None and len(set(a)) == len(a)),
                                       'length': len(a) if a is not None else None}
        n = result['obs_index']['length']; m = result['var_index']['length']
        result['alignment'] = {frame: all(len(v) == size for v in frames[frame].values())
                               for frame, size in [('obs', n), ('var', m)]}
        result['matrices'] = {}
        names = (['X'] if 'X' in f else []) + ['layers/' + k for k in f.get('layers', {})]
        if 'raw' in f and 'X' in f['raw']:
            names.append('raw/X')
        for name in names:
            obj = f[name]; encoding = decode(obj.attrs.get('encoding-type', 'array'))
            shape = obj.shape if isinstance(obj, h5py.Dataset) else obj.attrs.get('shape')
            info = {'encoding': encoding, 'shape': decode(shape),
                    'matches_obs_var': bool(tuple(shape) == (n,m)) if shape is not None else False,
                    'purported_counts': name == 'layers/' + str(counts_layer)}
            result['matrices'][name] = info
            if not full:
                continue
            try:
                if shape is None or len(shape) != 2:
                    raise ValueError('matrix is not two-dimensional')
                nr, nc = map(int, shape); row_nonzero = np.zeros(nr, dtype=np.int64)
                totals = {'nonfinite': 0, 'negative': 0, 'fractional': 0, 'stored_zeros': 0}
                lo, hi = float('inf'), float('-inf')
                def values(a):
                    nonlocal lo, hi
                    totals['nonfinite'] += int((~np.isfinite(a)).sum())
                    totals['negative'] += int((a < 0).sum())
                    totals['fractional'] += int((np.isfinite(a) & (a != np.rint(a))).sum())
                    totals['stored_zeros'] += int((a == 0).sum())
                    finite = a[np.isfinite(a)]
                    if finite.size:
                        lo = min(lo, float(finite.min())); hi = max(hi, float(finite.max()))
                if isinstance(obj, h5py.Dataset):
                    for start in range(0, nr, 2000):
                        a = obj[start:start+2000]; values(a)
                        row_nonzero[start:start+len(a)] = np.count_nonzero(a, axis=1)
                elif encoding in ('csr_matrix', 'csc_matrix'):
                    ptr = obj['indptr'][()]; nnz = len(obj['data'])
                    major, minor = (nr, nc) if encoding == 'csr_matrix' else (nc, nr)
                    valid = (len(ptr) == major+1 and ptr[0] == 0 and ptr[-1] == nnz
                             and np.all(np.diff(ptr) >= 0) and len(obj['indices']) == nnz)
                    info['structure_valid'] = bool(valid)
                    if not valid:
                        raise ValueError('invalid sparse pointers or array lengths')
                    bad_indices = 0
                    for start in range(0, nnz, 1000000):
                        a = obj['data'][start:start+1000000]; ix = obj['indices'][start:start+1000000]
                        values(a); good = (ix >= 0) & (ix < minor)
                        bad_indices += int((~good).sum())
                        rows = np.searchsorted(ptr, np.arange(start,start+len(a)), side='right')-1 if encoding == 'csr_matrix' else ix
                        keep = good & (a != 0)
                        np.add.at(row_nonzero, rows[keep], 1)
                    info['invalid_indices'] = bad_indices
                    info['structure_valid'] &= bad_indices == 0
                    info['stored_entries'] = nnz
                else:
                    raise ValueError('unsupported matrix encoding: ' + encoding)
                info.update(totals)
                info.update(value_min=lo if lo != float('inf') else None,
                            value_max=hi if hi != float('-inf') else None,
                            empty_rows=int((row_nonzero == 0).sum()))
            except Exception as exc:
                info['error'] = str(exc); result['errors'].append(name + ': ' + str(exc))
        obs = frames['obs']; result['identity_checks'] = {}
        for key in id_columns:
            if key not in obs:
                result['identity_checks'][key] = {'absent': True}; continue
            a = obs[key]
            item = {'duplicate_rows': len(a)-len(set(a))}
            if specimen_key and specimen_key in obs:
                item['within_specimen_duplicate_rows'] = len(a)-len(set(zip(obs[specimen_key],a)))
            result['identity_checks'][key] = item
        result['specimens'] = {'key': specimen_key, 'present': specimen_key in obs if specimen_key else False}
        if specimen_key in obs:
            groups = obs[specimen_key]; result['specimens']['summary'] = summarize_column(groups)
            result['specimens']['multi_value_mappings'] = {}
            for key in mapping_columns:
                if key not in obs:
                    result['specimens']['multi_value_mappings'][key] = {'absent': True}; continue
                mapping = {}
                for group, value in zip(groups,obs[key]):
                    mapping.setdefault(str(group),set()).add(str(value))
                result['specimens']['multi_value_mappings'][key] = {k: sorted(v) for k,v in mapping.items() if len(v)>1}
        result['spatial'] = {'key': spatial_key, 'present': 'obsm' in f and spatial_key in f['obsm'],
                             'units': 'not inferred', 'frame': 'not inferred'}
        if result['spatial']['present']:
            a = f['obsm'][spatial_key][()]
            result['spatial'].update(shape=list(a.shape), matches_obs=len(a)==n,
                                     nonfinite=int((~np.isfinite(a)).sum()))
            if a.ndim == 2 and len(a):
                def spatial_stats(v):
                    good = v[np.isfinite(v).all(axis=1)]
                    return {'finite_rows':len(good), 'axis_min':good.min(axis=0).tolist() if len(good) else None,
                            'axis_max':good.max(axis=0).tolist() if len(good) else None,
                            'duplicate_coordinate_rows':len(good)-len(np.unique(good,axis=0))}
                result['spatial']['overall'] = spatial_stats(a)
                if specimen_key in obs and len(a)==n:
                    result['spatial']['by_specimen'] = {str(g):spatial_stats(a[obs[specimen_key]==g]) for g in set(obs[specimen_key]) if not missing(g)}
        result['uns'] = {}
        if 'uns' in f:
            def uns_value(name,obj):
                if isinstance(obj,h5py.Dataset) and (obj.size is None or obj.size <= 100):
                    result['uns'][name] = decode(obj[()])
            f['uns'].visititems(uns_value)
    if check_anndata:
        try:
            import anndata
            ad = anndata.read_h5ad(path, backed='r')
            try:
                result['anndata_read'] = {'success':True,'shape':list(ad.shape),'layers':list(ad.layers),'obsm':list(ad.obsm)}
            finally:
                ad.file.close()
        except Exception as exc:
            result['anndata_read'] = {'success':False,'error':str(exc)}
            result['errors'].append('anndata_read: ' + str(exc))
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('input', nargs='?', type=Path)
    p.add_argument('--output', type=Path)
    p.add_argument('--check-runtime', action='store_true')
    p.add_argument('--matrix-scan', choices=['metadata','full'], default='metadata')
    p.add_argument('--counts-layer', help='Explicitly identify a purported raw-count layer')
    p.add_argument('--specimen-key')
    p.add_argument('--id-column', action='append', default=[])
    p.add_argument('--mapping-column', action='append', default=[])
    p.add_argument('--spatial-key', default='spatial')
    p.add_argument('--check-anndata', action='store_true', help='Read-only AnnData compatibility check; can load layers/graphs into RAM')
    args = p.parse_args()
    if args.check_runtime:
        result = {'versions': runtime(), 'imports': {}}
        for name in ['numpy', 'h5py'] + (['anndata'] if args.check_anndata else []):
            try:
                importlib.import_module(name)
                result['imports'][name] = {'success': True}
            except Exception as exc:
                result['imports'][name] = {'success': False, 'error': str(exc)}
        print(json.dumps(result, indent=2))
        if not all(v['success'] for v in result['imports'].values()):
            raise SystemExit(2)
        return
    if args.input is None or args.output is None:
        p.error('input and --output are required for inspection')
    if args.output.resolve() == args.input.resolve():
        p.error('output must differ from input')
    if args.output.exists():
        p.error('output already exists; choose a new result filename')
    result = inspect_file(args.input,args.matrix_scan=='full',args.counts_layer,args.specimen_key,
                          args.id_column,args.mapping_column,args.spatial_key,args.check_anndata)
    payload = json.dumps(result,indent=2,allow_nan=False)
    with args.output.open('x') as out:
        out.write(payload)
    print('Inspection saved; interpret evidence and incomplete checks before reporting.')
    if result['errors']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
