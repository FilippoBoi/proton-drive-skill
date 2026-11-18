# Changelog

## 0.1.0
- Local backend: folder synced by the Proton Drive desktop app (online-only placeholder detection on Windows and macOS, heuristic on Linux).
- Cloud backend: rclone `protondrive` (beta, unofficial) for phones and cloud sessions.
- Sandboxed root, excluded paths, confirmation for destructive actions, automatic backups outside the root, large-file gate, checkout/put workflow with verification.
- `doctor`, `install_rclone.py`, end-to-end tests, CI on Linux, macOS and Windows.

## Unreleased
- Skill moved from `.claude/skills/` to `skills/` (plugin layout); shebangs removed from scripts.
