"""Exercise caption accounting, report layout and preserved composition values."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).resolve().parents[1] / 'skills/xenium-composition/scripts/plot_composition.py'
spec = importlib.util.spec_from_file_location('plot_composition', SCRIPT)
plot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plot)


class CohortCLI(unittest.TestCase):
    def invoke(self, fields, layout="publication", supplements=False, detailed=False):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        (root / 'counts.tsv').write_text('sample_id\tcell_type\tcount\tdenominator\tproportion\nc1\tImm\t6\t6\t1\n')
        base = {'sample_id': 'c1', 'unit': 'u1', 'group': 'A', **fields}
        (root / 'metadata.tsv').write_text('\t'.join(base) + '\n' + '\t'.join(map(str, base.values())) + '\n')
        command = [sys.executable, str(SCRIPT), '--main-counts', str(root/'counts.tsv'),
            '--main-metadata', str(root/'metadata.tsv'), '--unit-key', 'unit', '--group-key', 'group',
            '--output-dir', str(root/'figures'), '--layout', layout]
        if not supplements:
            command.append('--main-only')
        if detailed:
            (root/'detailed.tsv').write_text('sample_id\tcell_type\tcount\tdenominator\tproportion\nc1\td1\t5\t6\t0.8333333333333333\nc1\td2\t1\t6\t0.16666666666666666\n')
            command += ['--detailed-counts', str(root/'detailed.tsv'), '--detailed-metadata', str(root/'metadata.tsv')]
        result = subprocess.run(command, capture_output=True, text=True)
        return result, root/'figures'

    def test_exclusions_are_preserved_outside_artwork(self):
        result, out = self.invoke({'input_cells': 10, 'included_cells': 6, 'excluded_cells': 4})
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out/'manifest.json').read_text())
        self.assertEqual(manifest['cohort']['excluded_cells'], 4)
        svg = (out/'01-main-composition.svg').read_text()
        self.assertEqual(manifest['main_caption_metadata']['cohort'], '6 retained; 4 excluded')
        self.assertNotIn('6 retained; 4 excluded', svg)
        self.assertNotIn('All supplied cells retained', svg)
        self.assertIn('excluded_cells', (out/'main_observation_plotted.tsv').read_text().splitlines()[0])

    def test_missing_exclusion_record_is_not_zero(self):
        result, out = self.invoke({})
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out/'manifest.json').read_text())
        self.assertIsNone(manifest['cohort']['excluded_cells'])
        self.assertFalse(manifest['cohort']['exclusions_recorded'])
        self.assertEqual(manifest['main_caption_metadata']['cohort'], 'Upstream exclusions not recorded')
        self.assertNotIn('Upstream exclusions not recorded', (out/'01-main-composition.svg').read_text())

    def test_documented_zero_exclusions(self):
        result, out = self.invoke({'input_cells': 6, 'included_cells': 6, 'excluded_cells': 0})
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out/'manifest.json').read_text())
        self.assertEqual(manifest['main_caption_metadata']['cohort'], 'All supplied cells retained')
        self.assertNotIn('All supplied cells retained', (out/'01-main-composition.svg').read_text())

    def test_report_cli_dimensions_fonts_and_clean_artwork(self):
        publication_result, publication_out = self.invoke({})
        self.assertEqual(publication_result.returncode, 0, publication_result.stderr)
        publication_values = (publication_out/'main_unit_plotted.tsv').read_text()
        publication_summary = (publication_out/'summary_plotted.tsv').read_text()
        publication = json.loads((publication_out/'manifest.json').read_text())
        result, out = self.invoke({}, layout="report")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out/'manifest.json').read_text())
        self.assertEqual((out/'main_unit_plotted.tsv').read_text(), publication_values)
        self.assertEqual((out/'summary_plotted.tsv').read_text(), publication_summary)
        self.assertEqual(manifest['main_layout'], 'report')
        self.assertEqual(len(manifest['figures']), 1)
        audit = manifest['figures'][0]['layout_audit']
        self.assertAlmostEqual(audit['width_mm'], 168)
        self.assertAlmostEqual(audit['height_mm'], 155)
        self.assertEqual(audit['minimum_font_pt'], 7)
        self.assertIn(10, audit['font_sizes_pt'])
        self.assertAlmostEqual(publication['figures'][0]['layout_audit']['width_mm'], 183)
        svg = (out/'01-main-composition.svg').read_text()
        for unwanted in ['Cell composition', 'Points represent', 'Horizontal lines indicate',
                         'Group summaries', 'n denotes', 'source specimens']:
            self.assertNotIn(unwanted, svg)
        self.assertEqual(manifest['main_caption_metadata']['group_n'], {'A': 1})

    def test_supplement_explanations_are_external_and_clipping_values_preserved(self):
        result, out = self.invoke({'input_cells': 10, 'included_cells': 6, 'excluded_cells': 4},
                                  supplements=True, detailed=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((out/'manifest.json').read_text())
        self.assertEqual(len(manifest['figures']), 3)
        captions = manifest['supplemental_caption_metadata']
        self.assertEqual(captions['detailed_composition']['row_order'], 'pooled abundance')
        self.assertIn('40%', captions['detailed_composition']['color_scale'])
        self.assertIn('actual percentages', captions['detailed_composition']['color_scale'])
        self.assertIn('Gray', captions['detailed_composition']['zero_denominator'])
        self.assertEqual(captions['core_inventory']['pages'], 1)
        self.assertEqual(captions['core_inventory']['cohort'], '6 retained; 4 excluded')
        for name in ['02-detailed-composition.svg', 'S1-core-inventory-01.svg']:
            svg = (out/name).read_text()
            for unwanted in ['Cell composition', 'Specimen-level proportions', 'Rows ordered',
                             'Color scale truncated', '6 retained; 4 excluded', 'Each bar represents',
                             'Cell-type proportions for individual observations']:
                self.assertNotIn(unwanted, svg)
            self.assertIn('Retained cells (%)', svg)
        heatmap = (out/'02-detailed-composition.svg').read_text()
        self.assertIn('40%', heatmap)
        self.assertIn('83', heatmap)
        saturated = pd.read_csv(out/'heatmap_saturated_cells.tsv', sep='\t')
        self.assertEqual(saturated.cell_type.tolist(), ['d1'])
        self.assertEqual(saturated.displayed_percent_label.tolist(), [83])
        self.assertAlmostEqual(saturated.proportion.iloc[0], 5/6)
        self.assertEqual(manifest['heatmap']['vmax'], 40)
        self.assertEqual(manifest['heatmap']['saturated_cells'], 1)
        unit = pd.read_csv(out/'detailed_unit_plotted.tsv', sep='\t')
        self.assertEqual(unit['count'].tolist(), [5, 1])
        np.testing.assert_allclose(unit.proportion, [5/6, 1/6])
        self.assertAlmostEqual(manifest['figures'][1]['layout_audit']['width_mm'], 183)
        self.assertAlmostEqual(manifest['figures'][2]['layout_audit']['height_mm'], 8.3 * 25.4)

    def test_inconsistent_or_invalid_counts_fail_before_output(self):
        for fields in ({'input_cells': 10, 'excluded_cells': 3},
                       {'input_cells': 5}, {'excluded_cells': -1}, {'excluded_cells': 1.5}):
            with self.subTest(fields=fields):
                result, out = self.invoke(fields)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(out.exists())


class MainArtwork(unittest.TestCase):
    def test_five_facets_share_scale_and_preserve_weighting_and_zero_totals(self):
        types = ['Epi', 'Imm', 'Mes', 'Endo', 'Unknown']
        counts = [[90, 5, 3, 1, 1], [1, 5, 2, 1, 1], [3, 3, 1, 1, 2], [0]*5]
        ids = ['u1a', 'u1b', 'u2a', 'u3a']
        rows = []
        for sample, values in zip(ids, counts):
            total = sum(values)
            rows.extend((sample, t, n, total, n/total if total else np.nan)
                        for t, n in zip(types, values))
        main = pd.DataFrame(rows, columns=['sample_id', 'cell_type', 'count', 'denominator', 'proportion'])
        md = pd.DataFrame({'sample_id': ids, 'unit_id': ['u1', 'u1', 'u2', 'u3'],
                           'unit_label': ['u1', 'u1', 'u2', 'u3'], 'group_label': ['A', 'A', 'A', 'B']})
        style = plot.main_style(plot.load_style(None), 'report')
        data = plot.prepare(main, None, md, style)
        plot.set_style(style)
        fig = plot.main_figure(data, style, 'Must stay outside artwork')
        self.addCleanup(plot.plt.close, fig)
        plot.audit_figure(fig, style)
        self.assertEqual(len(fig.axes), 6)  # One stacked panel and five data facets.
        self.assertEqual(data['types'], types)
        facets = fig.axes[1:]
        for ax in facets:
            self.assertEqual(tuple(ax.get_ylim()), (-2, 102))
            self.assertEqual(list(ax.get_yticks()), [0, 50, 100])
        widths = [ax.get_position().width for ax in facets]
        np.testing.assert_allclose(widths, widths[0])
        top_extent = [facets[0].get_position().x0, facets[2].get_position().x1]
        bottom_extent = [facets[3].get_position().x0, facets[4].get_position().x1]
        self.assertAlmostEqual(sum(top_extent)/2, sum(bottom_extent)/2)
        expected = ((91/110) + .3) / 2 * 100
        self.assertAlmostEqual(facets[0].lines[0].get_ydata()[0], expected)
        self.assertEqual(len(facets[0].lines), 1)  # Zero-total group has no mean line.
        self.assertEqual(data['total_cells'], 120)
        self.assertTrue(data['main_matrix'].loc['u3'].isna().all())
        self.assertIn('n=0', [text.get_text() for text in fig.axes[0].texts])
        legend_labels = [text.get_text() for text in fig.legends[0].texts]
        self.assertIn('Unknown', legend_labels)
        self.assertNotIn('Must stay outside artwork', [text.get_text() for text in fig.texts])
        supplemental = plot.prepare(main, main, md, style, {t: t for t in types})
        heatmap = plot.heatmap_figure(supplemental, style, 'Must stay outside artwork', 40)
        inventory = plot.core_figure(supplemental, style, 'Must stay outside artwork', 0, 24)
        self.addCleanup(plot.plt.close, heatmap)
        self.addCleanup(plot.plt.close, inventory)
        for artwork in [heatmap, inventory]:
            plot.audit_figure(artwork, style)
            self.assertEqual(artwork.texts, [])
        image = heatmap.axes[0].images[0]
        self.assertEqual(image.get_clim(), (0, 40))
        self.assertTrue(np.ma.getmaskarray(image.get_array())[:, -1].all())
        np.testing.assert_allclose(image.get_cmap()(np.ma.masked), plot.to_rgba('#D1D5DB'))
        self.assertIn('No retained cells', [text.get_text() for text in inventory.axes[0].texts])



if __name__ == '__main__':
    unittest.main()
