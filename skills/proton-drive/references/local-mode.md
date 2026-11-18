# Local mode (folder synced by the Proton Drive app)

You work with ordinary file tools and shell commands on the folder that the desktop app keeps synced. The app uploads every change within seconds.

## Configuration

Read `~/.proton-drive-skill/config.json` (on Windows `%USERPROFILE%\.proton-drive-skill\config.json`). If it does not exist, ask the user for the folder to use as **root** and any folders to exclude, then create it with the Write tool:

```json
{
  "root": "C:\\Users\\NAME\\Proton Drive\\Work",
  "exclude": ["Private", "*.kdbx"],
  "backup_dir": "~/.proton-drive-skill/backups",
  "work_dir": "~/.proton-drive-skill/work",
  "read_only": false,
  "large_file_mb": 100
}
```

`backup_dir` and `work_dir` must be **outside** the root: anything inside it is uploaded to the cloud. If the root does not exist, the app is probably not running or not signed in: tell the user instead of guessing another folder.

## Keep every path inside the root

Resolve the target first and compare it with the resolved root. This also catches `..` and symlinks that lead out.

```bash
root=$(realpath "$ROOT"); target=$(realpath -m "$ROOT/$REL")
case "$target" in "$root"|"$root"/*) echo inside ;; *) echo "OUTSIDE: refuse" ;; esac
```

```powershell
# PowerShell (not tested by the author: verify once on your machine)
$root = (Resolve-Path $Root).Path
$t = [IO.Path]::GetFullPath((Join-Path $root $Rel))
$inside = ($t -eq $root) -or $t.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)
$link = (Get-Item -LiteralPath $t -ErrorAction SilentlyContinue).LinkType   # non-empty = symlink or junction: resolve it and re-check
```

Also check the exclude patterns against the relative path, and refuse matches.

## Is the file really on this computer?

Online-only placeholders look like normal files, but opening one forces a download. Check the attributes **without opening** the file.

```powershell
# Windows (not tested by the author: depends on how the Proton app implements placeholders)
$a = [int](Get-Item -LiteralPath $p).Attributes
$onlineOnly = ($a -band 0x400000) -or ($a -band 0x40000) -or ($a -band 0x1000)   # RecallOnDataAccess, RecallOnOpen, Offline
```

```bash
# macOS: a "dataless" flag means online-only
ls -lO "$p" | grep -q dataless && echo online-only
# Linux: no reliable signal; a size above zero with zero allocated blocks is only a hint
[ "$(stat -c %s "$p")" -gt 0 ] && [ "$(stat -c %b "$p")" -eq 0 ] && echo "maybe online-only"
```

Check the size too (`stat -c %s`, or `(Get-Item).Length`). If the file is online-only or larger than `large_file_mb`, tell the user the size and ask before reading it. If the checks say "local" for a file you know is online-only, tell the user: the detection depends on the app.

## Edit a file

```bash
WORK=~/.proton-drive-skill/work/$(date +%Y%m%d-%H%M%S); mkdir -p "$WORK"
cp -p "$ROOT/$REL" "$WORK/"           # PowerShell: Copy-Item
# ... edit the copy ...
```

After approval (rule 5), back up and write back once:

```bash
ID=$(date +%Y%m%d-%H%M%S); B=~/.proton-drive-skill/backups/$ID/$(dirname "$REL"); mkdir -p "$B"
cp -p "$ROOT/$REL" "$B/"                              # 1. back up what is there now
cp -p "$WORK/FILE" "$ROOT/$REL"                       # 2. single write
cmp "$WORK/FILE" "$ROOT/$REL" && echo verified        # 3. verify (PowerShell: Get-FileHash on both)
```

Creating a new file: check that it does not exist first (`[ -e "$ROOT/$REL" ]` / `Test-Path`), then copy.

## Move, delete, restore

- **Move or rename:** refuse if the destination exists unless the user approves replacing it (back the destination up first). `mv` / `Move-Item`.
- **Delete:** after approval, move the item into the backup folder instead of removing it: `mv "$ROOT/$REL" ~/.proton-drive-skill/backups/$ID/$REL` (create the parent folders first; on Windows use `Move-Item`). Never `rm`/`Remove-Item` inside the root. The Proton web trash is a second safety net.
- **Restore:** after approval, copy `backups/ID/REL` back to the root (back up the current version first under a new ID).
- **Prune:** only on request and after approval; delete backup folders older than the user's retention (default 30 days).

## Limits

You cannot tell whether the app has finished uploading; if the user needs the change online right away, suggest checking the app's sync indicator. Two devices editing one file can create conflict copies: report them, don't resolve them.
