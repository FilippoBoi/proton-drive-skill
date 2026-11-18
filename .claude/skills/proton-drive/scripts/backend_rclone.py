"""Backend that talks to Proton Drive in the cloud through rclone (unofficial 'protondrive' backend).

The rclone config (with Proton session tokens) is read from ~/.proton-drive-skill/rclone.conf, or
materialised from the PROTON_RCLONE_CONF_B64 environment variable on first use.
"""
import base64, json, os, posixpath, re, shutil, stat, subprocess, sys, tempfile, time
from datetime import datetime
from common import Refused, check_backup_id, new_backup_id, backup_time

MIN_RCLONE = (1, 66)  # needs lsjson --stat
NOT_FOUND = ("not found", "doesn't exist", "does not exist")


def _epoch(s):
    try:
        s = re.sub(r"(\.\d{6})\d+", r"\1", s.replace("Z", "+00:00"))
        return int(datetime.fromisoformat(s).timestamp())
    except Exception:
        return 0


class RcloneBackend:
    name = "rclone"

    def __init__(self, cfg, home):
        self.home = home
        self.remote = (cfg.get("remote") or "proton").rstrip(":")
        self.root = (cfg.get("root") or "").strip("/")
        self.bk = (cfg.get("backup_path") or "").strip("/")
        self.timeout = int(cfg.get("rclone_timeout", 900))
        if not self.root or not self.bk:
            raise Refused("rclone backend needs both 'root' (the folder in Proton Drive to work in) and 'backup_path' (a folder OUTSIDE root for backups).")
        r, b = self.root + "/", self.bk + "/"
        if r.startswith(b) or b.startswith(r):
            raise Refused("'backup_path' and 'root' must not contain one another; pick sibling folders (e.g. root 'Work', backup_path '_backups').")
        self.conf = os.path.expanduser(cfg.get("rclone_conf") or os.path.join(home, "rclone.conf"))
        self.bin = self._find_bin(cfg.get("rclone_bin"))
        self._ensure_conf()
        self.work_dir = os.path.realpath(os.path.expanduser(cfg.get("work_dir") or os.path.join(home, "work")))

    # -- plumbing --
    def _find_bin(self, configured):
        for cand in (configured, os.environ.get("RCLONE_BIN"), shutil.which("rclone"),
                     os.path.join(self.home, "bin", "rclone"), os.path.join(self.home, "bin", "rclone.exe")):
            if cand and os.path.isfile(os.path.expanduser(cand)):
                return os.path.expanduser(cand)
        raise Refused("rclone not found. Run: python scripts/install_rclone.py (see references/cloud-setup.md).")

    def _ensure_conf(self):
        if os.path.isfile(self.conf):
            return
        b64 = os.environ.get("PROTON_RCLONE_CONF_B64")
        if not b64:
            raise Refused(f"No rclone config at {self.conf} and env PROTON_RCLONE_CONF_B64 is not set. See references/cloud-setup.md.")
        os.makedirs(os.path.dirname(self.conf), exist_ok=True)
        fd = os.open(self.conf, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(base64.b64decode(b64))

    def run(self, args, stdin=None, allow_fail=False):
        cmd = [self.bin, "--config", self.conf, *args]
        p = subprocess.run(cmd, input=stdin, capture_output=True, timeout=self.timeout)
        if p.returncode != 0 and not allow_fail:
            err = p.stderr.decode("utf-8", "replace").strip()[-800:]
            raise Refused(f"rclone failed ({' '.join(args[:2])}): {err}")
        return p

    def _p(self, rel):
        return f"{self.remote}:{posixpath.join(self.root, rel) if rel else self.root}"

    def _b(self, *parts):
        return f"{self.remote}:{posixpath.join(self.bk, *parts)}" if parts else f"{self.remote}:{self.bk}"

    @staticmethod
    def _entry(j):
        is_dir = j.get("IsDir", False)
        return {"type": "dir" if is_dir else "file", "size": -1 if is_dir else j.get("Size", 0),
                "mtime": _epoch(j.get("ModTime", "")), "availability": "remote", "detected_by": "rclone"}

    # -- state / listing --
    def stat(self, rel):
        p = self.run(["lsjson", "--stat", self._p(rel)], allow_fail=True)
        if p.returncode != 0:
            err = p.stderr.decode("utf-8", "replace").lower()
            if p.returncode in (3, 4) or any(s in err for s in NOT_FOUND):
                return None
            raise Refused(f"rclone failed (stat): {err.strip()[-800:]}")
        return self._entry(json.loads(p.stdout))

    def listdir(self, rel, recursive, limit, skip):
        args = ["lsjson", "--no-mimetype"] + (["-R"] if recursive else []) + [self._p(rel)]
        items = []
        for j in json.loads(self.run(args).stdout or "[]"):
            r = posixpath.join(rel, j["Path"]) if rel else j["Path"]
            if skip(r):
                continue
            items.append({"path": r, **self._entry(j)})
            if len(items) >= limit:
                return items, True
        return items, False

    # -- data movement --
    def fetch(self, rel, dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        st = self.stat(rel)
        self.run(["copy" if st and st["type"] == "dir" else "copyto", self._p(rel), dest])

    def store(self, src, rel):
        # --ignore-times: without it rclone skips the upload when size and modtime look equal
        # (e.g. two edits within Proton's 1 s timestamp precision), reporting a success that never happened
        self.run(["copyto", "--ignore-times", src, self._p(rel)])
        st = self.stat(rel)
        return bool(st) and st["size"] == os.path.getsize(src)

    def move(self, src, dst):
        self.run(["moveto", self._p(src), self._p(dst)])

    def delete(self, rel):
        st = self.stat(rel)
        self.run(["purge" if st and st["type"] == "dir" else "deletefile", self._p(rel)])

    def mkdir(self, rel):
        self.run(["mkdir", self._p(rel)])

    # -- backups: live in the same Proton account, outside root, so they survive ephemeral sessions --
    def log(self, *a, **k):
        pass  # the per-backup _meta.json is the audit trail in remote mode

    def backup(self, rel, action):
        bid, st = new_backup_id(), self.stat(rel)
        if not st:
            raise Refused(f"Nothing to back up at {rel!r}")
        dest = self._b(bid, rel)
        self.run(["copy" if st["type"] == "dir" else "copyto", self._p(rel), dest])
        meta = {"id": bid, "action": action, "path": rel, "type": st["type"], "time": int(time.time())}
        self.run(["rcat", self._b(bid, "_meta.json")], stdin=json.dumps(meta).encode())
        return bid, f"{self.remote}:{self.bk}/{bid}/{rel}"

    def _ids(self):
        out = json.loads(self.run(["lsjson", "--dirs-only", "--no-mimetype", self._b()], allow_fail=True).stdout or "[]")
        return sorted([j["Name"] for j in out if re.match(r"^\d{8}-\d{6}-[0-9a-f]{6}$", j["Name"])])

    def _meta(self, bid):
        p = self.run(["cat", self._b(bid, "_meta.json")], allow_fail=True)
        return json.loads(p.stdout) if p.returncode == 0 else None

    def list_backups(self, limit):
        res = []
        for bid in self._ids()[-limit:]:
            m = self._meta(bid)
            if m:
                res.append({**m, "backup": f"{self.remote}:{self.bk}/{bid}/{m['path']}"})
        return res

    def restore_backup(self, bid):
        check_backup_id(bid)
        m = self._meta(bid)
        if not m:
            raise Refused(f"Backup {bid} not found in {self.bk}.")
        rel = m["path"]
        if self.stat(rel):
            self.delete(rel)
        self.run(["copy" if m.get("type") == "dir" else "copyto", "--ignore-times", self._b(bid, rel), self._p(rel)])
        return rel

    def prune(self, days):
        cutoff, removed = time.time() - days * 86400, []
        for bid in self._ids():
            if backup_time(bid) < cutoff:
                self.run(["purge", self._b(bid)])
                removed.append(bid)
        return removed

    def doctor(self):
        checks = []
        try:
            v = self.run(["version"]).stdout.decode().split("\n")[0]
            m = re.search(r"v(\d+)\.(\d+)", v)
            ok = bool(m) and (int(m[1]), int(m[2])) >= MIN_RCLONE
            checks.append({"check": f"rclone version >= {MIN_RCLONE[0]}.{MIN_RCLONE[1]}", "ok": ok, "detail": v,
                           "hint": None if ok else "Reinstall with scripts/install_rclone.py"})
        except Refused as e:
            checks.append({"check": "rclone runs", "ok": False, "detail": str(e)})
            return checks
        p = self.run(["lsjson", "--max-depth", "1", f"{self.remote}:"], allow_fail=True)
        ok = p.returncode == 0
        checks.append({"check": "can reach and log in to Proton", "ok": ok,
                       "detail": p.stderr.decode("utf-8", "replace").strip()[-600:] if not ok else "ok",
                       "hint": None if ok else "Typical causes: host not in the environment's network allowlist (look for 'no rule allows host' and add that host), or expired session tokens (re-export the rclone config, see references/cloud-setup.md)."})
        if ok:
            st = self.stat("")
            checks.append({"check": f"root folder '{self.root}' exists", "ok": bool(st),
                           "hint": None if st else f"Create the folder '{self.root}' in the Proton account, or run: pd.py mkdir ."})
        return checks
