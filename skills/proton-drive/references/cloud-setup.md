# Cloud setup (rclone, e.g. from the Claude app on a phone)

## What you are agreeing to
Proton encrypts files end-to-end. For a cloud session to work on them, the session's container must hold your Proton login material (an rclone config with session tokens) and will see the files **decrypted**. This is a deliberate trade-off against Proton's zero-knowledge model. To keep the damage small:

1. **Use a dedicated secondary Proton account** and keep there only the files you want to work on from the phone. Never use the account that holds everything.
2. Store the login in a **personal** (not organization-shared) cloud environment: environment variables are stored in plain text and visible to anyone who can edit that environment.
3. Enable 2FA on that account (rclone supports it) and use a long unique password.
4. This skill contains no program that enforces limits: the safety rules are instructions that Claude follows. The `work:` alias limits which folder Claude uses, but the credentials reach the whole account. Treat them as full access to it.

The rclone `protondrive` backend is unofficial and marked beta, since it relies on reverse-engineered behaviour. Proton's own SDK is still a preview not meant for third-party use. Updates on Proton's side may break it.

## One-time setup on your PC
1. Install rclone 1.66 or newer by following [rclone's install instructions](https://rclone.org/install/).
2. Run `rclone config`, choose `n` (new remote), name it `proton`, storage type `protondrive`, then enter the secondary account's username and password (and the mailbox password if the account uses Proton's two-password mode) and the current 2FA code (it expires in seconds).
3. Check it: `rclone lsd proton:`
4. In that account create the folder to work in (for example `Work`) and a sibling folder for backups (for example `_backups`). They must not contain one another.
5. Save the remote to a file and add two alias remotes that point at those folders (change the folder names to yours):

   ```ini
   [work]
   type = alias
   remote = proton:Work

   [backup]
   type = alias
   remote = proton:_backups
   ```

   macOS/Linux: `rclone config show proton > proton.conf`, then append the block above to `proton.conf`.
   Windows PowerShell: `rclone config show proton | Out-File proton.conf -Encoding ascii`, then add the block with a text editor.
6. Turn the whole file into one base64 string:
   - macOS/Linux: `base64 -w0 proton.conf` (on macOS: `base64 -i proton.conf`)
   - Windows PowerShell: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("proton.conf"))`

   Treat the string like a password: do not paste it in a chat, a repository or an issue. Delete `proton.conf` afterwards.

## Cloud environment (claude.ai/code → environment settings)
- **Environment variables** (personal environment):
  - `PROTON_RCLONE_CONF_B64`: the string from step 6.
  - Optional: `PROTON_DRIVE_EXCLUDE` (for example `Private/**,*.kdbx`), `PROTON_DRIVE_READ_ONLY=1` to forbid writes, `PROTON_DRIVE_LARGE_MB`.
- **Network access:** allow the Proton API hosts. Proton does not document exact hosts for this use: start a session, run the health check in `cloud-mode.md`, and add each host that the proxy reports as blocked (typically names under `proton.me`). rclone's own host is needed only if you install it from inside the session.
- **rclone in the container:** install it with the environment's setup script, following the install instructions linked above, so that `rclone version` works in a new session.

## Getting the skill into cloud sessions
Install it as a plugin (see the README) in the environment if your setup allows it, or copy this folder into `.claude/skills/proton-drive/` of a repository that you attach to the session (a private repository of your own is fine), or install the packaged skill from your account settings (Capabilities → Skills). If it does not show up in a new session, use the repository route.

## Using it from the phone
Open the Code tab in the Claude app, start a session in the environment above, and ask in plain language ("list the files in Work", "rename the invoices from March"). The skill starts with a health check.

## Known issues and what to try
- **Login fails after a while:** session tokens expire or rotate, and a container cannot keep refreshed tokens between sessions. Repeat steps 2, 3, 5 and 6 on your PC and update `PROTON_RCLONE_CONF_B64`. If this happens often, the cloud mode is not reliable enough for you.
- **Upload says "already exists" after an interrupted transfer:** retry once; if it persists, remove the stale draft in the Proton web app.
- **Stale listings:** rclone caches metadata; list the parent folder again after a minute.
- **Slow or timed-out large transfers:** keep large files out of the working folder.
