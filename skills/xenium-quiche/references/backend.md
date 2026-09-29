# QUICHE backend contract

Reviewed source: [jranek/quiche at a9077f242ead80577c2aa4aedd46e25798e4475b](https://github.com/jranek/quiche/tree/a9077f242ead80577c2aa4aedd46e25798e4475b).
The wrapper requires installation metadata identifying this revision. A later
revision needs API review and renewed real-backend verification.

## Runtime selection

The [pinned package manifest](https://github.com/jranek/quiche/blob/a9077f242ead80577c2aa4aedd46e25798e4475b/pyproject.toml)
requires Python >=3.9,<3.11, AnnData >=0.7.6,<0.10.9, SciPy >=1.10,<1.13,
NumPy >=1.24,<2.2 and pandas >=1.5,<2.3. Use a separate Python 3.10 environment.
Preparation/tests need only h5py, NumPy, pandas and SciPy; backend execution also
needs QUICHE's full extras. The installation specification, when environment
preparation is requested, is:

```text
quiche[full] @ git+https://github.com/jranek/quiche.git@a9077f242ead80577c2aa4aedd46e25798e4475b
muon
rpy2
h5py
statsmodels==0.14.5
```

Pertpy 0.6 imports `multipletests` through `statsmodels.sandbox.stats.multicomp`;
statsmodels 0.15 removed that alias. The explicit 0.14.5 pin preserves this import.

The full extra specifies Squidpy 1.6.1, Pertpy 0.6.0, sketchKH >=0.1.4,
JAX/JAXlib >=0.4.13,<0.4.25, ott-jax 0.4.6 and further transitive dependencies.
The [upstream environment](https://github.com/jranek/quiche/blob/a9077f242ead80577c2aa4aedd46e25798e4475b/venv_quiche.yml)
pairs R 4.3 with rpy2 3.5.11 and uses Matrix, locfit, statmod and nlme. With
a different supplied R runtime, select a compatible rpy2 version and verify the
bridge before locking it. Formal DA requires accessible edgeR through rpy2; the upstream README example names edgeR 3.40.2. Record the version
actually loaded and lock the successfully resolved environment. These are upstream
constraints, not proof this combination was installed or passed here.

## API and scientific boundary

[Graph code](https://github.com/jranek/quiche/blob/a9077f242ead80577c2aa4aedd46e25798e4475b/src/quiche/tools/graph.py)
passes `fov_key` to Squidpy's library boundary. The adapter independently checks
returned edges for boundary violations and radius. The numerical radius uses the
coordinate values supplied; no unit conversion is hidden in the adapter.
For H5MU serialization, the adapter restores numeric/bool metadata dtypes after
QUICHE copies heterogeneous values into result columns. It records each dtype
change and preserves labels, numeric-looking IDs, missing values and columns.

[Composition code](https://github.com/jranek/quiche/blob/a9077f242ead80577c2aa4aedd46e25798e4475b/src/quiche/tools/metrics.py)
returns each focal cell's neighborhood cell-type proportions and a list of centers
below the neighbor threshold. The adapter explicitly excludes these centers from
further analysis and reports them, without removing them from the original graph.
Its working AnnData contains metadata and coordinates only; no expression data is
normalized or represented as a measured feature.

The [QUICHE class](https://github.com/jranek/quiche/blob/a9077f242ead80577c2aa4aedd46e25798e4475b/src/quiche/tools/quiche.py)
counts niche neighborhoods using `patient_key`, then calls Pertpy Milo/edgeR. The
original `da` entry uses confirmed biological subjects, with a two-group no-intercept design
and B-minus-A contrast. Multiple cores are pooled within subject at that count
stage; this is not a random-effect model for each core. Choice of pooled exposure,
sketch size and radius should match the question. Subject-consistent treatment is
required by this limited recipe. Pass `~quicheCondition` and the explicit B-minus-A
contrast: [Pertpy 0.6](https://github.com/scverse/pertpy/blob/0.6.0/pertpy/tools/_milo.py)
adds `+ 0` itself when a contrast is supplied; writing `0` in the incoming formula
misidentifies it as a metadata column. See the [method paper](https://pubmed.ncbi.nlm.nih.gov/41708893/)
for the statistical method; no causal cell-interaction claim follows from proximity.

## Resuming from precomputed niches

`da-precomputed` validates the completed canonical `niches` manifest and dense
`local-niches.h5ad`, uniformly selects eligible center rows per explicit unit, and
assigns them to `QUICHE.adata_niche`. `subsample(sketch_size=None)` keeps this selected
matrix intact; `differential_enrichment` and annotation then use their existing APIs.
No physical adjacency or local composition is recomputed. The technical
`patient_key=subject` is an alias for the selected working-unit column. Under
`source_block_record`, its name establishes neither animal identity nor independence.
That policy is mutually exclusive with the biological-confirmation flag.

The pinned graph implementation uses scikit-learn `NearestNeighbors` with
`algorithm='kd_tree'` on niche `.X`, not an approximate stochastic search. An explicit
seed controls NumPy uniform center selection; native sketching is disabled. Runtime
versions and this scope are recorded without claiming whole-run bitwise identity.

Pertpy's `count_nhoods` multiplies niche membership transpose by sample indicators.
The adapter independently checks the resulting unit-by-neighborhood matrix against
that operation and exports it with the binary membership matrix and row identifiers.
The counting universe is sampled eligible centers; membership totals can exceed the
number of sampled cells because neighborhoods overlap. No full-center backprojection
is performed. SpatialFDR and non-estimable rows retain their backend meaning; a
completed fit with nonfinite rows is not silently reported as fully estimable.
Pertpy filters all-zero count neighborhoods before fitting and joins untested rows
back with missing statistics. The adapter preserves these in
`nonestimable-niches.tsv` only when all three statistics are missing and membership
totals are zero; it fails on unexplained nonfinite output. Verification checks this
exact mask rather than changing the fixture or graph parameters to avoid exclusions.

## Actual compute verification

`QUICHE_SMOKE=1 python tests/test_quiche_backend.py` requires the reviewed backend
and executes its graph and niche APIs. Two FOVs occupy identical coordinate ranges
but have different cell labels. The hand-computed expected proportions test
isolation, focal-cell exclusion and shuffled-row correspondence, not merely the
presence of result files. R/edgeR is not exercised by that local-niche test.

With `QUICHE_DA_SMOKE=1` as well, an additional synthetic repeated-core fixture
executes the real DA/annotation APIs through the CLI, reloads the saved H5MU and
tables, and verifies exact subject IDs, design mapping, preserved cell labels,
numerical bounds and unchanged input bytes. It is an integration smoke,
not an expected-significance test, power study or FDR calibration. Both backend
paths are opt-in and remain unverified until actually run in the compatible
environment; a skipped test is not a pass. Use allocated compute for BioHPC runs.
