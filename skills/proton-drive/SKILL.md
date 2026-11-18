---
name: proton-drive
description: Work on files in the user's personal Proton Drive, either through the folder the Proton Drive desktop app keeps synced on their computer (local backend) or directly in the Proton cloud through rclone (cloud backend, e.g. from the Claude app on a phone). Lists, searches, reads, edits, creates, moves and deletes files inside ONE configured root folder, with automatic backups, explicit confirmation for destructive actions, and protection against accidental large or online-only downloads. Use this skill whenever the user mentions Proton Drive, "my drive", "my synced folder" or "my Proton cloud", or wants to open, find, edit, organize, upload or clean up files that live in their Proton storage, even if they don't say "skill" or give a path.
compatibility: Python 3.9+. Local backend needs the Proton Drive desktop app signed in and syncing. Cloud backend needs rclone >= 1.66 (installer included), outbound access to Proton and a one-time login exported from the user's PC (see references/cloud-setup.md).
---

# Proton Drive

Proton Drive has no public API, so this skill reaches it in one of two unofficial-but-safe ways, chosen in the config (`backend`):

- **`local`**: works on the folder the official Proton Drive desktop app keeps synced on the user's PC. The app handles sync and encryption. Any change you make is uploaded by the app within seconds.
- **`rclone`**: talks to the Proton cloud directly through rclone's `protondrive` backend, for places with no synced folder (the Claude app on a phone, cloud sessions). The backend is community-built and marked beta by rclone, so expect occasional breakage after Proton changes its apps.

In both modes a mistake affects the real cloud copy, which is why the rules below are strict and **enforced by the helper script** rather than left to judgement.

All operations go through `scripts/pd.py` (standard-library Python, JSON output): `python scripts/pd.py <command>` (use `py -3` on Windows if `python` is missing). Never bypass it with raw `rm`, `del`, `mv`, `rclone` or shell redirection on the Drive: the script is what guarantees the sandbox, the backups and the size/placeholder checks.

## First use: find out where you are

Run `pd.py status`.

- **Config exists:** run `pd.py doctor` once per session; it checks rclone, login, network and the root folder, and says how to fix what fails. Do not proceed on failures.
- **No config, user is on their PC:** ask for the folder to work in (the root) and any folders to exclude, then `pd.py init --backend local --root "<path>" [--exclude "Private"]`.
- **No config, cloud/phone session:** the config normally arrives as env `PROTON_DRIVE_SKILL_CONFIG_JSON`; if it is missing, tell the user to follow `references/cloud-setup.md` (one-time setup on their PC, then store two variables in their cloud environment). Do not try to log in to Proton yourself and never ask the user to paste a password, token or rclone config into the chat.

If `doctor` shows rclone missing, run `python scripts/install_rclone.py`. If it reports a blocked host ("no rule allows host" or DNS failure), tell the user which host to allow in the environment's network settings; do not look for a way around the proxy.

Backups live outside the root on purpose: on `local` in `~/.proton-drive-skill/backups` (anything inside the synced folder would be uploaded); on `rclone` in `backup_path` inside the same Proton account, because the container is ephemeral. The script refuses configs that break this.

## Working rules

1. **Stay in the root.** Use paths relative to the root. The script rejects `..`, absolute paths elsewhere, symlinks leading out and excluded folders. If the user asks for something outside, say it is out of scope and that the root can be changed in the config.
2. **Check before reading.** Use `pd.py state <paths>` first (it never downloads). On `local`, a file can be `online-only`; opening it forces a download. On both backends large files (default over 100 MB) are gated. When the script says a file is online-only or large, tell the user the size and ask before retrying with `--allow-download`. Don't read, hash or grep files with other tools until you know they are local and reasonably small.
3. **Edit via a work copy.** `pd.py checkout <path>` copies the file out of the Drive, edit that copy (for Office/PDF files use the matching docx/xlsx/pptx/pdf skills), then `pd.py put <work_copy> <path> --confirmed`. A single write means one clean version is synced instead of every intermediate save, and `put` verifies the result.
4. **Confirm before anything destructive or overwriting.** Overwrite (`put` onto an existing file), `mv`, `rm`, `restore` and `prune` need `--confirmed`. Pass it only after the user has seen exactly what will change and said yes. Approval for one action does not cover the next.
5. **Bulk operations need a preview.** For more than a couple of files (cleanup, renaming, reorganizing), list every affected path with `ls`/`find`, show the plan, get approval, then execute. Report failures instead of retrying silently.
6. **Backups are automatic; say so.** Overwrite, delete and move-over-existing create a backup first and return a `backup_id`. Tell the user the id and the undo command (the output includes it, usually `pd.py restore <id> --confirmed`). Use `--no-backup` only if the user explicitly asks.
7. **Protect secrets.** Never print, log, commit or summarize the contents of `rclone.conf`, `PROTON_RCLONE_CONF_B64` or any token. They give full access to the Proton account.
8. **Leave app internals alone.** Skip sync metadata, `desktop.ini`, `.protondrive` and conflict copies; report conflict copies rather than resolving them.
9. **Be honest about limits.** You cannot see sharing links, permissions or cloud-side version history. On `local` you cannot tell whether the app has finished uploading. On `rclone` the backend is beta: if a command fails oddly, run `doctor` and report the error text instead of guessing.

## Commands

| Goal | Command |
|---|---|
| Show config / health check | `pd.py status` / `pd.py doctor` |
| List a folder | `pd.py ls [path] [-r] [--max N]` |
| Find by name or glob | `pd.py find <pattern> [--under path]` |
| Availability, size, large flag | `pd.py state <path>...` |
| Copy a file out to edit | `pd.py checkout <path> [--allow-download]` |
| Write/overwrite a file | `pd.py put <local_file> <dest> [--confirmed]` |
| Make a folder | `pd.py mkdir <path>` |
| Move/rename | `pd.py mv <src> <dst> --confirmed [--overwrite]` |
| Delete (backup kept) | `pd.py rm <path> --confirmed` |
| Manual backup | `pd.py backup <path>` |
| List/restore backups | `pd.py backups` / `pd.py restore <id> --confirmed` |
| Clean old backups | `pd.py prune --confirmed` |
| Install rclone | `python scripts/install_rclone.py` |

Every command returns JSON with `ok`; on refusal `error` says what to do next. Read it and follow it (usually: ask the user) rather than looking for a way around.

## How to report

Keep answers short: what you did, the path(s) touched, the backup id if any, and how to undo. For listings, summarize and mention large or online-only files because they affect next steps. Phones show little text, so lead with the result.

Read `references/cloud-setup.md` for the cloud/phone setup and its security trade-offs, and `references/setup.md` for the synced-folder setup and how placeholders are detected.
