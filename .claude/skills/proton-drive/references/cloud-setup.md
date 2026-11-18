# Cloud setup (rclone backend, e.g. from the Claude app on a phone)

## What you are agreeing to
Proton encrypts files end-to-end. For a cloud session to work on them, the session's container must hold your Proton login material (rclone's config with session tokens) and will see the files **decrypted**. This is a deliberate trade-off against Proton's zero-knowledge model. To keep the blast radius small:

1. **Use a dedicated secondary Proton account** and put there only the files you want to work on from the phone. Never use the account that holds everything.
2. Store the login in a **personal** (not organization-shared) cloud environment: environment variables are stored in plain text and visible to anyone who can edit that environment.
3. Enable 2FA on that account (rclone supports it) and use a long unique password.
4. The skill's `root` limits what Claude does, not what the credentials can reach. Treat the credentials as full access to that account.

The rclone `protondrive` backend is unofficial and marked beta (it relies on reverse-engineered API behaviour). Proton's own SDK is still a preview not meant for third-party use. Expect that updates on Proton's side may break it.

## One-time setup (on your PC)
1. Install rclone >= 1.66 (https://rclone.org/install/).
2. `rclone config` → `n` (new remote) → name: `proton` → storage: `protondrive` → enter the secondary account's username and password (and mailbox password if the account uses Proton's two-password mode) → enter the current 2FA code quickly, it expires in seconds.
3. Check it works: `rclone lsd proton:`
4. Create in that account the folder to work in (e.g. `Work`) and a sibling folder for backups (e.g. `_backups`). They must not contain one another.
5. Export the remote as one base64 string:
   - macOS/Linux: `rclone config show proton | base64 -w0` (on macOS: `| base64`)
   - Windows PowerShell: `[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes((rclone config show proton | Out-String)))`
   Treat this string like a password. Do not paste it in a chat, a repo or an issue.

## Cloud environment (claude.ai/code → environment settings)
- **Environment variables** (personal environment):
  - `PROTON_RCLONE_CONF_B64` = the string from step 5
  - `PROTON_DRIVE_SKILL_CONFIG_JSON` = `{"backend":"rclone","remote":"proton","root":"Work","backup_path":"_backups","exclude":[]}`
- **Network access:** allow `downloads.rclone.org` (to install rclone) and the Proton API hosts. The exact hosts are not documented by Proton for this use; start a session, run `pd.py doctor`, and add each host that the proxy reports as blocked (typically names under `proton.me`).
- **Setup script (optional, faster sessions):** installs rclone once per fresh container, for example
  `curl -fsSL https://downloads.rclone.org/v1.69.3/rclone-v1.69.3-linux-amd64.zip -o /tmp/r.zip && unzip -j -o /tmp/r.zip '*/rclone' -d /usr/local/bin && chmod +x /usr/local/bin/rclone`
  Without it, the skill runs `scripts/install_rclone.py` on first use (verifies the SHA256 of the download, falls back to `go install`).

## Getting the skill into cloud sessions
Either commit the folder to a repository you attach to the session, as `.claude/skills/proton-drive/`, or install the `.skill` file from your account settings (Capabilities → Skills) so that it syncs to your sessions. If it does not show up in a new session, use the repository route.

## Using it from the phone
Open the Code tab in the Claude app, start a session in the environment above, and ask in plain language ("list the files in Work", "rename the invoices from March"). The skill runs `doctor` first.

## Known issues and what to try
- **Login fails after a while:** session tokens expire or rotate, and a container cannot persist refreshed tokens between sessions. Re-run steps 2, 3 and 5 on your PC and update `PROTON_RCLONE_CONF_B64`. If this happens often, the cloud mode is not reliable enough for you.
- **"already exists" / draft errors on upload** after an interrupted transfer: retry once; if it persists, remove the stale draft in the Proton web app. (rclone offers `--protondrive-replace-existing-draft` for this, but the skill does not pass it automatically.)
- **Stale listings:** rclone caches metadata; retry after a minute or list the parent folder again.
- **Slow or timed-out large transfers:** raise `rclone_timeout` in the config JSON (seconds), and keep large files out of the working folder.
