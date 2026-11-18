"""Shared helpers for the proton-drive skill (standard library only)."""
import hashlib, os, re, time

BID_RE = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


class Refused(Exception):
    """An operation was refused on purpose; the message tells the model what to do next."""


def home_dir():
    return os.path.join(os.path.expanduser("~"), ".proton-drive-skill")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def new_backup_id():
    return time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha1(os.urandom(8)).hexdigest()[:6]


def check_backup_id(bid):
    if not BID_RE.match(bid or ""):
        raise Refused(f"Invalid backup id: {bid!r}")
    return bid


def backup_time(bid):
    return time.mktime(time.strptime(bid[:15], "%Y%m%d-%H%M%S"))
