#!/bin/zsh
set -eu
set -x
cd <workspace>/trial-analysis
python skills/xenium-analysis-input-check/scripts/check_h5ad.py package/expression.h5ad --specimen-key core --output outputs/expression-metadata.json
