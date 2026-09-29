#!/bin/zsh
set -eu
set -x
cd <workspace>/trial-analysis
python skills/xenium-analysis-input-check/scripts/check_h5ad.py package/expression.h5ad --matrix-scan full --specimen-key core --id-column _index --mapping-column group --output outputs/expression-full.json
