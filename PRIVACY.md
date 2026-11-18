# Privacy

This skill is a set of instructions and a local Python script. **It has no server and sends no data to its authors**: no telemetry, no analytics, no accounts.

What happens to your data depends on the mode:

- **`local` mode:** the script reads and writes files in the folder you configured, and keeps backups and a small log under `~/.proton-drive-skill/` on your own computer. Syncing to Proton is done by the official Proton Drive app, under Proton's own privacy policy.
- **`cloud` (rclone) mode:** the script runs `rclone`, which connects from the environment where Claude runs (for example a cloud session) to Proton's servers with the login material you provide, and reads or writes files in the configured folder. Files you ask Claude to work on are decrypted in that environment and become part of the conversation with Claude, under Anthropic's privacy terms. Backups are stored in your own Proton account.
- In both modes, content of files you ask Claude to read becomes part of your conversation with Claude.

You are responsible for the credentials you store in a cloud environment; see [SECURITY.md](SECURITY.md). This project is not affiliated with Proton AG or Anthropic.
