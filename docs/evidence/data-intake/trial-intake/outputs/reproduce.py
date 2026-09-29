"""Reproduce the metadata comparison without modifying inputs or hashing content."""
import json
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
OUT = (ROOT / (sys.argv[1] if len(sys.argv) > 1 else "outputs/recheck")).resolve()
if not OUT.is_relative_to(ROOT / "outputs"):
    raise SystemExit("Choose a new output directory within outputs/")
OUT.mkdir(parents=True, exist_ok=False)
TOOL = "skills/xenium-data-intake/scripts/inventory.py"
commands = [
    [sys.executable, TOOL, "scan", "received", "--scope-key", "two-region-delivery", "--output", str(OUT / "received-inventory.json")],
    [sys.executable, TOOL, "compare", "shared-folder-inventory.json", str(OUT / "received-inventory.json"), "--output", str(OUT / "inventory-differences.json")],
]
records = []
for command in commands:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    records.append({"cwd": str(ROOT), "argv": command, "command": shlex.join(command), "exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr})
    (OUT / "command-results.json").write_text(json.dumps(records, indent=2) + "\n")
    if result.returncode:
        raise SystemExit(result.returncode)

paths = ["delivery-notes.md", "received/regionA/README.md", "received/regionB/README.md", "received/regionA/experiment.xenium", "sender-checksums.txt"]
evidence = {"text_evidence": {p: (ROOT / p).read_text() for p in paths}, "inspection_depth": "Document text reads and filesystem metadata comparison only. No count matrix/image parsing, no local hashes, no source-root access."}
baseline = json.loads((ROOT / "shared-folder-inventory.json").read_text())
recipient = json.loads((OUT / "received-inventory.json").read_text())
source_entries = {e["path"]: e for e in baseline["entries"]}
received_entries = {e["path"]: e for e in recipient["entries"]}
evidence["agreement_path_observations"] = [
    {"path": p, "baseline": source_entries.get(p), "recipient": received_entries.get(p)}
    for p in ["regionA/cell_feature_matrix/matrix.mtx.gz", "regionB/cell_feature_matrix/matrix.mtx.gz", "regionA/morphology.ome.tif", "regionA/aux_outputs/morphology_focus_qc_masks/morphology.ome.tif"]
]
(OUT / "scope-evidence.json").write_text(json.dumps(evidence, indent=2) + "\n")
comparison = json.loads((OUT / "inventory-differences.json").read_text())
result_summary = {"baseline_summary": baseline["summary"], "recipient_summary": recipient["summary"], "comparison": {k: comparison[k] for k in ["status", "missing_confirmed", "extra_confirmed", "type_differences", "size_differences"]}}
encoded = json.dumps(result_summary, indent=2) + "\n"
(OUT / "run-summary.json").write_text(encoded)
print(encoded, end="")
