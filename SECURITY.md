# Security notes

This skill can read, change and delete files in a Proton Drive, and in cloud mode it needs Proton login material. Please read this before using or reporting issues.

## Threat model in short
- **Cloud mode stores Proton session tokens** (inside an rclone config) in the environment that runs Claude. Anyone who can read that environment, or any process in the session, can use them. Use a dedicated secondary Proton account holding only the files you want to work on, in a personal environment. See `skills/proton-drive/references/cloud-setup.md`.
- **The root folder limits what the skill does, not what the credentials can reach.**
- Safety rules (sandbox, confirmation flags, backups) are enforced by `scripts/pd.py`, but a model can still call a command with `--confirmed`. The skill instructs it to do so only after your explicit approval; for stronger guarantees set `"read_only": true`, and review actions in your client's permission prompts.
- The rclone `protondrive` backend is unofficial and beta. Proton may change its behaviour at any time.

## Never share
`rclone.conf`, the `PROTON_RCLONE_CONF_B64` value, or the output of `rclone config show` for a Proton remote. Treat them like a password and rotate the Proton password if they leak.

## Reporting a vulnerability
Please open a private security advisory on the repository (or contact the maintainer privately) instead of a public issue, especially for anything involving path escapes, credential exposure or bypassing confirmation.
