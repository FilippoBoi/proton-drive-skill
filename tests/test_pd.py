"""End-to-end tests for the proton-drive skill. Run: python -m unittest discover -s tests -v

Local-backend tests always run. Cloud-backend tests use rclone's built-in `alias` remote pointing at a
temp folder (no Proton account needed) and run only if rclone >= 1.66 is available
(on PATH, in RCLONE_BIN, or in ~/.proton-drive-skill/bin).
"""
import base64, json, os, shutil, subprocess, sys, tempfile, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PD = os.path.join(HERE, "..", "skills", "proton-drive", "scripts", "pd.py")


def find_rclone():
    exe = "rclone.exe" if os.name == "nt" else "rclone"
    for c in (os.environ.get("RCLONE_BIN"), shutil.which("rclone"),
              os.path.join(os.path.expanduser("~"), ".proton-drive-skill", "bin", exe)):
        if c and os.path.isfile(c):
            try:
                v = subprocess.run([c, "version"], capture_output=True, text=True, timeout=30).stdout
                import re
                m = re.search(r"v(\d+)\.(\d+)", v)
                if m and (int(m[1]), int(m[2])) >= (1, 66):
                    return c
            except Exception:
                pass
    return None


class Shared:
    """Mixin with the tests both backends must pass; subclasses also inherit unittest.TestCase."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.env = {**os.environ, "HOME": self.home, "USERPROFILE": self.home}
        for k in ("PROTON_DRIVE_SKILL_CONFIG", "PROTON_DRIVE_SKILL_CONFIG_JSON", "PROTON_RCLONE_CONF_B64"):
            self.env.pop(k, None)
        self.setup_backend()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def pd(self, *args, ok=None):
        p = subprocess.run([sys.executable, PD, *args], capture_output=True, text=True, env=self.env, timeout=300)
        data = json.loads(p.stdout)
        if ok is not None:
            self.assertEqual(data["ok"], ok, msg=p.stdout)
        return data

    def write(self, name, text):
        p = os.path.join(self.tmp, name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)
        return p

    # ---- behaviour shared by both backends; `self.read(rel)` and `self.put_file(rel, text)` are backend specific ----
    def test_escape_and_absolute_paths_refused(self):
        for bad in ("..", "../x", "sub/../../x", "/etc/passwd", "C:/Windows"):
            self.assertFalse(self.pd("state", bad)["ok"], bad)

    def test_excluded_is_invisible_and_unreachable(self):
        self.put_file("Private/s.txt", "secret")
        self.assertFalse(self.pd("state", "Private/s.txt")["ok"])
        names = [i["path"] for i in self.pd("ls", "-r")["items"]]
        self.assertFalse([n for n in names if n.startswith("Private")])

    def test_overwrite_requires_confirmation_and_makes_backup(self):
        self.put_file("a.txt", "old")
        new = self.write("new.txt", "new")
        r = self.pd("put", new, "a.txt")
        self.assertFalse(r["ok"]); self.assertEqual(self.read("a.txt"), "old")
        r = self.pd("put", new, "a.txt", "--confirmed", ok=True)
        self.assertEqual(self.read("a.txt"), "new"); self.assertTrue(r["backup_id"])
        self.pd("restore", r["backup_id"], "--confirmed", ok=True)
        self.assertEqual(self.read("a.txt"), "old")

    def test_delete_requires_confirmation_and_is_restorable(self):
        self.put_file("sub/b.txt", "data")
        self.assertFalse(self.pd("rm", "sub")["ok"])
        r = self.pd("rm", "sub", "--confirmed", ok=True)
        self.assertIsNone(self.exists("sub"))
        self.pd("restore", r["backup_id"], "--confirmed", ok=True)
        self.assertEqual(self.read("sub/b.txt"), "data")

    def test_move_refuses_to_clobber(self):
        self.put_file("a.txt", "A"); self.put_file("b.txt", "B")
        self.assertFalse(self.pd("mv", "a.txt", "b.txt", "--confirmed")["ok"])
        self.assertEqual(self.read("b.txt"), "B")
        self.pd("mv", "a.txt", "c.txt", "--confirmed", ok=True)
        self.assertEqual(self.read("c.txt"), "A")

    def test_checkout_edit_put_roundtrip(self):
        self.put_file("doc.txt", "v1")
        co = self.pd("checkout", "doc.txt", ok=True)
        with open(co["work_copy"], "w") as f:
            f.write("v2")
        self.pd("put", co["work_copy"], "doc.txt", "--confirmed", ok=True)
        self.assertEqual(self.read("doc.txt"), "v2")

    def test_read_only_blocks_writes(self):
        self.set_cfg(read_only=True)
        new = self.write("n.txt", "x")
        self.assertFalse(self.pd("put", new, "n.txt")["ok"])
        self.assertFalse(self.pd("mkdir", "d")["ok"])

    def test_large_files_need_allow_download(self):
        self.set_cfg(large_file_mb=0)  # everything non-empty counts as large
        self.put_file("big.bin", "x" * 10)
        self.assertFalse(self.pd("checkout", "big.bin")["ok"])
        self.pd("checkout", "big.bin", "--allow-download", ok=True)

    def test_prune_needs_confirmation(self):
        self.assertFalse(self.pd("prune")["ok"])


class LocalBackend(Shared, unittest.TestCase):
    def setup_backend(self):
        self.root = os.path.join(self.tmp, "Drive")
        os.makedirs(os.path.join(self.root, "Work"))
        self.base_cfg = {"backend": "local", "root": self.root, "exclude": ["Private"]}
        os.makedirs(os.path.join(self.root, "Private"))
        self.set_cfg()

    def set_cfg(self, **extra):
        self.env["PROTON_DRIVE_SKILL_CONFIG_JSON"] = json.dumps({**self.base_cfg, **extra})

    def put_file(self, rel, text):
        p = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(text)

    def read(self, rel):
        with open(os.path.join(self.root, *rel.split("/"))) as f:
            return f.read()

    def exists(self, rel):
        return os.path.join(self.root, rel) if os.path.exists(os.path.join(self.root, rel)) else None

    def test_backup_dir_inside_root_refused(self):
        self.set_cfg(backup_dir=os.path.join(self.root, "bk"))
        self.assertFalse(self.pd("status")["ok"])

    def test_symlink_out_of_root_refused(self):
        outside = os.path.join(self.tmp, "outside"); os.makedirs(outside)
        try:
            os.symlink(outside, os.path.join(self.root, "Work", "link"))
        except (OSError, NotImplementedError):
            self.skipTest("symlinks not permitted here")
        self.assertFalse(self.pd("ls", "Work/link")["ok"])
        self.assertFalse(self.pd("state", "Work/link")["ok"])

    def test_backups_are_not_inside_the_synced_folder(self):
        self.put_file("a.txt", "old")
        r = self.pd("rm", "a.txt", "--confirmed", ok=True)
        self.assertFalse(os.path.exists(os.path.join(self.root, ".proton-drive-skill")))
        self.assertTrue(os.listdir(os.path.join(self.home, ".proton-drive-skill", "backups")))


@unittest.skipUnless(find_rclone(), "rclone >= 1.66 not available")
class RcloneBackend(Shared, unittest.TestCase):
    def setup_backend(self):
        self.fake = os.path.join(self.tmp, "fake")  # plays the role of the Proton account
        os.makedirs(os.path.join(self.fake, "Work")); os.makedirs(os.path.join(self.fake, "_backups"))
        conf = f"[proton]\ntype = alias\nremote = {self.fake}\n"
        self.env["PROTON_RCLONE_CONF_B64"] = base64.b64encode(conf.encode()).decode()
        self.env["RCLONE_BIN"] = find_rclone()
        self.base_cfg = {"backend": "rclone", "remote": "proton", "root": "Work", "backup_path": "_backups", "exclude": ["Private"]}
        self.set_cfg()

    def set_cfg(self, **extra):
        self.env["PROTON_DRIVE_SKILL_CONFIG_JSON"] = json.dumps({**self.base_cfg, **extra})

    def _p(self, rel):
        return os.path.join(self.fake, "Work", *rel.split("/"))

    def put_file(self, rel, text):
        os.makedirs(os.path.dirname(self._p(rel)), exist_ok=True)
        with open(self._p(rel), "w") as f:
            f.write(text)

    def read(self, rel):
        with open(self._p(rel)) as f:
            return f.read()

    def exists(self, rel):
        return self._p(rel) if os.path.exists(self._p(rel)) else None

    def test_doctor_ok(self):
        self.assertTrue(self.pd("doctor")["ok"])

    def test_overlapping_backup_path_refused(self):
        self.set_cfg(backup_path="Work/bk")
        self.assertFalse(self.pd("status")["ok"])

    def test_overwrite_with_same_size_and_mtime_is_not_skipped(self):
        # regression: rclone's default skips copies when size+modtime match, which made put report a fake success
        self.put_file("a.txt", "old")
        new = self.write("new.txt", "new")
        st = os.stat(self._p("a.txt"))
        os.utime(new, ns=(st.st_atime_ns, st.st_mtime_ns))
        self.pd("put", new, "a.txt", "--confirmed", ok=True)
        self.assertEqual(self.read("a.txt"), "new")

    def test_backups_live_outside_root_in_remote(self):
        self.put_file("a.txt", "old")
        r = self.pd("rm", "a.txt", "--confirmed", ok=True)
        self.assertTrue(os.path.isdir(os.path.join(self.fake, "_backups", r["backup_id"])))
        self.assertFalse(os.path.exists(os.path.join(self.fake, "Work", "_backups")))


if __name__ == "__main__":
    unittest.main()
