#!/bin/zsh
set -eu
set -x
cd <workspace>/trial-analysis
pwd -P
/usr/bin/stat -f '%N | %z bytes' package/*
cat skills/xenium-biohpc-setup/profile.md
cat package/README.md
cat package/sender-checksums.txt
head -n 8 package/annotations.csv
head -n 8 package/coordinates.csv
python skills/xenium-analysis-input-check/scripts/check_h5ad.py --help
python skills/xenium-analysis-input-check/scripts/check_h5ad.py --check-runtime
