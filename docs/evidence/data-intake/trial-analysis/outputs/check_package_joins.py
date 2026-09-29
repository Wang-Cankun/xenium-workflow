"""Read-only, complete checks of the supplied tiny curated package."""
import csv
import json
from collections import Counter
from pathlib import Path
import h5py
import numpy as np

PACKAGE = Path('<workspace>/trial-analysis/package')

def strings(ds):
    return [x.decode() if isinstance(x, bytes) else str(x) for x in ds[...]]

def key_records(keys):
    return [{'core': c, 'cell_id': i} for c, i in sorted(keys)]

def csv_check(filename, object_keys):
    with (PACKAGE / filename).open(newline='') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        columns = reader.fieldnames
    keys = [(r['core'], r['cell_id']) for r in rows]
    counts = Counter(keys)
    info = {
        'columns': columns,
        'rows': len(rows),
        'all_rows': rows,
        'malformed_rows': sum(None in r or any(v is None for v in r.values()) for r in rows),
        'missing_key_rows': sum(not c or not i for c, i in keys),
        'duplicate_key_rows': len(keys) - len(counts),
        'duplicate_keys': key_records(k for k, v in counts.items() if v > 1),
        'matched_object_keys': key_records(set(keys) & set(object_keys)),
        'missing_object_keys': key_records(set(object_keys) - set(keys)),
        'extra_csv_keys': key_records(set(keys) - set(object_keys)),
        'same_key_order_as_object': keys == object_keys,
    }
    assert len(counts) == len(keys), 'This targeted checker requires unique CSV composite keys.'
    return info, dict(zip(keys, rows))

with h5py.File(PACKAGE / 'expression.h5ad', 'r') as f:
    ids, cores, groups, features = (strings(f[k]) for k in ('obs/_index', 'obs/core', 'obs/group', 'var/_index'))
    object_keys = list(zip(cores, ids))
    spatial = f['obsm/spatial'][...]
    x = f['X'][...]
    scaled = f['layers/scaled'][...]
    counts = Counter(object_keys)
    result = {
        'scope': 'All object cells, all matrix entries, and every CSV row; no sampling.',
        'h5_root_attributes': {k: str(v) for k, v in f.attrs.items()},
        'h5_root_keys': list(f.keys()),
        'object_rows': [dict(core=c, cell_id=i, group=g, x=float(p[0]), y=float(p[1])) for c, i, g, p in zip(cores, ids, groups, spatial)],
        'object_composite_key_duplicate_rows': len(object_keys) - len(counts),
        'object_composite_duplicate_keys': key_records(k for k, v in counts.items() if v > 1),
        'features': features,
        'matrix_values': {'X': x.tolist(), 'layers/scaled': scaled.tolist()},
        'empty_feature_columns': {'X': int(np.all(x == 0, axis=0).sum()), 'layers/scaled': int(np.all(scaled == 0, axis=0).sum())},
        'core_to_groups': {c: sorted({g for co, g in zip(cores, groups) if co == c}) for c in sorted(set(cores))},
    }
    assert len(counts) == len(object_keys), 'This targeted checker requires unique object composite keys.'
    annotations, annotation_map = csv_check('annotations.csv', object_keys)
    annotations['missing_label_rows'] = sum(not r['label'].strip() for r in annotation_map.values())
    annotations['label_counts'] = dict(Counter(r['label'] for r in annotation_map.values()))
    annotations['aligned_object_labels'] = [annotation_map.get(k, {}).get('label') for k in object_keys]
    result['annotations'] = annotations
    coordinates, coordinate_map = csv_check('coordinates.csv', object_keys)
    csv_xy = np.array([[float(r['x']), float(r['y'])] for r in coordinate_map.values()])
    coordinates['nonfinite_values'] = int((~np.isfinite(csv_xy)).sum())
    coordinates['all_row_axis_min'] = np.min(csv_xy, axis=0).tolist()
    coordinates['all_row_axis_max'] = np.max(csv_xy, axis=0).tolist()
    comparisons = []
    for key, xy in zip(object_keys, spatial):
        if key in coordinate_map:
            row = coordinate_map[key]
            exported = np.array([float(row['x']), float(row['y'])])
            comparisons.append(dict(core=key[0], cell_id=key[1], exact_match=bool(np.array_equal(xy, exported)), max_abs_difference=float(np.max(np.abs(xy-exported)))))
    coordinates['matched_coordinate_comparisons'] = comparisons
    coordinates['per_core_coverage'] = {
        c: {'object_cells': sum(co == c for co, _ in object_keys),
            'matched_keys': sum(co == c and (co, i) in coordinate_map for co, i in object_keys),
            'missing_object_keys': key_records(k for k in set(object_keys)-set(coordinate_map) if k[0] == c),
            'extra_csv_keys': key_records(k for k in set(coordinate_map)-set(object_keys) if k[0] == c)}
        for c in sorted(set(cores))}
    result['coordinates'] = coordinates

print(json.dumps(result, indent=2, ensure_ascii=False))
