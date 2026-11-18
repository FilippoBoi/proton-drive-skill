# Local backend: setup and platform notes (synced folder on your PC)

## Requirements
- Proton Drive desktop app, signed in, with the folder you want to work on synced locally.
- Python 3.8+ on PATH (`python --version`; on Windows also `py -3 --version`).
- Install this skill as a folder named `proton-drive` in `~/.claude/skills/` (Claude Code), or install the packaged `.skill` file.

## Choosing the root
Pick the narrowest folder that covers the work (e.g. `.../Proton Drive/Work`), not the whole drive. Everything outside is invisible to the skill. Use `exclude` for sensitive subfolders inside it. Patterns are relative to the root and use `/`; a pattern matches a folder or file name anywhere (`*.kdbx`) or a path (`Clients/Private`).

## Online-only detection (stat only, never opens the file)
| Platform | Signal | Confidence |
|---|---|---|
| Windows | `FILE_ATTRIBUTE_RECALL_ON_DATA_ACCESS` / `RECALL_ON_OPEN` / `OFFLINE` (Cloud Files placeholders) | High if the app uses the Windows Cloud Files API like OneDrive; verify once with a file you know is online-only |
| macOS | `SF_DATALESS` flag (File Provider) | High |
| Linux | size > 0 but zero allocated blocks | Heuristic only |

If an online-only file is reported as `local` (or vice versa) on your setup, `pd.py state` output includes `detected_by`; open an issue with that value so the heuristic can be refined. If the app syncs everything fully offline, detection is simply never triggered.

## Where things are stored
- Config: `~/.proton-drive-skill/config.json` (or env `PROTON_DRIVE_SKILL_CONFIG_JSON`)
- Backups: `~/.proton-drive-skill/backups/<backup_id>/<relative path>` plus `index.jsonl` (an audit log of put/mv/rm actions)
- Work copies: `~/.proton-drive-skill/work/`
Both backup and work dirs must be outside the root; the script enforces it.

## Limits
- Sees only the synced folder. No sharing links, no cloud-side version history, no files that are not synced.
- Cannot tell whether the app has finished uploading.
- Two devices editing the same file can produce conflict copies; the skill reports them but does not resolve them.
- Backups of large files cost local disk space; `large_file_mb` makes the skill ask before copying or downloading big files.
