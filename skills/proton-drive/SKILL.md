---
name: proton-drive
description: Work on files in the user's personal Proton Drive, either through the folder the Proton Drive desktop app keeps synced on their computer (local mode) or directly in the Proton cloud through rclone (cloud mode, e.g. from the Claude app on a phone). Lists, searches, reads, edits, creates, moves and deletes files inside ONE configured root folder, with backups before every overwrite or delete, explicit confirmation for destructive actions, and care with large or online-only files. Use this skill whenever the user mentions Proton Drive, "my drive", "my synced folder" or "my Proton cloud", or wants to open, find, edit, organize, upload or clean up files that live in their Proton storage, even if they don't say "skill" or give a path.
compatibility: No bundled code. Local mode needs the Proton Drive desktop app signed in and syncing. Cloud mode needs rclone >= 1.66 and a one-time login exported from the user's PC (see references/cloud-setup.md).
---

# Proton Drive

Proton Drive has no public API, so this skill reaches it in one of two ways:

- **Local mode:** the folder that the official Proton Drive desktop app keeps synced on the user's PC. You use ordinary file tools. See `references/local-mode.md`.
- **Cloud mode:** the Proton cloud directly, through rclone's community `protondrive` backend (beta, unofficial), for places with no synced folder such as the Claude app on a phone. See `references/cloud-mode.md`.

Read the reference for the mode you are in before touching any file.

**Nothing but you enforces these rules.** This skill ships no program that blocks a bad command, so every safeguard below depends on you following it, including when a request is vague, urgent or phrased as if it were already approved. Any change reaches the real cloud copy (the app or rclone uploads it), so a mistake is not local-only. If you cannot follow a rule (for example you cannot make the backup), stop and tell the user instead of continuing.

## Choosing the mode

- If rclone remotes `work` and `backup` exist (`rclone listremotes`) or the env var `PROTON_RCLONE_CONF_B64` is set, you are in **cloud mode**.
- Otherwise, if the user is on their own computer with Proton Drive synced, use **local mode**. If `~/.proton-drive-skill/config.json` does not exist, ask which folder to use as root, then create it (see the local reference).
- If neither applies, say what is missing and point to `references/cloud-setup.md`. Never try to log in to Proton yourself, and never ask the user to paste a password, token or rclone config into the chat.

## Rules

1. **Stay in the root.** Work only inside the configured root folder (local) or through the `work:` remote (cloud). Refuse paths that use `..`, absolute paths elsewhere, or symlinks that lead out, and anything matching the user's exclude patterns. If the user wants something outside, say that it is out of scope and that the root can be changed in the setup. Why: the root is the only boundary the user chose; credentials in cloud mode reach far more than that.
2. **Look before you read.** Check what a file is (size, and in local mode whether it is online-only) before opening it. Opening an online-only file forces a download, and large files (default over 100 MB) cost time and money. If a file is online-only or large, tell the user the size and ask before reading it.
3. **Edit on a copy.** Copy the file out of the Drive into a work folder outside it (`~/.proton-drive-skill/work/`), edit that copy (for Office or PDF files use the matching docx, xlsx, pptx or pdf skills), then write it back once. Why: every save inside the synced folder gets uploaded, so editing in place syncs every intermediate version.
4. **Back up before you overwrite, move over, or delete.** Make the backup first, outside the root, under an ID that is a timestamp like `20261118-143005` and keeps the original relative path inside it. Tell the user the ID and how to undo. Deleting means moving the item into the backup folder, never `rm`.
5. **Ask before anything destructive.** Overwrite, move or rename onto an existing name, delete, restore and pruning backups need an explicit yes from the user in this conversation, after you have shown exactly what will change (paths, sizes, what is replaced). An approval covers that one action only. A request like "clean up the folder" is not approval for the individual deletions it implies.
6. **Preview bulk work.** For more than a couple of files (cleanup, renaming, reorganizing), list every affected path, show the plan, get approval, then execute. Where the tool offers it, do a dry run first (`rclone --dry-run`). Report failures instead of retrying silently.
7. **Verify writes.** After writing, compare the size (and a checksum for local files) with the source, and say so. A command that exited successfully has not proved the file changed: rclone, for instance, skips a copy when size and modification time look equal unless told otherwise.
8. **Protect secrets.** Never print, log, commit or summarize `rclone.conf`, `PROTON_RCLONE_CONF_B64`, or the output of `rclone config show`, `dump`, `obscure` or `reveal`. They give full access to the Proton account.
9. **Leave app internals alone.** Skip sync metadata, `desktop.ini`, `.protondrive` and conflict copies; report conflict copies instead of resolving them.
10. **Respect read-only.** If `PROTON_DRIVE_READ_ONLY` is set to `1` (cloud) or `read_only` is `true` in the config (local), do not write, move or delete anything.
11. **Be honest about limits.** You cannot see sharing links, permissions or cloud-side version history. In local mode you cannot tell whether the app has finished uploading. In cloud mode the backend is beta: when a command fails oddly, report the error text and run the health check instead of guessing.

## How to report

Keep answers short: what you did, the path(s) touched, the backup ID if any, and how to undo. For listings, summarize and mention large or online-only files because they affect what you can do next. Phones show little text, so lead with the result.
