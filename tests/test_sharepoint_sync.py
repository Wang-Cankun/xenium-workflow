"""SharePoint sync script: fake rclone/curl on PATH, synthetic source tree."""

import os
from pathlib import Path
import stat
import subprocess
import tempfile
import textwrap
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/xenium-data-download/scripts/sharepoint_sync.sh"
SITE = "https://tenant-my.sharepoint.com/personal/owner_example_org"
PREFIX = "/personal/owner_example_org/Documents/"

FAKE_RCLONE = """\
#!/usr/bin/env python3
import os, sys
from pathlib import Path
remote = next(a for a in sys.argv if a.startswith(":webdav"))
root = Path(os.environ["FAKE_SRC"]) / remote.rsplit(":", 1)[1]
for p in sorted(root.rglob("*")):
    if p.is_file():
        print(f"{p.stat().st_size}\\t{p.relative_to(root)}")
"""

FAKE_CURL = """\
#!/usr/bin/env python3
import os, sys, urllib.parse
from pathlib import Path
args = sys.argv[1:]
out = Path(args[args.index("-o") + 1])
url = args[-1]
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(url + "\\n")
code = os.environ.get("FAKE_CODE", "200")
once = os.environ.get("FAKE_429_ONCE")
if once:
    marker = Path(once) / urllib.parse.quote(url, safe="")
    if not marker.exists():
        marker.touch()
        code = "429"
if code != "200":
    with open(out, "ab") as fh:
        fh.write(b"<html>error page</html>")
    print(code, end="")
    sys.exit(0)
src_rel = urllib.parse.unquote(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["SourceUrl"][0])
data = (Path(os.environ["FAKE_SRC"]) / src_rel.removeprefix(os.environ["FAKE_PREFIX"])).read_bytes()
if "-C" in args and out.exists():
    have = out.stat().st_size
    with open(out, "ab") as fh:
        fh.write(data[have:])
    print("206", end="")
else:
    out.write_bytes(data)
    print("200", end="")
"""


class SharePointSync(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.src = self.root / "src"
        self.dest = self.root / "dest"
        self.logs = self.root / "logs"
        self.calls = self.root / "curl_calls.txt"
        self.cookie = self.root / "cookie.txt"
        self.cookie.write_text("FedAuth=synthetic")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        for name, body in (("rclone", FAKE_RCLONE), ("curl", FAKE_CURL)):
            exe = bin_dir / name
            exe.write_text(textwrap.dedent(body))
            exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                        FAKE_SRC=str(self.src), FAKE_LOG=str(self.calls), FAKE_PREFIX=PREFIX,
                        RETRY_DELAY="0")
        self.put("Batch 1/a (1).tiff", b"A" * 100)
        self.put("Batch 1/sub/b.tiff", b"B" * 50)
        self.put("Images/c.tiff", b"C" * 10)

    def put(self, rel, data):
        path = self.src / "Colorado" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def run_sync(self, *extra, **env):
        return subprocess.run(
            ["bash", str(SCRIPT), "--site", SITE, "--folder", "Colorado", "--dest", str(self.dest),
             "--cookie-file", str(self.cookie), "--log-dir", str(self.logs), *extra],
            env=dict(self.env, **env), capture_output=True, text=True)

    def curl_calls(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_mirrors_tree_through_download_aspx(self):
        proc = self.run_sync()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual((self.dest / "Batch 1/a (1).tiff").read_bytes(), b"A" * 100)
        self.assertEqual((self.dest / "Batch 1/sub/b.tiff").read_bytes(), b"B" * 50)
        self.assertEqual(list(self.dest.rglob("*.part")), [])
        self.assertTrue(all("/_layouts/15/download.aspx?SourceUrl=" in u for u in self.curl_calls()))
        self.assertIn("done: 3 downloaded, 0 already complete, 0 failed", proc.stdout)

    def test_rerun_skips_complete_and_resumes_partial(self):
        self.assertEqual(self.run_sync().returncode, 0)
        (self.dest / "Images/c.tiff").unlink()
        (self.dest / "Images/c.tiff.part").write_bytes(b"C" * 4)
        self.calls.unlink()
        proc = self.run_sync()
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual(len(self.curl_calls()), 1)
        self.assertEqual((self.dest / "Images/c.tiff").read_bytes(), b"C" * 10)
        self.assertIn("done: 1 downloaded, 2 already complete, 0 failed", proc.stdout)

    def test_expired_cookie_fails_without_keeping_body(self):
        proc = self.run_sync(FAKE_CODE="302")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("3 failed", proc.stdout)
        self.assertFalse(self.dest.joinpath("Images/c.tiff").exists())
        self.assertEqual(list(self.dest.rglob("*.part")), [])
        log = next(self.logs.glob("sync_*.log")).read_text()
        self.assertIn("FAIL http=302 Images/c.tiff", log)

    def test_throttled_attempt_is_retried_without_error_body(self):
        (self.dest / "Images").mkdir(parents=True)
        (self.dest / "Images/c.tiff.part").write_bytes(b"C" * 4)
        state = self.root / "throttle"
        state.mkdir()
        proc = self.run_sync(FAKE_429_ONCE=str(state))
        self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
        self.assertEqual((self.dest / "Images/c.tiff").read_bytes(), b"C" * 10)
        self.assertEqual((self.dest / "Batch 1/a (1).tiff").read_bytes(), b"A" * 100)
        self.assertEqual(len(self.curl_calls()), 6)

    def test_list_only_downloads_nothing(self):
        proc = self.run_sync("--list-only")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("listed 3 files", proc.stdout)
        self.assertEqual(len((self.logs / "filelist.tsv").read_text().splitlines()), 3)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.curl_calls(), [])

    def test_missing_argument_is_usage_error(self):
        proc = subprocess.run(["bash", str(SCRIPT), "--site", SITE], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("missing --folder", proc.stderr)


if __name__ == "__main__":
    unittest.main()
