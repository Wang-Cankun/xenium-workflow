#!/bin/zsh
set -eu
set -x
cd <workspace>/trial-analysis
python outputs/check_package_joins.py
