# Cloud mode (rclone)

Everything goes through two rclone remotes defined in the user's `rclone.conf`:

- `work:` is the only folder you may touch (an `alias` of one folder in the Proton account).
- `backup:` is where backups live, a sibling folder outside `work:`.

**Never use the underlying `proton:` remote directly** and never run `rclone config show/dump/obscure/reveal` (rule 8). Using only `work:` keeps every path inside the root even if a path contains `..`: tested with rclone, such a path does not leave the aliased folder.

Optional environment variables: `PROTON_DRIVE_EXCLUDE` (comma-separated patterns such as `Private/**,*.kdbx`: add one `--exclude "<pattern>"` per pattern to every listing, and refuse to touch matching paths), `PROTON_DRIVE_READ_ONLY` (`1` disables writes), `PROTON_DRIVE_LARGE_MB` (default 100).

Each Bash call starts a fresh shell, so repeat setup lines when you need them. `REL` means a path relative to the root; `ID` is `$(date +%Y%m%d-%H%M%S)` (add `-2` if that backup folder already exists).

## 0. Health check (once per session)

```bash
command -v rclone >/dev/null || echo "rclone missing: see references/cloud-setup.md"
rclone version | head -1                      # needs v1.66 or newer
mkdir -p ~/.config/rclone
[ -f ~/.config/rclone/rclone.conf ] || { printf %s "$PROTON_RCLONE_CONF_B64" | base64 -d > ~/.config/rclone/rclone.conf; chmod 600 ~/.config/rclone/rclone.conf; }
rclone lsjson --max-depth 1 work: >/dev/null && echo "login, network and root OK"
rclone lsjson --max-depth 1 backup: >/dev/null && echo "backup folder OK"
```

If the last commands fail, read the error. Typical causes: a host is not in the environment's network allowlist (the proxy says "no rule allows host": tell the user which host to allow, do not look for a way around the proxy), session tokens expired (the user must re-export the login, see `cloud-setup.md`), or the root folder does not exist in the Proton account.

## List, find, inspect

```bash
rclone lsjson --no-mimetype work:SUBFOLDER            # one level: Name, Size, ModTime, IsDir
rclone lsf -R work: | grep -i "invoice"               # find by name (add --exclude flags)
rclone lsjson --stat work:REL                         # one item; exit code 3 or 4 = not found
```

Every read downloads. Before downloading, check `Size` from `--stat`: above the large-file limit, tell the user and ask.

## Edit a file (copy, edit, write back)

```bash
WORK=~/.proton-drive-skill/work/$(date +%Y%m%d-%H%M%S); mkdir -p "$WORK"
rclone copyto work:REL "$WORK/$(basename REL)"        # download
# ... edit the copy ...
```

To write it back, ask for approval (rule 5), then back up the current version and upload. `--ignore-times` is required: without it rclone skips the upload when size and mtime match, and reports success.

```bash
ID=$(date +%Y%m%d-%H%M%S)
rclone copyto work:REL backup:$ID/REL                 # 1. back up what is there now
rclone copyto --ignore-times "$WORK/FILE" work:REL    # 2. upload
rclone lsjson --stat work:REL | grep '"Size"'; stat -c %s "$WORK/FILE"   # 3. sizes must match
```

## New file or folder (nothing exists yet)

```bash
rclone lsjson --stat work:REL >/dev/null 2>&1 && echo "EXISTS: stop and ask" || rclone copyto --ignore-times "$WORK/FILE" work:REL
rclone mkdir work:NEWFOLDER
```

Do not use `--immutable` as a safety net: it did not stop an overwrite in testing. Always check existence explicitly as above.

## Move or rename

After approval. Refuse if the destination exists unless the user approves replacing it (then back it up first as in "Edit a file").

```bash
rclone lsjson --stat work:DST >/dev/null 2>&1 && echo "DESTINATION EXISTS: stop and ask"
rclone moveto --dry-run work:SRC work:DST              # preview for bulk moves
rclone moveto work:SRC work:DST
```

Undo: `rclone moveto work:DST work:SRC`.

## Delete

After approval. Deleting is moving into the backup folder, which keeps it restorable:

```bash
ID=$(date +%Y%m%d-%H%M%S)
rclone moveto work:REL backup:$ID/REL
rclone lsjson --stat work:REL >/dev/null 2>&1 && echo "STILL THERE" || echo "removed; backup ID $ID"
```

Never use `rclone deletefile`, `delete`, `purge` or `sync` on `work:`.

## Restore and backups

```bash
rclone lsf backup: --dirs-only                        # backup IDs
rclone lsf -R backup:ID                                # what is inside one
# restore (after approval; if REL exists now, back it up under a new ID first):
rclone moveto backup:ID/REL work:REL
```

Prune old backups only on request and after approval: `rclone purge backup:ID` for each ID the user agrees to remove (the one place `purge` is allowed, and only on `backup:`).

## Known issues

- The backend is unofficial and beta; Proton updates may break it.
- Tokens can expire or rotate and an ephemeral container cannot keep refreshed ones: the user then has to re-export the login.
- Interrupted uploads can leave a draft that makes a retry fail with an "already exists" style error: retry once, then tell the user (rclone has `--protondrive-replace-existing-draft` for this; use it only if the user agrees).
- Listings can be stale because rclone caches metadata: list the parent again after a minute.
- Raise rclone's `--timeout`/`--contimeout` for slow large transfers, and keep large files out of the working folder.
