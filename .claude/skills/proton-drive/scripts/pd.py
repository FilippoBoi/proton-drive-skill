#!/usr/bin/env python3
"""proton-drive helper: safe file operations on a Proton Drive, locally synced folder OR cloud (rclone).

Standard library only. Every command prints JSON. Exit code 0 = ok, 1 = refused/error.
Safety rules enforced here (not left to the model):
  * every path is validated and must stay inside the configured root (no .., no symlink escape)
  * excluded paths are invisible
  * online-only files and large files are never downloaded/copied unless --allow-download
  * overwrite / move / delete / restore need --confirmed and always keep a backup outside the root
"""
import argparse, fnmatch, json, os, posixpath, sys, tempfile, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Refused, home_dir, sha256  # noqa: E402

CONFIG_ENV, CONFIG_JSON_ENV = "PROTON_DRIVE_SKILL_CONFIG", "PROTON_DRIVE_SKILL_CONFIG_JSON"
DEFAULTS = {"backend": "local", "root": "", "exclude": [], "read_only": False, "large_file_mb": 100,
            "backup_retention_days": 30, "work_dir": "",
            # local backend
            "backup_dir": "",
            # rclone backend
            "remote": "proton", "backup_path": "", "rclone_bin": "", "rclone_conf": "", "rclone_timeout": 900}


def out(obj, code=0):
    print(json.dumps(obj, indent=2, ensure_ascii=False))
    sys.exit(code)


def fail(msg, **extra):
    out({"ok": False, "error": msg, **extra}, 1)


def config_path():
    return os.environ.get(CONFIG_ENV) or os.path.join(home_dir(), "config.json")


def load_config():
    """Config comes from env PROTON_DRIVE_SKILL_CONFIG_JSON (cloud sessions) or from the config file."""
    raw = os.environ.get(CONFIG_JSON_ENV)
    if raw:
        data = json.loads(raw)
    else:
        p = config_path()
        if not os.path.isfile(p):
            raise Refused(f"No config found. Run: pd.py init --backend local --root <synced folder>  (or --backend rclone --root <folder in Proton> --backup-path <other folder>). Looked in {p} and env {CONFIG_JSON_ENV}.")
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    return {**DEFAULTS, **data}


def make_backend(cfg):
    if cfg["backend"] == "local":
        from backend_local import LocalBackend
        return LocalBackend(cfg, home_dir())
    if cfg["backend"] == "rclone":
        from backend_rclone import RcloneBackend
        return RcloneBackend(cfg, home_dir())
    raise Refused(f"Unknown backend {cfg['backend']!r} (use 'local' or 'rclone').")


class Ctx:
    def __init__(self):
        self.cfg = load_config()
        self.be = make_backend(self.cfg)
        self.work_dir = os.path.realpath(os.path.expanduser(self.cfg["work_dir"] or os.path.join(home_dir(), "work")))

    # ---- path validation (backend independent) ----
    def rel(self, p):
        p = (p or ".").replace("\\", "/")
        if hasattr(self.be, "root") and self.be.name == "local" and os.path.isabs(os.path.expanduser(p.replace("/", os.sep))):
            from backend_local import inside
            real = os.path.realpath(os.path.expanduser(p))
            if not inside(real, self.be.root):
                raise Refused(f"Path is outside the configured root: {p!r}")
            p = os.path.relpath(real, self.be.root).replace(os.sep, "/")
        elif p.startswith("/") or (len(p) > 1 and p[1] == ":"):
            raise Refused(f"Use paths relative to the root, not absolute ones: {p!r}")
        n = posixpath.normpath(p)
        if n == "." or n == "":
            return ""
        if n == ".." or n.startswith("../"):
            raise Refused(f"Path escapes the configured root: {p!r}")
        if self.excluded(n):
            raise Refused(f"Path is in an excluded area: {p!r}")
        return n

    def excluded(self, rel):
        if not rel:
            return False
        parts = rel.split("/")
        for i in range(len(parts)):
            cum = "/".join(parts[: i + 1])
            for pat in self.cfg["exclude"]:
                pat = pat.strip("/").replace("\\", "/")
                if fnmatch.fnmatch(cum, pat) or fnmatch.fnmatch(parts[i], pat):
                    return True
        return False

    # ---- guards ----
    def must_exist(self, rel):
        st = self.be.stat(rel)
        if st is None:
            raise Refused(f"Not found: {rel or '(root)'}")
        return st

    def need_readable(self, rel, st, allow, what):
        if st["type"] != "file":
            return
        limit = self.cfg["large_file_mb"] * 1048576
        if st["availability"] == "online-only" and not allow:
            raise Refused(f"{rel} is online-only; {what} would download it ({st['size']} bytes). Ask the user, then retry with --allow-download.")
        if st["size"] > limit and not allow:
            raise Refused(f"{rel} is large ({st['size'] // 1048576} MB > {self.cfg['large_file_mb']} MB). Ask the user, then retry with --allow-download.")

    def need_write(self):
        if self.cfg["read_only"]:
            raise Refused("Config has read_only=true: modifications are disabled.")

    @staticmethod
    def need_confirm(a, what):
        if not a.confirmed:
            raise Refused(f"{what} requires explicit user approval. Show the user exactly what will change, get a yes, then retry with --confirmed.")


def entry_view(e):
    return {k: v for k, v in e.items() if v is not None}


# ---------------- commands ----------------
def cmd_init(a):
    cfg = {**DEFAULTS, "backend": a.backend, "root": a.root, "exclude": a.exclude or []}
    if a.backend == "local":
        cfg["root"] = os.path.realpath(os.path.expanduser(a.root))
        if a.backup_dir:
            cfg["backup_dir"] = a.backup_dir
    else:
        cfg.update({"remote": a.remote, "backup_path": a.backup_path or ""})
    keep = {k: v for k, v in cfg.items() if v not in ("", None) or k in ("root",)}
    p = config_path()
    if a.backend == "local":  # validate before writing
        os.environ[CONFIG_JSON_ENV] = json.dumps(keep)
        Ctx()
        del os.environ[CONFIG_JSON_ENV]
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(keep, f, indent=2, ensure_ascii=False)
    out({"ok": True, "config_file": p, "config_json_for_env": json.dumps(keep), "next": "Run: pd.py doctor"})


def cmd_status(a):
    c = Ctx()
    out({"ok": True, "backend": c.be.name, "root": c.cfg["root"], "exclude": c.cfg["exclude"], "read_only": c.cfg["read_only"],
         "large_file_mb": c.cfg["large_file_mb"], "retention_days": c.cfg["backup_retention_days"],
         "backup_location": getattr(c.be, "backup_dir", None) or f"{c.cfg['remote']}:{c.cfg['backup_path']}",
         "work_dir": c.work_dir, "platform": sys.platform})


def cmd_doctor(a):
    c = Ctx()
    checks = c.be.doctor()
    out({"ok": all(x["ok"] for x in checks), "backend": c.be.name, "checks": checks}, 0 if all(x["ok"] for x in checks) else 1)


def cmd_ls(a):
    c = Ctx()
    rel = c.rel(a.path)
    st = c.must_exist(rel)
    if st["type"] != "dir":
        raise Refused(f"{rel} is a file; use 'state'.")
    items, trunc = c.be.listdir(rel, a.recursive, a.max, c.excluded)
    out({"ok": True, "base": rel or "(root)", "count": len(items), "truncated": trunc, "items": items})


def cmd_find(a):
    c = Ctx()
    base = c.rel(a.under)
    c.must_exist(base)
    items, trunc = c.be.listdir(base, True, 20000, c.excluded)
    pat = a.pattern.lower()
    pat = pat if any(ch in pat for ch in "*?[") else f"*{pat}*"
    hits = [i for i in items if fnmatch.fnmatch(posixpath.basename(i["path"]).lower(), pat)][: a.max]
    out({"ok": True, "count": len(hits), "searched_truncated": trunc, "items": hits})


def cmd_state(a):
    c = Ctx()
    items = []
    for p in a.paths:
        rel = c.rel(p)
        st = c.must_exist(rel)
        st["large"] = st["type"] == "file" and st["size"] > c.cfg["large_file_mb"] * 1048576
        items.append({"path": rel, **st})
    out({"ok": True, "items": items})


def cmd_checkout(a):
    c = Ctx()
    rel = c.rel(a.path)
    st = c.must_exist(rel)
    if st["type"] != "file":
        raise Refused("checkout works on single files")
    c.need_readable(rel, st, a.allow_download, "checkout")
    dest = os.path.join(c.work_dir, time.strftime("%Y%m%d-%H%M%S"), posixpath.basename(rel))
    c.be.fetch(rel, dest)
    out({"ok": True, "source": rel, "work_copy": dest, "sha256": sha256(dest),
         "next": f'Edit the work copy, then: pd.py put "{dest}" "{rel}" --confirmed'})


def cmd_put(a):
    c = Ctx()
    c.need_write()
    src = os.path.realpath(os.path.expanduser(a.src))
    if not os.path.isfile(src):
        raise Refused(f"Source file not found: {src}")
    if c.be.name == "local":
        from backend_local import inside
        if inside(src, c.be.root):
            raise Refused("Source is already inside the synced root; use 'mv' to move files within it.")
    dst = c.rel(a.dst)
    st = c.be.stat(dst)
    if st and st["type"] == "dir":
        dst = c.rel(posixpath.join(dst, os.path.basename(src)))
        st = c.be.stat(dst)
    bid = None
    if st:
        c.need_confirm(a, "Overwriting an existing file")
        c.need_readable(dst, st, a.allow_download, "backing up before overwrite")
        bid, _ = c.be.backup(dst, "overwrite")
    ok = c.be.store(src, dst)
    c.be.log("put", dst, id=bid or "-")
    out({"ok": bool(ok), "written": dst, "backup_id": bid, "verified": bool(ok),
         "undo": f"pd.py restore {bid} --confirmed" if bid else f'pd.py rm "{dst}" --confirmed'}, 0 if ok else 1)


def cmd_mv(a):
    c = Ctx()
    c.need_write()
    c.need_confirm(a, "Moving/renaming")
    src, dst = c.rel(a.src), c.rel(a.dst)
    if not src:
        raise Refused("Refusing to move the root folder.")
    c.must_exist(src)
    d = c.be.stat(dst)
    if d and d["type"] == "dir":
        dst = c.rel(posixpath.join(dst, posixpath.basename(src)))
        d = c.be.stat(dst)
    bid = None
    if d:
        if not a.overwrite:
            raise Refused(f"Destination exists: {dst}. Choose another name or pass --overwrite (backs up the destination).")
        c.need_readable(dst, d, a.allow_download, "backing up destination")
        bid, _ = c.be.backup(dst, "mv-overwrite")
        c.be.delete(dst)
    c.be.move(src, dst)
    c.be.log("mv", src, to=dst, id=bid or "-")
    out({"ok": True, "from": src, "to": dst, "backup_id": bid, "undo": f'pd.py mv "{dst}" "{src}" --confirmed'})


def cmd_rm(a):
    c = Ctx()
    c.need_write()
    c.need_confirm(a, "Deleting")
    rel = c.rel(a.path)
    if not rel:
        raise Refused("Refusing to delete the root folder.")
    st = c.must_exist(rel)
    bid = None
    if not a.no_backup:
        c.need_readable(rel, st, a.allow_download, "backing up before delete")
        bid, _ = c.be.backup(rel, "delete")
    c.be.delete(rel)
    c.be.log("rm", rel, id=bid or "-")
    out({"ok": True, "deleted": rel, "backup_id": bid,
         "undo": f"pd.py restore {bid} --confirmed" if bid else "No backup was made; Proton's web trash may still have it."})


def cmd_mkdir(a):
    c = Ctx()
    c.need_write()
    rel = c.rel(a.path)
    c.be.mkdir(rel)
    out({"ok": True, "created": rel or "(root)"})


def cmd_backup(a):
    c = Ctx()
    rel = c.rel(a.path)
    st = c.must_exist(rel)
    c.need_readable(rel, st, a.allow_download, "backup")
    bid, where = c.be.backup(rel, "manual")
    out({"ok": True, "backup_id": bid, "location": where})


def cmd_backups(a):
    c = Ctx()
    out({"ok": True, "items": c.be.list_backups(a.max)})


def cmd_restore(a):
    c = Ctx()
    c.need_write()
    c.need_confirm(a, "Restoring")
    # the current version is backed up first so a restore is itself undoable
    from common import check_backup_id
    check_backup_id(a.id)
    meta = [e for e in c.be.list_backups(10000) if e.get("id") == a.id]
    if not meta:
        raise Refused(f"No backup with id {a.id}")
    rel = c.rel(meta[-1]["path"])
    cur = c.be.stat(rel)
    cur_bid = None
    if cur:
        c.need_readable(rel, cur, a.allow_download, "backing up the current version")
        cur_bid, _ = c.be.backup(rel, "pre-restore")
    c.be.restore_backup(a.id)
    out({"ok": True, "restored": rel, "from_backup": a.id, "previous_version_backup_id": cur_bid})


def cmd_prune(a):
    c = Ctx()
    c.need_confirm(a, "Pruning backups")
    out({"ok": True, "removed_backup_ids": c.be.prune(c.cfg["backup_retention_days"])})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, help=None):
        sp = sub.add_parser(name, help=help)
        sp.set_defaults(fn=fn)
        return sp

    def flags(sp, confirm=False, dl=False):
        if confirm:
            sp.add_argument("--confirmed", action="store_true")
        if dl:
            sp.add_argument("--allow-download", action="store_true")
        return sp

    sp = add("init", cmd_init, "create config")
    sp.add_argument("--backend", choices=["local", "rclone"], default="local")
    sp.add_argument("--root", required=True, help="local: synced folder path; rclone: folder inside the Proton account")
    sp.add_argument("--exclude", action="append"); sp.add_argument("--backup-dir"); sp.add_argument("--remote", default="proton"); sp.add_argument("--backup-path")
    add("status", cmd_status, "show config")
    add("doctor", cmd_doctor, "check that everything works (rclone, login, network, root)")
    sp = add("ls", cmd_ls); sp.add_argument("path", nargs="?"); sp.add_argument("-r", "--recursive", action="store_true"); sp.add_argument("--max", type=int, default=500)
    sp = add("find", cmd_find); sp.add_argument("pattern"); sp.add_argument("--under"); sp.add_argument("--max", type=int, default=200)
    sp = add("state", cmd_state, "availability, size, large flag"); sp.add_argument("paths", nargs="+")
    sp = flags(add("checkout", cmd_checkout, "copy a file to the work dir for editing"), dl=True); sp.add_argument("path")
    sp = flags(add("put", cmd_put, "write a local file into the drive (create/overwrite)"), True, True); sp.add_argument("src"); sp.add_argument("dst")
    sp = flags(add("mv", cmd_mv), True, True); sp.add_argument("src"); sp.add_argument("dst"); sp.add_argument("--overwrite", action="store_true")
    sp = flags(add("rm", cmd_rm, "delete (backup kept)"), True, True); sp.add_argument("path"); sp.add_argument("--no-backup", action="store_true")
    sp = add("mkdir", cmd_mkdir); sp.add_argument("path")
    sp = flags(add("backup", cmd_backup), dl=True); sp.add_argument("path")
    sp = add("backups", cmd_backups); sp.add_argument("--max", type=int, default=20)
    sp = flags(add("restore", cmd_restore), True, True); sp.add_argument("id")
    flags(add("prune", cmd_prune, "delete backups older than retention"), True)

    args = ap.parse_args()
    try:
        args.fn(args)
    except Refused as e:
        fail(str(e))
    except (OSError, json.JSONDecodeError) as e:
        fail(f"{type(e).__name__}: {e}")
    except Exception as e:  # subprocess timeouts etc.
        fail(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
