"""Metadata-only intake: synthetic filesystem fixtures and actual CLI calls."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-data-intake/scripts/inventory.py"
spec = importlib.util.spec_from_file_location("inventory", SCRIPT)
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


class DataIntake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.a = self.root / "source"
        self.b = self.root / "recipient"
        self.a.mkdir()
        self.b.mkdir()
        self.serial = 0

    def output(self):
        self.serial += 1
        return self.root / (str(self.serial) + ".json")

    def cli(self, *args):
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              env=env, capture_output=True, text=True)

    def scan(self, root, *flags, code=0):
        output = self.output()
        proc = self.cli("scan", root, "--scope-key", "delivery-v1", "--output", output, *flags)
        self.assertEqual(proc.returncode, code, proc.stderr)
        return output, json.loads(output.read_text())

    def compare(self, a, b, code=0):
        output = self.output()
        proc = self.cli("compare", a, b, "--output", output)
        self.assertEqual(proc.returncode, code, proc.stderr)
        return json.loads(output.read_text())

    def test_cli_metadata_zero_file_symlink_and_no_content_identity(self):
        for path in (self.a, self.b):
            (path / "folder").mkdir()
            (path / "empty").touch()
            (path / "outside-link").symlink_to(self.root, target_is_directory=True)
        (self.a / "same-size").write_text("AAAA")
        (self.b / "same-size").write_text("BBBB")
        pa, a = self.scan(self.a)
        pb, b = self.scan(self.b)
        self.assertEqual(a["summary"], {"entries": 4, "files": 2, "directories": 1, "symlinks": 1, "other": 0, "file_bytes": 4})
        self.assertEqual({e["path"] for e in a["entries"]}, {"folder", "empty", "same-size", "outside-link"})
        self.assertTrue(all(e["availability"] == "unknown" for e in a["entries"]))
        self.assertTrue(all("size_bytes" not in e for e in a["entries"] if e["type"] != "file"))
        result = self.compare(pa, pb)
        self.assertEqual(result["same_file_metadata"], ["empty", "same-size"])
        self.assertIn("content identity", " ".join(result["limitations"]))
        with patch.object(Path, "open", side_effect=AssertionError("Scan must not open file contents")):
            self.assertEqual(inventory.scan(self.a, "delivery-v1")["status"], "complete")

    def test_path_count_trap_and_exact_unicode_case(self):
        for name in ("A", "é", "same"):
            (self.a / name).write_text("x")
        for name in ("a", "e\u0301", "same"):
            (self.b / name).write_text("y")
        pa, a = self.scan(self.a)
        pb, b = self.scan(self.b)
        self.assertEqual(a["summary"], b["summary"])
        diff = self.compare(pa, pb)
        self.assertEqual(set(diff["missing_confirmed"]), {"A", "é"})
        self.assertEqual(set(diff["extra_confirmed"]), {"a", "e\u0301"})
        self.assertEqual(diff["status"], "complete")

    def test_partial_coverage_is_asymmetric(self):
        (self.a / "left").touch()
        (self.b / "right").touch()
        for p in (self.a, self.b):
            (p / "unexamined").mkdir()
        full_a, _ = self.scan(self.a)
        part_a, a = self.scan(self.a, "--skip", "unexamined", code=1)
        full_b, _ = self.scan(self.b)
        part_b, _ = self.scan(self.b, "--skip", "unexamined", code=1)
        one = self.compare(part_a, full_b, code=1)
        self.assertEqual(one["missing_confirmed"], ["left"])
        self.assertEqual(one["extra_confirmed"], [])
        self.assertIn("right", one["recipient_only_unobserved"])
        two = self.compare(full_a, part_b, code=1)
        self.assertEqual(two["missing_confirmed"], [])
        self.assertEqual(two["extra_confirmed"], ["right"])
        self.assertIn("left", two["baseline_only_unobserved"])
        self.assertEqual(a["scope"]["exclusions"], [])
        self.assertTrue(a["skips"])

    def test_exclusions_and_scope_keys_restrict_absence_claims(self):
        for p in (self.a, self.b):
            (p / "images").mkdir()
            (p / "images" / "large.tif").touch()
        (self.a / "a").touch()
        (self.b / "b").touch()
        pa, a = self.scan(self.a, "--exclude", "images")
        pb, _ = self.scan(self.b, "--exclude", "images")
        self.assertEqual(a["status"], "complete")
        self.assertFalse(a["skips"])
        self.assertEqual([e["path"] for e in a["entries"]], ["a"])
        self.assertEqual(self.compare(pa, pb)["missing_confirmed"], ["a"])
        pc, _ = self.scan(self.b)
        mismatch = self.compare(pa, pc, code=1)
        self.assertFalse(mismatch["scopes_comparable"])
        self.assertFalse(mismatch["missing_confirmed"])
        self.assertFalse(mismatch["extra_confirmed"])
        b = json.loads(pb.read_text())
        b["scope"]["key"] = "different-delivery"
        pb.write_text(json.dumps(b))
        self.assertFalse(self.compare(pa, pb, code=1)["scopes_comparable"])
        proc = self.cli("scan", self.a, "--scope-key", "x", "--exclude", "images", "--skip", "images/sub", "--output", self.output())
        self.assertEqual(proc.returncode, 2)

    def test_file_sizes_and_types_are_separate(self):
        (self.a / "kind").touch()
        (self.b / "kind").mkdir()
        (self.a / "bytes").write_text("short")
        (self.b / "bytes").write_text("longer")
        pa, _ = self.scan(self.a)
        pb, _ = self.scan(self.b)
        d = self.compare(pa, pb)
        self.assertEqual(d["type_differences"], [{"path": "kind", "baseline_type": "file", "recipient_type": "directory"}])
        self.assertEqual(d["size_differences"], [{"path": "bytes", "baseline_bytes": 5, "recipient_bytes": 6}])

    def test_root_not_directory_missing_and_symlink_fail_with_evidence(self):
        not_dir = self.root / "not-dir"
        not_dir.write_text("unchanged")
        link = self.root / "root-link"
        link.symlink_to(self.a, target_is_directory=True)
        for p in (not_dir, self.root / "missing", link, self.a / ".." / "missing"):
            _, result = self.scan(p, code=2)
            self.assertEqual(result["status"], "failed")
            self.assertTrue(result["errors"])
            self.assertEqual(result["entries"], [])
            inventory.validate_manifest(result)
        self.assertEqual(not_dir.read_text(), "unchanged")
        _, empty = self.scan(self.a)
        self.assertEqual(empty["status"], "complete")
        self.assertFalse(empty["errors"])

    def test_read_error_preserves_partial_evidence(self):
        (self.a / "good").touch()
        (self.a / "denied").mkdir()
        original = os.open

        def denied(path, *args, **kwargs):
            if path == "denied":
                raise PermissionError("synthetic permission denied")
            return original(path, *args, **kwargs)

        output = self.output()
        with patch.object(inventory.os, "open", side_effect=denied), contextlib.redirect_stdout(io.StringIO()):
            code = inventory.main(["scan", str(self.a), "--scope-key", "x", "--output", str(output)])
        result = json.loads(output.read_text())
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "partial")
        self.assertEqual({e["path"] for e in result["entries"]}, {"good", "denied"})
        self.assertEqual(result["errors"][0]["path"], "denied")
        self.assertTrue(result["skips"])
        with patch.object(inventory.os, "scandir", side_effect=PermissionError("cannot enumerate")):
            root_error = inventory.scan(self.a, "x")
        self.assertEqual(root_error["status"], "partial")
        self.assertEqual(root_error["entries"], [])
        self.assertTrue(root_error["errors"])

    def test_stat_failure_and_mid_enumeration_failure_keep_prior_entries(self):
        (self.a / "good").touch()
        (self.a / "bad").touch()
        original = os.stat

        def stat_failure(path, *args, **kwargs):
            if path == "bad" and "dir_fd" in kwargs:
                raise FileNotFoundError("synthetic file vanished")
            return original(path, *args, **kwargs)

        with patch.object(inventory.os, "stat", side_effect=stat_failure):
            result = inventory.scan(self.a, "x")
        self.assertEqual([e["path"] for e in result["entries"]], ["good"])
        self.assertEqual(result["status"], "partial")
        inventory.validate_manifest(result)
        real_scandir = os.scandir

        class PartialIterator:
            def __init__(self, fd):
                self.iterator = real_scandir(fd)
            def __enter__(self): return self
            def __exit__(self, *args): self.iterator.close()
            def __iter__(self):
                yield next(self.iterator)
                raise PermissionError("synthetic enumeration interruption")

        with patch.object(inventory.os, "scandir", side_effect=PartialIterator):
            result = inventory.scan(self.a, "x")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(len(result["entries"]), 1)
        self.assertTrue(result["errors"])
        inventory.validate_manifest(result)

    def test_output_protection(self):
        for out in (self.a / "report.json", self.a / "nested" / "report.json"):
            p = self.cli("scan", self.a, "--scope-key", "x", "--output", out)
            self.assertEqual(p.returncode, 2)
            self.assertFalse(out.exists())
        alias = self.root / "alias"
        alias.symlink_to(self.a, target_is_directory=True)
        self.assertEqual(self.cli("scan", self.a, "--scope-key", "x", "--output", alias / "report.json").returncode, 2)
        pa, _ = self.scan(self.a)
        pb, _ = self.scan(self.b)
        original = pa.read_text()
        self.assertEqual(self.cli("compare", pa, pb, "--output", pa).returncode, 2)
        self.assertEqual(pa.read_text(), original)
        self.assertEqual(self.cli("compare", pa, pb, "--output", self.a / "report.json").returncode, 2)
        out = self.output()
        out.write_text("retain")
        self.assertEqual(self.cli("scan", self.a, "--scope-key", "x", "--output", out).returncode, 2)
        self.assertEqual(out.read_text(), "retain")

    def test_malformed_manifests_fail_without_inventory_access(self):
        pa, a = self.scan(self.a)
        pb, _ = self.scan(self.b)
        invalid = ["{", '{"schema_version":1,"schema_version":1}', 'NaN']
        for content in invalid:
            bad = self.output()
            bad.write_text(content)
            proc = self.cli("compare", bad, pb, "--output", self.output())
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stderr)["status"], "failed")
        entry = {"path": "file", "type": "file", "size_bytes": 1, "availability": "unknown"}
        for badpath in ("/absolute", "../escape", "a/../b", "a//b", "./a", "", "C:\\absolute"):
            bad = copy.deepcopy(a)
            bad["entries"] = [{**entry, "path": badpath}]
            bad["summary"] = inventory.summary(bad["entries"])
            with self.assertRaises(ValueError):
                inventory.validate_manifest(bad)
        for change in ("duplicate", "version", "size", "complete-skips", "summary"):
            bad = copy.deepcopy(a)
            bad["entries"] = [entry.copy()]
            if change == "duplicate": bad["entries"].append(entry.copy())
            if change == "version": bad["schema_version"] = 999
            if change == "size": bad["entries"][0]["size_bytes"] = True
            if change == "complete-skips": bad["skips"] = [{"path": "unknown", "reason": "skip"}]
            bad["summary"] = inventory.summary(bad["entries"])
            if change == "summary": bad["summary"]["files"] = 99
            with self.assertRaises(ValueError): inventory.validate_manifest(bad)
        for kind in ("file", "symlink", "other"):
            bad = copy.deepcopy(a)
            parent = {**entry, "type": kind}
            if kind != "file": del parent["size_bytes"]
            bad["entries"] = [parent, {**entry, "path": "file/child"}]
            bad["summary"] = inventory.summary(bad["entries"])
            with self.assertRaises(ValueError): inventory.validate_manifest(bad)
        a["source"]["root"] = "/unavailable/remote/source"
        with patch.object(Path, "open", side_effect=AssertionError("Do not inspect manifest roots or entries")), patch.object(inventory.os, "stat", side_effect=AssertionError("Do not stat source paths")):
            self.assertEqual(inventory.compare(a, a)["status"], "complete")


if __name__ == "__main__":
    unittest.main()
