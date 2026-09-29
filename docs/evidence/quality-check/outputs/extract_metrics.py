"""Extract the supplied descriptive summaries without reading cell matrices."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = root / 'inputs' / 'received_summary.json'
data = json.loads(source.read_text())
regions = data['regions']
fields = [
    'region', 'administrative_folder', 'reported_cells', 'gene_transcripts_min',
    'gene_transcripts_p25', 'gene_transcripts_p50', 'gene_transcripts_p75',
    'gene_transcripts_max', 'quantile_units', 'quantile_population',
    'native_median_gene_transcripts', 'native_median_population',
    'q20_reported_fraction', 'q20_denominator', 'assignment_reported_fraction',
    'assignment_denominator', 'matrix_reported_available', 'reported_alerts',
    'filtering_history', 'evidence_status', 'source'
]
with (root / 'outputs' / 'metric_table.csv').open('w', newline='') as handle:
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    for region in regions:
        q = region['gene_count_quantiles']
        row = {
            'region': region['id'],
            'administrative_folder': region['folder'],
            'reported_cells': region['cells'],
            **{f'gene_transcripts_{key}': q[key] for key in ('min', 'p25', 'p50', 'p75', 'max')},
            'quantile_units': 'gene transcripts per cell; excludes control counts',
            'quantile_population': 'supplied regional summary; exact cell inclusion not explicitly stated',
            'native_median_gene_transcripts': region['native_median_transcripts'],
            'native_median_population': data['native_median_population'],
            'q20_reported_fraction': 'NA' if region['q20'] is None else region['q20'],
            'q20_denominator': 'not supplied; software version and exact definition unverified',
            'assignment_reported_fraction': 'NA' if region['assignment'] is None else region['assignment'],
            'assignment_denominator': 'not supplied; software version and exact definition unverified',
            'matrix_reported_available': str(region['matrix_available']).lower(),
            'reported_alerts': json.dumps(region['alerts']),
            'filtering_history': data['processing'],
            'evidence_status': 'reused from supplied summary; underlying files not inspected',
            'source': 'inputs/received_summary.json'
        }
        assert list(q) == ['min', 'p25', 'p50', 'p75', 'max']
        assert list(q.values()) == sorted(q.values())
        for metric in ('q20', 'assignment'):
            assert region[metric] is None or 0 <= region[metric] <= 1
        writer.writerow(row)

with (root / 'outputs' / 'metric_table.csv').open(newline='') as handle:
    rows = list(csv.DictReader(handle))
assert len(rows) == len(regions) == 3
assert sum(int(row['reported_cells']) for row in rows) == 350
assert rows[2]['q20_reported_fraction'] == rows[2]['assignment_reported_fraction'] == 'NA'
assert [float(row['native_median_gene_transcripts']) for row in rows] == [35, 80, 10]
print('Saved metric_table.csv: 3 regions, 350 reported cells; missing fractions preserved as NA.')
