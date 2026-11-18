# Security notes

This skill can read, change and delete files in a Proton Drive, and in cloud mode it needs Proton login material. Please read this before using or reporting issues.

## Threat model in short
- **Cloud mode stores Proton session tokens** (inside an rclone config) in the environment that runs Claude. Anyone who can read that environment, or any process in the session, can use them. Use a dedicated secondary Proton account holding only the files you want to work on, in a personal environment. See `skills/proton-drive/references/cloud-setup.md`.
- **The root folder limits what the skill does, not what the credentials can reach.**
- **This version has no code that enforces the rules.** Boundaries, backups and confirmations are instructions that the model follows; a model can make mistakes or be steered by file contents. Mitigations: use a dedicated Proton account, keep your client's permission prompts on for shell commands and read them before approving, use `PROTON_DRIVE_READ_ONLY=1` when you only need to read, and use the `scripted` branch if you want the rules enforced by a program.
- The rclone `protondrive` backend is unofficial and beta. Proton may change its behaviour at any time.

## Never share
`rclone.conf`, the `PROTON_RCLONE_CONF_B64` value, or the output of `rclone config show` for a Proton remote. Treat them like a password and rotate the Proton password if they leak.

## Reporting a vulnerability
Please open a private security advisory on the repository (or contact the maintainer privately) instead of a public issue, especially for anything involving path escapes, credential exposure or bypassing confirmation.
