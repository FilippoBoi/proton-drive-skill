# proton-drive: a Claude skill for your Proton Drive

Lets Claude list, search, read, edit, create, move and delete files in your personal Proton Drive, following safety rules: one root folder, a backup before every overwrite or delete, your explicit yes before anything destructive, care with large or online-only files.

> **Unofficial.** Not affiliated with or endorsed by Proton AG. Proton Drive has no public API for this; see "How it works".

> **Instructions only.** This version contains no code, only Markdown. Plugin directories restrict code from unverified publishers, which this version avoids; the trade-off is that **the safety rules are followed by Claude, not enforced by a program**. A version with a script that enforces them in code (sandboxed paths, mandatory confirmation flags, automatic backups, tests) lives on the [`scripted`](https://github.com/FilippoBoi/proton-drive-skill/tree/scripted) branch; the official directory does not accept scripts from unverified organizations.

## Two modes

| | local | cloud (rclone) |
|---|---|---|
| Where | your PC, with the Proton Drive desktop app signed in | anywhere: Claude app on a phone, cloud sessions |
| How | the folder the app keeps synced | rclone's community `protondrive` backend (beta) |
| Credentials | none, the app is already signed in | Proton session tokens in the environment: **use a dedicated secondary account** |
| Boundary | the root folder you configure | the `work:` rclone alias you configure |

## Install

As a Claude Code plugin, from this repository's own marketplace:
```bash
claude plugin marketplace add FilippoBoi/proton-drive-skill
claude plugin install proton-drive@proton-drive-marketplace
```
or copy `skills/proton-drive` to `~/.claude/skills/` (Windows: `%USERPROFILE%\.claude\skills\`). On first use Claude asks which folder to use as root.

Phone and cloud sessions need a one-time setup on your PC and an environment with your login: read [cloud-setup.md](skills/proton-drive/references/cloud-setup.md) first.

## How it works
Proton publishes no stable public API; its Drive SDK is still a preview not meant for third parties. So the skill uses the desktop app's synced folder (local) or rclone's `protondrive` backend (cloud), which is built from reverse-engineered behaviour and may break when Proton updates its apps. The skill is a set of instructions and verified command recipes in [`skills/proton-drive`](skills/proton-drive). The recipes are tested in CI against an rclone alias remote (not against Proton itself).

## Known limits
- Rules are followed, not enforced: review what Claude proposes before approving destructive actions, and keep your client's permission prompts on for shell commands.
- Sees only the synced folder (local) or the configured alias (cloud); no sharing links, permissions or cloud-side version history.
- Cloud mode: tokens can expire and an ephemeral container cannot keep refreshed ones, so you may need to re-export your login now and then.
- Never tested against a live Proton account by the author; the Windows commands in `local-mode.md` are untested. Please report what you see.

## Security and privacy
See [SECURITY.md](SECURITY.md) and [PRIVACY.md](PRIVACY.md). License: [MIT](LICENSE).
