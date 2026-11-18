"""Backend for a folder kept in sync by the Proton Drive desktop app (Windows/macOS/Linux)."""
import json, os, shutil, sys, time
from common import Refused, check_backup_id, new_backup_id, sha256, backup_time

WIN_RECALL = 0x400000 | 0x40000 | 0x1000  # RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE
MAC_DATALESS = 0x40000000  # SF_DATALESS


def norm(p):
    return os.path.normcase(os.path.realpath(p))


def inside(path, root):
    a, r = norm(path), norm(root)
    try:
        return os.path.commonpath([a, r]) == r
    except ValueError:  # different drives on Windows
        return False


class LocalBackend:
    name = "local"

    def __init__(self, cfg, home):
        self.root = os.path.realpath(os.path.expanduser(cfg["root"] or ""))
        if not cfg["root"] or not os.path.isdir(self.root):
            raise Refused(f"Configured root is not an existing folder: {cfg['root']!r}. Is the Proton Drive app running and synced?")
        self.backup_dir = os.path.realpath(os.path.expanduser(cfg.get("backup_dir") or os.path.join(home, "backups")))
        self.work_dir = os.path.realpath(os.path.expanduser(cfg.get("work_dir") or os.path.join(home, "work")))
        for label, d in (("backup_dir", self.backup_dir), ("work_dir", self.work_dir)):
            if inside(d, self.root):
                raise Refused(f"{label} ({d}) must be OUTSIDE the synced root, otherwise it would be uploaded to the cloud.")
        self.index = os.path.join(self.backup_dir, "index.jsonl")

    # -- paths / state --
    def _abs(self, rel):
        real = os.path.realpath(os.path.join(self.root, *rel.split("/")) if rel else self.root)
        if not inside(real, self.root):
            raise Refused(f"Path resolves outside the root (symlink?): {rel!r}")
        return real

    def _state(self, p):
        st = os.stat(p)
        is_dir = os.path.isdir(p)
        online, how = False, "none"
        if not is_dir:
            attrs, flags = getattr(st, "st_file_attributes", None), getattr(st, "st_flags", None)
            if attrs is not None:
                online, how = bool(attrs & WIN_RECALL), "windows-attributes"
            elif flags is not None and sys.platform == "darwin":
                online, how = bool(flags & MAC_DATALESS), "macos-dataless-flag"
            elif hasattr(st, "st_blocks"):
                online, how = (st.st_size > 0 and st.st_blocks == 0), "linux-blocks-heuristic"
        return {"type": "dir" if is_dir else "file", "size": st.st_size, "mtime": int(st.st_mtime),
                "availability": "online-only" if online else "local", "detected_by": how}

    def stat(self, rel):
        p = self._abs(rel)
        return self._state(p) if os.path.lexists(p) else None

    def listdir(self, rel, recursive, limit, skip):
        base = self._abs(rel)
        walker = os.walk(base) if recursive else [(base, [], os.listdir(base))]
        items = []
        for d, dirs, names in walker:
            names = (dirs + names) if recursive else names
            if recursive:
                dirs[:] = [x for x in dirs if not skip(self._rel(os.path.join(d, x)))]
            for n in sorted(names):
                p = os.path.join(d, n)
                r = self._rel(p)
                if skip(r):
                    continue
                try:
                    if os.path.islink(p) and not inside(p, self.root):
                        e = {"type": "symlink", "note": "points outside the root; not accessible"}
                    else:
                        e = self._state(p)
                        if os.path.islink(p):
                            e["symlink"] = True
                except OSError as ex:
                    e = {"error": str(ex)}
                items.append({"path": r, **e})
                if len(items) >= limit:
                    return items, True
        return items, False

    def _rel(self, p):
        return os.path.relpath(p, self.root).replace(os.sep, "/")

    # -- data movement --
    def fetch(self, rel, dest):
        src = self._abs(rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(src, dest) if os.path.isdir(src) else shutil.copy2(src, dest)

    def store(self, src, rel):
        dst = self._abs(rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)  # single write: avoids syncing temp files to the cloud
        return sha256(src) == sha256(dst)

    def move(self, src, dst):
        d = self._abs(dst)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.move(self._abs(src), d)

    def delete(self, rel):
        p = self._abs(rel)
        shutil.rmtree(p) if os.path.isdir(p) else os.remove(p)

    def mkdir(self, rel):
        os.makedirs(self._abs(rel), exist_ok=True)

    # -- backups (kept outside the synced root) --
    def _log(self, entry):
        os.makedirs(self.backup_dir, exist_ok=True)
        with open(self.index, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _entries(self):
        if not os.path.isfile(self.index):
            return []
        with open(self.index, encoding="utf-8") as f:
            return [json.loads(l) for l in f if l.strip()]

    def log(self, action, path, **extra):
        self._log({"id": extra.pop("id", "-"), "action": action, "path": path, "time": int(time.time()), **extra})

    def backup(self, rel, action):
        bid, src = new_backup_id(), self._abs(rel)
        dest = os.path.join(self.backup_dir, bid, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copytree(src, dest) if os.path.isdir(src) else shutil.copy2(src, dest)
        self._log({"id": bid, "action": action, "path": rel, "backup": dest, "time": int(time.time())})
        return bid, dest

    def list_backups(self, limit):
        return [e for e in self._entries() if e.get("backup")][-limit:]

    def restore_backup(self, bid):
        check_backup_id(bid)
        m = [e for e in self._entries() if e.get("id") == bid and e.get("backup")]
        if not m or not os.path.exists(m[-1]["backup"]):
            raise Refused(f"Backup {bid} not found (pruned or removed).")
        rel, src = m[-1]["path"], m[-1]["backup"]
        dst = self._abs(rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.exists(dst):
            shutil.rmtree(dst) if os.path.isdir(dst) else os.remove(dst)
        shutil.copytree(src, dst) if os.path.isdir(src) else shutil.copy2(src, dst)
        return rel

    def prune(self, days):
        cutoff, removed = time.time() - days * 86400, []
        if os.path.isdir(self.backup_dir):
            for name in os.listdir(self.backup_dir):
                top = os.path.join(self.backup_dir, name)
                try:
                    check_backup_id(name)
                    if os.path.isdir(top) and backup_time(name) < cutoff:
                        shutil.rmtree(top)
                        removed.append(name)
                except Refused:
                    continue
        return removed

    def doctor(self):
        ok = os.path.isdir(self.root)
        return [{"check": "root folder exists", "ok": ok, "hint": None if ok else "Start the Proton Drive app and wait for the sync."},
                {"check": "backup dir outside root", "ok": True, "detail": self.backup_dir}]
