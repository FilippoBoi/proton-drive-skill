"""Install rclone (>= 1.66, needed for the Proton Drive backend) into ~/.proton-drive-skill/bin.

Order: 1) reuse an rclone that is already new enough, 2) download the official release from
downloads.rclone.org and check its SHA256 against the published SHA256SUMS, 3) fall back to
`go install` if Go is available. Standard library only.
"""
import hashlib, io, os, platform, re, shutil, stat, subprocess, sys, urllib.request, zipfile

VERSION = os.environ.get("RCLONE_VERSION", "1.69.3")
BIN_DIR = os.path.join(os.path.expanduser("~"), ".proton-drive-skill", "bin")
EXE = "rclone.exe" if os.name == "nt" else "rclone"


def version_of(binary):
    try:
        v = subprocess.run([binary, "version"], capture_output=True, text=True, timeout=30).stdout
        m = re.search(r"v(\d+)\.(\d+)", v)
        return (int(m[1]), int(m[2])) if m else None
    except Exception:
        return None


def target():
    sysname = {"Linux": "linux", "Darwin": "osx", "Windows": "windows"}.get(platform.system())
    arch = {"x86_64": "amd64", "AMD64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine())
    if not (sysname and arch):
        raise RuntimeError(f"unsupported platform {platform.system()}/{platform.machine()}")
    return f"{sysname}-{arch}"


def get(url):
    # downloads.rclone.org answers 403 to urllib's default User-Agent
    req = urllib.request.Request(url, headers={"User-Agent": "proton-drive-skill-installer/0.1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def download():
    name = f"rclone-v{VERSION}-{target()}.zip"
    base = f"https://downloads.rclone.org/v{VERSION}/"
    data = get(base + name)
    sums = get(base + "SHA256SUMS").decode()
    want = next((l.split()[0] for l in sums.splitlines() if l.strip().endswith(name)), None)
    got = hashlib.sha256(data).hexdigest()
    if not want or want != got:
        raise RuntimeError(f"checksum mismatch or missing for {name} (expected {want}, got {got})")
    os.makedirs(BIN_DIR, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        member = next(n for n in z.namelist() if n.endswith("/" + EXE))
        dest = os.path.join(BIN_DIR, EXE)
        with z.open(member) as src, open(dest, "wb") as dst:
            shutil.copyfileobj(src, dst)
    os.chmod(dest, os.stat(dest).st_mode | stat.S_IEXEC)
    return dest


def go_install():
    if not shutil.which("go"):
        raise RuntimeError("go not available")
    os.makedirs(BIN_DIR, exist_ok=True)
    env = {**os.environ, "GOBIN": BIN_DIR}
    subprocess.run(["go", "install", f"github.com/rclone/rclone@v{VERSION}"], env=env, check=True, timeout=1500)
    return os.path.join(BIN_DIR, EXE)


def main():
    for cand in (shutil.which("rclone"), os.path.join(BIN_DIR, EXE)):
        if cand and os.path.isfile(cand) and (version_of(cand) or (0, 0)) >= (1, 66):
            print(f"ok: using existing rclone at {cand}")
            return
    errors = []
    for fn in (download, go_install):
        try:
            path = fn()
            print(f"ok: installed {path} ({fn.__name__})")
            return
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")
            print(f"{fn.__name__} failed: {e}", file=sys.stderr)
    print("Could not install rclone. Allow downloads.rclone.org (or proxy.golang.org + github.com for 'go install') in the environment's network settings.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
